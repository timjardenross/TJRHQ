#!/usr/bin/env python3
"""MSN-0057: Research Memory Retrieval Engine

Implements knowledge retrieval before research execution.

Responsibilities:
- Search research memory for prior research
- Calculate similarity to current question
- Assess freshness of prior findings
- Make reuse/refresh/new research decisions
- Report retrieval status to user

Design:
- Non-blocking (failures don't crash workflow)
- Incremental (keyword matching for MVP; semantic search future)
- Confidence-based (report confidence in match)
- Decision-ready (explicit reuse/refresh/new recommendation)
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class ResearchMemoryEntry:
    """Retrieved research memory entry."""
    id: str
    mission_id: str
    original_question: str
    consolidated_findings: str
    recommendation: str
    confidence_level: float
    created_at: str
    tags: list[str]
    reuse_count: int
    provider_path: list[str]
    tasks_completed: int
    task_count: int

    @property
    def freshness_days(self) -> int:
        """Days since research was created."""
        try:
            created = datetime.fromisoformat(self.created_at)
            age = datetime.utcnow() - created
            return age.days
        except Exception:
            return 999  # Treat unparseable dates as very old

    @property
    def is_fresh(self) -> bool:
        """< 30 days = fresh."""
        return self.freshness_days < 30

    @property
    def is_recent(self) -> bool:
        """< 90 days = recent."""
        return self.freshness_days < 90

    @property
    def is_stale(self) -> bool:
        """> 180 days = stale."""
        return self.freshness_days > 180


@dataclass
class RetrievalResult:
    """Result of research memory retrieval."""
    found: bool
    entry: Optional[ResearchMemoryEntry] = None
    match_confidence: float = 0.0  # 0.0-1.0 confidence in match
    recommendation: str = ""  # "REUSE" | "REFRESH" | "NEW_RESEARCH"
    reason: str = ""


class ResearchMemoryRetriever:
    """Search and retrieve prior research from memory."""

    def __init__(self, supabase_client=None):
        """
        Initialize retriever.

        Args:
            supabase_client: Optional Supabase client for database queries.
                            If not provided, retrieval is disabled (returns no matches).
        """
        self.supabase = supabase_client
        self.enabled = supabase_client is not None

    def search_prior_research(self, research_question: str) -> RetrievalResult:
        """
        Search research memory for relevant prior research.

        Workflow:
        1. Extract search terms from question
        2. Query research memory table
        3. Score candidates by keyword overlap
        4. Assess freshness of top match
        5. Make reuse/refresh/new decision

        Args:
            research_question: User's research question

        Returns:
            RetrievalResult with decision (REUSE/REFRESH/NEW_RESEARCH) and entry
        """

        if not self.enabled:
            log.debug("[KB-RETRIEVE] Supabase not available; skipping retrieval")
            return RetrievalResult(found=False, recommendation="NEW_RESEARCH", reason="KB disabled")

        try:
            # Step 1: Extract search terms
            search_terms = self._extract_search_terms(research_question)
            log.debug(f"[KB-RETRIEVE] Search terms: {search_terms}")

            # Step 2: Query research memory
            candidates = self._query_knowledge_base(search_terms)
            if not candidates:
                log.info("[KB-RETRIEVE] No prior research found")
                return RetrievalResult(
                    found=False,
                    recommendation="NEW_RESEARCH",
                    reason="No prior research in knowledge base"
                )

            # Step 3: Score and rank candidates
            scored = self._score_candidates(search_terms, candidates)
            if not scored:
                return RetrievalResult(
                    found=False,
                    recommendation="NEW_RESEARCH",
                    reason="No candidates matched search terms"
                )

            # Step 4: Get best match
            best_match_score, best_entry = scored[0]
            log.info(f"[KB-RETRIEVE] Best match: {best_entry.mission_id} (score={best_match_score:.2f})")

            # Step 5: Make reuse/refresh/new decision
            recommendation, reason = self._make_retrieval_decision(best_entry)

            return RetrievalResult(
                found=True,
                entry=best_entry,
                match_confidence=min(best_match_score, 1.0),  # Normalize to 0-1
                recommendation=recommendation,
                reason=reason
            )

        except Exception as e:
            log.error(f"[KB-RETRIEVE] Retrieval failed: {e}")
            return RetrievalResult(
                found=False,
                recommendation="NEW_RESEARCH",
                reason=f"Retrieval error: {str(e)[:50]}"
            )

    def _extract_search_terms(self, question: str) -> list[str]:
        """Extract searchable keywords from question."""
        # Simple MVP: split by whitespace, filter short words
        words = question.lower().split()
        # Filter: remove common words, keep 3+ char words
        common = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'as', 'is', 'are', 'be', 'was', 'were', 'have', 'has', 'do', 'does', 'did', 'should', 'would', 'could', 'will'}
        terms = [w for w in words if w not in common and len(w) > 2]
        return terms[:10]  # Limit to top 10 terms

    def _query_knowledge_base(self, search_terms: list[str]) -> list[dict]:
        """
        Query Supabase for research matching search terms.

        Returns:
            List of research_memory entries (dicts)
        """
        try:
            # Query all non-stale research (within 6 months)
            cutoff_date = (datetime.utcnow() - timedelta(days=180)).isoformat()

            response = self.supabase.table("research_memory") \
                .select("*") \
                .gt("created_at", cutoff_date) \
                .execute()

            entries = response.data or []
            log.debug(f"[KB-RETRIEVE] Found {len(entries)} non-stale entries")
            return entries

        except Exception as e:
            log.warning(f"[KB-RETRIEVE] Query failed: {e}")
            return []

    def _score_candidates(self, search_terms: list[str], candidates: list[dict]) -> list[tuple[float, ResearchMemoryEntry]]:
        """
        Score candidates by keyword overlap with search terms.

        Returns:
            List of (score, entry) tuples, sorted by score descending
        """
        scored = []

        for candidate in candidates:
            try:
                # Build entry object
                entry = ResearchMemoryEntry(
                    id=candidate.get("id", ""),
                    mission_id=candidate.get("mission_id", ""),
                    original_question=candidate.get("original_question", ""),
                    consolidated_findings=candidate.get("consolidated_findings", ""),
                    recommendation=candidate.get("recommendation", ""),
                    confidence_level=candidate.get("confidence_level", 0.0),
                    created_at=candidate.get("created_at", ""),
                    tags=candidate.get("tags", []),
                    reuse_count=candidate.get("reuse_count", 0),
                    provider_path=candidate.get("provider_path", []),
                    tasks_completed=candidate.get("tasks_completed", 0),
                    task_count=candidate.get("task_count", 0),
                )

                # Calculate match score
                question_lower = entry.original_question.lower()
                tag_matches = sum(1 for term in search_terms if term in entry.tags)
                question_matches = sum(1 for term in search_terms if term in question_lower)
                findings_matches = sum(1 for term in search_terms if term in entry.consolidated_findings.lower())

                # Weight: tags > question > findings
                score = (tag_matches * 3.0) + (question_matches * 2.0) + (findings_matches * 1.0)

                # Bonus: high confidence and complete research
                if entry.confidence_level >= 0.8:
                    score += 2.0
                if entry.tasks_completed == entry.task_count:
                    score += 1.0

                # Penalty: old research
                if entry.freshness_days > 90:
                    score *= 0.8
                if entry.freshness_days > 180:
                    score *= 0.5

                if score > 0:
                    scored.append((score, entry))

            except Exception as e:
                log.debug(f"[KB-RETRIEVE] Failed to score candidate: {e}")
                continue

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def _make_retrieval_decision(self, entry: ResearchMemoryEntry) -> tuple[str, str]:
        """
        Decide whether to reuse, refresh, or do new research.

        Returns:
            (recommendation, reason) tuple
        """
        if entry.is_fresh:
            return (
                "REUSE",
                f"Fresh research from {entry.freshness_days} days ago (high confidence)"
            )
        elif entry.is_recent:
            return (
                "REUSE",
                f"Recent research from {entry.freshness_days} days ago (suggest refresh if critical)"
            )
        elif entry.freshness_days < 180:
            return (
                "REFRESH",
                f"Research from {entry.freshness_days} days ago; recommend refresh"
            )
        else:
            return (
                "NEW_RESEARCH",
                f"Research too stale ({entry.freshness_days} days); execute new research"
            )

    def format_retrieval_report(self, result: RetrievalResult) -> str:
        """
        Format retrieval result as user-friendly message.

        Returns:
            Markdown-formatted report
        """
        if not result.found:
            return f"ℹ️ No prior research found. {result.reason}\nProceeding with new research..."

        entry = result.entry
        report = f"🎯 *Prior Research Found*\n"
        report += f"━━━━━━━━━━━━━━━━━━\n"
        report += f"*Previous Question:* {entry.original_question}\n"
        report += f"*Research Age:* {entry.freshness_days} days old\n"
        report += f"*Confidence:* {entry.confidence_level:.0%}\n"
        report += f"*Reuse Count:* {entry.reuse_count} times\n"
        report += f"\n"
        report += f"*Previous Recommendation:*\n"
        report += f"_{entry.recommendation}_\n"
        report += f"\n"
        report += f"*Decision:* {result.recommendation}\n"
        report += f"_{result.reason}_\n"

        if result.recommendation == "REUSE":
            report += f"\n✅ Reusing prior research (no new execution needed)\n"
        elif result.recommendation == "REFRESH":
            report += f"\n⚠️ Refreshing research (new execution + merge with prior)\n"
        else:
            report += f"\n🔄 Executing new research\n"

        return report

    def increment_reuse_count(self, entry_id: str) -> bool:
        """
        Increment reuse count for a retrieved entry (to track knowledge reuse).

        Args:
            entry_id: UUID of research_memory entry

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False

        try:
            # Increment reuse_count
            response = self.supabase.table("research_memory") \
                .update({"reuse_count": self.supabase.rpc("increment_reuse_count", {"entry_id": entry_id})}) \
                .eq("id", entry_id) \
                .execute()

            log.debug(f"[KB-RETRIEVE] Incremented reuse count for {entry_id}")
            return True

        except Exception as e:
            log.warning(f"[KB-RETRIEVE] Failed to increment reuse count: {e}")
            return False
