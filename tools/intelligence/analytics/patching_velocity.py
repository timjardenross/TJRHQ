"""P2 (prototype, NON-PRODUCTION): technology change and patching velocity framework.

Source volume is NOT velocity. This script separates six stages and computes only
metrics that the stored rows can support, saying plainly where they cannot:

  S1 disclosure         NVD CVE rows
  S2 exploitation       CISA KEV additions
  S3 patch availability text markers in NVD/vendor advisories (presence, not date)
  S4 remediation        KEV due dates, only if present in text (usually absent)
  S5 vendor release     vendor/CISA/ACSC advisory activity
  S6 change disruption  status incidents whose OWN text names a change

Usage:
    python tools/intelligence/analytics/patching_velocity.py \
        --input status_and_security.jsonl --input nvd.jsonl --as-of 2026-11-24T00:40:00Z

Offline only. Coincidence is reported as PLAUSIBLE RELATIONSHIP, never causation.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analytics_common import (
    HYPOTHESIS,
    LABEL_LEGEND,
    OBSERVED,
    PLAUSIBLE,
    load_jsonl,
    median,
    parse_ts,
)
from provider_failure import build_incidents, is_status_source

CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}")
KEV_SRC = "CISA Known Exploited Vulnerabilities"
NVD_SRC = "NVD / NIST CVE Database"
MIRROR_SRC = {"CISA Alerts"}  # republishes KEV additions: not independent of KEV
VENDOR_ADVISORY_SRC = {
    "Microsoft Security Response Center", "Fortinet PSIRT Advisories",
    "Palo Alto Networks Security Advisories", "Cisco Security Advisories",
    "Google Cloud Security Bulletins",
}
NATIONAL_ALERT_SRC = {"ACSC Alerts & Advisories", "ACSC Advisories"}

PATCH_MARKERS = re.compile(
    r"\bfixed in\b|\bupdate to\b|\bupgrade to\b|\bpatch(?:ed|es)?\b|\bhotfix\b|\bsecurity update\b|"
    r"\bbefore (?:version |v)?\d+(?:\.\d+)+|\bprior to (?:version |v)?\d+(?:\.\d+)+|\bremediat",
    re.IGNORECASE,
)
DUE_DATE = re.compile(
    r"(?:due date|remediation deadline|required action due|apply updates? by)\W{0,3}"
    r"(\d{4}-\d{2}-\d{2}|\d{1,2} \w+ \d{4})",
    re.IGNORECASE,
)
# Change markers on the provider's OWN words. Status-line words ('Update -', 'next update')
# are excluded on purpose so that routine status updates do not count as changes.
CHANGE_MARKERS = re.compile(
    r"\bdeploy(?:ment|ments|ed|ing)?\b|\brollout\b|\brolled out\b|\brolling out\b|\brollback\b|\brolled back\b|"
    r"\bconfiguration change|\bconfig change|\bchange (?:was|that was)\b|\brelease[ds]?\b|"
    r"\bmigrat(?:ion|ing|ed)\b|\bupgrad(?:e|ed|ing)\b|\bsoftware update\b|\bpatch(?:ed|ing)?\b",
    re.IGNORECASE,
)


def cves_in(text):
    return set(CVE_RE.findall(text or ""))


def day(ts):
    return ts.date() if ts else None


def disclosure_to_kev(rows):
    """S1->S2: days from NVD publication to KEV addition, for CVEs present in both."""
    nvd, kev = {}, {}
    for r in rows:
        ts = parse_ts(r.get("published_at"))
        if r["source_name"] == NVD_SRC and ts:
            for c in set(r.get("affected_cves") or []) | cves_in(r.get("raw_title")):
                if c not in nvd or ts < nvd[c]:
                    nvd[c] = ts
        elif r["source_name"] == KEV_SRC and ts:
            for c in cves_in(r.get("raw_title")):
                kev[c] = ts
    pairs = []
    for c in sorted(set(nvd) & set(kev)):
        pairs.append({"cve": c, "nvd_published": nvd[c].date().isoformat(),
                      "kev_added": kev[c].date().isoformat(), "days": (kev[c].date() - nvd[c].date()).days})
    return {"n_nvd_cves": len(nvd), "n_kev_cves": len(kev), "pairs": pairs, "kev": kev}


def first_advisory_to_kev(rows, kev):
    """Signed days (advisory_published - kev_added) per advisory source group.

    Negative = an advisory existed before KEV listed the CVE; positive = after.
    CISA Alerts are shown separately because they mirror KEV additions.
    """
    first = defaultdict(dict)  # cve -> source -> earliest ts
    for r in rows:
        src = r["source_name"]
        if src in (KEV_SRC, NVD_SRC):
            continue
        group = ("mirror" if src in MIRROR_SRC else "vendor_advisory" if src in VENDOR_ADVISORY_SRC
                 else "national_alert" if src in NATIONAL_ALERT_SRC else None)
        ts = parse_ts(r.get("published_at"))
        if not group or not ts:
            continue
        for c in cves_in(f"{r.get('raw_title')} {r.get('raw_summary')} {r.get('canonical_url')}"):
            if c in kev:
                cur = first[c].get(src)
                if cur is None or ts < cur[0]:
                    first[c][src] = (ts, group)
    by_group = defaultdict(list)
    examples = []
    for c, per_src in first.items():
        for src, (ts, group) in per_src.items():
            delta = (ts.date() - kev[c].date()).days
            by_group[group].append(delta)
            examples.append({"cve": c, "source": src, "group": group, "days_vs_kev": delta,
                             "advisory_date": ts.date().isoformat(), "kev_added": kev[c].date().isoformat()})
    summary = {}
    for g, vals in by_group.items():
        summary[g] = {"n": len(vals), "median_days": median(vals), "min": min(vals), "max": max(vals),
                      "same_day_share": round(sum(1 for v in vals if v == 0) / len(vals), 2),
                      "before_kev_share": round(sum(1 for v in vals if v < 0) / len(vals), 2)}
    return summary, examples


def kev_due_dates(rows, assume_days=None):
    kev_rows = [r for r in rows if r["source_name"] == KEV_SRC]
    with_due = []
    for r in kev_rows:
        m = DUE_DATE.search(r.get("raw_summary") or "")
        if m:
            with_due.append((r, m.group(1)))
    out = {"kev_rows": len(kev_rows), "rows_with_due_date_text": len(with_due), "assumed_days": assume_days}
    if assume_days is not None:
        out["hypothetical_deadlines"] = [
            {"cve": next(iter(cves_in(r.get("raw_title"))), None),
             "kev_added": parse_ts(r["published_at"]).date().isoformat(),
             "hypothetical_due": (parse_ts(r["published_at"]) + timedelta(days=assume_days)).date().isoformat()}
            for r in kev_rows if r.get("published_at")
        ][:5]
    return out


def patch_markers(rows):
    """S3: share of rows whose text carries a patch/fixed-version marker (presence only)."""
    out = {}
    for src in sorted({r["source_name"] for r in rows}):
        rs = [r for r in rows if r["source_name"] == src]
        if src in (NVD_SRC, KEV_SRC) or src in VENDOR_ADVISORY_SRC or src in NATIONAL_ALERT_SRC or src in MIRROR_SRC:
            n = sum(1 for r in rs if PATCH_MARKERS.search(f"{r.get('raw_title')} {r.get('raw_summary')}"))
            out[src] = {"rows": len(rs), "with_patch_marker": n, "share": round(n / len(rs), 2) if rs else None}
    return out


def vendor_release_activity(rows, as_of):
    """S5: distinct advisory titles per source per 30d window, last 90 days (activity, not velocity)."""
    out = {}
    for src in sorted(VENDOR_ADVISORY_SRC | NATIONAL_ALERT_SRC | MIRROR_SRC):
        buckets = [set(), set(), set()]
        for r in (x for x in rows if x["source_name"] == src):
            ts = parse_ts(r.get("published_at"))
            if not ts:
                continue
            age = (as_of - ts).days
            if 0 <= age < 90:
                buckets[age // 30].add(r.get("raw_title"))
        out[src] = {"d0_30": len(buckets[0]), "d30_60": len(buckets[1]), "d60_90": len(buckets[2])}
    return out


def change_related_incidents(rows):
    """S6: per provider, unplanned incidents whose own text names a change."""
    status_rows = [r for r in rows if is_status_source(r["source_name"])]
    incs = build_incidents(status_rows)
    per = defaultdict(lambda: {"scheduled": 0, "unplanned": 0, "unplanned_change_named": 0, "examples": []})
    for inc in incs:
        p = per[inc["source"]]
        if inc["schedule"] == "scheduled":
            p["scheduled"] += 1
            continue
        p["unplanned"] += 1
        text = " ".join(f"{e.get('raw_title') or ''} {e.get('raw_summary') or ''}" for e in inc["entries"])
        m = CHANGE_MARKERS.search(text)
        if m:
            p["unplanned_change_named"] += 1
            if len(p["examples"]) < 2:
                start = max(0, m.start() - 70)
                p["examples"].append({"date": inc["first_pub"].date().isoformat() if inc["first_pub"] else None,
                                      "title": (inc["entries"][0].get("raw_title") or "")[:80],
                                      "excerpt": text[start:m.end() + 70].strip()})
    return dict(per), incs


def coincidence_after_scheduled(incs, window_h=24, shifts=range(3, 62, 3)):
    """Same-provider: unplanned incident starting within window_h after a scheduled event's publication.

    Baseline: the same count with all unplanned start times circularly shifted by 3..60 days.
    A count near the baseline means no pattern is visible; a higher count is only PLAUSIBLE,
    because scheduled events are frequent and the data cannot show a mechanism.
    """
    res = {}
    by = defaultdict(list)
    for inc in incs:
        by[inc["source"]].append(inc)
    for src, items in by.items():
        sched = sorted(i["first_pub"] for i in items if i["schedule"] == "scheduled" and i["first_pub"])
        unpl = sorted(i["first_pub"] for i in items if i["schedule"] == "unplanned" and i["first_pub"])
        if len(sched) < 5 or len(unpl) < 5:
            continue
        lo, hi = min(unpl + sched), max(unpl + sched)
        span = hi - lo

        def count(times, sched=sched):
            n = 0
            for t in times:
                if any(timedelta(0) <= t - s <= timedelta(hours=window_h) for s in sched):
                    n += 1
            return n

        obs = count(unpl)
        base = []
        for k in shifts:
            shifted = [lo + ((t - lo + timedelta(days=k)) % span) for t in unpl] if span.total_seconds() > 0 else unpl
            base.append(count(shifted))
        res[src] = {"scheduled": len(sched), "unplanned": len(unpl), "observed_followers": obs,
                    "baseline_mean": round(sum(base) / len(base), 2), "baseline_max": max(base)}
    return res


def vendor_release_vs_incident_pairs(incs, rows):
    """Providers having both a vendor-advisory feed and a status feed. Usually none."""
    pairs = {"Google Cloud": ("Google Cloud Status", "Google Cloud Security Bulletins"),
             "Microsoft": ("Microsoft Azure Status", "Microsoft Security Response Center")}
    out = {}
    for name, (st, adv) in pairs.items():
        n_inc = sum(1 for i in incs if i["source"] == st)
        n_adv = sum(1 for r in rows if r["source_name"] == adv)
        out[name] = {"status_incidents": n_inc, "advisory_rows": n_adv, "computable": n_inc >= 10 and n_adv >= 10}
    return out


def analyse(rows, as_of, assume_kev_days=None):
    d2k = disclosure_to_kev(rows)
    adv_summary, adv_examples = first_advisory_to_kev(rows, d2k["kev"])
    change, incs = change_related_incidents(rows)
    return {
        "as_of": as_of.isoformat(),
        "disclosure_to_kev": {k: v for k, v in d2k.items() if k != "kev"},
        "advisory_vs_kev": adv_summary,
        "advisory_examples": adv_examples,
        "kev_due": kev_due_dates(rows, assume_kev_days),
        "patch_markers": patch_markers(rows),
        "vendor_activity": vendor_release_activity(rows, as_of),
        "change_incidents": change,
        "scheduled_then_unplanned": coincidence_after_scheduled(incs),
        "vendor_release_vs_incident": vendor_release_vs_incident_pairs(incs, rows),
    }


def render_markdown(res):
    d = res["disclosure_to_kev"]
    o = ["# P2 technology change and patching velocity (prototype, non-production)", "", LABEL_LEGEND, "",
         f"As-of: {res['as_of']}", "",
         "## What this adds beyond the intelligence brief", "",
         ("The brief shows advisory/CVE volume. This report separates six stages and computes timing only where two "
          "stages are both present for the same CVE or provider, and states when a metric cannot be computed."), "",
         "## S1 -> S2 disclosure to exploitation (NVD publication to KEV addition)", ""]
    o.append(f"- [{OBSERVED}] NVD CVEs stored: {d['n_nvd_cves']}; KEV CVEs stored: {d['n_kev_cves']}; present in both: {len(d['pairs'])}.")
    for p in d["pairs"]:
        o.append(f"- [{OBSERVED}] {p['cve']}: NVD published {p['nvd_published']}, KEV added {p['kev_added']} ({p['days']} days).")
    o.append(f"- [{OBSERVED}] Not computable as a distribution: n={len(d['pairs'])}. The NVD feed holds recent CVEs; KEV additions are mostly older CVEs.")
    o += ["", "## S2 -> advisory timing relative to KEV addition (signed days; negative = advisory before KEV)", ""]
    for g, s in sorted(res["advisory_vs_kev"].items()):
        o.append(f"- [{OBSERVED}] {g}: n={s['n']}, median {s['median_days']} days (min {s['min']}, max {s['max']}), "
                 f"same-day {s['same_day_share']}, before-KEV {s['before_kev_share']}.")
    o.append(f"- [{PLAUSIBLE}] 'mirror' (CISA Alerts) timing is not independent evidence: it republishes KEV additions.")
    o.append(f"- [{HYPOTHESIS}] a vendor advisory preceding KEV does not show the vendor shipped a fix first; fix availability is not dated in the rows.")
    k = res["kev_due"]
    o += ["", "## S4 remediation deadlines", "",
          (f"- [{OBSERVED}] KEV rows: {k['kev_rows']}; with a due date in stored text: {k['rows_with_due_date_text']}. "
           "Deadline lead time is therefore NOT computable from stored data.")]
    if k.get("assumed_days") is not None:
        o.append(f"- [{HYPOTHESIS}] with an ASSUMED {k['assumed_days']}-day window (not in the data): {k['hypothetical_deadlines']}")
    o += ["", "## S3 patch-availability markers in text (presence only, undated)", ""]
    for src, s in res["patch_markers"].items():
        o.append(f"- [{OBSERVED}] {src}: {s['with_patch_marker']} of {s['rows']} rows carry a patch/fixed-version marker ({s['share']}).")
    o += ["", "## S5 vendor and agency advisory activity (distinct titles per 30 days; activity, not velocity)", ""]
    for src, s in res["vendor_activity"].items():
        o.append(f"- [{OBSERVED}] {src}: {s['d0_30']} / {s['d30_60']} / {s['d60_90']} (latest 30d / prior / earlier).")
    o += ["", "## S6 operational disruption naming a change (provider's own words)", ""]
    for src, s in sorted(res["change_incidents"].items(), key=lambda kv: -kv[1]["unplanned"]):
        if s["unplanned"] < 5:
            continue
        o.append(f"- [{OBSERVED}] {src}: {s['unplanned_change_named']} of {s['unplanned']} unplanned incidents name a change-type word; "
                 f"{s['scheduled']} scheduled events.")
        for ex in s["examples"][:1]:
            o.append(f"  - e.g. {ex['date']} '{ex['title']}': ...{ex['excerpt']}...")
    o.append(f"- [{PLAUSIBLE}] a change word in the provider's own incident text is the provider's account, not verified causation; "
             "words like 'release' or 'upgrade' can also appear in mitigation steps.")
    o += ["", "## Coincidence: unplanned incident within 24h after a same-provider scheduled event", ""]
    for src, s in res["scheduled_then_unplanned"].items():
        o.append(f"- [{OBSERVED}] {src}: {s['observed_followers']} of {s['unplanned']} unplanned incidents followed one of {s['scheduled']} "
                 f"scheduled events within 24h; time-shifted baseline mean {s['baseline_mean']} (max {s['baseline_max']}).")
    o.append(f"- [{PLAUSIBLE}] only if observed clearly exceeds the baseline; [{HYPOTHESIS}] any mechanism. No causal claim is made.")
    o += ["", "## Vendor release vs incident coincidence", ""]
    for name, s in res["vendor_release_vs_incident"].items():
        o.append(f"- [{OBSERVED}] {name}: {s['status_incidents']} status incidents, {s['advisory_rows']} advisory rows; "
                 f"computable: {s['computable']}.")
    o += ["", "## Limits", "",
          "- first-mention-in-our-feed is not first public disclosure; collection lag and feed windows distort dates.",
          "- KEV due dates, fix release dates and CVSS-based urgency are not stored; no deadline or fix-lag metric is claimed.",
          "- No claim about any organisation's patching speed or any vendor being slow.", ""]
    return "\n".join(o)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--assume-kev-due-days", type=int, default=None, help="UNVERIFIED assumption, display only")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    rows = []
    for p in args.input:
        rows += load_jsonl(p)
    as_of = parse_ts(args.as_of) if args.as_of else max(parse_ts(r["collected_at"]) for r in rows if r.get("collected_at"))
    text = render_markdown(analyse(rows, as_of, args.assume_kev_due_days))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
