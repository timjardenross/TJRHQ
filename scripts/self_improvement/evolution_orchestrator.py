#!/usr/bin/env python3
"""
HQ Evolution overnight cycle (spec sections 13-14, 42, 50 Phase 7).

    OBSERVE -> DISCOVER (internal + external) -> RELEVANCE GATE -> DEDUP
    -> SHORTLIST -> INVESTIGATE -> PREPARE

This is a separate entry point from orchestrator.py (the existing daily
self-improvement cycle) and never calls its AutoRemediationExecutor or
git_commit path — HQ Evolution's overnight authority ends at investigation
and proposal (section 14). It reuses, unmodified:

- EvidenceCollector (observation)
- PolicyEngine (the sole authority on automation_eligibility/risk_level)
- ModelRouterClient (LLM assistance only, opinion not permission)

and reads (never writes) the existing findings/run artifacts so internal
discovery can fold in what the model-analysis pipeline already found,
without re-running it.
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from collector import EvidenceCollector
from router_client import ModelRouterClient
from policy import PolicyEngine
from opportunity_store import OpportunityStore, new_fingerprint, MISSION_ONLY_CLASSES
from relevance import RelevanceGate
import internal_discovery
import external_discovery

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core" / "platform"))
from heartbeat import record_heartbeat  # noqa: E402

log = logging.getLogger("evolution_orchestrator")
_HEARTBEAT_DOMAIN = "hq_evolution_cycle"


class EvolutionOrchestrator:
    def __init__(self, repo_root: Path, data_root: Path, router_url: str = "http://127.0.0.1:8891"):
        self.repo_root = repo_root
        self.data_root = data_root
        self.collector = EvidenceCollector(repo_root)
        self.router = ModelRouterClient(router_url)
        self.policy = PolicyEngine(repo_root / "config" / "self_improvement_policy.json")
        self.evolution_config: dict[str, Any] = self.policy.config.get("evolution", {})
        self.store = OpportunityStore(data_root)
        self.gate = RelevanceGate(self.evolution_config, self.store)
        self.watchlist_path = repo_root / "config" / "evolution_watchlist.json"

    def _load_watchlist(self) -> list[dict[str, Any]]:
        if not self.watchlist_path.exists():
            log.warning(f"No watchlist at {self.watchlist_path} — external discovery skipped this cycle")
            return []
        try:
            with open(self.watchlist_path) as f:
                return json.load(f).get("topics", [])
        except Exception as exc:
            log.error(f"Failed to load watchlist: {exc}")
            return []

    def _load_latest_classified_findings(self) -> list[dict[str, Any]]:
        """Reuse the existing daily cycle's most recent classified findings,
        if any exist — never re-runs model analysis itself. Same mtime-sort
        fix as auto_remediation.py's load_latest_findings()."""
        runs_dir = self.data_root / "runs"
        if not runs_dir.exists():
            return []
        run_dirs = sorted(
            (d for d in runs_dir.iterdir() if d.is_dir()),
            key=lambda d: d.stat().st_mtime, reverse=True,
        )
        for run_dir in run_dirs:
            findings_file = run_dir / "findings_classified.json"
            if findings_file.exists():
                try:
                    with open(findings_file) as f:
                        return json.load(f).get("findings", [])
                except Exception as exc:
                    log.warning(f"Failed to read {findings_file}: {exc}")
                    continue
        return []

    def _investigate(self, candidate: dict[str, Any], router_reachable: bool) -> dict[str, Any]:
        """Section 22/45: the model may interpret evidence already in
        `candidate`; it may not invent evidence, and its recommendation is
        advisory only — it never sets lifecycle_state or automation
        authority (relevance.py's deterministic score and PolicyEngine do
        that)."""
        if router_reachable:
            try:
                result = self.router.investigate_opportunity(candidate)
                if result.get("success") and result.get("investigation"):
                    inv = result["investigation"]
                    inv["method"] = "model_synthesis"
                    return inv
            except Exception as exc:
                log.warning(f"Model investigation failed, falling back to template: {exc}")

        return {
            "why_hq_is_looking_at_this": candidate.get("why_relevant", ""),
            "fit_with_hq": candidate.get("fit", "moderate"),
            "potential_benefits": [candidate["summary"]] if candidate.get("summary") else [],
            "cost_impact": candidate.get("cost_impact", "unknown"),
            "risks": ["Model synthesis unavailable this cycle — template-based investigation only, needs human review."],
            "implementation_effort": candidate.get("complexity", "moderate"),
            "alternatives": [],
            "confidence": candidate.get("confidence", 0.0),
            "recommendation": "keep_watching",
            "recommendation_rationale": "Model Router unreachable or synthesis failed; deterministic placeholder pending re-investigation.",
            "method": "template_fallback",
        }

    def run_cycle(self, dry_run: bool = False) -> dict[str, Any]:
        t0 = time.monotonic()
        run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
        budget_s = self.evolution_config.get("run_duration_budget_minutes", 20) * 60

        log.info("=" * 80)
        log.info("HQ EVOLUTION CYCLE START (OBSERVE / DISCOVER)")
        log.info("=" * 80)

        evidence = self.collector.collect_all()
        classified_findings = self._load_latest_classified_findings()

        max_internal = self.evolution_config.get("max_internal_candidates_per_cycle", 20)
        internal_candidates = internal_discovery.discover(classified_findings, evidence, max_internal)

        external_candidates: list[dict[str, Any]] = []
        if not dry_run:
            watchlist = self._load_watchlist()
            if watchlist:
                external_candidates = external_discovery.discover(watchlist, self.evolution_config)

        all_candidates = internal_candidates + external_candidates
        for c in all_candidates:
            c["fingerprint"] = new_fingerprint(c["title"], c.get("source", ""), c["discovery_source"])

        log.info(f"Discovered {len(internal_candidates)} internal + {len(external_candidates)} external "
                 f"= {len(all_candidates)} candidates")

        # RELEVANCE GATE + DEDUP
        log.info("\nRELEVANCE GATE / DEDUP")
        evaluated = [(c, self.gate.evaluate(c)) for c in all_candidates]
        duplicates = [(c, v) for c, v in evaluated if v.is_duplicate]
        passed = [(c, v) for c, v in evaluated if v.passes_investigate and not v.is_duplicate]
        log.info(f"{len(duplicates)} duplicate/already-considered, {len(passed)} clear the relevance gate")

        # Persist every gate-cleared candidate as a lightweight DISCOVERED
        # record (so future cycles can dedup against it) before spending
        # any investigation budget.
        discovered_opps = []
        for candidate, verdict in passed:
            opp = self.store.create_new(
                title=candidate["title"],
                change_class=candidate["change_class"],
                discovery_source=candidate["discovery_source"],
                lifecycle_state="discovered",
                fingerprint=candidate["fingerprint"],
                summary=candidate.get("summary", ""),
                why_relevant=candidate.get("why_relevant", ""),
                value=candidate.get("value"),
                cost_impact=candidate.get("cost_impact"),
                complexity=candidate.get("complexity"),
                fit=candidate.get("fit"),
                relevance_score=verdict.score,
                confidence=candidate.get("confidence", 0.0),
                evidence_strength=candidate.get("evidence_strength", "weak"),
                provenance=candidate.get("provenance", []),
                source_finding_id=candidate.get("source_finding_id"),
                run_id=run_id,
            ) if not dry_run else None
            discovered_opps.append((candidate, verdict, opp))

        # SHORTLIST -> INVESTIGATE (the expensive step; bounded)
        log.info("\nSHORTLIST / INVESTIGATE")
        max_shortlist = self.evolution_config.get("max_shortlist_per_cycle", 6)
        max_investigations = self.evolution_config.get("max_investigations_per_cycle", 6)
        shortlisted = sorted(discovered_opps, key=lambda t: t[1].score, reverse=True)[:max_shortlist]
        to_investigate = shortlisted[:max_investigations]

        router_reachable = False if dry_run else self.router.health_check()
        min_surface = self.evolution_config.get("min_relevance_score_to_surface", 0.65)
        max_surfaced = self.evolution_config.get("max_opportunities_surfaced_per_cycle", 3)

        investigated: list[dict[str, Any]] = []
        for candidate, verdict, opp in to_investigate:
            if time.monotonic() - t0 > budget_s:
                log.warning(f"Run duration budget ({budget_s}s) exceeded — stopping investigation early")
                break

            investigation = self._investigate(candidate, router_reachable)

            category_for_policy = candidate.get("category") or candidate["change_class"]
            severity = "medium" if candidate["change_class"] in MISSION_ONLY_CLASSES else "low"
            policy_input = {**candidate, "category": category_for_policy, "severity": candidate.get("risk_level") or severity}
            classified = self.policy.classify_finding(policy_input)

            state = "proposed" if verdict.score >= min_surface else "investigating"

            if not dry_run and opp is not None:
                opp = self.store.update(
                    opp.opportunity_id,
                    lifecycle_state=state,
                    investigation=investigation,
                    risk_level=classified.get("risk_level"),
                    automation_eligibility=classified.get("automation_eligibility"),
                    policy_decision_rationale=classified.get("policy_decision_rationale"),
                    run_id=run_id,
                )
            investigated.append({"candidate": candidate, "verdict": verdict, "opportunity": opp, "state": state,
                                  "investigation": investigation})

        surfaced = [i for i in investigated if i["state"] == "proposed"][:max_surfaced]
        # Anything investigated beyond the surfaced cap stays "investigating"
        # rather than "proposed" — never exceed the surfaced bound even if
        # more than max_surfaced scored above the surface threshold.
        if not dry_run:
            for i in investigated[max_surfaced:]:
                if i["state"] == "proposed" and i["opportunity"] is not None:
                    i["opportunity"] = self.store.update(i["opportunity"].opportunity_id, lifecycle_state="investigating")
                    i["state"] = "investigating"

        highest_value = None
        if surfaced:
            top = max(surfaced, key=lambda i: i["verdict"].score)
            highest_value = {
                "opportunity_id": top["opportunity"].opportunity_id if top["opportunity"] else None,
                "title": top["candidate"]["title"],
                "change_class": top["candidate"]["change_class"],
                "summary": top["candidate"].get("summary", ""),
            }

        pending_decisions_count = sum(
            1 for rec in self.store.all_current() if rec.get("lifecycle_state") == "proposed"
        ) if not dry_run else len(surfaced)

        summary = {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": dry_run,
            "investigated_count": len(all_candidates),
            "cleared_relevance_gate_count": len(passed),
            "duplicate_count": len(duplicates),
            "shortlisted_count": len(shortlisted),
            "deep_investigated_count": len(investigated),
            "worth_considering_count": len(surfaced),
            "nothing_worth_changing": len(surfaced) == 0,
            "highest_value_opportunity": highest_value,
            "pending_decisions_count": pending_decisions_count,
            "duration_ms": int((time.monotonic() - t0) * 1000),
        }

        if not dry_run:
            summary_file = self.data_root / "review" / "evolution_summary.json"
            summary_file.parent.mkdir(parents=True, exist_ok=True)
            with open(summary_file, "w") as f:
                json.dump(summary, f, indent=2, default=str)
            log.info(f"\nEvolution summary saved: {summary_file}")

        log.info("\n" + "=" * 80)
        log.info(f"HQ EVOLUTION CYCLE COMPLETE — {summary['worth_considering_count']} worth considering "
                 f"out of {summary['investigated_count']} investigated")
        log.info("=" * 80)
        return summary


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the HQ Evolution overnight discovery cycle")
    parser.add_argument("--repo-root", type=Path, default=Path("/opt/starship-endeavour"))
    parser.add_argument("--data-root", type=Path, default=Path("/opt/starship-endeavour/data/self-improvement"))
    parser.add_argument("--router-url", default="http://127.0.0.1:8891")
    parser.add_argument("--dry-run", action="store_true", help="Skip external network calls, model calls, and all writes")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    orchestrator = EvolutionOrchestrator(args.repo_root, args.data_root, args.router_url)

    t0 = time.monotonic()
    try:
        result = orchestrator.run_cycle(dry_run=args.dry_run)
    except Exception as exc:
        record_heartbeat(_HEARTBEAT_DOMAIN, status="failed", error_message=str(exc)[:500])
        raise

    latency_ms = int((time.monotonic() - t0) * 1000)
    record_heartbeat(
        _HEARTBEAT_DOMAIN, status="ok",
        detail=f"{result['investigated_count']} investigated, {result['worth_considering_count']} worth considering",
        latency_ms=latency_ms,
    )

    print("\n" + "=" * 80)
    print("HQ EVOLUTION CYCLE SUMMARY")
    print("=" * 80)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
