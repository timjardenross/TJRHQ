"""Deterministic evidence-only fallback narrative (WP3).

Used when the claim gate rejects a generated narrative (flag ``BRIEF_CLAIM_GATE_V1=enforce``). It restates what the collected
evidence says and what is missing, adds no analysis, makes no causal or forecast statements, and never reads as an all-clear.
No network, no LLM, no clock (``now`` is passed in), no randomness: the same input gives the same output.
"""
from __future__ import annotations

import re
from datetime import datetime

from intelligence import claim_gate
from intelligence.claim_gate import sanitize_untrusted

MAX_LISTED = 8
_RANK = {"RED": 0, "AMBER": 1, "GREEN": 2, "UNKNOWN": 3}


def instruction_like(*texts: object) -> bool:
    """True only for genuinely instruction-like text (not for emergency-alert phrasing)."""
    return claim_gate.source_instruction_like(*texts)


def _line(e: dict) -> tuple[str, bool] | None:
    """(rendered line, withheld). A withheld item still shows its risk tag and source name, never its text."""
    title = sanitize_untrusted(e.get("title"), 160)
    if not title:
        return None
    risk = str(e.get("risk_rating") or "").upper()
    src = sanitize_untrusted(e.get("source_name") or e.get("source") or e.get("domain"), 60)
    tag = f"[{risk}] " if risk in _RANK else ""
    if instruction_like(title, e.get("summary")):
        return (f"{tag}[text withheld: instruction-like content in source text]" + (f" ({src})" if src else ""), True)
    if claim_gate.scam_like(title):
        return (f"{tag}[text withheld: scam-like content in source text]" + (f" ({src})" if src else ""), True)
    return (f"{tag}{title}" + (f" ({src})" if src else ""), False)


def build_evidence_fallback(events: list[dict], coverage: dict, *, now: datetime) -> dict:
    """Return the narrative sections (same keys as the generated narrative) plus ``mode``/``generated_at``/``items``."""
    events = [e for e in (events or []) if isinstance(e, dict)]
    coverage = coverage if isinstance(coverage, dict) else {}
    ordered = sorted(events, key=lambda e: _RANK.get(str(e.get("risk_rating") or "").upper(), 4))
    rendered = [r for r in (_line(e) for e in ordered) if r]
    lines = [r[0] for r in rendered]
    withheld = sum(1 for r in rendered if r[1])
    shown, extra = lines[:MAX_LISTED], max(0, len(lines) - MAX_LISTED)

    failed = coverage.get("sources_failed", coverage.get("failed"))
    missing = [sanitize_untrusted(m, 60) for m in (coverage.get("missing_sources") or [])[:10]]
    unknowns = ["No analytical narrative is available for this period; the items listed are reported text only, not assessed."]
    if missing:
        unknowns.append("Sources that did not report: " + ", ".join(m for m in missing if m) + ".")
    elif isinstance(failed, int) and failed > 0:
        unknowns.append(f"{failed} source(s) did not report.")
    if withheld:
        unknowns.append(f"{withheld} item(s) had their text withheld because the source text contained instruction-like or scam-like content.")
    unknowns.append("The absence of an item from this list does not mean nothing happened.")

    item_lines = shown + ([f"... and {extra} more item(s)"] if extra else [])
    if shown:
        snapshot = (f"Automated analysis was withheld because it could not be checked against the evidence. "
                    f"{len(lines)} item(s) were collected this period; they are listed as reported, without analysis"
                    + (f" ({withheld} with text withheld)." if withheld else ".")
                    + "".join(f"\n- {ln}" for ln in item_lines))
        bottom = "Analysis unavailable for this brief. Review the listed items directly. This is not an all-clear."
    else:
        snapshot = ("Automated analysis was withheld and no items were available to list for this period. "
                    "This does not confirm that nothing occurred.")
        bottom = "Analysis unavailable and no items to list. This is not an all-clear."
    return {
        "mode": "evidence_fallback",
        "generated_at": now.isoformat(),
        "executive_snapshot": snapshot,
        "emerging_themes": None,
        "forward_watch": None,
        "cps230_implications": None,
        "bottom_line": bottom,
        "known_unknowns": unknowns,
        "items": item_lines,
        "withheld_count": withheld,
    }


# ── Deterministic so-what (the same table as BriefGenerator._infer_so_what, keyed by the stored event type) ──────────────────

_SO_WHAT_TEMPLATES = {
    "regulatory": "Review regulatory obligations and assess compliance posture",
    "cyber": "Assess exposure, review controls, monitor ACSC advisories",
    "technology_outage": "Assess dependency on affected platform; activate contingency if critical",
    "payments_disruption": "Assess payment channel availability; prepare customer communications",
    "severe_weather": "Review site and workforce continuity plans for affected regions",
    "telecom_outage": "Assess connectivity dependencies; activate backup channels if available",
    "energy_disruption": "Review UPS and backup power; assess data centre resilience",
}
_SO_WHAT_DEFAULT = "Monitor situation; assess operational exposure and escalate if conditions worsen"


def template_so_what(event_type: object) -> str:
    """Deterministic so-what for an event type, given either the raw type ('technology_outage') or the stored display form
    ('Technology Outage')."""
    key = re.sub(r"[\s-]+", "_", str(event_type or "").strip().lower())
    return _SO_WHAT_TEMPLATES.get(key, _SO_WHAT_DEFAULT)


def display_so_what(brief: dict | None, event: dict) -> str | None:
    """The so-what a reader of a STORED brief may see. With BRIEF_CLAIM_GATE_V1 off or shadow the stored value is shown as before. In
    enforce it is shown only when the brief records that its so-whats were governed by the gate in enforce mode at generation time;
    otherwise (a row written before governance, by a process with the gate off, or with no record) the deterministic template is shown,
    so ungated model text is never what the Captain reads while enforcement is on."""
    stored = event.get("so_what")
    try:
        if claim_gate.gate_mode() != "enforce":
            return stored
        cov = (brief or {}).get("coverage")
        rec = (cov or {}).get("claim_gate_v1") if isinstance(cov, dict) else None
        so = rec.get("so_what") if isinstance(rec, dict) else None
        if isinstance(so, dict) and so.get("governed") is True and so.get("mode") == "enforce":
            return stored
        return template_so_what(event.get("event_type"))
    except Exception:  # noqa: BLE001 - fail to the deterministic text, never to ungated text
        return template_so_what(event.get("event_type"))
