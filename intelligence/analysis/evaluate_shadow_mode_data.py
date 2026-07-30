#!/usr/bin/env python3
"""
Issue 15: Build the LLM-vs-heuristic evaluation harness.

Analyzes shadow-mode data (Issue 14) against ground truth (QA decisions) to determine:
  1. Overall agreement rate between heuristic and LLM
  2. Which confidence band shows most disagreement (where LLM might add value)
  3. Whether LLM helps signals in the "ambiguous" band get correct QA decisions
  4. Recommended Issue 16 routing threshold

Ground truth source: intelligence_briefs.approval_audit ('qa' decision) linked via brief_id.

Usage:
    python -m intelligence.analysis.evaluate_shadow_mode_data \\
        --start-date 2026-07-30 \\
        --days 14 \\
        --output report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(_REPO_ROOT / ".env")

import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [evaluate] %(levelname)s %(message)s",
)
log = logging.getLogger("evaluation-harness")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


@dataclass
class SignalEvaluation:
    """One signal's evaluation: heuristic vs LLM vs ground truth."""
    event_id: str
    collected_at: str
    heuristic_rating: str
    llm_rating: Optional[str]
    agree: bool
    heuristic_score: float
    llm_score: Optional[float]
    brief_id: Optional[str]
    qa_approved: Optional[bool]  # True if brief was QA-passed, False if rejected, None if not in brief
    qa_decision_timestamp: Optional[str]


@dataclass
class ConfidenceBandAnalysis:
    """Statistics for one confidence band (e.g., 3.0–3.5)."""
    band_name: str  # "HIGH (4.0-5.0)", "MEDIUM (3.0-3.9)", "LOW (1.0-2.9)"
    score_min: float
    score_max: float
    signal_count: int
    agree_count: int
    disagree_count: int
    agree_pct: float
    qa_passed_when_agree: int  # Signals where both agree AND brief was QA-passed
    qa_passed_when_disagree: int  # Signals where they disagree AND brief was QA-passed
    qa_pass_rate_when_agree: float
    qa_pass_rate_when_disagree: float


@dataclass
class EvaluationReport:
    """Full evaluation report for Issue 15."""
    report_date: str
    period_start: str
    period_end: str
    total_signals: int
    signals_with_llm_scores: int
    heuristic_llm_agreement_pct: float
    confidence_bands: list  # ConfidenceBandAnalysis
    recommendation: str
    issue_16_threshold: Optional[str]  # e.g. "3.0-3.9" if this band shows LLM value
    findings: list  # [str] key observations


