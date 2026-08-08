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

--backfill widens the corroboration window to all non-suppressed history
(one-time use). Without it, corroboration only scans the last 3 days —
that's the steady-state daily mode.
"""

import os
import re
import sys
import logging
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from itertools import combinations
from collections import defaultdict

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

RISK_SCORES = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}
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


def _title_words(title):
    return set(re.findall(r"\w{4,}", (title or "").lower()))


class SignalScoreRecomputer:
    def __init__(self, dry_run=False, backfill=False, limit=None):
        self.dry_run = dry_run
        self.backfill = backfill
        self.limit = limit
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.stats = {
            "signals_confidence_recomputed": 0,
            "signals_rank_recomputed": 0,
            "corroboration_pairs_inserted": 0,
            "snapshots_inserted": 0,
            "escalations_logged": 0,
            "errors": 0,
        }

    def _fetch_all(self, build_query, page_size=1000):
        """PostgREST caps unpaginated responses at 1000 rows by default — the
        first version of this script silently processed only the first 1000
        of 4304 non-suppressed events on its initial backfill run because of
        this. build_query is a zero-arg callable returning a fresh query
        builder (so .range() can be reapplied each page)."""
        all_rows = []
        offset = 0
        while True:
            if self.limit and offset >= self.limit:
                break
            end = offset + page_size - 1
            if self.limit:
                end = min(end, self.limit - 1)
            resp = build_query().range(offset, end).execute()
            rows = resp.data or []
            all_rows.extend(rows)
            if len(rows) < (end - offset + 1):
                break
            offset += page_size
        return all_rows

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
        existing = self._fetch_all(lambda: self.supabase.table("signal_corroboration").select("signal_id, corroborating_signal_id"))
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
        for sector, bucket in by_sector.items():
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
                    self.supabase.table("signal_corroboration").insert(chunk).execute()
                except Exception as e:
                    logger.error(f"Corroboration insert failed for chunk {i}: {e}")
                    self.stats["errors"] += 1
        self.stats["corroboration_pairs_inserted"] = len(to_insert)

    def _corroboration_counts(self, event_ids):
        """Count corroborating rows (either direction) per event_id."""
        counts = defaultdict(int)
        rows = self._fetch_all(lambda: self.supabase.table("signal_corroboration").select("signal_id, corroborating_signal_id"))
        for r in rows:
            counts[r["signal_id"]] += 1
            counts[r["corroborating_signal_id"]] += 1
        return counts

    # ─── Confidence + criticality ────────────────────────────────────────

    def recompute_confidence_and_criticality(self):
        events = self._fetch_all(lambda: (
            self.supabase.table("intelligence_events")
            .select("event_id, source_id, risk_rating, operational_relevance, banking_relevance, "
                    "cps230_relevance, intelligence_source_registry(reliability_tier)")
            .eq("suppressed", False)
        ))
        logger.info(f"Confidence/criticality recompute: {len(events)} events")

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
            updates.append({"event_id": e["event_id"], "osint_confidence_level": osint_confidence_level, "criticality_score": criticality})

        if not self.dry_run:
            for i in range(0, len(updates), 200):
                chunk = updates[i:i + 200]
                for row in chunk:
                    try:
                        self.supabase.table("intelligence_events").update(
                            {"osint_confidence_level": row["osint_confidence_level"], "criticality_score": row["criticality_score"]}
                        ).eq("event_id", row["event_id"]).execute()
                    except Exception as e:
                        logger.error(f"Confidence/criticality update failed for {row['event_id']}: {e}")
                        self.stats["errors"] += 1
                logger.info(f"  ...{min(i + 200, len(updates))}/{len(updates)} updated")

        self.stats["signals_confidence_recomputed"] = len(updates)

    # ─── Rank score (reuses intelligence.ranking.ranker.rank() verbatim) ──

    def recompute_rank_scores(self):
        from intelligence.models import ClassifiedEvent
        from intelligence.ranking.ranker import rank

        rows = self._fetch_all(lambda: (
            self.supabase.table("intelligence_events")
            .select("event_id, source_id, raw_title, raw_summary, canonical_url, published_at, collected_at, "
                    "dedup_hash, event_type, geography, sector, operational_relevance, customer_impact, "
                    "banking_relevance, cps230_relevance, dependency_risk, confidence, suppressed, "
                    "suppression_reason, intelligence_source_registry(source_name, priority_rank, "
                    "confidence_weight, category)")
            .eq("suppressed", False)
        ))
        logger.info(f"Rank score recompute: {len(rows)} events")

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
                    raw_title=r.get("raw_title") or "", raw_summary=r.get("raw_summary"),
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
            except Exception as e:
                logger.warning(f"Skipping {r.get('event_id')} in rank recompute: {e}")
                self.stats["errors"] += 1

        ranked = rank(classified)
        logger.info(f"Rank recompute: {len(ranked)} events scored")

        if not self.dry_run:
            for i, ev in enumerate(ranked):
                try:
                    self.supabase.table("intelligence_events").update(
                        {"rank_score": ev.rank_score}
                    ).eq("event_id", ev.event_id).execute()
                except Exception as e:
                    logger.error(f"rank_score update failed for {ev.event_id}: {e}")
                    self.stats["errors"] += 1
                if (i + 1) % 500 == 0:
                    logger.info(f"  ...{i + 1}/{len(ranked)} rank_scores written")

        self.stats["signals_rank_recomputed"] = len(ranked)

    # ─── Source reliability snapshots ──────────────────────────────────

    def insert_snapshots(self):
        sources = self.supabase.table("intelligence_source_registry").select(
            "source_id, reliability_score, reliability_tier, accuracy_ratio, false_positive_rate, accuracy_sample_size"
        ).eq("active", True).execute().data or []

        rows = [{
            "source_id": s["source_id"], "reliability_score": s["reliability_score"],
            "reliability_tier": s["reliability_tier"], "accuracy_ratio": s["accuracy_ratio"],
            "false_positive_rate": s["false_positive_rate"], "accuracy_sample_size": s["accuracy_sample_size"],
        } for s in sources]

        logger.info(f"Snapshotting {len(rows)} sources")
        if not self.dry_run and rows:
            try:
                self.supabase.table("source_reliability_snapshot").insert(rows).execute()
            except Exception as e:
                logger.error(f"Snapshot insert failed: {e}")
                self.stats["errors"] += 1
        self.stats["snapshots_inserted"] = len(rows)

    # ─── Escalation history (only on change) ───────────────────────────

    def log_escalation_changes(self):
        events = self._fetch_all(lambda: (
            self.supabase.table("intelligence_events")
            .select("event_id, raw_title, risk_rating, osint_confidence_level, criticality_score")
            .eq("suppressed", False)
            .gte("rank_score", 70)
        ))
        logger.info(f"Escalation check: {len(events)} signals with rank_score >= 70")

        logged = 0
        for e in events:
            probability = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}.get(e.get("risk_rating"), "medium")
            impact = impact_from_criticality(e.get("criticality_score"))
            confidence = e.get("osint_confidence_level") or "UNKNOWN"
            decision = compute_escalation(confidence, impact)

            last = (
                self.supabase.table("signal_escalation_history")
                .select("escalation_decision")
                .eq("signal_id", e["event_id"])
                .order("escalated_at", desc=True)
                .limit(1)
                .execute().data
            )
            last_decision = last[0]["escalation_decision"] if last else None
            if last_decision == decision:
                continue

            if not self.dry_run:
                try:
                    self.supabase.table("signal_escalation_history").insert({
                        "signal_id": e["event_id"], "probability": probability, "impact": impact,
                        "confidence": confidence, "escalation_decision": decision,
                        "reason": f"Auto-computed: confidence={confidence}, impact={impact}",
                        "escalated_by": "system",
                    }).execute()
                except Exception as ex:
                    logger.error(f"Escalation log failed for {e['event_id']}: {ex}")
                    self.stats["errors"] += 1
                    continue
            logged += 1
        self.stats["escalations_logged"] = logged

    # ─── Orchestration ──────────────────────────────────────────────────

    def run(self):
        started_at = datetime.now(timezone.utc).isoformat()
        run_row = None
        if not self.dry_run:
            try:
                run_row = self.supabase.table("validation_job_runs").insert(
                    {"started_at": started_at, "status": "running"}
                ).execute().data[0]
            except Exception as e:
                logger.error(f"Could not create validation_job_runs row: {e}")

        try:
            self.compute_corroboration()
            self.recompute_confidence_and_criticality()
            self.recompute_rank_scores()
            self.insert_snapshots()
            self.log_escalation_changes()

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
    args = parser.parse_args()

    recomputer = SignalScoreRecomputer(dry_run=args.dry_run, backfill=args.backfill, limit=args.limit)
    recomputer.run()


if __name__ == "__main__":
    main()
