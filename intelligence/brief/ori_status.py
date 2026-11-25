"""Production status for ORI briefs (``intelligence_briefs``), behind ``BRIEF_STATUS_V1`` (default OFF).

Thin, pure wiring between three Batch 1 pieces, so neither WP2 nor WP3 has to know about the ORI path:
  * WP3 leaves a record under ``coverage['claim_gate_v1']`` (and ``narrative_available``/``llm_used`` follow its fixed contract);
  * WP2 ``compute_production_status`` turns content + collection into NORMAL / DEGRADED / FAILED;
  * the result is stored under ``coverage['production_status_v1']`` (namespaced, versioned, additive: no existing key is touched).

Status is computed from content and collection ONLY. There is no delivery input anywhere in this module, so publishing, e-mailing or
failing to e-mail a brief can never change it. The deterministic evidence fallback (``narrative_available=False`` together with
``claim_gate_v1.fallback_used``) is DEGRADED, never NORMAL.
"""
from __future__ import annotations

from datetime import datetime, timezone

from intelligence import production_status as ps
from intelligence.claim_gate import ClaimGateResult

KEY = "production_status_v1"
SCHEMA = 1
GATE_KEY = "claim_gate_v1"


def enabled() -> bool:
    return ps.enabled()


def claim_gate_from_record(rec: dict | None) -> ClaimGateResult | None:
    """Rebuild a real ``ClaimGateResult`` from the stored ``coverage['claim_gate_v1']`` record (counts and kinds only: the record holds
    no claim text, so ``failures`` is empty). None when no record exists (gate off). A record that does not say ``passed`` is a
    failed gate (fail closed)."""
    if not isinstance(rec, dict) or not rec:
        return None
    reasons = [str(r) for r in (rec.get("reasons") or [])][:6]
    if rec.get("parse_rejected"):
        reasons.append(f"parse_rejected:{rec['parse_rejected']}")
    return ClaimGateResult(
        passed=rec.get("passed") is True, mode=str(rec.get("mode") or "shadow"),
        claims_total=int(rec.get("claims_total") or 0), claims_supported=int(rec.get("claims_supported") or 0),
        fabricated_citations=int(rec.get("fabricated_citations") or 0), unsupported_causal=int(rec.get("unsupported_causal") or 0),
        reasons=reasons)


def narrative_text_of(executive_snapshot, bottom_line) -> str:
    return "\n".join(str(x).strip() for x in (executive_snapshot, bottom_line) if x and str(x).strip())


def compute(*, executive_snapshot, bottom_line, llm_used: bool, narrative_available: bool, coverage: dict,
            collection_ready: bool, row_stored: bool = True, now: datetime | None = None) -> dict:
    """The ``coverage['production_status_v1']`` record. ``coverage`` is the brief's coverage dict (it may carry ``claim_gate_v1``).
    ``row_stored`` defaults to True because the status is computed before the row is written; a failed save leaves no row to carry it."""
    gate_rec = (coverage or {}).get(GATE_KEY)
    gate = claim_gate_from_record(gate_rec)
    res = ps.compute_production_status(
        narrative_text=narrative_text_of(executive_snapshot, bottom_line) or None, llm_used=bool(llm_used),
        narrative_available=bool(narrative_available), claim_gate=gate, coverage=coverage or {}, row_stored=row_stored,
        collection_ready=bool(collection_ready))
    reasons = list(res.reasons)
    fallback_used = bool(isinstance(gate_rec, dict) and gate_rec.get("fallback_used"))
    if fallback_used and not narrative_available and "evidence_fallback_in_use" not in reasons:
        reasons.append("evidence_fallback_in_use")        # narrative_available=False + fallback_used is DEGRADED, never NORMAL
    status = res.status
    if fallback_used and not narrative_available and status is ps.ProductionStatus.NORMAL:
        status = ps.ProductionStatus.DEGRADED               # defensive: cannot happen with the current rules, pinned by test
    return {
        "schema": SCHEMA, "kind": "production_status", "published": False,
        "computed_at": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "status": status.value, "reasons": reasons,
        "inputs": {"llm_used": bool(llm_used), "narrative_available": bool(narrative_available), "fallback_used": fallback_used,
                   "claim_gate_mode": gate.mode if gate else None, "claim_gate_passed": gate.passed if gate else None,
                   "collection_ready": bool(collection_ready)},
    }


def collection_ready_from(sources_available: int) -> bool:
    """Collection produced something to assess: at least one source completed. Partial or chronic degradation is NOT 'not ready' (it is
    reported by the coverage reasons and yields DEGRADED); zero completed sources is."""
    return bool(sources_available and sources_available > 0)


def attach(coverage: dict, record: dict) -> dict:
    """Add the single ``production_status_v1`` key to a copy of ``coverage`` (every existing key preserved unchanged)."""
    out = dict(coverage or {})
    out[KEY] = record
    return out


def from_row(row: dict) -> dict | None:
    """Read side for the Captain's-brief shadow: the stored record if present, else None (never recomputed here)."""
    cov = (row or {}).get("coverage")
    rec = cov.get(KEY) if isinstance(cov, dict) else None
    return rec if isinstance(rec, dict) else None
