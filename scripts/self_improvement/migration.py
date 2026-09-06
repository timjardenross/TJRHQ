#!/usr/bin/env python3
"""
Migrate legacy self-improvement findings/decisions into the HQ Evolution
opportunity model (spec section 34 / Phase 14).

Scope note: findings_classified.json's finding_id (e.g. "FND-001") is only
unique *within* a single orchestrator run — each daily cycle reassigns
FND-001, FND-002, ... from scratch (see orchestrator.py's Phase 3 comment).
decisions.jsonl has always been read joined against whatever run was
"latest" at request time (dashboard.py's load_findings()/load_decisions()),
so that is the only join the legacy system itself ever guaranteed. This
migration reproduces that exact join — the latest run's findings + the
decisions recorded against it — rather than inventing a cross-run history
the legacy system never had. Opportunities get a
"{run_id}:{finding_id}"-qualified source_finding_id so that a later cycle
reusing the same finding_id numbering never collides with this one.

Idempotent: safe to run repeatedly. Already-migrated findings (matched by
fingerprint, which encodes run_id + finding_id + title) are skipped, not
re-created — "existing approved findings should not be re-requested as new
opportunities."
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from opportunity_store import OpportunityStore, new_fingerprint
from internal_discovery import finding_to_candidate

log = logging.getLogger("migration")

DECISION_TO_STATE = {
    "approved": "approved",
    "rejected": "rejected",
    "more_evidence": "investigating",
}


def _get_latest_run(data_root: Path) -> Optional[Path]:
    runs_dir = data_root / "runs"
    if not runs_dir.exists():
        return None
    run_dirs = sorted((d for d in runs_dir.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime, reverse=True)
    for run_dir in run_dirs:
        if (run_dir / "findings_classified.json").exists():
            return run_dir
    return None


def _load_decisions(data_root: Path) -> dict[str, dict[str, Any]]:
    decisions_file = data_root / "review" / "decisions.jsonl"
    decisions: dict[str, dict[str, Any]] = {}
    if not decisions_file.exists():
        return decisions
    with open(decisions_file) as f:
        for line in f:
            if line.strip():
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fid = d.get("finding_id")
                if fid:
                    decisions[fid] = d  # last write wins, matching decision_processor.py
    return decisions


def _load_remediation_results(data_root: Path) -> dict[str, list[dict[str, Any]]]:
    result_file = data_root / "review" / "remediation_results.jsonl"
    by_fid: dict[str, list[dict[str, Any]]] = {}
    if not result_file.exists():
        return by_fid
    with open(result_file) as f:
        for line in f:
            if line.strip():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fid = r.get("finding_id")
                if fid:
                    by_fid.setdefault(fid, []).append(r)
    return by_fid


def migrate_legacy_findings_to_opportunities(data_root: Path) -> dict[str, Any]:
    """Returns a summary: {run_id, migrated_count, skipped_already_migrated_count, total_findings}."""
    store = OpportunityStore(data_root)
    run_dir = _get_latest_run(data_root)
    if run_dir is None:
        return {"run_id": None, "migrated_count": 0, "skipped_already_migrated_count": 0, "total_findings": 0}

    with open(run_dir / "findings_classified.json") as f:
        findings = json.load(f).get("findings", [])

    decisions = _load_decisions(data_root)
    remediation_by_fid = _load_remediation_results(data_root)
    run_id = run_dir.name

    migrated = 0
    skipped = 0

    for finding in findings:
        fid = finding.get("finding_id")
        if not fid:
            continue
        qualified_id = f"{run_id}:{fid}"
        candidate = finding_to_candidate(finding)
        fingerprint = new_fingerprint(candidate["title"], qualified_id, "internal")

        if store.find_by_fingerprint(fingerprint) is not None:
            skipped += 1
            continue

        decision = decisions.get(fid)
        state = "discovered"
        rejection_reason = None
        watch_reason = None
        outcome: dict[str, Any] = {}

        if decision:
            state = DECISION_TO_STATE.get(decision.get("decision"), "discovered")
            if state == "rejected":
                rejection_reason = decision.get("reasoning") or "Migrated legacy rejection (no structured reason captured at the time)."
            if state == "investigating":
                watch_reason = None

        remediation_records = remediation_by_fid.get(fid, [])
        if remediation_records:
            last = remediation_records[-1]
            outcome = {
                "implementation_success": last.get("success"),
                "improvement_success": None,  # section 28: not measured — say so rather than fabricate
                "improvement_success_note": "Not yet measured — legacy remediation path recorded implementation "
                                             "success/failure only, not whether the intended outcome improved.",
                "remediation_history": [
                    {"timestamp": r.get("timestamp"), "success": r.get("success"), "message": r.get("message")}
                    for r in remediation_records
                ],
            }
            if state == "approved" and last.get("success"):
                state = "learned"

        store.create_new(
            title=candidate["title"],
            change_class=candidate["change_class"],
            discovery_source="internal",
            lifecycle_state=state,
            fingerprint=fingerprint,
            summary=candidate.get("summary", ""),
            why_relevant=candidate.get("why_relevant", ""),
            value=candidate.get("value"),
            cost_impact=candidate.get("cost_impact"),
            complexity=candidate.get("complexity"),
            fit=candidate.get("fit"),
            confidence=candidate.get("confidence", 0.0),
            evidence_strength=candidate.get("evidence_strength", "weak"),
            risk_level=finding.get("risk_level"),
            automation_eligibility=finding.get("automation_eligibility"),
            policy_decision_rationale=finding.get("policy_decision_rationale"),
            provenance=candidate.get("provenance", []),
            source_finding_id=qualified_id,
            rejection_reason=rejection_reason,
            watch_reason=watch_reason,
            outcome=outcome,
            investigation={
                "why_hq_is_looking_at_this": candidate.get("why_relevant", ""),
                "method": "migrated_legacy_finding",
            },
            run_id=f"migration-of-{run_id}",
        )
        migrated += 1

    log.info(f"Migration complete: {migrated} migrated, {skipped} already migrated, {len(findings)} total findings in {run_id}")
    return {
        "run_id": run_id,
        "migrated_count": migrated,
        "skipped_already_migrated_count": skipped,
        "total_findings": len(findings),
    }


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Migrate legacy self-improvement findings/decisions into HQ Evolution opportunities")
    parser.add_argument("--data-root", type=Path, default=Path("/opt/starship-endeavour/data/self-improvement"))
    args = parser.parse_args()

    result = migrate_legacy_findings_to_opportunities(args.data_root)
    print(json.dumps(result, indent=2))
