"""Weekly "Trends" markdown product (wk-trends/0.1.0-prototype) -- OFFLINE, default OFF, not wired into any report or scheduler.

Renders the result of ``intelligence.longitudinal_trends.build_trends`` as one markdown page with the four labelled sections used by the
other intelligence products: Confirmed evidence, Analytical inference, Potential exposure, Unknowns. It manufactures nothing: a trend
that does not meet the minimum-evidence rule is not listed, and when only weak signals exist the page says so in its first lines.
"""
from __future__ import annotations

import html
from datetime import date, timedelta

from intelligence import longitudinal_trends as lt

SECTIONS = ("Confirmed evidence", "Analytical inference", "Potential exposure", "Unknowns")
RATE_MIN_INCIDENTS = 8
RATE_MAX_P = 0.01


def _cell(text, limit: int = 110) -> str:
    t = html.unescape(str(text)).replace("|", "/").replace("\n", " ").strip()
    return t if len(t) <= limit else t[: limit - 1] + "…"


def rate_change(res: dict, volume: dict, week: str, weeks: list[str], reliability: dict, basis: str) -> dict:
    """This week's incidents per published report against the pooled trailing (up to 4 reliable) weeks. A change is reported only if
    this week has at least RATE_MIN_INCIDENTS incidents and the one-sided binomial tail is <= RATE_MAX_P."""
    idx = weeks.index(week)
    base = [w for w in weeks[:idx] if reliability[w]["reliable"]][-4:]
    n = res["counts"][week]["total"]
    big_n = volume[week]["published"]
    bn = sum(res["counts"][w]["total"] for w in base)
    bN = sum(volume[w]["published"] for w in base)
    out = {"basis": basis, "week_incidents": n, "week_published": big_n, "baseline_weeks": base,
           "baseline_incidents": bn, "baseline_published": bN, "state": "insufficient evidence"}
    if not reliability[week]["reliable"] or len(base) < 3 or big_n == 0 or bN == 0:
        out["state"] = "not assessed (unreliable week or fewer than 3 reliable baseline weeks)"
        return out
    p0 = max(bn, 0.5) / bN
    out["rate_per_1000"] = round(1000 * n / big_n, 2)
    out["baseline_rate_per_1000"] = round(1000 * bn / bN, 2)
    up, down = lt.binom_tail(n, big_n, p0), 1 - lt.binom_tail(n + 1, big_n, p0)
    out["p_up"], out["p_down"] = float(f"{up:.2g}"), float(f"{down:.2g}")
    if n >= RATE_MIN_INCIDENTS and up <= RATE_MAX_P:
        out["state"] = "higher than baseline"
    elif bn >= RATE_MIN_INCIDENTS and down <= RATE_MAX_P:
        out["state"] = "lower than baseline"
    else:
        out["state"] = "no change distinguishable from the baseline"
    return out


def _vol_table(res: dict, week: str, n_weeks: int = 8) -> list[str]:
    weeks = res["weeks"]
    shown = weeks[max(0, weeks.index(week) - n_weeks + 1): weeks.index(week) + 1]
    lines = ["| Week (Mon, UTC) | Reports collected | Reports published (dated) | Undated | Of published: primary / mainstream / specialist / aggregator / content / other | Active sources | Incidents (all) | Incidents (constant set) | Reliable |",
             "|---|---|---|---|---|---|---|---|---|"]
    for w in shown:
        v, c = res["volume"][w], res["coverage"][w]
        bc = v["published_by_class"]
        other = sum(n for k, n in bc.items() if k not in ("primary", "mainstream", "specialist", "aggregator", "content"))
        cls = " / ".join(str(bc.get(k, 0)) for k in ("primary", "mainstream", "specialist", "aggregator", "content")) + f" / {other}"
        rel = res["reliability"][w]
        lines.append(f"| {w} | {v['collected']} | {v['published']} | {v['undated']} | {cls} | {c['active_sources']} | "
                     f"{res['all']['counts'][w]['total']} | {res['constant']['counts'][w]['total']} | "
                     f"{'yes' if rel['reliable'] else 'NO: ' + '; '.join(rel['reasons'])} |")
    return lines


