"""Recurring provider disruption report generator (OFFLINE, default OFF, not wired).

Reads a read-only events export (JSONL or .gz, the format used by PR #698/#706 tooling) and writes a dated
markdown report with one section per provider feed. Counts are of REPORTED unplanned incidents
(`provider_failure.build_incidents`; scheduled maintenance excluded), not true incidents.

Minimum evidence thresholds (from PR #706, docs/PROVIDER-TAXONOMY-AND-DEPENDENCY-EVIDENCE.md section 3):
  (a) >= 20 distinct unplanned incidents in the 90-day window
  (b) unplanned incidents in >= 10 distinct ISO weeks
  (c) bulk-ingest rows < 20% of the feed's rows in the window
  recurring component: the same parsed component in >= 5 unplanned incidents
A feed that fails any of (a)-(c) is listed as INSUFFICIENT EVIDENCE: it gets no spread figure, gap, trend or
rate, only the facts that explain why.

Usage:
    python provider_disruption_report.py --enable --input status.jsonl[.gz] --as-of 2026-11-24 --out report.md
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import itertools

from analytics_common import (
    HYPOTHESIS,
    LABEL_LEGEND,
    OBSERVED,
    PLAUSIBLE,
    median,
    parse_ts,
)
from product_common import (
    clean_text,
    iso_week,
    load_rows,
    md_cell,
    require_enabled,
    short,
)
from provider_failure import build_incidents, detect_backfill_batches, is_status_source

DISCLAIMER = "Incident counts reflect what each source publishes and are not a resilience ranking."
WINDOW_DAYS = 90
RECENT_DAYS = 30
MIN_INCIDENTS = 20
MIN_WEEKS = 10
MAX_BULK_SHARE = 0.20
MIN_COMPONENT_INCIDENTS = 5
MIN_TREND_INCIDENTS = (
    5  # per window, for the trend line only (this tool's rule, not from #706)
)
TREND_RATIO = 1.5
EVIDENCE_N = 5

COMPONENT_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 /&()'.-]{1,45}$")
SENTENCE_WORDS = re.compile(
    r"\b(?:the|is|are|was|were|has|have|may|will|between|during|we|our)\b",
    re.IGNORECASE,
)


def _unplanned(incidents):
    return sorted(
        (i for i in incidents if i["schedule"] == "unplanned" and i["first_pub"]),
        key=lambda i: i["first_pub"],
    )


def median_gap_days(incs):
    starts = [i["first_pub"] for i in incs]
    gaps = [(b - a).total_seconds() / 86400.0 for a, b in itertools.pairwise(starts)]
    return median(gaps)


def trend(incs, as_of, bulk_in_windows):
    """Recent 30d vs prior 60d (normalised per 30d). Returns (label, detail)."""
    recent_start = as_of - timedelta(days=RECENT_DAYS)
    prior_start = recent_start - timedelta(days=WINDOW_DAYS - RECENT_DAYS)
    recent = [i for i in incs if recent_start <= i["first_pub"] < as_of]
    prior = [i for i in incs if prior_start <= i["first_pub"] < recent_start]
    detail = f"{len(recent)} in last 30d vs {len(prior)} in prior 60d ({len(prior) / 2:.1f} per 30d)"
    if bulk_in_windows:
        return (
            "not assessed",
            detail
            + "; bulk-ingest batch inside the windows (collection artefact risk)",
        )
    if len(recent) < MIN_TREND_INCIDENTS or len(prior) < MIN_TREND_INCIDENTS:
        return (
            "not assessed",
            detail + f"; needs >= {MIN_TREND_INCIDENTS} incidents in each window",
        )
    ratio = len(recent) / (len(prior) / 2.0)
    label = (
        "higher"
        if ratio >= TREND_RATIO
        else "lower"
        if ratio <= 1 / TREND_RATIO
        else "about the same"
    )
    return (
        label,
        detail
        + f"; ratio {ratio:.2f} (higher/lower only at >= {TREND_RATIO}x / <= {1 / TREND_RATIO:.2f}x)",
    )


def recurring_components(incs):
    counts = Counter()
    for i in incs:
        for s in set(i["services"]):
            s = clean_text(s)
            if COMPONENT_OK.match(s) and not SENTENCE_WORDS.search(s):
                counts[s] += 1
    return [(c, n) for c, n in counts.most_common() if n >= MIN_COMPONENT_INCIDENTS]


def analyse(rows, as_of):
    start = as_of - timedelta(days=WINDOW_DAYS)
    in_win = [
        r
        for r in rows
        if is_status_source(r.get("source_name"))
        and (p := parse_ts(r.get("published_at")))
        and start <= p < as_of
    ]
    batches = detect_backfill_batches(in_win)
    incidents = build_incidents(in_win)
    feeds = {}
    for src in sorted({r["source_name"] for r in in_win}):
        frows = [r for r in in_win if r["source_name"] == src]
        incs = [i for i in incidents if i["source"] == src]
        unp = _unplanned(incs)
        bulk_rows = [
            r
            for r in frows
            if r.get("collected_at")
            and (src, parse_ts(r["collected_at"]).strftime("%Y-%m-%dT%H:%M")) in batches
        ]
        weeks = sorted({iso_week(i["first_pub"]) for i in unp})
        share = len(bulk_rows) / len(frows) if frows else 0.0
        reasons = []
        if len(unp) < MIN_INCIDENTS:
            reasons.append(
                f"(a) {len(unp)} unplanned incidents, needs >= {MIN_INCIDENTS}"
            )
        if len(weeks) < MIN_WEEKS:
            reasons.append(
                f"(b) unplanned incidents in {len(weeks)} ISO weeks, needs >= {MIN_WEEKS}"
            )
        if share >= MAX_BULK_SHARE:
            reasons.append(
                f"(c) bulk-ingest share {100 * share:.0f}% of rows, needs < {100 * MAX_BULK_SHARE:.0f}%"
            )
        sev = [i["severity"] for i in unp if i["severity"]]
        durs = [i["duration_minutes"] for i in unp if i["duration_minutes"] is not None]
        annotation = {
            "practice": "status-page publisher (the provider's own feed)",
            "severity_stated": len(sev),
            "severity_major_or_critical": sum(
                1 for x in sev if x in ("major", "critical")
            ),
            "durations_stated": len(durs),
            "median_duration_min": median(durs),
            "au_strong": sum(1 for i in unp if i["au"] == "strong"),
        }
        sched = sum(1 for i in incs if i["schedule"] == "scheduled")
        feeds[src] = {
            "feed": src,
            "provider": incs[0]["provider"] if incs else src,
            "rows": len(frows),
            "incidents_all": len(incs),
            "scheduled": sched,
            "unplanned": unp,
            "weeks": weeks,
            "bulk_rows": len(bulk_rows),
            "bulk_share": share,
            "reasons": reasons,
            "annotation": annotation,
            "sufficient": not reasons,
            "batches": {k[1]: v for k, v in batches.items() if k[0] == src},
        }
        if feeds[src]["sufficient"]:
            f = feeds[src]
            f["median_gap_days"] = median_gap_days(unp)
            f["trend"] = trend(unp, as_of, bool(f["batches"]))
            f["components"] = recurring_components(unp)
    return feeds, start


def _evidence_lines(unp):
    out = []
    for i in unp[-EVIDENCE_N:][::-1]:
        e = i["entries"][0]
        out.append(
            f"  - `{e['event_id']}` {i['first_pub'].date()} | {md_cell(short(e.get('raw_title'), 100))} | "
            f"{e.get('canonical_url') or 'no url'}"
        )
    return out


def render(feeds, as_of, start, source_note):
    ok = [f for f in feeds.values() if f["sufficient"]]
    bad = [f for f in feeds.values() if not f["sufficient"]]
    ok.sort(key=lambda f: f["feed"].lower())  # alphabetical: never ordered by raw count
    bad.sort(key=lambda f: f["feed"].lower())
    out = [
        f"# Recurring provider disruption report, generated {as_of.date().isoformat()}",
        "",
        (
            f"Source: {source_note}. Window: {start.date()} to {as_of.date()} (90 days, `published_at` basis). "
            "Offline, read-only, default OFF, not wired into any service."
        ),
        "",
        LABEL_LEGEND,
        "",
        f"**{DISCLAIMER}**",
        "",
        (
            "Unit: DISTINCT UNPLANNED INCIDENT as grouped from status-feed entries (scheduled maintenance excluded). "
            "These are reported incidents. Reporting practice differs by provider, so figures are not comparable "
            "across providers and are not a reliability ranking."
        ),
        "",
        "## Minimum-evidence thresholds (PR #706)",
        "",
        f"- (a) at least {MIN_INCIDENTS} distinct unplanned incidents in 90 days",
        f"- (b) unplanned incidents in at least {MIN_WEEKS} distinct ISO weeks",
        (
            f"- (c) bulk-ingest rows under {int(MAX_BULK_SHARE * 100)}% of the feed's rows (bulk batch = 8+ rows in one "
            "collection minute with median publish-to-collect lag over 24h)"
        ),
        f"- recurring component: same parsed component in at least {MIN_COMPONENT_INCIDENTS} unplanned incidents",
        "",
        f"Result: {len(ok)} feeds meet thresholds; {len(bad)} are listed as insufficient evidence and are not scored.",
        "",
        "## Summary (feeds meeting thresholds)",
        "",
        "| Feed (alphabetical) | Unplanned incidents | ISO weeks with one | Median gap (days) | Bulk-row share | Reporting practice | AU-relevant | Trend (30d vs prior 60d) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for f in ok:
        out.append(
            f"| {f['feed']} | {len(f['unplanned'])} | {len(f['weeks'])} | {f['median_gap_days']:.1f} | "
            f"{100 * f['bulk_share']:.0f}% | status-page publisher | {f['annotation']['au_strong']} | {f['trend'][0]} |"
        )
    if not ok:
        out.append("| none | | | | | | | |")
    out += ["", "## Per provider", ""]
    for f in ok:
        out += [
            f"### {f['provider']} ({f['feed']})",
            "",
            (
                f"- [{OBSERVED}] Incident count: {len(f['unplanned'])} unplanned "
                f"({f['scheduled']} scheduled maintenance incidents excluded) from {f['rows']} feed rows."
            ),
            (
                f"- [{OBSERVED}] ISO-week spread: unplanned incidents in {len(f['weeks'])} distinct weeks "
                f"({f['weeks'][0]} to {f['weeks'][-1]})."
            ),
            f"- [{OBSERVED}] Median gap between consecutive incident start times: {f['median_gap_days']:.1f} days.",
            f"- [{OBSERVED}] Trend: {f['trend'][0]} ({f['trend'][1]}).",
            f"- [{OBSERVED}] Collection-artefact check: {f['bulk_rows']} of {f['rows']} rows "
            f"({100 * f['bulk_share']:.0f}%) are in bulk-ingest batches"
            + (
                f"; batches at {', '.join(sorted(f['batches']))} UTC."
                if f["batches"]
                else "; none detected."
            ),
        ]
        if f["components"]:
            comps = ", ".join(f"{c} ({n})" for c, n in f["components"][:5])
            out.append(
                f"- [{OBSERVED}] Recurring components (>= {MIN_COMPONENT_INCIDENTS} incidents): {comps}."
            )
        else:
            out.append(
                f"- Recurring components: none parse cleanly with >= {MIN_COMPONENT_INCIDENTS} incidents."
            )
        an = f["annotation"]
        out.append(
            f"- Context (read before comparing): reporting practice = {an['practice']}; window = 90 days; bulk-ingest share "
            f"{100 * f['bulk_share']:.0f}%; severity stated on {an['severity_stated']} incidents "
            f"({an['severity_major_or_critical']} major/critical); duration stated on {an['durations_stated']}"
            + (
                f" (median {an['median_duration_min']:.0f} min)"
                if an["median_duration_min"] is not None
                else ""
            )
            + f"; Australian-relevant (strong text match) {an['au_strong']}. {DISCLAIMER}"
        )
        out.append(
            f"- [{PLAUSIBLE}] Recurrence exists as reported entries; that it reflects reliability is not shown."
        )
        out.append(
            f"- Evidence (latest {EVIDENCE_N} of {len(f['unplanned'])}; event id, date, title, url):"
        )
        out += _evidence_lines(f["unplanned"])
        out.append("")
    out += ["## Insufficient evidence (listed, never scored)", ""]
    if bad:
        out += [
            "| Feed | Unplanned incidents | Scheduled | Why insufficient |",
            "|---|---|---|---|",
        ]
        for f in bad:
            out.append(
                f"| {f['feed']} | {len(f['unplanned'])} | {f['scheduled']} | {md_cell('; '.join(f['reasons']))} |"
            )
        out.append("")
        out.append(
            "Counts above are facts about the export, not recurrence scores. A feed with a bulk-ingest artefact "
            "(for example a batch re-ingest of old incidents) can show a spread that the provider did not produce."
        )
    else:
        out.append("None.")
    out += [
        "",
        "## Limits",
        "",
        "- Status feeds only. Silence cannot be told from 'no incidents' without a collector liveness signal.",
        "- Incident identity relies on URL ids and title/minute matching (provider_failure.build_incidents).",
        "- Scheduled-vs-unplanned is a text rule; a feed that labels everything 'maintenance' under-counts.",
        f"- [{HYPOTHESIS}] Why any feed has more or fewer incidents is not inferred.",
        "",
    ]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument(
        "--as-of",
        default=None,
        help="ISO date/time; default latest published_at not after now",
    )
    ap.add_argument("--out", default=None)
    ap.add_argument("--source-note", default="events export (read-only SELECT)")
    ap.add_argument("--enable", action="store_true")
    args = ap.parse_args(argv)
    if not require_enabled(args.enable):
        return 2
    rows = load_rows(args.input)
    if args.as_of:
        as_of = parse_ts(args.as_of if "T" in args.as_of else args.as_of + "T00:00:00Z")
    else:
        as_of = max(p for r in rows if (p := parse_ts(r.get("published_at"))))
    feeds, start = analyse(rows, as_of)
    text = render(feeds, as_of, start, args.source_note)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
