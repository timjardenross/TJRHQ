"""Cross-sector / systemic provider-involvement view (OFFLINE, default OFF, not wired).

Uses the PR #706 taxonomy (`provider_involvement.InvolvementTagger`, text only, own-feed tagging excluded) to find
EVIDENCED links where the same provider is DIRECTLY_INVOLVED in reports spanning 2+ sectors or 3+ named
organisations inside a rolling window. Only links with item-level evidence (event id, sector label, evidence span
and the window span) are printed. Nothing here is a dependency finding: a report that names a provider is not
evidence that any organisation or sector depends on it.

Shared-provider CONCENTRATION is a separate, stricter claim (from #706): at least 3 distinct organisations each with
item-level AFFECTED or SUPPLYING evidence naming the same provider, across at least 2 independent events, plus a
public source for any organisation-specific link. When that evidence does not exist the report says so and prints
no concentration score. This tool never prints a numeric concentration score.

Usage:
    python systemic_risk_view.py --enable --input context.jsonl[.gz] --as-of 2026-11-24 --out view.md
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analytics_common import HYPOTHESIS, LABEL_LEGEND, OBSERVED, PLAUSIBLE, parse_ts
from product_common import clean_text, load_rows, md_cell, require_enabled, short
from provider_involvement import (
    AFFECTED,
    DIRECTLY_INVOLVED,
    SUPPLYING,
    InvolvementTagger,
)

NON_SECTORS = {"", "cross_sector", "general", None}
NON_INCIDENT_TYPES = {
    "",
    "other",
    None,
}  # classifier gave no incident-type label: not eligible for a link
CRITICAL_SECTORS = {"energy", "transport", "financial_services", "technology"}
CRITICAL_EVENT_TYPES = {
    "technology_outage",
    "third_party_disruption",
    "energy_disruption",
    "transport_disruption",
    "cyber",
}
WINDOW_DAYS = 14
MIN_SECTORS = 2
MIN_ORGS = 3
CONC_MIN_ORGS = 3
CONC_MIN_EVENTS = 2


def _norm_title(title):
    t = clean_text(title).lower()
    t = re.sub(r"\s+[-|]\s+[^-|]{3,60}$", "", t)  # trailing ' - Publisher'
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def tag_rows(rows, tagger=None):
    """Return [{row, tags}] with text-only tags (no own-feed tagging)."""
    tagger = tagger or InvolvementTagger()
    out = []
    for r in rows:
        tags = tagger.tag(
            clean_text(r.get("raw_title")), clean_text(r.get("raw_summary")), None
        )
        out.append({"row": r, "pub": parse_ts(r.get("published_at")), "tags": tags})
    return out


def _distinct_reports(items):
    """Collapse items with the same normalised headline (one report per headline)."""
    seen = {}
    for it in sorted(items, key=lambda i: i["pub"]):
        seen.setdefault(_norm_title(it["row"].get("raw_title")), it)
    return list(seen.values())


def find_links(tagged, as_of, window_days=WINDOW_DAYS, lookback_days=90):
    start = as_of - timedelta(days=lookback_days)
    per_provider = defaultdict(list)
    for it in tagged:
        if not it["pub"] or not (start <= it["pub"] < as_of):
            continue
        for t in it["tags"]:
            if (
                t.cls == DIRECTLY_INVOLVED
                and it["row"].get("event_type") not in NON_INCIDENT_TYPES
            ):
                per_provider[t.provider].append({**it, "tag": t})
    links = []
    for prov, items in sorted(per_provider.items()):
        items = _distinct_reports(items)
        items.sort(key=lambda i: i["pub"])
        qualifying = []
        for a in items:
            win = [
                b
                for b in items
                if a["pub"] <= b["pub"] < a["pub"] + timedelta(days=window_days)
            ]
            sectors = {b["row"].get("sector") for b in win} - NON_SECTORS
            orgs = {b["row"].get("organisation") for b in win} - {None, ""}
            if len(sectors) >= MIN_SECTORS or len(orgs) >= MIN_ORGS:
                qualifying.append(
                    (
                        a["pub"],
                        a["pub"] + timedelta(days=window_days),
                        win,
                        sectors,
                        orgs,
                    )
                )
        # merge overlapping qualifying windows
        merged = []
        for s, e, win, sectors, orgs in qualifying:
            if merged and s < merged[-1]["end"]:
                m = merged[-1]
                m["end"] = max(m["end"], e)
                for b in win:
                    m["items"][b["row"]["event_id"]] = b
            else:
                merged.append(
                    {
                        "start": s,
                        "end": e,
                        "items": {b["row"]["event_id"]: b for b in win},
                    }
                )
        for m in merged:
            its = sorted(m["items"].values(), key=lambda i: i["pub"])
            sectors = {i["row"].get("sector") for i in its} - NON_SECTORS
            orgs = {i["row"].get("organisation") for i in its} - {None, ""}
            links.append(
                {
                    "provider": prov,
                    "items": its,
                    "sectors": sorted(sectors),
                    "orgs": sorted(orgs),
                    "span": (its[0]["pub"], its[-1]["pub"]),
                    "sector_rule": len(sectors) >= MIN_SECTORS,
                    "org_rule": len(orgs) >= MIN_ORGS,
                }
            )
    return links


def concentration_evidence(tagged, as_of, lookback_days=90):
    """Item-level AFFECTED/SUPPLYING evidence and whether the #706 concentration threshold is met."""
    start = as_of - timedelta(days=lookback_days)
    by_provider = defaultdict(list)
    counts = Counter()
    for it in tagged:
        if not it["pub"] or not (start <= it["pub"] < as_of):
            continue
        for t in it["tags"]:
            if t.cls in (AFFECTED, SUPPLYING):
                counts[t.cls] += 1
                by_provider[t.provider].append((it, t))
    eligible = {}
    for prov, pairs in by_provider.items():
        orgs = {p[0]["row"].get("organisation") for p in pairs} - {None, ""}
        events = {_norm_title(p[0]["row"].get("raw_title")) for p in pairs}
        if len(orgs) >= CONC_MIN_ORGS and len(events) >= CONC_MIN_EVENTS:
            eligible[prov] = pairs
    return counts, by_provider, eligible


