"""Shadow wiring of the layered executive brief into the morning path (flag ``BRIEF_LAYERED_V1``, default OFF).

Thin adapter, no analysis of its own. It maps data the morning brief already has onto the pure ``layered_render.render_layered`` inputs:

  * incidents   <- ``brief_evidence.IncidentView`` objects (the same evidence set the morning text is built from)
  * PIR tags    <- the REAL WP5 ``requirements.tag_item`` / ``PirTagResult`` (shadow tagging; selection is untouched)
  * status      <- the REAL WP2 ``production_status.compute_production_status`` / ``StatusResult``
  * claim gate  <- the REAL WP3 ``ClaimGateResult``, rebuilt from the latest ORI brief's ``coverage['claim_gate_v1']`` record
  * coverage    <- the latest ORI brief's ``coverage`` record plus the morning collection caveat

The result is a ``shadow_v1`` payload (``published: false``) merged into the jsonb object that is ALREADY being stored
(``captains_daily_briefs.health_snapshot``): exactly one key is added, every existing key is kept, and the delivered text is never
touched. Convention for several shadow producers (documented decision): the layered payload owns ``shadow_v1``; the WP5 PIR payload
nests under ``shadow_v1.companions['pir_tagging']`` (WP5's own ``merge_shadow``), added only when ``PIR_TAGGING_SHADOW_V1`` is on and
only while the whole value stays within the SHADOW_MAX_BYTES bound.

The audio alternative (``BRIEF_LAYERED_V1_AUDIO``, default OFF) reads the stored layered payload back and speaks L1, L2 and L6; it is
only a text source for the existing audio pre-generation and never alters the written brief.

No network, LLM, send or production write happens in this module (reads go through the caller-supplied ``sb_get``).
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from intelligence import coverage_criticality as cc
from intelligence import freshness as fr
from intelligence import production_status as ps
from intelligence import requirements as req
from intelligence.brief import layered_render as lr
from intelligence.brief import ori_status

log = logging.getLogger("layered-shadow")

FLAG = lr.FLAG
AUDIO_FLAG = "BRIEF_LAYERED_V1_AUDIO"
SHADOW_KEY = lr.SHADOW_KEY
PIR_COMPANION = "pir_tagging"
_TRUE = ("1", "true", "yes", "on")
_HEALTHISH = frozenset({"health", "medical", "public_health", "health_signal"})
_STATE = {"ongoing": "ongoing", "partially_restored": "partially restored", "restored": "restored", "unknown": "current status unknown"}
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


def enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in _TRUE


def audio_enabled() -> bool:
    return os.getenv(AUDIO_FLAG, "").strip().lower() in _TRUE


# --------------------------------------------------------------------------------------------------------------------------------
# input mapping
# --------------------------------------------------------------------------------------------------------------------------------
def _g(o: Any, k: str, d=None):
    return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)


def _clean(s: Any, n: int) -> str:
    return _CTRL.sub("", str(s or "")).strip()[:n]


def _iso(t) -> str | None:
    return t.isoformat() if isinstance(t, datetime) else (str(t) if t else None)


CLASSIFIER_COLUMNS = "event_id,event_type,risk_rating,customer_impact,disposition,operational_relevance,geography,sector"
_RISK_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
_IMPACT_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_DISP_ORDER = {"ESCALATE": 5, "BRIEF": 4, "WATCH": 3, "REFERENCE": 2, "SUPPRESS": 1}
_CLASSIFIER_CHUNK = 80


def scope_of(reports: list[dict], fallback_geography: str = "") -> str:
    """domestic when any report is AU-tagged; international when reports carry only non-AU geography; unknown when none do.
    ``fallback_geography`` (the stored classifier value) is used only when no report carries a geography."""
    geos = {str(r.get("geography") or "").strip().upper() for r in reports} - {""}
    if not geos and fallback_geography:
        geos = {str(fallback_geography).strip().upper()}
    if "AU" in geos:
        return "domestic"
    return "international" if geos else "unknown"


def load_classifier_fields(sb_get, event_ids: list[str]) -> dict[str, dict]:
    """Stored classifier columns (SELECT only, through the caller's getter) for the given event ids, keyed by event_id. Fails soft
    ({}): without them the adapter reports relevance as not assessed rather than guessing."""
    out: dict[str, dict] = {}
    ids = sorted({str(e) for e in event_ids if e})
    for k in range(0, len(ids), _CLASSIFIER_CHUNK):
        chunk = ids[k:k + _CLASSIFIER_CHUNK]
        try:
            rows = sb_get("intelligence_events", f"event_id=in.({','.join(chunk)})&select={CLASSIFIER_COLUMNS}")
        except Exception as exc:  # noqa: BLE001 - classifier fields are an enrichment
            log.warning("[layered-shadow] classifier fields unavailable: %s", exc)
            return out
        for r in rows or []:
            out[str(r.get("event_id"))] = r
    return out


def incident_classifier(view: Any, fields_by_event: dict[str, dict] | None) -> dict:
    """Incident-level classifier fields from the STORED event rows of its reports (strongest value wins), in the vocabulary the PIR
    config was built on (``event_type`` here is the stored column, e.g. telecom_outage, not the evidence layer's type). {} when none."""
    rows = [fields_by_event[str(r.get("report_id"))] for r in (_g(view, "reports", []) or []) if fields_by_event and str(r.get("report_id")) in fields_by_event]
    if not rows:
        return {}
    types = [str(r.get("event_type") or "") for r in rows if r.get("event_type") and r.get("event_type") != "other"]
    risks = [str(r.get("risk_rating") or "").upper() for r in rows if r.get("risk_rating")]
    impacts = [str(r.get("customer_impact") or "").lower() for r in rows if r.get("customer_impact")]
    disps = [str(r.get("disposition") or "").upper() for r in rows if r.get("disposition")]
    rel = []
    for r in rows:
        try:
            rel.append(float(r.get("operational_relevance")))
        except (TypeError, ValueError):
            pass
    out = {"event_type": max(set(types), key=types.count) if types else ("other" if any(r.get("event_type") for r in rows) else ""),
           "risk_rating": max(risks, key=lambda x: _RISK_ORDER.get(x, 0)) if risks else "",
           "customer_impact": max(impacts, key=lambda x: _IMPACT_ORDER.get(x, 0)) if impacts else "",
           "disposition": max(disps, key=lambda x: _DISP_ORDER.get(x, 0)) if disps else "",
           "geography": next((str(r["geography"]) for r in rows if r.get("geography")), ""),
           "sector": next((str(r["sector"]) for r in rows if r.get("sector")), "")}
    if rel:
        out["operational_relevance"] = max(rel)
    return out


def pir_item(view: Any, cls: dict | None = None) -> dict:
    """The item handed to WP5 ``tag_item``: public headline/report text plus the STORED classifier fields (event_type in the stored
    vocabulary, risk_rating, customer_impact, disposition, operational_relevance, geography, sector) when the caller supplied them,
    and the evidence layer's operational ``materiality``. Nothing is synthesised: absent fields stay absent. A high-materiality
    incident with no STRONG requirement match lands in the uncapped unmatched high-severity lane."""
    reports = list(_g(view, "reports", []) or [])
    originals = [r for r in reports if r.get("role") == "original"] or reports
    titles = " . ".join([_clean(_g(view, "headline", ""), 300)] + [_clean(r.get("title"), 200) for r in originals[:4]])
    item = {"id": _g(view, "incident_id"), "title": titles, "summary": _clean(originals[0].get("summary") if originals else "", 600),
            "materiality": str(_g(view, "materiality", "") or "")}
    cls = cls or {}
    for k in ("event_type", "risk_rating", "customer_impact", "disposition", "operational_relevance", "geography", "sector"):
        if cls.get(k) not in (None, ""):
            item[k] = cls[k]
    return item


def derive_relevance(pir, cls: dict, *, priority: str, materiality: str) -> tuple[str | None, str]:
    """(relevance, basis) for the renderer from PIR strength and stored classifier fields. 'low' only when DEMONSTRATED by classifier
    fields (LOW risk, low customer impact, REFERENCE/WATCH/SUPPRESS disposition, low operational relevance) with no requirement matched
    and nothing urgent. None (renderer: not assessed) when relevance cannot be established. Never inferred from silence."""
    strong = pir.strong_matches
    if any(m.priority == "A" for m in strong):
        return "high", f"requirement {strong[0].pir_id} ({strong[0].basis})"
    if strong:
        return "medium", f"requirement {strong[0].pir_id} ({strong[0].basis})"
    if pir.matches:
        return "medium", f"weak requirement match {pir.matches[0].pir_id} ({pir.matches[0].basis}); stored type only"
    if pir.unmatched_high_severity:
        return "medium", "watch lane (review): high severity on stored classifier or operational materiality; no standing requirement matched"
    if pir.emerging:
        return "medium", "emerging-risk language"
    if priority in ("ESCALATE", "VERIFY") or materiality in ("high", "medium"):
        return "medium", f"priority {priority}, materiality {materiality}"
    if not cls:
        return None, ""
    risk, impact, disp = str(cls.get("risk_rating") or "").upper(), str(cls.get("customer_impact") or "").lower(), str(cls.get("disposition") or "").upper()
    try:
        opr = float(cls.get("operational_relevance"))
    except (TypeError, ValueError):
        opr = None
    if risk in ("MEDIUM", "HIGH", "CRITICAL") or impact in ("medium", "high", "critical") or disp in ("BRIEF", "ESCALATE") or (opr is not None and opr >= 0.4):
        return "medium", f"stored classifier: risk {risk or 'n/a'}, impact {impact or 'n/a'}, disposition {disp or 'n/a'}"
    if risk == "LOW" and impact in ("low", "") and disp in ("REFERENCE", "WATCH", "SUPPRESS") and (opr is None or opr < 0.4):
        return "low", f"stored classifier: risk LOW, impact {impact or 'n/a'}, disposition {disp}; no requirement matched"
    return None, ""


def incident_input(view: Any, pirs: list[dict], fields_by_event: dict[str, dict] | None = None, *, outside_window: bool = False) -> dict:
    """One ``LayeredIncident`` input dict from an ``IncidentView`` (or an equivalent dict). Never raises on missing optional fields."""
    reports = list(_g(view, "reports", []) or [])
    record = _g(view, "record", {}) or {}
    originals = [r for r in reports if r.get("role") == "original"] or reports
    etype = str(_g(view, "event_type", "") or "")
    cls = incident_classifier(view, fields_by_event)
    pir = req.tag_item(pir_item(view, cls), pirs)
    priority, materiality = _g(view, "priority", "WATCH"), _g(view, "materiality", "low")
    relevance, basis = derive_relevance(pir, cls, priority=priority, materiality=materiality)
    return {
        "incident_id": _g(view, "incident_id"), "headline": _clean(_g(view, "headline", ""), 300),
        "priority": priority, "materiality": materiality,
        "scope": scope_of(reports, cls.get("geography", "")), "event_type": etype,
        "relevance": relevance or "unassessed", "relevance_basis": basis, "outside_window": outside_window,
        "impact_status": _g(view, "impact_status", "unconfirmed"), "evidence_status": _g(view, "evidence_status", "reported"),
        "independent_publishers": int(_g(view, "independent_publishers", 1) or 1), "provisional": bool(_g(view, "provisional", True)),
        "state": _STATE.get(record.get("restoration_status"), ""), "n_reports": len(reports) or 1,
        "sectors": [str(s) for s in (record.get("critical_service_dependencies") or [])],
        "summary": _clean(originals[0].get("summary") if originals else "", 280),
        "next_step": _clean(record.get("next_verification_action"), 300),
        "domain": "health" if etype.lower() in _HEALTHISH or str(cls.get("event_type") or "").lower() in _HEALTHISH else "",
        "pir": pir,
        "last_seen": _iso(_g(view, "last_seen")),
        "severity": "high" if (str(cls.get("risk_rating") or "").upper() in ("HIGH", "CRITICAL") and str(cls.get("customer_impact") or "").lower() in ("high", "critical")) else "",
        "reports": [{"report_id": str(r.get("report_id", ""))[:8], "publisher": _clean(r.get("source_name") or r.get("publisher"), 80),
                     "role": r.get("role"), "url": _clean(r.get("url"), 200) or None} for r in reports[:6]],
    }


def ori_guard(ori_brief: dict | None, now: datetime | None = None) -> dict | None:
    """Staleness guard for the canonical ORI brief, applied INSIDE the layered adapter whatever other flags are set (it no longer depends on
    BRIEF_STATUS_V1). A missing row is passed through (coverage then reads DEGRADED 'no coverage record'); a row older than the usable-age
    limit, or with no usable timestamp, keeps its content but its coverage is marked degraded with the reason, and ``events_evaluated`` is
    dropped (it describes an earlier run). Idempotent with the status-flag path in captains_brief."""
    if not ori_brief:
        return ori_brief
    if (ori_brief.get("coverage") or {}).get("stale_canonical_brief"):
        return ori_brief
    if not ps.ori_brief_stale(ori_brief, now):
        return ori_brief
    age = ps.ori_brief_age_hours(ori_brief, now)
    cov = dict(ori_brief.get("coverage") or {}) if isinstance(ori_brief.get("coverage"), dict) else {}
    cov["degraded"] = True
    cov["reason"] = "canonical brief is " + (f"{age:.0f} h old" if age is not None else "of unknown age") + "; it does not describe this morning"
    cov["stale_canonical_brief"] = True
    cov["collection_status"] = cov.get("collection_status") or "stale"
    out = {**ori_brief, "coverage": cov}
    out.pop("events_evaluated", None)
    return out


def load_source_state(sb_get) -> tuple[list[dict] | None, dict | None]:
    """(registry rows, {source_name: latest health status}) by SELECT through the caller's getter. (None, None) when unavailable: the
    criticality producer then relies on the coverage record alone and states that the registry was not checked."""
    try:
        reg = sb_get("intelligence_source_registry", "select=source_id,source_name,category,active")
        hl = sb_get("intelligence_source_health_latest", "select=source_id,status")
    except Exception as exc:  # noqa: BLE001 - enrichment
        log.warning("[layered-shadow] source state unavailable: %s", exc)
        return None, None
    if not isinstance(reg, list) or not reg:
        return None, None
    by_id = {str(r.get("source_id")): r.get("source_name") for r in reg}
    health = {by_id[str(h.get("source_id"))]: h.get("status") for h in (hl or []) if str(h.get("source_id")) in by_id and h.get("status")}
    return reg, health or None


def morning_status(*, text: str, ori_brief: dict | None, collection_caveat: str | None) -> ps.StatusResult:
    """WP2 status for the shadow. Same content+collection inputs as the Captain's-brief status hook, plus the ORI evidence layer's
    claim-gate record and coverage (so a failed gate or degraded coverage upstream is visible). No delivery input."""
    cov = dict((ori_brief or {}).get("coverage") or {}) if isinstance((ori_brief or {}).get("coverage"), dict) else {}
    if collection_caveat:
        cov["degraded"] = True
    gate = ori_status.claim_gate_from_record(cov.get(ori_status.GATE_KEY))
    return ps.compute_production_status(
        narrative_text=text, llm_used=True, narrative_available=bool(text and text.strip()), claim_gate=gate, coverage=cov,
        row_stored=True, collection_ready=not collection_caveat)


def build_from_evidence(ev: Any, *, text: str, ori_brief: dict | None = None, collection_caveat: str | None = None, pirs: list[dict] | None = None,
                        now: datetime | None = None, fields_by_event: dict[str, dict] | None = None,
                        registry: list[dict] | None = None, source_health: dict | None = None,
                        criticality_enabled: bool | None = None) -> tuple[dict, list[dict], dict]:
    """Pure core. ``ev`` is a ``brief_evidence.EvidenceSet``; ``fields_by_event`` the stored classifier rows (``load_classifier_fields``).
    Returns (layered_result, pir_items, meta). Every incident of the evidence set is accounted for: rendered (in window, or older than the
    window and then counted with its title / one line when material), or excluded as health-domain (counted in meta, never listed)."""
    pirs = pirs if pirs is not None else req.load_pirs()
    now = now or getattr(ev, "generated_at", None) or datetime.now(timezone.utc)
    ori_brief = ori_guard(ori_brief, now)
    cutoff = now - fr.brief_window()
    def in_window(i) -> bool:
        return bool(_g(i, "last_seen") and _g(i, "last_seen") >= cutoff)
    all_inc = list(ev.incidents)
    inputs_all = [incident_input(i, pirs, fields_by_event, outside_window=not in_window(i)) for i in all_inc]
    inputs = [i for i in inputs_all if i["domain"].lower() not in lr.SHADOW_BLOCKED_DOMAINS]     # no health/personal content in a shadow payload
    cov = dict((ori_brief or {}).get("coverage") or {}) if isinstance((ori_brief or {}).get("coverage"), dict) else {}
    if collection_caveat and cov:
        cov["degraded"] = True
    ori_eval = (ori_brief or {}).get("events_evaluated")
    ori_eval = ori_eval if isinstance(ori_eval, int) and not isinstance(ori_eval, bool) else None
    status = morning_status(text=text, ori_brief=ori_brief, collection_caveat=collection_caveat)
    crit = None
    if (cc.enabled() if criticality_enabled is None else criticality_enabled):
        crit = cc.evaluate(cov, registry=registry, health=source_health)
    gate = ori_status.claim_gate_from_record(cov.get(ori_status.GATE_KEY))
    result = lr.render_layered(
        inputs, posture=None, coverage=cov, confidence=None, judgements=None, outlook=None,
        limits=[collection_caveat] if collection_caveat else None, evidence_refs=None,
        production_status={"status": status.status.value, "reasons": list(status.reasons)}, claim_gate=gate, n_events=getattr(ev, "n_events", None),
        events_evaluated=ori_eval, criticality=crit)
    # real reconciliation: the evidence-set incident ids (minus health-domain exclusions) against what the RENDERED layers contain
    blocked = {i["incident_id"] for i in inputs_all if i["domain"].lower() in lr.SHADOW_BLOCKED_DOMAINS}
    recon = lr.reconcile([_g(i, "incident_id") for i in all_inc if _g(i, "incident_id") not in blocked], result)
    older = sum(1 for i in inputs if i["outside_window"])
    excluded = len(inputs_all) - len(inputs)
    meta = {"incidents_total": len(all_inc), "incidents_in_window": len(inputs) - older, "incidents_older_than_window": older,
            "incidents_rendered": len(inputs), "excluded_health_domain": excluded,
            "reconciliation": recon,
            "unaccounted": len(recon["missing_from_l3"]) + (len(all_inc) - len(inputs) - excluded),
            "criticality": ({k: crit[k] for k in ("critical_sources_failed", "critical_missing", "registry_checked", "failed_names_complete")} | {"pir_coverage_gaps": len(crit["pir_coverage_gaps"]), "authoritative_unavailable": len(crit["authoritative_unavailable"]), "posture_unknown_reasons": crit["posture_unknown_reasons"]}) if crit else None,
            "classifier_fields_for": sum(1 for i in all_inc if incident_classifier(i, fields_by_event)), "events": getattr(ev, "n_events", None),
            "events_evaluated_ori": ori_eval,
            "status_basis": "wp2 compute_production_status over the morning text, ORI claim_gate_v1 record and ORI coverage",
            "ori_brief_present": bool(ori_brief), "claim_gate_recorded": gate is not None}
    kept = {i["incident_id"] for i in inputs}
    return result, [pir_item(i, incident_classifier(i, fields_by_event)) for i in all_inc if _g(i, "incident_id") in kept], meta


def _size(o: Any) -> int:
    return len(json.dumps(o, default=str).encode())


def _with_companion(merged: dict, companion: dict) -> dict:
    """Add the PIR payload to ``merged`` without ever overwriting another producer's ``shadow_v1``: under ``companions`` of a layered
    top-level value; when the top level is itself a PIR payload, that payload is replaced by the new one (same producer) and any
    companions it carried are kept."""
    cur = merged.get(SHADOW_KEY)
    if isinstance(cur, dict) and cur.get("kind") == companion.get("kind") and cur.get("companions"):
        companion = dict(companion, companions=cur["companions"])
    return req.merge_shadow(merged, companion)


def attach_shadow(existing: dict | None, layered_result: dict, *, pir_items: list[dict] | None = None, meta: dict | None = None,
                  pirs: list[dict] | None = None, now: datetime | None = None, env: dict | None = None) -> dict:
    """Return a copy of ``existing`` with ONLY ``shadow_v1`` added (layered payload; PIR payload under ``companions`` when its flag is on
    and the whole value fits SHADOW_MAX_BYTES). No other key is touched; ``existing`` is not mutated."""
    in_ids = [e["incident_id"] for e in layered_result.get("L7", [])]       # the render input set
    smeta = None
    if meta:
        smeta = {k: v for k, v in meta.items() if k not in ("reconciliation", "status_basis")}
        smeta["reconciliation_rendered"] = {k: v for k, v in (meta.get("reconciliation") or {}).items() if k not in ("extra_not_in_input",)}
    payload = lr.build_shadow_payload(layered_result, generated_at=now, meta=smeta)       # health-domain incidents were excluded at input time
    if meta:       # checked against the STORED (possibly compact) layers, after compaction
        payload["meta"]["reconciliation_stored"] = {k: v for k, v in lr.reconcile(in_ids, payload["layers"]).items() if k != "extra_not_in_input"}
        if lr._size(payload) > lr.SHADOW_MAX_BYTES:
            raise ValueError("shadow_v1 exceeds the size bound")
    merged = lr.merge_shadow(existing, payload)
    if pir_items is not None and req.shadow_enabled(env):
        try:
            companion = req.build_shadow_payload(pir_items, pirs, now=now)
            candidate = _with_companion(merged, companion)
            if _size(candidate[SHADOW_KEY]) <= lr.SHADOW_MAX_BYTES:
                merged = candidate
            else:
                merged[SHADOW_KEY]["companions_skipped"] = "size"
        except Exception as exc:  # noqa: BLE001 - shadow companion is optional
            log.warning("[layered-shadow] PIR companion skipped: %s", exc)
    if _size(merged[SHADOW_KEY]) > lr.SHADOW_MAX_BYTES:
        raise ValueError("shadow_v1 exceeds the size bound")
    return merged


def attach_to_health(health: dict | None, *, text: str, collection_caveat: str | None, sb_get, ori_brief: dict | None = None,
                     now: datetime | None = None) -> dict | None:
    """Morning-path entry point (the caller checks ``enabled()`` first). Loads the same 72 h evidence the morning text used (reads only),
    builds the layered shadow and returns ``health`` with ``shadow_v1`` added. Any failure returns ``health`` unchanged."""
    try:
        from intelligence import brief_evidence as be
        events = be.load_events(sb_get, hours=72)
        ev = be.build_evidence(events, window_hours=72) if events else be.EvidenceSet(be.ed.METHOD_VERSION, now or datetime.now(timezone.utc), 72, 0, [])
        fields = load_classifier_fields(sb_get, [r.get("report_id") for i in ev.incidents for r in (_g(i, "reports", []) or [])])
        reg, hl = load_source_state(sb_get) if cc.enabled() else (None, None)
        result, pir_items, meta = build_from_evidence(ev, text=text, ori_brief=ori_brief, collection_caveat=collection_caveat, now=now, fields_by_event=fields,
                                                      registry=reg, source_health=hl)
        return attach_shadow(health, result, pir_items=pir_items, meta=meta, now=now)
    except Exception as exc:  # noqa: BLE001 - shadow only; the brief is stored and sent exactly as without it
        log.warning("[layered-shadow] not attached: %s", exc)
        return health


# --------------------------------------------------------------------------------------------------------------------------------
# audio alternative text source (BRIEF_LAYERED_V1_AUDIO)
# --------------------------------------------------------------------------------------------------------------------------------
def audio_text_from_row(row: dict, *, minutes: float = lr.AUDIO_DEFAULT_MINUTES) -> str | None:
    """Spoken script from the layered payload stored on a ``captains_daily_briefs`` row, or None (caller keeps its legacy text).
    Never raises."""
    try:
        snap = (row or {}).get("health_snapshot")
        sh = snap.get(SHADOW_KEY) if isinstance(snap, dict) else None
        if not isinstance(sh, dict) or sh.get("kind") != "layered_brief" or sh.get("published") is not False:
            return None
        layers = sh.get("layers") or {}
        if "L1" not in layers or "L6" not in layers:
            return None
        script = lr.audio_script(layers, minutes=minutes)["script"]
        return script if script.strip() else None
    except Exception as exc:  # noqa: BLE001 - audio source is optional
        log.warning("[layered-shadow] audio text unavailable: %s", exc)
        return None