def _count_table(counts: dict, key: str) -> list[str]:
    a, c = counts["all"][key], counts["constant"][key]
    names = sorted(set(a) | set(c), key=lambda k: (-a.get(k, 0), k))
    lines = ["| " + key.replace("by_", "").replace("au", "Australian relevance").replace("sector", "Sector") + " | All sources | Constant sources |", "|---|---|---|"]
    lines += [f"| {k} | {a.get(k, 0)} | {c.get(k, 0)} |" for k in names] or ["| (none) | 0 | 0 |"]
    return lines


def render_trends_markdown(res: dict, *, week: str, generated_on: str | None = None) -> str:
    if not res.get("enabled", True):
        return f"# Trends\n\nNot generated: {res.get('reason')}.\n"
    weeks = res["weeks"]
    if week not in weeks:
        raise ValueError(f"{week} is outside the analysed window {weeks[0]}..{weeks[-1]}")
    wk_end = (date.fromisoformat(week) + timedelta(days=6)).isoformat()
    rel = res["reliability"][week]
    cnt = {b: res[b]["counts"][week] for b in ("all", "constant")}
    cnt_tables = {"all": {k: res["all"]["counts"][week][k] for k in ("by_sector", "by_au", "by_type")},
                  "constant": {k: res["constant"]["counts"][week][k] for k in ("by_sector", "by_au", "by_type")}}
    rc = {b: rate_change(res[b], res["volume"] if b == "all" else res["constant_volume"], week, weeks, res["reliability"], b)
          for b in ("all", "constant")}
    emerging = [e for b in ("all", "constant") for e in res[b]["emerging"] if e["week"] == week]
    emerging_supported = [e for e in res["all"]["emerging"] if e["week"] == week and e["label"] == "supported-in-constant-sources"]
    repeats = [r for r in res["all"]["repeats"] if r["week"] == week]
    const_repeats = {(r["subject"], r["week"]) for r in res["constant"]["repeats"]}
    weak = not emerging_supported and not any(r["state"].startswith(("higher", "lower")) for r in rc.values())

    L: list[str] = []
    L += [f"# Trends: week commencing {week} (UTC)", "",
          "> **GENERATED FROM THE REAL STORED HISTORY, OFFLINE.** Produced by `intelligence/longitudinal_trends.py` "
          f"(`{res['method']}`) from a read-only export of `intelligence_events` ({res['data_range'][0]} to {res['data_range'][1]}). "
          f"Not a live product: the generator is default OFF (`{lt.FLAG}`) and nothing schedules it. "
          + (f"Generated on {generated_on}. " if generated_on else "")
          + "Single-reviewer audit; see the limitations in the Unknowns section and `docs/INTELLIGENCE-LONGITUDINAL-TRENDS-AUDIT.md`.", ""]
    L += ["## Headline", ""]
    if weak:
        L += [(f"**Only weak signals this week ({week} to {wk_end}).** No term met the minimum-evidence rule on both bases, and the "
              "incident rate is not distinguishable from its baseline. Nothing below should be read as an established trend."), ""]
    else:
        L += [f"One or more signals met the minimum-evidence rule for the week {week} to {wk_end}; each is labelled with the basis on which it holds.", ""]
    if not rel["reliable"]:
        L += [f"**This week is flagged unreliable for trend comparison:** {'; '.join(rel['reasons'])}.", ""]

    L += ["## Volume denominator and coverage (read first)", "",
          ("Every count below is per the reports that were stored. The table shows how much was collected and published each week, so a change in "
          "collection cannot be mistaken for a change in the world. **Constant set** = sources that collected at a steady rate throughout the window "
          f"({len(res['constant_sources']['sources'])} sources: window {res['constant_sources']['window'][0]} to {res['constant_sources']['window'][1]}); "
          "it is the primary basis for any trend."), ""]
    L += _vol_table(res, week) + [""]
    cov = res["coverage"][week]
    ch = [f"{c['date']} ({c['kind']}): {c['note']}" for c in cov["changes"]]
    L += [f"- Active sources this week by class: {', '.join(f'{k} {v}' for k, v in cov['active_by_class'].items())}.",
          f"- Sources first seen this week: {', '.join(cov['new_sources']) or 'none'}. Sources whose last stored report was last week (sparse feeds can be quiet without being broken): {', '.join(cov['went_silent']) or 'none'}.",
          f"- Dated coverage changes in this week: {'; '.join(ch) or 'none'}.",
          f"- Known broken or retired sources overlapping this week: {', '.join(cov['known_broken']) or 'none'}.", ""]

    # --- Confirmed evidence
    L += [f"## {SECTIONS[0]}", "",
          ("Counted directly from stored reports (incident = a group of reports from the existing incident detection that states, or reports as unconfirmed, a service-affecting event; "
          "natural-hazard notices, vulnerability advisories, warnings, forecasts, retrospectives and commentary are not counted)."), "",
          (f"- Incidents with first publication in the week: **{cnt['all']['total']}** from all sources, **{cnt['constant']['total']}** from the constant set "
          f"(denominator: {res['volume'][week]['published']} dated reports published in the week, {res['constant_volume'][week]['published']} from the constant set)."), ""]
    L += _count_table({"all": cnt_tables["all"], "constant": cnt_tables["constant"]}, "by_sector") + [""]
    L += _count_table({"all": cnt_tables["all"], "constant": cnt_tables["constant"]}, "by_au") + [""]
    L += _count_table({"all": cnt_tables["all"], "constant": cnt_tables["constant"]}, "by_type") + [
        "", "`physical` is the detector's broad fire/explosion/collapse/attack vocabulary and includes much world news; treat it as the noisiest class.", ""]
    rs = res["all"]["restoration"][week]
    L += [f"- Restoration duration: {rs['outage_incidents']} outage-class incidents, {rs['with_restoration_evidence']} with a dated restoration report"
          + (f"; median {rs['median_hours']} h" if rs["median_hours"] is not None else f"; {rs['note']}")
          + f" ({rs['dropped_implausible']} dropped as implausible).", ""]
    L += ["### Repeated disruption of the same service (3+ episodes in 28 days) detected this week", ""]
    if not repeats:
        L += ["None met the rule this week.", ""]
    for r in repeats:
        L += [f"- **{r['subject']}**: {r['episodes_in_final_window']} episodes in the 28 days to {r['last'][:10]}"
              f" ({r['episodes']} in the overlapping run since {r['first'][:10]}). "
              f"Basis: {r['label'].replace('-', ' ')}"
              + ("; also holds on the constant set" if (r['subject'], r['week']) in const_repeats else "") + ".", ""]
        L += [f"  - {e['published'][:10]} {e['type']}: {_cell(e['headline'])}" for e in r["evidence"]] + [""]

    # --- Analytical inference
    L += [f"## {SECTIONS[1]}", "",
          "Comparisons and inferences. These depend on the detector's grouping and on the labelled assumptions; they are not facts.", "",
          "### Incident rate against the trailing baseline", ""]
    for b in ("all", "constant"):
        r = rc[b]
        if "rate_per_1000" in r:
            L += [(f"- {b} sources: {r['week_incidents']} incidents per {r['week_published']} published reports = {r['rate_per_1000']} per 1,000; "
                  f"baseline {r['baseline_incidents']} per {r['baseline_published']} = {r['baseline_rate_per_1000']} per 1,000 "
                  f"(weeks {', '.join(r['baseline_weeks'])}). Result: **{r['state']}** (one-sided p up {r['p_up']}, down {r['p_down']}; "
                  f"a change is reported only with >= {RATE_MIN_INCIDENTS} incidents and p <= {RATE_MAX_P}).")]
        else:
            L += [f"- {b} sources: {r['state']}."]
    L += ["", "### Emerging terms and entities", ""]
    if not emerging:
        L += [(f"No term met the minimum-evidence rule this week (>= {lt.PARAMS['min_term_incidents']} incidents, >= {lt.PARAMS['min_term_publishers']} independent publishers, "
              f">= {lt.PARAMS['min_term_days']} days, ratio >= {lt.PARAMS['min_ratio']}, p <= {lt.PARAMS['max_p']}, against a pooled baseline of up to "
              f"{lt.PARAMS['baseline_weeks']} reliable weeks)."), ""]
    for e in emerging:
        L += [(f"- `{e['term']}` ({'constant set' if e['label'].startswith('constant') else 'all sources'}): {e['incidents']} of {e['week_incidents']} incidents this week "
              f"against {e['baseline_incidents_with_term']} of {e['baseline_incidents']} in the baseline (ratio {e['ratio']}, p {e['p']}, {e['publishers']} publishers, {e['days']} days). "
              f"Label: **{e['label']}**.")]
        L += [f"  - {x['published'][:10]}: {_cell(x['headline'])}" for x in e["evidence"][:6]]
    L += [""]
    L += ["### Interpretation limits", "",
          ("- A flagged term is a candidate for human reading, not a finding: in the audit most flagged words were one story reported several ways, "
          "or a generic word that a short baseline made look new."),
          ("- Repeats are counted per named service from status-page items and news; status-page feeds report many small incidents, so a repeat there is "
          "evidence of reported disruption frequency, not of service quality."), ""]

    # --- Potential exposure
    L += [f"## {SECTIONS[2]}", "",
          ("What the week's incident set could mean for Australian operations (`physical` incidents with no recognised sector are left out as noise). Relevance is the detector's, from headlines and summaries only; "
          "**dependency means a plausible platform dependency, not demonstrated Australian impact.**"), ""]
    inc_wk = [i for i in res["all"]["incidents"] if i["week"] == week]
    au = [i for i in inc_wk if i["au_relevance"] in ("operational", "dependency")
          and (i["event_type"] != "physical" or i["sector"] != "unclassified")]
    if not au:
        L += ["No incident this week carried Australian operational relevance or a plausible dependency.", ""]
    else:
        L += ["| First published | Type | Sector | Australian relevance | Independent publishers | Headline |", "|---|---|---|---|---|---|"]
        for i in sorted(au, key=lambda x: x["first_published"])[:15]:
            L += [f"| {i['first_published'][:10]} | {i['event_type']} | {i['sector']} | {i['au_relevance']} | {i['independent_publishers']} | {_cell(i['headline'])} |"]
        L += [""]
    dep = [r for r in repeats]
    if dep:
        L += ["Repeated-disruption subjects above are candidates for dependency review (check whether the organisation relies on them); nothing here shows they affected it.", ""]

    # --- Unknowns
    L += [f"## {SECTIONS[3]}", ""]
    unreliable = [w for w in weeks if not res["reliability"][w]["reliable"]]
    L += [f"- **Unreliable weeks in this window ({len(unreliable)} of {len(weeks)}):** "
          + "; ".join(f"{w} ({'; '.join(res['reliability'][w]['reasons'])})" for w in unreliable) + "." if unreliable else "- No week in this window is flagged unreliable.",
          "- **Collection changed during the history.** " + " ".join(f"{c['date']}: {c['note']}" for c in res["coverage_changes"]),
          "- **Known broken or silent sources:** " + "; ".join(f"{b['source']} (from {b['from']}{' to ' + b['to'] if b.get('to') else ''}: {b['note']})" for b in res["known_broken"]),
          f"- **Constant-source set** excludes {len(res['constant_sources']['excluded'])} sources that were not steady across the window; it is smaller and less diverse than the full set, so absence of a trend there is weak evidence of absence.",
          ("- **Publication dates:** a report is placed in a week by its own verified publication time; undated reports (shown per week) are excluded from weekly counts. "
          "The 24 Nov RSS repair assumed a constant +10 h shift and left 487 rows uncorrected; at most a few reports near a Monday boundary could sit in the wrong week."),
          "- **Detector limits:** headline-only classification, keyword vocabularies, and a correlator that sometimes merges two services or splits one story into several incidents (both seen in the audit). Counts are of detected incident groups, not of verified incidents.",
          "- **Restoration duration** exists only where a later report in the same group affirms restoration with its own timestamp; most incidents have none.",
          "- **Short history:** about 18 complete weeks, one coverage regime for only the last 11. No seasonality can be assessed. Single human reviewer; no inter-rater check.", ""]
    return "\n".join(L)