def critical_infra_cut(tagged, as_of, lookback_days=90):
    start = as_of - timedelta(days=lookback_days)
    sel = [
        it
        for it in tagged
        if it["pub"]
        and start <= it["pub"] < as_of
        and it["row"].get("geography") == "AU"
        and it["row"].get("sector") in CRITICAL_SECTORS
        and it["row"].get("event_type") in CRITICAL_EVENT_TYPES
    ]
    cls = Counter(t.cls for it in sel for t in it["tags"])
    return sel, cls


def render(tagged, as_of, source_note, window_days=WINDOW_DAYS):
    start = as_of - timedelta(days=90)
    in_win = [it for it in tagged if it["pub"] and start <= it["pub"] < as_of]
    links = find_links(tagged, as_of, window_days)
    counts, _by_provider, eligible = concentration_evidence(tagged, as_of)
    crit, crit_cls = critical_infra_cut(tagged, as_of)
    orgs_populated = sum(1 for it in in_win if it["row"].get("organisation"))
    dist = Counter(t.cls for it in in_win for t in it["tags"])
    out = [
        f"# Cross-sector and systemic provider view, generated {as_of.date().isoformat()}",
        "",
        (
            f"Source: {source_note}. Window: {start.date()} to {as_of.date()}. Offline, read-only, default OFF, not wired "
            "into any service. Taxonomy and tagger: PR #706 (`provider_involvement`), text only, own-feed tagging off."
        ),
        "",
        LABEL_LEGEND,
        "",
        "## Evidence base",
        "",
        f"- [{OBSERVED}] {len(in_win)} items in window; tags: "
        + ", ".join(f"{k} {v}" for k, v in sorted(dist.items()))
        + ".",
        f"- [{OBSERVED}] Items with a populated `organisation` field: {orgs_populated} of {len(in_win)}.",
        f"- [{OBSERVED}] AFFECTED tags: {counts.get(AFFECTED, 0)}; SUPPLYING tags: {counts.get(SUPPLYING, 0)}.",
        f"- [{OBSERVED}] AU critical-infrastructure cut (geography AU, sector in energy/transport/financial_services/"
        f"technology, event type in technology_outage/third_party_disruption/energy_disruption/transport_disruption/cyber): "
        f"{len(crit)} items; tags "
        + (
            ", ".join(f"{k} {v}" for k, v in sorted(crit_cls.items()))
            if crit_cls
            else "none"
        )
        + f"; AFFECTED {crit_cls.get(AFFECTED, 0)}, SUPPLYING {crit_cls.get(SUPPLYING, 0)}.",
        "",
        "## Shared-provider concentration",
        "",
    ]
    if eligible:
        out.append(
            "The #706 threshold (>= 3 organisations with item-level AFFECTED/SUPPLYING evidence naming the same "
            "provider across >= 2 independent events) is met for the providers below. These are CANDIDATES that still "
            "need a public primary source for each organisation-specific link. No numeric concentration score is produced."
        )
        out.append("")
        for prov, pairs in sorted(eligible.items()):
            out.append(
                f"- {prov}: "
                + "; ".join(
                    f"`{p[0]['row']['event_id']}` ({p[1].cls})" for p in pairs[:8]
                )
            )
    else:
        out += [
            (
                f"**INSUFFICIENT EVIDENCE. No concentration score is produced.** Required: at least {CONC_MIN_ORGS} distinct "
                f"organisations, each with item-level AFFECTED or SUPPLYING evidence naming the same provider, across at least "
                f"{CONC_MIN_EVENTS} independent events, plus a public source for each organisation-specific link. "
                f"Found: {counts.get(AFFECTED, 0)} AFFECTED and {counts.get(SUPPLYING, 0)} SUPPLYING tags in the window, "
                f"{orgs_populated} items with an organisation value, and "
                f"{crit_cls.get(AFFECTED, 0) + crit_cls.get(SUPPLYING, 0)} AFFECTED/SUPPLYING tags among the {len(crit)} AU "
                "critical-infrastructure items."
            ),
            "",
            (
                "Telstra and Optus recurrence in this corpus is repeated news about single-provider outages. It is not "
                "shared-provider concentration."
            ),
        ]
    out += [
        "",
        f"## Provider-involvement links across 2+ sectors or 3+ organisations (window {window_days} days)",
        "",
        (
            f"Rule: the same provider is DIRECTLY_INVOLVED in distinct reports (collapsed by headline, event type not 'other') whose sector labels "
            f"include at least {MIN_SECTORS} different sectors (cross_sector/general are not sectors), or that name at least "
            f"{MIN_ORGS} different organisations, all within {window_days} days. [{PLAUSIBLE}] Sector labels are assigned by "
            "the platform classifier to each report. A span across sector labels shows where the provider is being reported, "
            "not that those sectors depend on it, and several reports can describe one event."
        ),
        "",
    ]
    org_rule_hits = sum(1 for link in links if link["org_rule"])
    out.append(
        f"Organisation rule (3+ named organisations): {org_rule_hits} links, because `organisation` is populated on "
        f"{orgs_populated} items. Insufficient evidence for any organisation-based link."
    )
    out.append("")
    if not links:
        out += ["No sector-spanning links found.", ""]
    for n, link in enumerate(
        sorted(links, key=lambda x: x["span"][0], reverse=True), 1
    ):
        a, b = link["span"]
        out += [
            f"### Link {n}: {link['provider']}, {a.date()} to {b.date()}",
            "",
            f"- [{OBSERVED}] Evidence span: {a.isoformat()} to {b.isoformat()} ({len(link['items'])} distinct reports).",
            (
                f"- [{OBSERVED}] Sector labels: {', '.join(link['sectors']) or 'none'}; organisations named: "
                f"{', '.join(link['orgs']) or 'none'}."
            ),
            f"- [{PLAUSIBLE}] Reported involvement in more than one sector label within the window; not a dependency claim.",
            "",
            "| Event id | Published | Sector label | Geography | Source | Title | Evidence span (clause the tag rests on) |",
            "|---|---|---|---|---|---|---|",
        ]
        for it in link["items"]:
            r, t = it["row"], it["tag"]
            out.append(
                f"| `{r['event_id']}` | {it['pub'].date()} | {r.get('sector') or ''} | {r.get('geography') or ''} | "
                f"{md_cell(r.get('source_name'))} | {md_cell(short(r.get('raw_title'), 80))} | "
                f"{md_cell(short(t.evidence_span, 90))} |"
            )
        out.append("")
    out += [
        "## Limits",
        "",
        "- Reported involvement, not dependency: every tag carries `dependency_proven = False`.",
        (
            "- The tagger is deterministic and conservative; PR #706 measured about 77% strict class precision and did not "
            "measure recall. Many involvements are filed as MENTIONED or UNCERTAIN and so never reach this view."
        ),
        "- Collapse by headline does not merge different headlines about one outage, so sector spans can be inflated.",
        "- The export is a sample, with a heavy Telstra news share and no organisation values.",
        f"- [{HYPOTHESIS}] Whether any sector would be affected by a provider failure is not inferred.",
        "",
    ]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--window-days", type=int, default=WINDOW_DAYS)
    ap.add_argument("--out", default=None)
    ap.add_argument("--source-note", default="events export (read-only SELECT)")
    ap.add_argument("--enable", action="store_true")
    args = ap.parse_args(argv)
    if not require_enabled(args.enable):
        return 2
    rows = load_rows(args.input)
    tagged = tag_rows(rows)
    if args.as_of:
        as_of = parse_ts(args.as_of if "T" in args.as_of else args.as_of + "T00:00:00Z")
    else:
        as_of = max(it["pub"] for it in tagged if it["pub"])
    text = render(tagged, as_of, args.source_note, args.window_days)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
