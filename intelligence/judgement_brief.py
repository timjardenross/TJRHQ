"""Section 2 of the morning brief: current judgements from the existing register (flag ``BRIEF_JUDGEMENTS_V1``, default OFF).

Read only. No model call, no register write, no principal input shown. A judgement appears only if it is open (not retired or
rejected), has not failed evidence review, and is not past its review date. Anything else is stated as an abstention or as not
available; neither is a finding of low risk.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from urllib.parse import urldefrag

from intelligence import judgements as jd

log = logging.getLogger("judgement_brief")

FLAG = "BRIEF_JUDGEMENTS_V1"
MAX_SHOWN = jd.MAX_DAILY
FRESH_DAYS = 1                       # a run from today or yesterday (Melbourne); older is stale
_NOT_AVAILABLE = "- NOT AVAILABLE. {why} This is not an abstention or a finding of low risk."


def enabled(env: dict | None = None) -> bool:
    return str((env if env is not None else os.environ).get(FLAG, "")).strip().lower() in ("1", "true", "yes", "on")


def _failed_reviews(records: list[dict]) -> tuple[set[str], set[str]]:
    """(ids whose latest version failed evidence review, ids whose latest version passed). A new version resets the review."""
    failed: set[str] = set()
    passed: set[str] = set()
    for r in records:
        if r.get("type") == "judgement":
            failed.discard(r["id"])
            passed.discard(r["id"])
        elif r.get("type") == "review":
            ok = r.get("facts") == "pass" and r.get("reasoning") == "pass"
            (passed if ok else failed).add(r.get("id"))
            (failed if ok else passed).discard(r.get("id"))
    return failed, passed


def _entry(n: int, j: dict, *, new_today: bool, reviewed: bool) -> list[str]:
    sources = {s["ref"]: s for s in j.get("evidence", [])}
    why = str(j.get("change_reason") or "")
    shown_why = why and jd._gate(jd._unscoped(why), j.get("evidence", []), "so_what")       # the producer does not check this text
    change = f"{j['change']}" + (f": {why}" if shown_why else "")
    if not new_today:
        change = f"standing, not reassessed in the latest run (last assessed {j['run_date']})"
    lines = [f"Judgement {n} [{j['id']}] {jd.AREAS[j['area']]}",
             f"- Assessment (judgement): {j['assessment']}",
             *[f"- Reported: {f['text']} [{'; '.join(dict.fromkeys(sources[r]['source'] for r in f['refs'] if r in sources))}]"
               for f in j["facts"]],
             f"- Why (analysis): {j['reasoning']} Assumes: {j['key_assumption']}",
             f"- Confidence: {j['confidence']} ({j['confidence_basis']}).",
             f"- Uncertainty: {j['uncertainty']} Alternative explanation: {j['competing_explanation']}"]
    if j.get("connection"):
        lines.append(f"- Reported connection: {j['connection']['statement']}")
    if j.get("australian_relevance"):
        lines.append(f"- Australian relevance: {j['australian_relevance']}")
    lines += [f"- Implications (forecast, not fact): {j['implications']}",
              f"- Change: {change}.",
              *[f"- Watch: {i['indicator']}; trigger: {i['threshold']}; check by {i['check_by']}." for i in j.get("indicators", [])],
              f"- Review by {j['review_by']}. First issued {j['first_issued']}. Evidence review: {'passed' if reviewed else 'pending'}."]
    cited = list(dict.fromkeys([r for f in j["facts"] for r in f["refs"]] + list((j.get("connection") or {}).get("refs", []))))
    lines += [f"- Evidence: {sources[r]['source']}: {urldefrag(sources[r]['url'])[0]}" for r in cited if r in sources]
    return lines


def section_lines(today: date, register: jd.Register) -> list[str]:
    records = register.records()
    runs = [r for r in records if r.get("type") == "run"]
    oldest = (today - timedelta(days=FRESH_DAYS)).isoformat()
    recent = [r for r in runs if str(r.get("run_date") or "") >= oldest]
    if not recent:
        last = f"The last run was {runs[-1]['run_date']}." if runs else "No run is recorded."
        return [_NOT_AVAILABLE.format(why=f"No current assessment run. {last}")]
    run = recent[-1]
    open_, _rejected = register.state()
    failed, passed = _failed_reviews(records)
    current = [j for j in open_.values() if str(j.get("review_by") or "") >= today.isoformat()]
    usable = [j for j in current if j["id"] not in failed]
    issued = set(run.get("issued") or [])
    usable.sort(key=lambda j: (j["id"] not in issued, j.get("confidence") != "high", j["id"]))
    outcome = run.get("outcome")
    status = jd.OUTCOMES.get(outcome, f"Run status: {run.get('status')}.")
    if run.get("status") == "drafting_unavailable":
        status += " This is not an abstention or a finding of low risk."
    lines = [f"Assessment run {run['run_date']}: {status}",
             "Model-drafted from public-source reports, checked by code; for your adjudication. Not established fact."]
    if not usable:
        if run.get("status") == "drafting_unavailable":
            lines.append("- NOT AVAILABLE. No judgement is open.")
        else:
            lines.append("- ABSTAINED. No judgement is offered: the evidence did not support one that passed the checks. "
                         "This is not a finding of low risk.")
    for n, j in enumerate(usable[:MAX_SHOWN], 1):
        lines += ["", *_entry(n, j, new_today=j["id"] in issued, reviewed=j["id"] in passed)]
    notes = []
    if len(usable) > MAX_SHOWN:
        notes.append(f"- {len(usable) - MAX_SHOWN} further open judgement(s) not shown.")
    if held := sum(1 for j in current if j["id"] in failed):
        notes.append(f"- {held} judgement(s) withheld after failing evidence review.")
    # Only text that passed the producer's checks is printed: a retirement shows the judgement as it was issued, and rejected
    # drafts and the model's own abstention notes are counted, never quoted. Their detail stays in the evaluation record.
    since = {r.get("run_date") for r in recent}
    issued_text = {r["id"]: r["assessment"] for r in records if r.get("type") == "judgement"}
    notes += [f"- Retired since the previous brief ({r['status']}): {issued_text[r['id']]}" for r in records
              if r.get("type") == "retire" and r.get("run_date") in since and r.get("id") in issued_text]
    if declined := len(run.get("abstentions") or []):
        notes.append(f"- {declined} further topic(s) not offered as judgements; reasons are in the evaluation record.")
    return [*lines, *([""] if notes else []), *notes, "", f"- {jd.SCREENING_LIMITATION}"]


def morning_section(today: date, register: jd.Register | None = None) -> list[str] | None:
    """None when the flag is off (the brief is then unchanged). Never raises: a failure is stated in the section."""
    if not enabled():
        return None
    try:
        return section_lines(today, register or jd.Register())
    except Exception as exc:  # noqa: BLE001 - the brief must still be produced, and must say what is missing
        log.warning("[judgement-brief] unavailable: %s", type(exc).__name__)
        return [_NOT_AVAILABLE.format(why="The judgement register could not be read.")]
