#!/usr/bin/env python3
"""
Signal Score Recompute — technical OSINT workbench gap-closure (2026-08-08).

Runs after validate_source_accuracy.py's source-level accuracy pass, as part
of the same daily 01:00 UTC job. Per TECHNICAL_OSINT_WORKBENCH.md section 7:

  1. (done by validate_source_accuracy.py) Recompute SRS for all sources.
  2. Recompute confidence_level for all signals (source tier + corroboration).
  3. Recompute rank_score for all signals (reuses intelligence.ranking.ranker.rank()
     verbatim — same formula used at collection time, no parallel reimplementation).
  4. Insert a source_reliability_snapshot row per active source (enables real
     30-day trending in source-network, replacing hardcoded placeholder data).
  5. Log validation results to validation_job_runs (audit trail).

Plus, not in the original spec but required to close real gaps found auditing
against it:
  - Populate signal_corroboration (persisted; replaces source-network's and
    credibility's in-memory per-request title-overlap recompute).
  - Compute criticality_score (spec defines the column, gives no formula —
    see compute_criticality() below for the formula used here).
  - Log signal_escalation_history only when a signal's escalation decision
    changes from its last logged value (not on every read).

Usage:
    python3 tools/intelligence/recompute_signal_scores.py [--dry-run] [--backfill] [--limit N]
                                                           [--window-days N] [--full]

--backfill widens the corroboration window to all non-suppressed history
(one-time use). Without it, corroboration only scans the last 3 days —
that's the steady-state daily mode.

Egress control (2026-10): the confidence and rank passes only reload events
collected in the last WINDOW_DAYS (default 21: ranker._recency_decay() stops
decaying at 14 days, plus a 7-day margin). A full, unwindowed sweep runs on
Sundays (UTC) or with --full, so source-reliability changes still reach old
events once a week. The final "Recompute complete" line reports calls and
response bytes per phase.
"""

import argparse
import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

sys.path.insert(0, str(REPO_ROOT))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

from supabase import create_client

# Events older than this are skipped by the nightly confidence/rank passes.
# ranker._recency_decay() is a constant 0.10 floor from day 14, so 21 days is
# that plus a 7-day margin. Sundays (UTC) and --full run with no window.
WINDOW_DAYS = 21
FULL_SWEEP_WEEKDAY = 6  # datetime.weekday(): Sunday

# Escalation-history lookups are batched this many signal_ids per .in_() call.
ESCALATION_LOOKUP_CHUNK = 200

RISK_SCORES = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}


def _same_score(stored, computed) -> bool:
    """Stored numeric comes back from PostgREST as int/float/str; treat it as
    unchanged if it matches the freshly computed value to 1e-6."""
    if stored is None or computed is None:
        return stored is None and computed is None
    try:
        return abs(float(stored) - float(computed)) < 1e-6
    except (TypeError, ValueError):
        return False
RELEVANCE_SCORES = {"high": 1.0, "medium": 0.6, "low": 0.3}


def compute_criticality(risk_rating, operational_relevance, banking_relevance, cps230_relevance):
    """0-1 impact severity. TECHNICAL_OSINT_WORKBENCH.md defines the column but
    gives no formula — this weighting (risk 0.4 / operational 0.35 / banking 0.25,
    +0.1 CPS230 boost) is this implementation's design choice, not spec-derived."""
    risk_component = RISK_SCORES.get(risk_rating, 0.5)
    op_component = operational_relevance if operational_relevance is not None else 0.5
    bank_component = RELEVANCE_SCORES.get(banking_relevance, 0.5)
    score = 0.4 * risk_component + 0.35 * float(op_component) + 0.25 * bank_component
    if cps230_relevance:
        score = min(1.0, score + 0.1)
    return round(score, 2)


def impact_from_criticality(score):
    if score is None:
        return "MEDIUM"
    if score >= 0.85:
        return "CRITICAL"
    if score >= 0.60:
        return "HIGH"
    if score >= 0.35:
        return "MEDIUM"
    return "LOW"


