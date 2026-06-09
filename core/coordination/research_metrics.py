"""
Research Mission Metrics (MSN-0055C WP7)

Collects and persists research performance metrics to Supabase for monitoring and optimization.

Tables:
- research_metrics: Per-mission performance data

Tracks:
- Task completion rate
- Provider success/failure patterns
- Consolidation method and success
- Recommendation confidence
- Execution timing breakdown
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional
import os
import logging

log = logging.getLogger(__name__)


@dataclass
class ResearchMetrics:
    """
    Collect and store research mission metrics.

    Measures performance, reliability, and quality indicators.
    """

    # Identity
    mission_id: str
    topic: str

    # Task performance
    task_count: int = 0
    successful_tasks: int = 0

    # Provider tracking
    primary_provider: Optional[str] = None
    provider_failures: int = 0
    provider_path: Optional[str] = None  # "gemini-2.5-flash → ollama"

    # Consolidation method
    consolidation_success: bool = False
    consolidation_method: str = "unknown"  # "llm", "deterministic", "fallback"

    # Recommendation
    recommendation_generated: bool = False
    confidence: float = 0.0

    # Timing (milliseconds)
    total_duration_ms: int = 0
    queue_wait_ms: int = 0
    execution_ms: int = 0
    consolidation_ms: int = 0

    # Metadata
    mission_date: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d"))

    def __post_init__(self):
        """Validate metrics after initialization."""
        log.info(
            f"[research-metrics] Initialized: mission_id={self.mission_id}, "
            f"topic={self.topic}, task_count={self.task_count}"
        )

    def finalize(self):
        """Finalize metrics before storage (calculate derived fields)."""
        if self.task_count > 0:
            success_rate = (self.successful_tasks / self.task_count) * 100
            log.info(
                f"[research-metrics] Finalized: success_rate={success_rate:.1f}%, "
                f"total_duration={self.total_duration_ms}ms, "
                f"consolidation_method={self.consolidation_method}, "
                f"confidence={self.confidence:.2f}"
            )

    def store_to_supabase(self):
        """
        Save metrics to Supabase database.

        Persists to public.research_metrics table for analysis and dashboarding.
        """

        try:
            from supabase import create_client

            # Get Supabase credentials
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_KEY")

            if not supabase_url or not supabase_key:
                log.warning(
                    "[research-metrics] Supabase credentials not configured. "
                    "Metrics not persisted. (Set SUPABASE_URL and SUPABASE_KEY)"
                )
                return

            # Create client and insert
            client = create_client(supabase_url, supabase_key)

            # Convert to dict, excluding None values
            metrics_dict = {k: v for k, v in asdict(self).items() if v is not None}

            response = client.table("research_metrics").insert(metrics_dict).execute()

            log.info(
                f"[research-metrics] Stored to Supabase: mission_id={self.mission_id}, "
                f"rows_inserted={len(response.data) if response.data else 0}"
            )

        except ImportError:
            log.warning(
                "[research-metrics] Supabase client not available. "
                "Metrics not persisted. (Install supabase-py)"
            )
        except Exception as e:
            log.error(
                f"[research-metrics] Failed to store metrics: {type(e).__name__}: {str(e)[:100]}"
            )

    def get_success_rate(self) -> float:
        """Get task completion success rate (0.0 - 1.0)."""
        if self.task_count == 0:
            return 0.0
        return self.successful_tasks / self.task_count

    def get_provider_reliability(self) -> float:
        """
        Get provider reliability estimate.

        Based on failure count vs. task count.
        """
        if self.task_count == 0:
            return 1.0
        # Assume each task tries a provider; failures reduce reliability
        return 1.0 - (self.provider_failures / self.task_count)

    def get_consolidation_rate(self) -> float:
        """Get consolidation success rate."""
        return 1.0 if self.consolidation_success else 0.0

    def format_summary(self) -> str:
        """
        Format metrics as human-readable summary.

        Returns summary for logging or reporting.
        """

        success_rate = int(self.get_success_rate() * 100)
        reliability = int(self.get_provider_reliability() * 100)

        summary = (
            f"Research Mission {self.mission_id}\n"
            f"  Topic: {self.topic}\n"
            f"  Task Completion: {self.successful_tasks}/{self.task_count} ({success_rate}%)\n"
            f"  Provider Reliability: {reliability}%\n"
            f"  Consolidation: {self.consolidation_method} "
            f"({'✓ Success' if self.consolidation_success else '✗ Fallback'})\n"
            f"  Recommendation: {'✓ Generated' if self.recommendation_generated else '✗ Not generated'} "
            f"(confidence: {self.confidence:.2f})\n"
            f"  Execution Time: {self.total_duration_ms}ms "
            f"(queue: {self.queue_wait_ms}ms, execution: {self.execution_ms}ms, "
            f"consolidation: {self.consolidation_ms}ms)"
        )

        return summary


class ResearchMetricsCollector:
    """
    Facade for collecting metrics throughout research orchestration.

    Provides convenient methods for recording metrics at each phase.
    """

    def __init__(self, mission_id: str, topic: str):
        """Initialize collector with mission context."""
        self.metrics = ResearchMetrics(mission_id=mission_id, topic=topic)
        self.phase_start_times = {}

    def start_phase(self, phase_name: str):
        """Record start time for a phase (e.g., 'execution', 'consolidation')."""
        import time
        self.phase_start_times[phase_name] = time.time()

    def end_phase(self, phase_name: str) -> int:
        """
        Record end time for a phase and return elapsed milliseconds.

        Args:
            phase_name: Name of the phase

        Returns:
            Elapsed milliseconds
        """
        import time

        if phase_name not in self.phase_start_times:
            log.warning(f"[research-metrics] Phase {phase_name} not started")
            return 0

        elapsed_sec = time.time() - self.phase_start_times[phase_name]
        elapsed_ms = int(elapsed_sec * 1000)

        # Store in metrics if matching known phase
        if phase_name == "execution":
            self.metrics.execution_ms = elapsed_ms
        elif phase_name == "consolidation":
            self.metrics.consolidation_ms = elapsed_ms
        elif phase_name == "queue_wait":
            self.metrics.queue_wait_ms = elapsed_ms

        return elapsed_ms

    def record_task_completion(self, count: int, successful: int, primary_provider: Optional[str] = None):
        """Record task completion metrics."""
        self.metrics.task_count = count
        self.metrics.successful_tasks = successful
        if primary_provider:
            self.metrics.primary_provider = primary_provider

    def record_provider_failure(self):
        """Increment provider failure counter."""
        self.metrics.provider_failures += 1

    def record_consolidation(self, success: bool, method: str = "unknown"):
        """Record consolidation success and method."""
        self.metrics.consolidation_success = success
        self.metrics.consolidation_method = method

    def record_recommendation(self, generated: bool, confidence: float = 0.0):
        """Record recommendation generation and confidence."""
        self.metrics.recommendation_generated = generated
        self.metrics.confidence = confidence

    def record_total_duration(self, duration_ms: int):
        """Record total mission duration."""
        self.metrics.total_duration_ms = duration_ms

    def finalize_and_store(self):
        """Finalize metrics and persist to database."""
        self.metrics.finalize()
        self.metrics.store_to_supabase()
        return self.metrics.format_summary()
