"""
Issue 21: Cost/rate-limit governance for new LLM-scoring routes.

Monitors LLM call volume and estimated spend, enforces daily/weekly ceilings,
and implements fallback behavior when limits are exceeded. Used by phase_a_enrichment
and brief_generator to decide whether to fire LLM calls.

Design: Non-blocking (never raises), safe to call synchronously. All persistence
is via Supabase's llm_call_metrics and llm_cost_governance tables. Defaults to
permissive (no limit) if config/metrics unavailable — so a cost-governance failure
doesn't break the pipeline.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional
import urllib.request
import urllib.error

log = logging.getLogger(__name__)


@dataclass
class CostCheckResult:
    """Result of checking whether we can fire an LLM call."""
    allowed: bool                   # Should we attempt the LLM call?
    reason: str                     # Why (or why not)
    task_type: str                  # The task_type we checked
    daily_calls_so_far: int = 0
    daily_cost_so_far: float = 0.0
    daily_limit: Optional[int] = None
    cost_limit: Optional[float] = None


class LLMCostGovernance:
    """Non-blocking cost governance controller."""

    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        self.supabase_url = supabase_url or ""
        self.supabase_key = supabase_key or ""
        self._config_cache: dict = {}
        self._last_config_load: Optional[datetime] = None

    def _headers(self) -> dict:
        return {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get_config(self, task_type: str, force_refresh: bool = False) -> Optional[dict]:
        """Fetch cost governance config for a task_type from Supabase (cached for 5m)."""
        if not self.supabase_url or not self.supabase_key:
            return None

        # Use in-memory cache to avoid hammering Supabase on every call
        if not force_refresh and task_type in self._config_cache:
            if self._last_config_load and \
               (datetime.utcnow() - self._last_config_load).total_seconds() < 300:
                return self._config_cache.get(task_type)

        try:
            url = (f"{self.supabase_url}/rest/v1/llm_cost_governance"
                   f"?task_type=eq.{task_type}&select=*")
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                config = data[0] if data else None
                if config:
                    self._config_cache[task_type] = config
                    self._last_config_load = datetime.utcnow()
                return config
        except Exception as exc:
            log.warning(f"Failed to fetch cost governance config: {exc}")
            return None

    def _get_daily_spent(self, task_type: str) -> tuple[int, float]:
        """Fetch today's call count and estimated spend from llm_daily_costs view."""
        if not self.supabase_url or not self.supabase_key:
            return 0, 0.0

        try:
            today = date.today().isoformat()
            url = (f"{self.supabase_url}/rest/v1/llm_daily_costs"
                   f"?cost_date=eq.{today}&task_type=eq.{task_type}")
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                if data:
                    row = data[0]
                    return int(row.get("call_count", 0)), float(row.get("total_cost_usd", 0.0))
                return 0, 0.0
        except Exception as exc:
            log.warning(f"Failed to fetch daily costs: {exc}")
            return 0, 0.0

    def can_call_llm(self, task_type: str) -> CostCheckResult:
        """
        Check whether an LLM call should be allowed for this task_type.

        Returns CostCheckResult with allowed=True/False. Never raises.
        """
        config = self._get_config(task_type)

        # No config = no limit (permissive default)
        if not config:
            return CostCheckResult(
                allowed=True,
                reason=f"No cost governance config for {task_type}; allowing by default",
                task_type=task_type,
            )

        if not config.get("enabled"):
            return CostCheckResult(
                allowed=True,
                reason=f"Cost governance disabled for {task_type}",
                task_type=task_type,
            )

        calls_so_far, cost_so_far = self._get_daily_spent(task_type)
        call_limit = config.get("daily_call_limit")
        cost_limit = config.get("daily_cost_limit_usd")

        # Check call limit
        if call_limit and calls_so_far >= call_limit:
            throttle = config.get("throttle_on_exceed", "alert")
            if throttle == "stop_calls":
                return CostCheckResult(
                    allowed=False,
                    reason=f"Daily call limit ({call_limit}) exceeded for {task_type}",
                    task_type=task_type,
                    daily_calls_so_far=calls_so_far,
                    daily_cost_so_far=cost_so_far,
                    daily_limit=call_limit,
                    cost_limit=cost_limit,
                )
            elif throttle == "fall_back_to_heuristic":
                log.warning(
                    f"Daily call limit ({call_limit}) for {task_type} exceeded; "
                    f"caller should fall back to heuristic"
                )
            else:  # alert
                log.warning(
                    f"Daily call limit ({call_limit}) for {task_type} reached; "
                    f"firing calls anyway but alerting"
                )

        # Check cost limit
        if cost_limit and cost_so_far >= cost_limit:
            throttle = config.get("throttle_on_exceed", "alert")
            if throttle == "stop_calls":
                return CostCheckResult(
                    allowed=False,
                    reason=f"Daily cost limit (${cost_limit}) exceeded for {task_type}",
                    task_type=task_type,
                    daily_calls_so_far=calls_so_far,
                    daily_cost_so_far=cost_so_far,
                    daily_limit=call_limit,
                    cost_limit=cost_limit,
                )
            elif throttle == "fall_back_to_heuristic":
                log.warning(
                    f"Daily cost limit (${cost_limit}) for {task_type} exceeded; "
                    f"caller should fall back to heuristic"
                )
            else:  # alert
                log.warning(
                    f"Daily cost limit (${cost_limit}) for {task_type} reached; "
                    f"firing calls anyway but alerting"
                )

        # Check alert threshold (80% of limit)
        alert_at = float(config.get("alert_at_percent", 80)) / 100.0
        if cost_limit and cost_so_far >= (alert_at * cost_limit):
            log.warning(
                f"Approaching daily cost limit for {task_type}: "
                f"${cost_so_far:.2f} / ${cost_limit} ({100*cost_so_far/cost_limit:.1f}%)"
            )

        return CostCheckResult(
            allowed=True,
            reason=f"Within limits for {task_type}",
            task_type=task_type,
            daily_calls_so_far=calls_so_far,
            daily_cost_so_far=cost_so_far,
            daily_limit=call_limit,
            cost_limit=cost_limit,
        )

    def log_call(
        self,
        task_type: str,
        provider: str,
        model_name: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        latency_ms: Optional[int] = None,
        success: bool = True,
        failure_reason: Optional[str] = None,
        event_id: Optional[str] = None,
        estimated_cost_usd: Optional[float] = None,
    ) -> bool:
        """
        Log an LLM call to llm_call_metrics. Non-blocking (never raises).
        Returns True if logged, False on error.
        """
        if not self.supabase_url or not self.supabase_key:
            return False

        # Estimate cost if not provided (rough USD estimate for common models)
        if estimated_cost_usd is None:
            estimated_cost_usd = self._estimate_cost(
                input_tokens, output_tokens, provider, model_name
            )

        payload = {
            "task_type": task_type,
            "provider": provider,
            "model_name": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "success": success,
            "failure_reason": failure_reason,
            "event_id": event_id,
            "estimated_cost_usd": estimated_cost_usd,
            "metadata": {},
        }

        try:
            url = f"{self.supabase_url}/rest/v1/llm_call_metrics"
            headers = self._headers()
            headers["Prefer"] = "return=minimal"
            body = json.dumps(payload).encode()
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 201
        except Exception as exc:
            log.warning(f"Failed to log LLM call: {exc}")
            return False

    @staticmethod
    def _estimate_cost(
        input_tokens: Optional[int],
        output_tokens: Optional[int],
        provider: str,
        model_name: Optional[str] = None,
    ) -> float:
        """Estimate USD cost for an LLM call. Rough estimates; real pricing varies."""
        if not input_tokens or not output_tokens:
            return 0.0

        # Pricing as of 2026-07 (adjust as needed)
        costs = {
            "mistral": {"mistral-7b": (0.00025, 0.00075), "mistral-large": (0.0007, 0.0021)},
            "gemini": {"gemini-pro": (0.0005, 0.0015), "gemini-pro-vision": (0.0005, 0.0015)},
            "ollama": {"*": (0.0, 0.0)},  # Local, free
        }
        rates = costs.get(provider.lower(), {}).get(model_name or "*", (0.0001, 0.0003))
        return (input_tokens * rates[0] + output_tokens * rates[1]) / 1000.0