def compute_confidence_level(tier, corroboration_count):
    """Per TECHNICAL_OSINT_WORKBENCH.md section 3 confidence mapping."""
    if tier == "TIER_1":
        return "HIGH"
    if tier == "TIER_2":
        return "HIGH" if corroboration_count >= 3 else "MEDIUM"
    if tier == "TIER_3":
        return "MEDIUM" if corroboration_count >= 2 else "LOW"
    if tier == "TIER_4":
        return "LOW"
    return "UNKNOWN"


def compute_escalation(confidence, impact):
    """Per TECHNICAL_OSINT_WORKBENCH.md section 4 escalation decision logic."""
    if confidence == "HIGH" and impact == "CRITICAL":
        return "ESCALATE"
    if confidence == "HIGH" or impact == "CRITICAL":
        return "WATCH"
    if confidence == "MEDIUM" and impact == "HIGH":
        return "WATCH"
    return "MONITOR"


def _is_full_sweep_day():
    """True on the weekly unwindowed sweep day (Sunday, UTC)."""
    return datetime.now(timezone.utc).weekday() == FULL_SWEEP_WEEKDAY


def _title_words(title):
    return set(re.findall(r"\w{4,}", (title or "").lower()))


class SignalScoreRecomputer:
    # Class-level defaults so instances built without __init__ (tests) behave
    # like a normal windowed run.
    window_days = WINDOW_DAYS
    _phase = "other"
    _corroboration_rows = None

    def __init__(self, dry_run=False, backfill=False, limit=None, window_days=WINDOW_DAYS, full=False):
        self.dry_run = dry_run
        self.backfill = backfill
        self.limit = limit
        sunday = _is_full_sweep_day()
        # None = no window (full sweep): explicit --full, --backfill, or Sunday UTC.
        self.window_days = None if (full or backfill or sunday) else window_days
        self.full_reason = ("--full" if full else "--backfill" if backfill else "sunday-utc" if sunday else None)
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self._call_counts = {}
        self._response_bytes = {}
        self.stats = {
            "signals_confidence_recomputed": 0,
            "signals_rank_recomputed": 0,
            "corroboration_pairs_inserted": 0,
            "snapshots_inserted": 0,
            "escalations_logged": 0,
            "errors": 0,
        }

    def _fetch_all(self, build_query, page_size=1000, apply_limit=True):
        """PostgREST caps unpaginated responses at 1000 rows by default — the
        first version of this script silently processed only the first 1000
        of 4304 non-suppressed events on its initial backfill run because of
        this. build_query is a zero-arg callable returning a fresh query
        builder (so .range() can be reapplied each page). apply_limit=False
        ignores --limit (which caps events, not lookup tables)."""
        all_rows = []
        offset = 0
        cap = self.limit if apply_limit else None
        while True:
            if cap and offset >= cap:
                break
            end = offset + page_size - 1
            if cap:
                end = min(end, cap - 1)
            resp = self._exec(build_query().range(offset, end))
            rows = resp.data or []
            all_rows.extend(rows)
            if len(rows) < (end - offset + 1):
                break
            offset += page_size
        return all_rows

    def _exec(self, query):
        """query.execute() with per-phase call and response-byte accounting.
        Bytes are len() of the compact JSON of the response body: nothing else
        on the VM logs payload size, and this is the number the egress quota
        is made of (headers and compression aside)."""
        resp = query.execute()
        try:
            size = len(json.dumps(getattr(resp, "data", None), separators=(",", ":"), default=str))
        except (TypeError, ValueError):
            size = 0
        phase = self._phase
        calls = self.__dict__.setdefault("_call_counts", {})
        sizes = self.__dict__.setdefault("_response_bytes", {})
        calls[phase] = calls.get(phase, 0) + 1
        sizes[phase] = sizes.get(phase, 0) + size
        return resp

    def _io_summary(self):
        calls = getattr(self, "_call_counts", {})
        sizes = getattr(self, "_response_bytes", {})
        return {
            "calls_total": sum(calls.values()),
            "response_bytes_total": sum(sizes.values()),
            "by_phase": {ph: {"calls": calls[ph], "response_bytes": sizes.get(ph, 0)} for ph in calls},
        }

    def _window_cutoff(self):
        """ISO cutoff for the windowed passes, or None for a full sweep."""
        if not self.window_days:
            return None
        return (datetime.now(timezone.utc) - timedelta(days=self.window_days)).isoformat()

    def _load_corroboration_rows(self):
        """signal_corroboration is read once per run and shared by the dedupe
        in compute_corroboration() and the counts in _corroboration_counts().
        Pairs this run inserts are appended, so the counts match what a second
        full read would have returned."""
        if self._corroboration_rows is None:
            self._corroboration_rows = self._fetch_all(
                lambda: self.supabase.table("signal_corroboration").select("signal_id, corroborating_signal_id")
            )
        return self._corroboration_rows

    # ─── Corroboration ───────────────────────────────────────────────────

    def compute_corroboration(self):
        """Windowed pairwise title-overlap: only compares events in the same
        sector within +/-3 days of each other, not a full O(n^2) cross join."""
        window_days = None if self.backfill else 3
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat() if window_days else None

        def build():
            q = (
                self.supabase.table("intelligence_events")
                .select("event_id, sector, raw_title, published_at, collected_at")
                .eq("suppressed", False)
            )
            if cutoff:
                q = q.gt("collected_at", cutoff)
            return q

        events = self._fetch_all(build)
        logger.info(f"Corroboration scan: {len(events)} candidate events "
                    f"({'full history' if self.backfill else f'last {window_days}d'})")

        # existing pairs, to avoid duplicate inserts
        existing = self._load_corroboration_rows()
        existing_pairs = {(r["signal_id"], r["corroborating_signal_id"]) for r in existing}

        # bucket by sector for windowed comparison
        by_sector = defaultdict(list)
        for e in events:
            ts = e.get("published_at") or e.get("collected_at")
            if not ts:
                continue
            e["_ts"] = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            by_sector[e.get("sector")].append(e)

        to_insert = []
        confirm_counts = defaultdict(int)
        for bucket in by_sector.values():
            bucket.sort(key=lambda e: e["_ts"])
            for a, b in combinations(bucket, 2):
                if abs((a["_ts"] - b["_ts"]).days) > 3:
                    continue
                wa, wb = _title_words(a["raw_title"]), _title_words(b["raw_title"])
                overlap = len(wa & wb)
                if overlap < 2:
                    continue
                pair = (a["event_id"], b["event_id"])
                rpair = (b["event_id"], a["event_id"])
                if pair in existing_pairs or rpair in existing_pairs:
                    continue
                existing_pairs.add(pair)
                confirm_counts[a["event_id"]] += 1
                confirm_counts[b["event_id"]] += 1
                to_insert.append({
                    "signal_id": a["event_id"],
                    "corroborating_signal_id": b["event_id"],
                    "overlap_type": "title_match",
                    "title_word_overlap": overlap,
                })

        for row in to_insert:
            row["confirmation_count"] = confirm_counts[row["signal_id"]]

        logger.info(f"Corroboration: {len(to_insert)} new pairs found")
        if not self.dry_run and to_insert:
            for i in range(0, len(to_insert), 500):
                chunk = to_insert[i:i + 500]
                try:
                    self._exec(self.supabase.table("signal_corroboration").insert(chunk))
                except Exception as e:  # noqa: BLE001 - per-chunk insert inside a batch loop — one bad chunk must not abort the run; already logged + counted in self.stats['errors']
                    logger.error(f"Corroboration insert failed for chunk {i}: {e}")
                    self.stats["errors"] += 1
                else:
                    existing.extend(
                        {"signal_id": r["signal_id"], "corroborating_signal_id": r["corroborating_signal_id"]}
                        for r in chunk
                    )
        self.stats["corroboration_pairs_inserted"] = len(to_insert)

    def _corroboration_counts(self, event_ids):
        """Count corroborating rows (either direction) per event_id."""
        counts = defaultdict(int)
        for r in self._load_corroboration_rows():
            counts[r["signal_id"]] += 1
            counts[r["corroborating_signal_id"]] += 1
        return counts

    # ─── Confidence + criticality ────────────────────────────────────────

    def recompute_confidence_and_criticality(self):
        cutoff = self._window_cutoff()

        def build():
            q = (
                self.supabase.table("intelligence_events")
                .select("event_id, source_id, risk_rating, operational_relevance, banking_relevance, "
                        "cps230_relevance, osint_confidence_level, criticality_score, "
                        "intelligence_source_registry(reliability_tier)")
                .eq("suppressed", False)
            )
            if cutoff:
                q = q.gt("collected_at", cutoff)
            return q

        events = self._fetch_all(build)
        logger.info(f"Confidence/criticality recompute: {len(events)} events "
                    f"({f'last {self.window_days}d' if cutoff else 'full sweep'})")

        corroboration_counts = self._corroboration_counts([e["event_id"] for e in events])

        updates = []
        for e in events:
            # No "or TIER_4" fallback here on purpose: TIER_4 is a claim we've
            # matched a real source and it's proven unreliable — asserting
            # that for an event whose source join came back empty would be
            # wrong, not just imprecise. compute_confidence_level(None, ...)
            # already falls through to "UNKNOWN", which was previously dead
            # code because this line masked every missing-tier case as TIER_4.
            tier = (e.get("intelligence_source_registry") or {}).get("reliability_tier")
            corrob = corroboration_counts.get(e["event_id"], 0)
            osint_confidence_level = compute_confidence_level(tier, corrob)
            criticality = compute_criticality(
                e.get("risk_rating"), e.get("operational_relevance"),
                e.get("banking_relevance"), e.get("cps230_relevance"),
            )
            if (e.get("osint_confidence_level") == osint_confidence_level
                    and _same_score(e.get("criticality_score"), criticality)):
                continue
            updates.append({"event_id": e["event_id"], "osint_confidence_level": osint_confidence_level, "criticality_score": criticality})

        logger.info(f"Confidence/criticality: {len(updates)} of {len(events)} changed")
        if not self.dry_run:
            self._bulk_update_scores(updates, "Confidence/criticality")

        self.stats["signals_confidence_recomputed"] = len(updates)

    # ─── Rank score (reuses intelligence.ranking.ranker.rank() verbatim) ──

    def recompute_rank_scores(self):
        from intelligence.models import ClassifiedEvent
        from intelligence.ranking.ranker import rank

        cutoff = self._window_cutoff()

        def build():
            # raw_summary is deliberately not selected: rank() never reads it.
            q = (
                self.supabase.table("intelligence_events")
                .select("event_id, source_id, raw_title, canonical_url, published_at, collected_at, "
                        "dedup_hash, event_type, geography, sector, operational_relevance, customer_impact, "
                        "banking_relevance, cps230_relevance, dependency_risk, confidence, suppressed, "
                        "suppression_reason, rank_score, intelligence_source_registry(source_name, priority_rank, "
                        "confidence_weight, category)")
                .eq("suppressed", False)
            )
            if cutoff:
                q = q.gt("collected_at", cutoff)
            return q

        rows = self._fetch_all(build)
        logger.info(f"Rank score recompute: {len(rows)} events "
                    f"({f'last {self.window_days}d' if cutoff else 'full sweep'})")

        classified = []
        for r in rows:
            src = r.get("intelligence_source_registry") or {}
            try:
                classified.append(ClassifiedEvent(
                    event_id=r["event_id"], source_id=r["source_id"],
                    source_name=src.get("source_name", "Unknown"),
                    source_priority=src.get("priority_rank", 5),
                    source_confidence_weight=src.get("confidence_weight", 0.5),
                    source_category=src.get("category", "unknown"),
                    raw_title=r.get("raw_title") or "", raw_summary="",
                    canonical_url=r.get("canonical_url"),
                    published_at=datetime.fromisoformat(r["published_at"].replace("Z", "+00:00")) if r.get("published_at") else None,
                    collected_at=datetime.fromisoformat(r["collected_at"].replace("Z", "+00:00")) if r.get("collected_at") else datetime.now(timezone.utc),
                    dedup_hash=r.get("dedup_hash") or r["event_id"],
                    event_type=r.get("event_type") or "other", geography=r.get("geography") or "unknown",
                    sector=r.get("sector") or "general",
                    operational_relevance=float(r.get("operational_relevance") or 0.5),
                    customer_impact=r.get("customer_impact") or "low",
                    banking_relevance=r.get("banking_relevance") or "low",
                    cps230_relevance=bool(r.get("cps230_relevance")),
                    dependency_risk=bool(r.get("dependency_risk")),
                    confidence=float(r.get("confidence") or 0.5),
                    suppressed=False,
                ))
            except Exception as e:  # noqa: BLE001 - per-row rank-recompute skip inside a batch loop — one bad row must not abort the run; already logged + counted in self.stats['errors']
                logger.warning(f"Skipping {r.get('event_id')} in rank recompute: {e}")
                self.stats["errors"] += 1

        ranked = rank(classified)
        logger.info(f"Rank recompute: {len(ranked)} events scored")

        current = {r["event_id"]: r.get("rank_score") for r in rows}
        updates = [
            {"event_id": ev.event_id, "rank_score": ev.rank_score}
            for ev in ranked
            if not _same_score(current.get(ev.event_id), ev.rank_score)
        ]
        logger.info(f"Rank score: {len(updates)} of {len(ranked)} changed")
        if not self.dry_run:
            self._bulk_update_scores(updates, "rank_score")

        self.stats["signals_rank_recomputed"] = len(ranked)

    def _bulk_update_scores(self, updates, label, chunk_size=500):
        """Write score changes via bulk_update_signal_scores (migration 0225):
        one RPC per chunk instead of one PATCH per row — the per-row version
        was ~31k requests a night, half the project's API/log volume."""
        for i in range(0, len(updates), chunk_size):
            chunk = updates[i:i + chunk_size]
            try:
                self._exec(self.supabase.rpc("bulk_update_signal_scores", {"p_rows": chunk}))
            except Exception as e:  # noqa: BLE001 - per-chunk write inside a batch loop — one bad chunk must not abort the run; already logged + counted in self.stats['errors']
                logger.error(f"{label} bulk update failed for chunk {i}: {e}")
                self.stats["errors"] += 1
            logger.info(f"  ...{min(i + chunk_size, len(updates))}/{len(updates)} {label} written")

    # ─── Source reliability snapshots ──────────────────────────────────

    def insert_snapshots(self):
        sources = self._exec(self.supabase.table("intelligence_source_registry").select(
            "source_id, reliability_score, reliability_tier, accuracy_ratio, false_positive_rate, accuracy_sample_size"
        ).eq("active", True)).data or []

        rows = [{
            "source_id": s["source_id"], "reliability_score": s["reliability_score"],
            "reliability_tier": s["reliability_tier"], "accuracy_ratio": s["accuracy_ratio"],
            "false_positive_rate": s["false_positive_rate"], "accuracy_sample_size": s["accuracy_sample_size"],
        } for s in sources]

        logger.info(f"Snapshotting {len(rows)} sources")
        if not self.dry_run and rows:
            try:
                self._exec(self.supabase.table("source_reliability_snapshot").insert(rows))
            except Exception as e:  # noqa: BLE001 - best-effort snapshot insert, already logged + counted in self.stats['errors']
                logger.error(f"Snapshot insert failed: {e}")
                self.stats["errors"] += 1
        self.stats["snapshots_inserted"] = len(rows)

    # ─── Escalation history (only on change) ───────────────────────────

    def _latest_escalation_decisions(self, signal_ids):
        """{signal_id: most recent escalation_decision}, from chunked .in_()
        reads (ESCALATION_LOOKUP_CHUNK ids per call) instead of one query per
        signal. Rows come back newest-first, so the first one seen per signal
        is the latest, which is what the old per-signal order+limit(1) returned."""
        latest = {}
        for i in range(0, len(signal_ids), ESCALATION_LOOKUP_CHUNK):
            chunk = signal_ids[i:i + ESCALATION_LOOKUP_CHUNK]
            rows = self._fetch_all(lambda chunk=chunk: (
                self.supabase.table("signal_escalation_history")
                .select("signal_id, escalation_decision")
                .in_("signal_id", chunk)
                .order("escalated_at", desc=True)
            ), apply_limit=False)
            for r in rows:
                latest.setdefault(r["signal_id"], r["escalation_decision"])
        return latest

    def log_escalation_changes(self):
        events = self._fetch_all(lambda: (
            self.supabase.table("intelligence_events")
            .select("event_id, raw_title, risk_rating, osint_confidence_level, criticality_score")
            .eq("suppressed", False)
            .gte("rank_score", 70)
        ))
        logger.info(f"Escalation check: {len(events)} signals with rank_score >= 70")

        last_decisions = self._latest_escalation_decisions([e["event_id"] for e in events])

        logged = 0
        for e in events:
            probability = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}.get(e.get("risk_rating"), "medium")
            impact = impact_from_criticality(e.get("criticality_score"))
            confidence = e.get("osint_confidence_level") or "UNKNOWN"
            decision = compute_escalation(confidence, impact)

            last_decision = last_decisions.get(e["event_id"])
            if last_decision == decision:
                continue

            if not self.dry_run:
                try:
                    self._exec(self.supabase.table("signal_escalation_history").insert({
                        "signal_id": e["event_id"], "probability": probability, "impact": impact,
                        "confidence": confidence, "escalation_decision": decision,
                        "reason": f"Auto-computed: confidence={confidence}, impact={impact}",
                        "escalated_by": "system",
                    }))
                except Exception as ex:  # noqa: BLE001 - per-event escalation-log write inside a batch loop — one bad event must not abort the run; already logged + counted in self.stats['errors']
                    logger.error(f"Escalation log failed for {e['event_id']}: {ex}")
                    self.stats["errors"] += 1
                    continue
            logged += 1
        self.stats["escalations_logged"] = logged

    # ─── Orchestration ──────────────────────────────────────────────────

    def run(self):
        started_at = datetime.now(timezone.utc).isoformat()
        run_row = None
        self._phase = "bookkeeping"
        logger.info(f"Recompute mode: {f'windowed, last {self.window_days}d' if self.window_days else f'FULL sweep ({self.full_reason})'}")
        if not self.dry_run:
            try:
                run_row = self._exec(self.supabase.table("validation_job_runs").insert(
                    {"started_at": started_at, "status": "running"}
                )).data[0]
            except Exception as e:  # noqa: BLE001 - best-effort job-run tracking row, already logged; the actual validation work below proceeds regardless
                logger.error(f"Could not create validation_job_runs row: {e}")

        try:
            self._phase = "corroboration"
            self.compute_corroboration()
            self._phase = "confidence"
            self.recompute_confidence_and_criticality()
            self._phase = "rank"
            self.recompute_rank_scores()
            self._phase = "snapshots"
            self.insert_snapshots()
            self._phase = "escalation"
            self.log_escalation_changes()
            self._phase = "bookkeeping"

            self.stats.update(self._io_summary())
            logger.info("Recompute complete: %s", self.stats)

            if run_row and not self.dry_run:
                self.supabase.table("validation_job_runs").update({
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "signals_confidence_recomputed": self.stats["signals_confidence_recomputed"],
                    "signals_rank_recomputed": self.stats["signals_rank_recomputed"],
                    "snapshots_inserted": self.stats["snapshots_inserted"],
                    "escalations_logged": self.stats["escalations_logged"],
                    "errors": self.stats["errors"],
                    "status": "completed",
                }).eq("run_id", run_row["run_id"]).execute()
        except Exception as e:
            logger.error(f"Fatal error in recompute job: {e}")
            if run_row and not self.dry_run:
                self.supabase.table("validation_job_runs").update({
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "status": "failed", "error_detail": str(e),
                }).eq("run_id", run_row["run_id"]).execute()
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backfill", action="store_true", help="widen corroboration scan to all history (one-time use)")
    parser.add_argument("--limit", type=int, default=None, help="cap events processed (testing)")
    parser.add_argument("--window-days", type=int, default=WINDOW_DAYS,
                        help=f"only recompute events collected in the last N days (default {WINDOW_DAYS}); "
                             "ignored on Sundays (UTC) and with --full")
    parser.add_argument("--full", action="store_true", help="no window: recompute all non-suppressed events")
    args = parser.parse_args()

    recomputer = SignalScoreRecomputer(dry_run=args.dry_run, backfill=args.backfill, limit=args.limit,
                                       window_days=args.window_days, full=args.full)
    recomputer.run()


if __name__ == "__main__":
    main()
