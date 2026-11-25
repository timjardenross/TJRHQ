"""Coverage criticality producer (shadow only; flag ``COVERAGE_CRITICALITY_SHADOW_V1``, default OFF).

Ownership: the Product Development Board owns INTELLIGENCE criticality: which sources a Priority Intelligence Requirement (PIR) needs in
order to be assessed, whether the healthy sources still suffice, and what the analytical consequence of missing evidence is. Production
Operations owns technical source-health monitoring and alerting; this module CONSUMES their health signal (the coverage record, the
registry, the latest source health) and never replaces or re-implements it.

Criticality derives ONLY from PIR service (``config/intelligence_requirements.json`` -> ``pirs[].service`` and ``service_policy``). It is
never derived from whether any organisation uses a vendor or technology.

Pure and deterministic: no I/O, no LLM, no network. Output keys (all JSON-safe):

  critical_sources_failed   names of sources in a PIR ``critical`` list that failed this run
  critical_missing          critical sources that are not collected at all (absent or inactive in the registry)
  pir_coverage_gaps         PIRs whose healthy serving sources are fewer than ``min_healthy`` (sufficiency)
  authoritative_unavailable PIR roles (authoritative evidence) with no healthy source
  declared_gaps             standing known absences of any serving source (reported, never a trigger)
  posture_unknown_reasons   the subset of the above that, for the configured priorities, makes the posture NOT ASSESSED
  limits                    human-readable limits for L6, each with the analytical consequence
  sufficiency               per-PIR reasoning (healthy/required, failed, missing)
"""
from __future__ import annotations

import os

from intelligence import requirements as req

FLAG = "COVERAGE_CRITICALITY_SHADOW_V1"
_TRUE = ("1", "true", "yes", "on")


def enabled(env: dict | None = None) -> bool:
    return str((env if env is not None else os.environ).get(FLAG, "")).strip().lower() in _TRUE


def _policy(cfg: dict) -> dict:
    return cfg.get("service_policy") or {}


def source_states(names, coverage: dict | None, *, cfg: dict, registry: list[dict] | None, health: dict | None) -> dict[str, str]:
    """{name: 'healthy' | 'failed' | 'missing'} for every name. failed = named in the run's missing_sources, an unavailable external
    domain, or a health status outside ``healthy_statuses``; missing = not collected at all (registry absent/inactive; only when a registry
    was supplied). Without a registry or health map nothing is assumed beyond the coverage record."""
    cov = coverage or {}
    pol = _policy(cfg)
    ok = {str(s).lower() for s in pol.get("healthy_statuses", ["ok", "degraded"])}
    missing_run = {str(s) for s in cov.get("missing_sources") or []}
    domains = cov.get("domains") or {}
    ext = pol.get("external_domains") or {}
    reg = {str(r.get("source_name")): r for r in (registry or [])}
    out: dict[str, str] = {}
    for n in names:
        if n in ext:
            d = domains.get(ext[n])
            out[n] = "failed" if (n in missing_run or (isinstance(d, dict) and (d.get("available") is False or d.get("error")))) else "healthy"
            continue
        if registry is not None and (n not in reg or reg[n].get("active") is False):
            out[n] = "missing"
        elif n in missing_run or health and n in health and str(health[n]).lower() not in ok:
            out[n] = "failed"
        else:
            out[n] = "healthy"
    return out


def _all_names(pirs: list[dict]) -> list[str]:
    seen: list[str] = []
    for p in pirs:
        s = p.get("service") or {}
        for r in s.get("roles") or []:
            seen += list(r.get("any_of") or [])
        seen += list(s.get("supporting") or [])
        seen += list(s.get("critical") or [])
    return sorted(set(seen))


def evaluate(coverage: dict | None, *, config: dict | None = None, registry: list[dict] | None = None, health: dict | None = None) -> dict:
    cfg = config if config is not None else req._default_cfg()
    pirs = cfg["pirs"]
    pol = _policy(cfg)
    prios = set(pol.get("posture_priorities") or ["A"])
    cov = coverage or {}
    states = source_states(_all_names(pirs), cov, cfg=cfg, registry=registry, health=health)
    named = len(cov.get("missing_sources") or [])
    failed_total = cov.get("failed")
    complete = not (isinstance(failed_total, int) and failed_total > named and not health)
    crit_failed, crit_missing = set(), set()
    gaps, auth, declared, suff, limits, unknown = [], [], [], [], [], []
    for p in pirs:
        s = p.get("service") or {}
        pid, prio = p["id"], p["priority"]
        purpose = str(p.get("decision_purpose") or p.get("question") or "")[:140]
        if s.get("declared_gap"):
            declared.append({"pir": pid, "priority": prio, "gap": s["declared_gap"]})
        crit = list(s.get("critical") or [])
        for n in crit:
            if states.get(n) == "failed":
                crit_failed.add(n)
            elif states.get(n) == "missing":
                crit_missing.add(n)
        role_names = {n for r in s.get("roles") or [] for n in r.get("any_of") or []}
        serving = sorted(role_names | set(s.get("supporting") or []))
        healthy = [n for n in serving if states.get(n) == "healthy"]
        bad = [n for n in serving if states.get(n) != "healthy"]
        need = int(s.get("min_healthy") or 0)
        entry = {"pir": pid, "priority": prio, "healthy": len(healthy), "required": need, "serving": len(serving),
                 "unhealthy": bad, "sufficient": len(healthy) >= need}
        suff.append(entry)
        if serving and len(healthy) < need:
            g = {"pir": pid, "priority": prio, "healthy": len(healthy), "required": need, "unhealthy": bad,
                 "consequence": f"{pid} is under-served ({len(healthy)} healthy of {need} needed): {purpose}"}
            gaps.append(g)
            limits.append(g["consequence"])
            if prio in prios:
                unknown.append(f"PIR {pid} coverage gap: {len(healthy)} healthy serving source(s), {need} needed")
        for r in s.get("roles") or []:
            any_of = list(r.get("any_of") or [])
            if any_of and not any(states.get(n) == "healthy" for n in any_of):
                a = {"pir": pid, "priority": prio, "role": r.get("role"), "sources": any_of,
                     "consequence": f"no authoritative evidence for {pid} ({r.get('role')}): {purpose}"}
                auth.append(a)
                limits.append(a["consequence"])
                if prio in prios:
                    unknown.append(f"authoritative evidence unavailable for {pid}: {r.get('role')}")
    if crit_failed:
        limits.append("critical source(s) failed: " + ", ".join(sorted(crit_failed)))
    if crit_missing:
        limits.append("critical source(s) not collected: " + ", ".join(sorted(crit_missing)))
    if crit_failed:
        unknown.append("critical source(s) failed: " + ", ".join(sorted(crit_failed)))
    if crit_missing:
        unknown.append("critical source(s) not collected: " + ", ".join(sorted(crit_missing)))
    if not complete:
        msg = f"{failed_total} source(s) failed but only {named} named: the loss of a critical source cannot be excluded"
        limits.append(msg)
        unknown.append(msg)
    return {"schema": 1, "published": False, "kind": "coverage_criticality", "owner": pol.get("owner", "PDB"),
            "registry_checked": registry is not None, "health_checked": bool(health), "failed_names_complete": complete,
            "critical_sources_failed": sorted(crit_failed), "critical_missing": sorted(crit_missing),
            "pir_coverage_gaps": gaps, "authoritative_unavailable": auth, "declared_gaps": declared,
            "posture_unknown_reasons": unknown, "limits": limits, "sufficiency": suff}