class EvaluationHarness:
    """Analyzes shadow-mode data to recommend LLM routing."""

    def __init__(self):
        pass

    def _fetch_signals_with_dual_scores(
        self, start_date: date, end_date: date
    ) -> list[SignalEvaluation]:
        """Fetch all signals with both heuristic and LLM scores."""
        if not SUPABASE_URL or not SUPABASE_KEY:
            log.error("Supabase not configured")
            return []

        # Query: signals with llm_score_breakdown (shadow-mode ran) + linked QA decisions
        # PostgREST doesn't easily do multi-table left joins, so we do two queries
        start_iso = start_date.isoformat()
        end_iso = end_date.isoformat()

        # 1. Fetch all signals with both scores
        query = (
            f"intelligence_events"
            f"?llm_score_breakdown=not.is.null"
            f"&collected_at=gte.{start_iso}T00:00:00Z"
            f"&collected_at=lte.{end_iso}T23:59:59Z"
            f"&select="
            f"event_id,collected_at,risk_rating,relevance_score,"
            f"llm_risk_rating,llm_relevance_score,brief_id"
            f"&limit=10000"
        )
        url = f"{SUPABASE_URL}/rest/v1/{query}"
        try:
            req = urllib.request.Request(url, headers=_headers())
            with urllib.request.urlopen(req, timeout=30) as resp:
                signals = json.loads(resp.read())
        except Exception as exc:
            log.error(f"Failed to fetch signals: {exc}")
            return []

        # 2. For each signal, fetch its brief's QA decision
        evaluations = []
        for sig in signals:
            event_id = sig["event_id"]
            brief_id = sig["brief_id"]
            qa_approved = None
            qa_timestamp = None

            if brief_id:
                try:
                    # Fetch brief's approval_audit
                    brief_url = (
                        f"{SUPABASE_URL}/rest/v1/intelligence_briefs"
                        f"?brief_id=eq.{brief_id}&select=approval_audit,updated_at"
                    )
                    brief_req = urllib.request.Request(brief_url, headers=_headers())
                    with urllib.request.urlopen(brief_req, timeout=10) as resp:
                        briefs = json.loads(resp.read())
                        if briefs:
                            brief = briefs[0]
                            audit = brief.get("approval_audit", {})
                            qa_entry = audit.get("qa", {})
                            # QA status: approved/rejected/pending
                            qa_approved = qa_entry.get("status") == "approved"
                            qa_timestamp = qa_entry.get("timestamp")
                except Exception as exc:
                    log.debug(f"Failed to fetch brief {brief_id}: {exc}")

            evaluations.append(
                SignalEvaluation(
                    event_id=event_id,
                    collected_at=sig["collected_at"],
                    heuristic_rating=sig.get("risk_rating", "UNKNOWN"),
                    llm_rating=sig.get("llm_risk_rating"),
                    agree=sig.get("risk_rating") == sig.get("llm_risk_rating"),
                    heuristic_score=float(sig.get("relevance_score") or 0),
                    llm_score=float(sig.get("llm_relevance_score") or 0) if sig.get("llm_relevance_score") else None,
                    brief_id=brief_id,
                    qa_approved=qa_approved,
                    qa_decision_timestamp=qa_timestamp,
                )
            )

        return evaluations

    def _analyze_confidence_bands(
        self, evaluations: list[SignalEvaluation]
    ) -> list[ConfidenceBandAnalysis]:
        """Analyze agreement rates by confidence band."""
        # Define bands
        bands = [
            ("HIGH (4.0-5.0)", 4.0, 5.0),
            ("MEDIUM (3.0-3.9)", 3.0, 3.9),
            ("AMBIGUOUS (2.5-2.9)", 2.5, 2.9),
            ("LOW (1.0-2.4)", 1.0, 2.4),
        ]

        analyses = []
        for band_name, min_score, max_score in bands:
            # Filter to this band (using heuristic score as the baseline)
            in_band = [
                e
                for e in evaluations
                if min_score <= e.heuristic_score <= max_score
            ]

            if not in_band:
                continue

            agree_count = sum(1 for e in in_band if e.agree)
            disagree_count = len(in_band) - agree_count

            # QA pass rates within this band
            qa_passed_when_agree = sum(
                1 for e in in_band if e.agree and e.qa_approved is True
            )
            qa_passed_when_disagree = sum(
                1 for e in in_band if not e.agree and e.qa_approved is True
            )
            qa_pass_rate_agree = (
                100.0 * qa_passed_when_agree / sum(1 for e in in_band if e.agree)
                if agree_count > 0
                else 0
            )
            qa_pass_rate_disagree = (
                100.0 * qa_passed_when_disagree / disagree_count
                if disagree_count > 0
                else 0
            )

            analyses.append(
                ConfidenceBandAnalysis(
                    band_name=band_name,
                    score_min=min_score,
                    score_max=max_score,
                    signal_count=len(in_band),
                    agree_count=agree_count,
                    disagree_count=disagree_count,
                    agree_pct=100.0 * agree_count / len(in_band) if in_band else 0,
                    qa_passed_when_agree=qa_passed_when_agree,
                    qa_passed_when_disagree=qa_passed_when_disagree,
                    qa_pass_rate_when_agree=qa_pass_rate_agree,
                    qa_pass_rate_when_disagree=qa_pass_rate_disagree,
                )
            )

        return analyses

    def evaluate(self, start_date: date, days: int = 14) -> EvaluationReport:
        """Run full evaluation."""
        end_date = start_date + timedelta(days=days)

        log.info(f"Fetching signals from {start_date} to {end_date}...")
        evaluations = self._fetch_signals_with_dual_scores(start_date, end_date)

        if not evaluations:
            log.error("No signals with dual scores found")
            return EvaluationReport(
                report_date=datetime.utcnow().isoformat(),
                period_start=start_date.isoformat(),
                period_end=end_date.isoformat(),
                total_signals=0,
                signals_with_llm_scores=0,
                heuristic_llm_agreement_pct=0,
                confidence_bands=[],
                recommendation="No data available",
                issue_16_threshold=None,
                findings=[],
            )

        log.info(f"Fetched {len(evaluations)} signals with dual scores")

        # Overall agreement
        overall_agree = sum(1 for e in evaluations if e.agree)
        agree_pct = 100.0 * overall_agree / len(evaluations)

        # Confidence band analysis
        log.info("Analyzing confidence bands...")
        bands = self._analyze_confidence_bands(evaluations)

        # Findings + recommendations
        findings = []
        issue_16_threshold = None

        if agree_pct > 85:
            findings.append(
                f"Heuristic and LLM agree {agree_pct:.1f}% of the time. "
                "High agreement suggests heuristic is already strong; LLM routing may have limited value."
            )
            recommendation = (
                "Consider skipping Issue 16 (selective augmentation) for now. "
                "The heuristic-only approach is reliable. Re-evaluate in 30 days."
            )
        else:
            findings.append(
                f"Heuristic and LLM agree {agree_pct:.1f}% of the time. "
                "Disagreement suggests LLM could add value in specific confidence bands."
            )

            # Find band with highest disagreement rate
            high_disagree_band = max(
                (b for b in bands if b.disagree_count > 0),
                key=lambda b: b.disagree_count,
                default=None,
            )

            if high_disagree_band:
                findings.append(
                    f"Most disagreement in {high_disagree_band.band_name} band: "
                    f"{high_disagree_band.disagree_count} signals. "
                    f"LLM pass rate: {high_disagree_band.qa_pass_rate_when_disagree:.1f}% vs "
                    f"heuristic pass rate: {high_disagree_band.qa_pass_rate_when_agree:.1f}%"
                )
                issue_16_threshold = high_disagree_band.band_name
                recommendation = (
                    f"Recommend Issue 16 routing threshold: {issue_16_threshold}. "
                    f"Route signals in this band to LLM path; keep high/low confidence on heuristic."
                )
            else:
                recommendation = (
                    "No clear band with high LLM value found. "
                    "Collect more data (Issue 14 continues) before Issue 16."
                )

        return EvaluationReport(
            report_date=datetime.utcnow().isoformat(),
            period_start=start_date.isoformat(),
            period_end=end_date.isoformat(),
            total_signals=len(evaluations),
            signals_with_llm_scores=len(evaluations),
            heuristic_llm_agreement_pct=agree_pct,
            confidence_bands=[asdict(b) for b in bands],
            recommendation=recommendation,
            issue_16_threshold=issue_16_threshold,
            findings=findings,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Issue 15: Evaluate shadow-mode data against QA decisions"
    )
    parser.add_argument(
        "--start-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date.today() - timedelta(days=14),
        help="Start date (YYYY-MM-DD), default 14 days ago",
    )
    parser.add_argument(
        "--days", type=int, default=14, help="Number of days to analyze (default 14)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="evaluation_report.json",
        help="Output file for JSON report",
    )
    args = parser.parse_args()

    harness = EvaluationHarness()
    report = harness.evaluate(args.start_date, args.days)

    # Pretty-print to console
    print("\n" + "=" * 80)
    print("ISSUE 15: LLM-vs-Heuristic Evaluation Report")
    print("=" * 80)
    print(f"\nPeriod: {report['period_start']} to {report['period_end']}")
    print(f"Signals analyzed: {report['total_signals']}")
    print(f"Agreement rate: {report['heuristic_llm_agreement_pct']:.1f}%")
    print(f"\nRecommendation:\n  {report['recommendation']}")
    print(f"\nIssue 16 Routing Threshold: {report['issue_16_threshold'] or 'Not yet recommended'}")
    print(f"\nFindings:")
    for i, finding in enumerate(report['findings'], 1):
        print(f"  {i}. {finding}")
    print(f"\nConfidence Band Analysis:")
    for band in report['confidence_bands']:
        print(
            f"  {band['band_name']}: {band['signal_count']} signals, "
            f"{band['agree_pct']:.1f}% agree, "
            f"QA pass rate (agree): {band['qa_pass_rate_when_agree']:.1f}%, "
            f"(disagree): {band['qa_pass_rate_when_disagree']:.1f}%"
        )

    # Save JSON
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    log.info(f"Report saved to {args.output}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
