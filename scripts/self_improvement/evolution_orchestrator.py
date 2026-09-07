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

import fcntl
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, IO, Optional

from collector import EvidenceCollector
from router_client import ModelRouterClient
from policy import PolicyEngine
from opportunity_store import OpportunityStore, new_fingerprint, MISSION_ONLY_CLASSES
from relevance import RelevanceGate
from investigation_schema import validate_investigation, honest_fallback_investigation
import internal_discovery
import external_discovery
import state_validation
import outcome_evaluation
import evolution_memory

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
        self._lock_path = data_root / "review" / ".evolution_cycle.lock"
        self._lock_fd: Optional[IO] = None

    def _try_acquire_lock(self) -> bool:
        """Section 5: no overlapping Evolution runs. Non-blocking exclusive
        flock — if another real (non-dry-run) cycle already holds it, this
        run steps aside cleanly rather than running concurrently. Never
        blocks: a stuck prior run must not wedge every future scheduled
        run, it just means this run skips (and says so honestly)."""
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = open(self._lock_path, "w")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            fd.close()
            return False
        fd.write(str(datetime.now(timezone.utc).isoformat()))
        fd.flush()
        self._lock_fd = fd
        return True

    def _release_lock(self) -> None:
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                self._lock_fd.close()
            except OSError:
                pass
            self._lock_fd = None

    def _resolve_watchlist(self, run_id: str, dry_run: bool) -> list[dict[str, Any]]:
        """Section 13/17: INTERNAL VALIDATION before EXTERNAL DISCOVERY.
        Checks each watchlist topic's gap_hypothesis against current repo
        evidence; suppresses external search for topics whose hypothesis no
        longer holds, and records why (persisted, not silently dropped —
        section 15). Returns only the topics still worth external research."""
        watchlist = self._load_watchlist()
        if not watchlist:
            return []

        active_topics, resolved_topics = state_validation.validate_watchlist(watchlist, self.repo_root)

        for topic in resolved_topics:
            verdict = topic["validation_verdict"]
            fingerprint = new_fingerprint(topic["id"], "evolution_watchlist", "external")
            existing = self.store.find_by_fingerprint(fingerprint)
            if existing is not None and existing.get("lifecycle_state") == "resolved_before_research":
                continue  # already recorded this exact resolution — don't rewrite every cycle
            log.info(f"Watchlist topic '{topic['id']}' resolved before research: {verdict['reason']}")
            if dry_run:
                continue
            if existing is not None:
                self.store.update(
                    existing["opportunity_id"],
                    lifecycle_state="resolved_before_research",
                    validation_result=verdict["result"],
                    validation_evidence=verdict["evidence"],
                    validated_at=verdict["validated_at"],
                    run_id=run_id,
                )
            else:
                self.store.create_new(
                    title=topic.get("gap_hypothesis", topic["id"]),
                    change_class=topic.get("class", "capability"),
                    discovery_source="external",
                    lifecycle_state="resolved_before_research",
                    fingerprint=fingerprint,
                    summary=topic.get("gap_hypothesis", ""),
                    why_relevant=topic.get("why_relevant", ""),
                    validation_result=verdict["result"],
                    validation_evidence=verdict["evidence"],
                    validated_at=verdict["validated_at"],
                    provenance=[{"source": "internal_state_validation", "detail": verdict["reason"]}],
                    run_id=run_id,
                )

        return active_topics

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

    def _count_cycles_since(self, since_iso: str) -> int:
        """V2 section 9: an honest cycle count for observation_window types
        "cycles"/"events" — there is no separate cycle-counter state
        anywhere in this codebase, so this counts DISTINCT `run_id` values
        already stamped on every OpportunityStore write (the append-only
        log in opportunity_store.py) that are `>= since_iso`, INCLUDING
        this cycle's own run_id (the caller always passes a run_id that is
        itself >= since_iso once this cycle's writes land).

        `run_id` is formatted "%Y-%m-%d-%H%M%S" (always UTC — see
        _run_cycle_locked's run_id line), not directly comparable to an
        ISO datetime, so both sides are parsed into real datetimes before
        comparing. Per-record parsing is wrapped so one malformed run_id
        string never crashes the whole count — this must never raise."""
        try:
            since_dt = datetime.fromisoformat(since_iso)
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError) as exc:
            log.warning(f"_count_cycles_since: could not parse since_iso={since_iso!r}: {exc}")
            return 0

        distinct_run_ids: set[str] = set()
        for rec in self.store.all_records():
            rid = rec.get("run_id")
            if not rid or rid in distinct_run_ids:
                continue
            try:
                rid_dt = datetime.strptime(rid, "%Y-%m-%d-%H%M%S").replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue  # malformed/legacy run_id — skip rather than crash the count
            if rid_dt >= since_dt:
                distinct_run_ids.add(rid)
        return len(distinct_run_ids)

    def _evaluate_due_outcomes(self, run_id: str) -> dict[str, Any]:
        """V2 sections 9-37: EVALUATE DUE OUTCOMES. Runs before discovery
        each cycle (spec ordering: "1. Validate previous observation
        windows. 2. Evaluate any outcomes now ready. 3. Run discovery.").

        Reads self._cycle_t0 / self._cycle_budget_s / self._cycle_router_
        reachable, set by _run_cycle_locked immediately before calling this
        — they carry this cycle's shared run-duration budget and the one
        Model Router health check already made this cycle, so this phase
        never starts its own clock or makes a second health_check() call.

        Never raises: each opportunity's evaluation is independently
        wrapped in try/except (log a warning, continue) as defense in
        depth, matching this file's discipline elsewhere — even though
        outcome_evaluation.evaluate_outcome() is itself documented never
        to raise."""
        max_evaluations = self.evolution_config.get("max_evaluations_per_cycle", 10)
        t0 = self._cycle_t0
        budget_s = self._cycle_budget_s
        router_reachable = self._cycle_router_reachable
        now_iso = datetime.now(timezone.utc).isoformat()

        # Only records with an outcome_contract are ours to evaluate —
        # records with none are pre-V2/manually-created, nothing to check
        # against, and that's not an error, just silently out of scope.
        candidates = [
            opp for opp in self.store.all_current()
            if opp.get("lifecycle_state") in ("approved", "implementing", "verifying")
            and opp.get("outcome_contract")
        ]

        implementations_confirmed = 0
        outcomes_evaluated = 0
        regressions = 0
        latest_material_learning: Optional[dict[str, Any]] = None
        latest_material_learning_ts: Optional[str] = None

        for opp in candidates[:max_evaluations]:
            if time.monotonic() - t0 > budget_s:
                log.warning(f"Run duration budget ({budget_s}s) exceeded — stopping outcome evaluation early")
                break

            opportunity_id = opp.get("opportunity_id")
            try:
                lifecycle_state = opp.get("lifecycle_state")
                contract = opp.get("outcome_contract") or {}
                evaluate_now = False

                if lifecycle_state in ("approved", "implementing") and not contract.get("observation_started_at"):
                    impl = outcome_evaluation.check_implementation_status(opp, self.repo_root, self.data_root)
                    if impl.get("implemented"):
                        impl_source = impl.get("source")
                        # First confirmation. Missions take real time to
                        # land, so "implementing" is a more honest interim
                        # label than jumping straight to "verifying" the
                        # moment a fresh "approved" Mission's status flips
                        # to implemented — a remediation is synchronous
                        # (it already ran, success or not, by the time we
                        # see it) and a manual confirmation means a human
                        # already watched it happen, so both of those (and
                        # an opportunity that reaches this check already in
                        # "implementing" from some other path) go straight
                        # to "verifying". Invariant preserved either way:
                        # once implemented=True is confirmed, the
                        # observation window starts ticking now — "verifying"
                        # is simply the state in which this method actually
                        # calls evaluate_outcome() on it.
                        if lifecycle_state == "approved" and impl_source == "mission":
                            new_state = "implementing"
                        else:
                            new_state = "verifying"

                        verified_at = impl.get("verified_at") or now_iso
                        new_outcome = {
                            **opp.get("outcome", {}),
                            "implementation_success": True,
                            "implementation_source": impl_source,
                            "implementation_verified_at": verified_at,
                        }
                        new_contract = {
                            **contract,
                            "observation_started_at": verified_at,
                            "evaluation_status": "observing",
                        }
                        updated = self.store.update(
                            opportunity_id,
                            lifecycle_state=new_state,
                            outcome=new_outcome,
                            outcome_contract=new_contract,
                            run_id=run_id,
                        )
                        if updated is None:
                            log.warning(f"{opportunity_id}: store.update returned None confirming implementation — skipping")
                            continue
                        opp = updated.to_dict()
                        implementations_confirmed += 1
                        lifecycle_state = new_state
                        contract = new_contract

                        if new_state == "verifying":
                            # No reason to wait a whole extra cycle when the
                            # observation window is "immediate" (or already
                            # elapsed) — try evaluating right away.
                            evaluate_now = True
                    else:
                        # Normal, expected, not-yet state — info at most,
                        # and only ever logged once per cycle per
                        # opportunity (never a repeated warning every cycle
                        # for the same still-pending record).
                        log.info(f"{opportunity_id}: not yet implemented ({impl.get('detail', '')})")

                elif lifecycle_state == "verifying":
                    evaluate_now = True

                if not evaluate_now:
                    continue

                cycles_elapsed = None
                observation_started_at = contract.get("observation_started_at")
                if observation_started_at:
                    cycles_elapsed = self._count_cycles_since(observation_started_at)

                result = outcome_evaluation.evaluate_outcome(
                    opp, self.repo_root, self.data_root, self.store,
                    router=self.router if router_reachable else None,
                    cycles_elapsed=cycles_elapsed,
                )

                if result.get("skip"):
                    # Defensive only — shouldn't normally happen here since
                    # we only reach this for state "verifying", but
                    # evaluate_outcome is the sole authority on readiness.
                    continue

                outcome_result = result.get("outcome_result")
                if outcome_result == "not_yet_ready":
                    # Calm, valid, non-urgent (section 42) — stays
                    # "verifying". Only write if evaluation_status would
                    # actually change, to avoid spamming a store write
                    # every cycle for a record that isn't ready yet.
                    if contract.get("evaluation_status") != "observing":
                        self.store.update(
                            opportunity_id,
                            outcome_contract={**contract, "evaluation_status": "observing"},
                            run_id=run_id,
                        )
                    continue

                # Terminal result: improved / no_material_change / regressed
                # / inconclusive. Section 37: append to evaluation_history
                # BEFORE overwriting the top-level outcome fields, so a
                # later re-evaluation (should one ever happen) never
                # silently loses this verdict.
                evaluated_at = result.get("evaluated_at") or now_iso
                history_entry = {
                    "outcome_result": outcome_result,
                    "confidence": result.get("confidence"),
                    "evidence_summary": result.get("evidence_summary"),
                    "evaluated_at": evaluated_at,
                    "method": result.get("method"),
                }
                new_history = list(opp.get("outcome", {}).get("evaluation_history", [])) + [history_entry]
                merged_outcome = {
                    **opp.get("outcome", {}),
                    "outcome_result": outcome_result,
                    "evidence_summary": result.get("evidence_summary"),
                    "confidence": result.get("confidence"),
                    "what_worked": result.get("what_worked"),
                    "what_did_not": result.get("what_did_not"),
                    "unexpected_effects": result.get("unexpected_effects"),
                    "future_implication": result.get("future_implication"),
                    "attribution_risk": result.get("attribution_risk"),
                    "method": result.get("method"),
                    "evaluated_at": evaluated_at,
                    "evaluation_history": new_history,
                }
                updated = self.store.update(
                    opportunity_id,
                    lifecycle_state="learned",
                    outcome=merged_outcome,
                    outcome_contract={**contract, "evaluation_status": "evaluated"},
                    run_id=run_id,
                )
                if updated is None:
                    log.warning(f"{opportunity_id}: store.update returned None recording evaluation — skipping")
                    continue

                outcomes_evaluated += 1
                if outcome_result == "regressed":
                    regressions += 1

                if outcome_result in ("improved", "regressed"):
                    if latest_material_learning_ts is None or evaluated_at > latest_material_learning_ts:
                        latest_material_learning = {
                            "opportunity_id": opportunity_id,
                            "title": opp.get("title"),
                            "outcome_result": outcome_result,
                            "future_implication": result.get("future_implication"),
                        }
                        latest_material_learning_ts = evaluated_at

            except Exception as exc:
                log.warning(f"Outcome evaluation failed for {opportunity_id}: {exc}")
                continue

        return {
            "implementations_confirmed": implementations_confirmed,
            "outcomes_evaluated": outcomes_evaluated,
            "regressions": regressions,
            "latest_material_learning": latest_material_learning,
        }

    def _investigate(self, candidate: dict[str, Any], router_reachable: bool) -> dict[str, Any]:
        """Section 7-10/22/45: the model may interpret evidence already in
        `candidate` (a bounded, opportunity-specific evidence bundle — see
        router_client.py's investigation prompt); it may not invent
        evidence, and its recommendation is advisory only — it never sets
        lifecycle_state or automation authority (relevance.py's
        deterministic score and PolicyEngine do that; classify_finding()
        below never reads this dict at all).

        Every path here returns a schema-validated shape (investigation_
        schema.py) — a malformed model response degrades individual fields
        rather than propagating an unvalidated shape into the store/UI.

        V2 sections 20-23: evolution_memory recall is deterministic and
        cheap (no model call), so both the model-synthesis path and the
        template-fallback path get it — not just the model path."""
        related = evolution_memory.find_related_outcomes(candidate, self.store, max_results=3)
        related_summary = evolution_memory.format_related_experience(related) if related else ""

        if router_reachable:
            try:
                result = self.router.investigate_opportunity(candidate, context=related_summary if related_summary else None)
                if result.get("success") and result.get("investigation"):
                    inv = validate_investigation(result["investigation"])
                    inv["method"] = "model_synthesis"
                    inv["related_experience"] = related
                    inv["related_experience_summary"] = related_summary
                    return inv
            except Exception as exc:
                log.warning(f"Model investigation failed, falling back to template: {exc}")

        fallback = honest_fallback_investigation(candidate)
        fallback["related_experience"] = related
        fallback["related_experience_summary"] = related_summary
        return fallback

    def run_cycle(self, dry_run: bool = False) -> dict[str, Any]:
        """dry_run is fully lock-free (section 5: "dry-run remains
        scheduler-independent and side-effect free") — only a real cycle
        takes the overlap-prevention lock, since only a real cycle writes
        anything an overlapping run could collide with."""
        if not dry_run and not self._try_acquire_lock():
            log.warning(f"Another HQ Evolution cycle already holds {self._lock_path} — skipping this run")
            return {
                "run_id": None, "timestamp": datetime.now(timezone.utc).isoformat(),
                "dry_run": dry_run, "skipped": True, "skipped_reason": "another cycle already running",
                "investigated_count": 0, "worth_considering_count": 0, "nothing_worth_changing": True,
                "highest_value_opportunity": None, "pending_decisions_count": 0, "duration_ms": 0,
            }
        try:
            return self._run_cycle_locked(dry_run)
        finally:
            self._release_lock()

    def _run_cycle_locked(self, dry_run: bool) -> dict[str, Any]:
        t0 = time.monotonic()
        run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
        budget_s = self.evolution_config.get("run_duration_budget_minutes", 20) * 60

        log.info("=" * 80)
        log.info("HQ EVOLUTION CYCLE START (OBSERVE / DISCOVER)")
        log.info("=" * 80)

        evidence = self.collector.collect_all()
        classified_findings = self._load_latest_classified_findings()

        # ONE Model Router health check per cycle — health_check() is a
        # real network call, shared between this phase and the
        # investigation phase further down rather than made twice.
        router_reachable = False if dry_run else self.router.health_check()

        # V2 EVALUATE DUE OUTCOMES — spec ordering: "1. Validate previous
        # observation windows. 2. Evaluate any outcomes now ready.
        # 3. Run discovery. ..." — genuinely the first substantive phase,
        # ahead of internal/external discovery. dry_run stays fully
        # side-effect free (this phase only ever writes via
        # self.store.update()), so it's skipped outright rather than run
        # in some read-only mode.
        self._cycle_t0 = t0
        self._cycle_budget_s = budget_s
        self._cycle_router_reachable = router_reachable
        # Belt-and-suspenders on top of _evaluate_due_outcomes' own
        # per-opportunity try/except (section 8 of the audit checklist):
        # this new, less battle-tested V2 phase must never be able to take
        # the WHOLE cycle down with it — discovery/investigation below is
        # the pre-existing, load-bearing pipeline and has to run regardless
        # of what happens here.
        try:
            outcome_eval_summary = self._evaluate_due_outcomes(run_id) if not dry_run else {
                "implementations_confirmed": 0, "outcomes_evaluated": 0, "regressions": 0, "latest_material_learning": None,
            }
        except Exception as exc:
            log.error(f"Outcome evaluation phase failed entirely — continuing to discovery unaffected: {exc}")
            outcome_eval_summary = {
                "implementations_confirmed": 0, "outcomes_evaluated": 0, "regressions": 0, "latest_material_learning": None,
            }

        max_internal = self.evolution_config.get("max_internal_candidates_per_cycle", 20)
        internal_candidates = internal_discovery.discover(classified_findings, evidence, max_internal)

        # Section 17 RESEARCH ORDER: INTERNAL VALIDATION happens before
        # EXTERNAL DISCOVERY — never "watchlist -> search internet -> then
        # check whether HQ needs it".
        external_candidates: list[dict[str, Any]] = []
        active_topics: list[dict[str, Any]] = []
        if not dry_run:
            active_topics = self._resolve_watchlist(run_id, dry_run)
            if active_topics:
                external_candidates = external_discovery.discover(active_topics, self.evolution_config)

        all_candidates = internal_candidates + external_candidates
        for c in all_candidates:
            c["fingerprint"] = new_fingerprint(c["title"], c.get("source", ""), c["discovery_source"])

        log.info(f"Discovered {len(internal_candidates)} internal + {len(external_candidates)} external "
                 f"= {len(all_candidates)} candidates ({len(active_topics)} watchlist topic(s) still active "
                 f"after current-state validation)")

        # RELEVANCE GATE + DEDUP
        log.info("\nRELEVANCE GATE / DEDUP")
        evaluated = [(c, self.gate.evaluate(c)) for c in all_candidates]
        duplicates = [(c, v) for c, v in evaluated if v.is_duplicate]
        passed = [(c, v) for c, v in evaluated if v.passes_investigate and not v.is_duplicate]
        log.info(f"{len(duplicates)} duplicate/already-considered, {len(passed)} clear the relevance gate")

        # Persist every gate-cleared candidate as a lightweight DISCOVERED
        # record (so future cycles can dedup against it) before spending
        # any investigation budget. A candidate the relevance gate is
        # RECONSIDERING (verdict.reconsider_of set — a prior "discovered"/
        # "investigating"/"watching"/"rejected" record for this same
        # fingerprint) must update that SAME opportunity_id rather than
        # create_new() a fresh one: otherwise something rediscovered every
        # cycle without ever being promoted would pile up one new
        # "discovered" card per cycle forever instead of one card that
        # just keeps refreshing (found alongside the fix that stopped
        # "discovered"/"investigating" from being permanently frozen).
        discovered_opps = []
        for candidate, verdict in passed:
            fields = dict(
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
                validation_result=candidate.get("validation_result"),
                validation_evidence=candidate.get("validation_evidence", []),
                validated_at=candidate.get("validated_at"),
                measurement_hint=candidate.get("measurement_hint"),
                run_id=run_id,
            )
            if dry_run:
                opp = None
            elif verdict.reconsider_of:
                opp = self.store.update(verdict.reconsider_of, **fields)
            else:
                opp = self.store.create_new(**fields)
            discovered_opps.append((candidate, verdict, opp))

        # SHORTLIST -> INVESTIGATE (the expensive step; bounded)
        log.info("\nSHORTLIST / INVESTIGATE")
        max_shortlist = self.evolution_config.get("max_shortlist_per_cycle", 6)
        max_investigations = self.evolution_config.get("max_investigations_per_cycle", 6)
        shortlisted = sorted(discovered_opps, key=lambda t: t[1].score, reverse=True)[:max_shortlist]
        to_investigate = shortlisted[:max_investigations]

        # router_reachable was already computed once above, before the
        # EVALUATE DUE OUTCOMES phase — reused here rather than calling
        # health_check() a second time this cycle.
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

        # worth_considering_count (this cycle's surfaced shortlist) is
        # deliberately distinct from pending_decisions_count (the whole
        # current backlog of undecided "proposed" opportunities, which
        # accumulates across cycles until the user acts) — section 20.
        # Captain's Chair's signal reads pending_decisions_count; the
        # Discover tab's morning-compression line reads worth_considering_count.
        pending_decisions_count = sum(
            1 for rec in self.store.all_current() if rec.get("lifecycle_state") == "proposed"
        ) if not dry_run else len(surfaced)

        model_synthesis_count = sum(1 for i in investigated if i["investigation"].get("method") == "model_synthesis")
        resolved_before_research_count = sum(
            1 for rec in self.store.all_current()
            if rec.get("run_id") == run_id and rec.get("lifecycle_state") == "resolved_before_research"
        ) if not dry_run else 0

        cycle_timestamp = datetime.now(timezone.utc).isoformat()

        summary = {
            "run_id": run_id,
            "timestamp": cycle_timestamp,
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
            # V2 sections 9-37: outcome-evaluation phase results — see
            # _evaluate_due_outcomes(), run before discovery this cycle.
            "outcomes_completed_count": outcome_eval_summary["outcomes_evaluated"],
            "regressions_count": outcome_eval_summary["regressions"],
            "latest_material_learning": outcome_eval_summary["latest_material_learning"],
            "implementations_confirmed_count": outcome_eval_summary["implementations_confirmed"],
            # This cycle reached completion — a crash never reaches this
            # line, so "ok" is the only value ever written here. Distinct
            # from record_heartbeat()'s own failed/skipped tracking in
            # main(); this field is for evolution_summary.json's own
            # consumers (dashboard.py's /api/evolution-summary).
            "cycle_status": "ok",
            # Same timestamp as summary["timestamp"] — deliberately aliased
            # rather than a second, possibly-different datetime.now() call.
            "freshness": cycle_timestamp,
            # Section 18: operational cost telemetry, not a human-facing
            # dashboard — kept out of the Discover tab's morning summary.
            "cost_accounting": {
                "internal_candidates_checked": len(internal_candidates),
                "watchlist_topics_total": len(active_topics) + resolved_before_research_count,
                "watchlist_topics_resolved_before_research": resolved_before_research_count,
                "external_searches_made": len(active_topics),
                "external_candidates_found": len(external_candidates),
                "investigation_model_calls": model_synthesis_count,
                "investigation_template_fallbacks": len(investigated) - model_synthesis_count,
            },
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
    if result.get("skipped"):
        record_heartbeat(_HEARTBEAT_DOMAIN, status="skipped", detail=result.get("skipped_reason", ""), latency_ms=latency_ms)
    else:
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
