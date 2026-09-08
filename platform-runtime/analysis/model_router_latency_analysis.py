"""
Model Router Latency Analysis Tool

Samples Model Router latency and reports per-model timing stats, so a real
latency regression can be diagnosed from actual numbers instead of guesswork.

2026-09-07: rewritten. The first version (merged via PR #73, an AI-drafted
"[Mistral] Elevated average latency across model router invocations" handoff)
had two real problems:

1. It imported `phoenix.server.api.dataloaders.average_experiment_run_latency.
   AverageExperimentRunLatencyDataLoader` and `phoenix.server.types.
   DbSessionFactory` — private implementation details of Arize Phoenix's own
   self-hosted GraphQL server, not a public API. This repo's one real Phoenix
   usage (platform-runtime/lib/telemetry.py) only ever calls
   `phoenix.otel.register()` for tracing — nothing resembling this. Nothing
   anywhere in the repo constructs a `DbSessionFactory`, so the function using
   it could never actually run. Dropped entirely rather than reworked: there
   is no lightweight way to query Phoenix's internal experiment data without
   running its own server process, and that's a separate concern from this
   tool's job.

2. It tried to "compare latency across different models" by looping over
   labels like "ollama:local-model-1" / "openrouter:cloud-model-1" and
   passing each as `model_router.call(prompt, model=model)`'s `model` kwarg —
   but that argument is never sent in the request payload (see
   core/engineering/providers/model_router.py: `call()` POSTs only
   `{"prompt": prompt}` to one fixed endpoint; `model` is used solely as a
   fallback *label* for whatever the server already decided to return). So
   every call in that loop hit the exact same backend regardless of the
   `model` argument — the "comparison" was measuring the same thing against
   itself under different names, not actually comparing models.

The only per-model signal `call()` genuinely exposes is the `model` label it
returns *after* the call, reflecting whichever model the server actually used
to serve that specific request. This tool samples repeated real calls and
buckets latency by that observed label — the one comparison the router's
actual public client supports.
"""

from __future__ import annotations

import argparse
import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional

from core.engineering.providers.model_router import call as router_call

log = logging.getLogger(__name__)

DEFAULT_TEST_PROMPTS = [
    "Summarize the purpose of automated testing in one sentence.",
    "What is 17 + 25?",
    "Name one benefit of code review.",
]

# Two calls served by the same backend rarely differ by more than this under
# steady-state load; a bigger spread points at cold starts or contention
# rather than the model itself being slow.
HIGH_VARIANCE_THRESHOLD_SECONDS = 2.0


class ModelRouterLatencyAnalyzer:
    """Samples Model Router latency, bucketed by the model label each call
    actually reports (see module docstring — that's the only per-model
    signal available; this cannot force a specific model to be used)."""

    def analyze_latency(
        self,
        prompts: Optional[List[str]] = None,
        samples_per_prompt: int = 1,
    ) -> Dict[str, Dict[str, float]]:
        """Call the Model Router for each prompt `samples_per_prompt` times,
        recording elapsed time against whichever model label the response
        reports. A failed call is logged and skipped — one bad call must not
        void the rest of the sample."""
        prompts = prompts if prompts is not None else DEFAULT_TEST_PROMPTS
        timings_by_model: Dict[str, List[float]] = defaultdict(list)

        for prompt in prompts:
            for _ in range(samples_per_prompt):
                start = time.time()
                try:
                    _, model_label = router_call(prompt)
                except Exception as exc:
                    log.error(f"Model Router call failed: {exc}")
                    continue
                elapsed = time.time() - start
                timings_by_model[model_label].append(elapsed)
                log.info(f"model={model_label} elapsed={elapsed:.2f}s")

        return {
            model_label: {
                "count": len(timings),
                "total_time": sum(timings),
                "avg_time": sum(timings) / len(timings),
                "min_time": min(timings),
                "max_time": max(timings),
            }
            for model_label, timings in timings_by_model.items()
        }

    def generate_recommendations(self, results: Dict[str, Dict[str, float]]) -> List[str]:
        """Plain-language next steps from a completed analyze_latency() run."""
        if not results:
            return ["No successful Model Router calls to analyze — check connectivity "
                    "(model_router.check_connectivity()) before tuning anything."]

        recommendations: List[str] = []

        if len(results) == 1:
            (only_model,) = results.keys()
            recommendations.append(
                f"Every sampled call reported the same model ({only_model}) — this tool "
                f"can only compare models the router actually reports serving, so if more "
                f"than one backend is in rotation, check the Model Router's own config/logs "
                f"directly for a true per-model breakdown."
            )

        slowest_model, slowest_stats = max(results.items(), key=lambda item: item[1]["avg_time"])
        recommendations.append(
            f"{slowest_model} had the highest average latency "
            f"({slowest_stats['avg_time']:.2f}s over {slowest_stats['count']} calls) — "
            f"investigate its keep_alive/cold-start behavior first."
        )

        high_variance = [
            model for model, stats in results.items()
            if stats["count"] > 1 and (stats["max_time"] - stats["min_time"]) > HIGH_VARIANCE_THRESHOLD_SECONDS
        ]
        if high_variance:
            recommendations.append(
                f"High latency variance (> {HIGH_VARIANCE_THRESHOLD_SECONDS:.0f}s between "
                f"fastest and slowest call) for: {', '.join(high_variance)} — usually a cold "
                f"start or concurrency contention rather than the model's steady-state speed."
            )

        return recommendations


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample Model Router latency and report per-model stats")
    parser.add_argument("--samples", type=int, default=3, help="Calls per prompt (default: 3)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    analyzer = ModelRouterLatencyAnalyzer()
    results = analyzer.analyze_latency(samples_per_prompt=args.samples)

    if not results:
        print("No successful Model Router calls — is the router reachable? "
              "See core.engineering.providers.model_router.check_connectivity().")
        return 1

    print("Latency Analysis Results:")
    for model, stats in results.items():
        print(f"\nModel: {model}")
        print(f"  Average Time: {stats['avg_time']:.2f}s")
        print(f"  Min Time: {stats['min_time']:.2f}s")
        print(f"  Max Time: {stats['max_time']:.2f}s")
        print(f"  Calls: {stats['count']}")

    print("\nRecommendations:")
    for rec in analyzer.generate_recommendations(results):
        print(f"- {rec}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
