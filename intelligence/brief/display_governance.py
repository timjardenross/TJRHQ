"""Display-time governance of STORED generated narrative (flag ``BRIEF_CLAIM_GATE_V1``).

The claim gate governs text when it is generated. A reader of a stored brief (Telegram morning text, XO, Captain's Chair excerpt, the
published-brief e-mail, the workflow digest line) can also be shown a row that was written with the flag off or in shadow mode, by an
older gate, by another process with a different environment, or edited afterwards. In ``enforce`` mode such a row must not put ungated
model text in front of the Captain.

Rule (enforce only; with the flag off or in shadow every function here returns the stored values unchanged):

* A stored narrative is SHOWN when the row's own record (``coverage.claim_gate_v1``) says it was produced in enforce mode by a gate of at
  least this revision, the outcome is "passed", "evidence-only fallback" or "list items withheld", AND the record's ``display_sha`` equals
  the hash of the narrative fields as stored now (the record cannot vouch for text it was not written for).
* Otherwise the narrative fields are WITHHELD with an explicit disclosure that is never worded as an all-clear.

Control and invisible characters are removed from whatever is shown (a stored value with a NUL, a Unicode tag character or a bidi override
would otherwise be displayed as written).
"""
from __future__ import annotations

from intelligence import claim_gate

WITHHELD_READ = ("The generated narrative stored for this brief was not checked against the evidence under the current policy, so it is withheld. "
                 "This is not an all-clear: the incidents listed below are reported text only.")
WITHHELD_LIST_NOTE = "Generated analysis withheld (not checked against the evidence under the current policy)."

FIELDS = ("executive_snapshot", "bottom_line", "emerging_themes", "forward_watch", "cps230_implications", "known_unknowns")


def enforcing() -> bool:
    """True when the gate is in enforce mode. An unreadable flag is treated as enforce-safe for DISPLAY (it can only withhold)."""
    try:
        return claim_gate.gate_mode() == "enforce"
    except Exception:  # noqa: BLE001
        return True


def _record(brief: dict | None) -> dict:
    cov = (brief or {}).get("coverage")
    rec = cov.get("claim_gate_v1") if isinstance(cov, dict) else None
    return rec if isinstance(rec, dict) else {}


def is_governed(brief: dict | None) -> bool:
    """Whether the stored narrative fields of ``brief`` were governed in enforce mode and are the text the record vouches for."""
    try:
        b = brief or {}
        rec = _record(b)
        if rec.get("mode") != "enforce" or int(rec.get("gate_rev") or 0) < claim_gate.GATE_REV:
            return False
        outcome_ok = bool(rec.get("passed") is True or rec.get("fallback_used") is True or int(rec.get("items_withheld") or 0) > 0)
        if not outcome_ok:
            return False
        want = rec.get("display_sha")
        if not want:
            return False
        got = claim_gate.display_sha(b.get("executive_snapshot"), b.get("bottom_line"), b.get("emerging_themes"), b.get("forward_watch"),
                                     b.get("cps230_implications"), b.get("known_unknowns"))
        return want == got
    except Exception:  # noqa: BLE001 - cannot establish governance: not governed
        return False


def _clean(v):
    if isinstance(v, str):
        return claim_gate.strip_control_chars(v) if claim_gate.has_control_chars(v) else v
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def narrative_view(brief: dict | None) -> dict:
    """The six narrative fields as a reader may see them, plus ``governed`` and ``withheld`` flags."""
    b = brief or {}
    if not enforcing():
        return {**{f: b.get(f) for f in FIELDS}, "governed": None, "withheld": False}
    if is_governed(b):
        return {**{f: _clean(b.get(f)) for f in FIELDS}, "governed": True, "withheld": False}
    has_any = any(b.get(f) for f in FIELDS)
    out = {f: None for f in FIELDS}
    out["emerging_themes"] = out["forward_watch"] = out["cps230_implications"] = []
    out["known_unknowns"] = [WITHHELD_LIST_NOTE] if has_any else []
    out["executive_snapshot"] = WITHHELD_READ if has_any else None
    return {**out, "governed": False, "withheld": has_any}


def governed_text(brief: dict | None, field: str = "executive_snapshot", *fallback_fields: str) -> str:
    """One display string (first non-empty of the fields), governed. Empty string when there is nothing to show."""
    v = narrative_view(brief)
    for f in (field, *fallback_fields):
        x = v.get(f)
        if isinstance(x, str) and x.strip():
            return x
    return ""
