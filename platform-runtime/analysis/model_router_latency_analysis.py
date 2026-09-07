"""
Model Router Latency Analysis Tool

Compares execution times between local Ollama models and cloud endpoints
to identify performance bottlenecks and recommend tuning parameters.
"""

import time
import logging
from typing import Dict, List, Tuple
from core.engineering.providers.model_router import call as router_call
from phoenix.server.api.dataloaders.average_experiment_run_latency import (
    AverageExperimentRunLatencyDataLoader
)
from phoenix.server.types import DbSessionFactory

log = logging.getLogger(__name__)

class ModelRouterLatencyAnalyzer:
    def __init__(self, db_session_factory: DbSessionFactory):
        self.db = db_session_factory
        self.latency_dataloader = AverageExperimentRunLatencyDataLoader(db_session_factory)

    async def analyze_latency(self, test_prompts: List[str], models: List[str]) -> Dict[str, Dict[str, float]]:
        """
        Compare latency across different models for given test prompts.

        Args:
            test_prompts: List of prompts to test with
            models: List of model identifiers to test

        Returns:
            Dictionary with model names as keys and latency metrics as values
        """
        results = {}

        for model in models:
            model_results = {
                'total_time': 0.0,
                'avg_time': 0.0,
                'min_time': float('inf'),
                'max_time': 0.0,
                'count': 0
            }

            for prompt in test_prompts:
                start_time = time.time()
                try:
                    response, _ = router_call(prompt, model=model)
                    elapsed = time.time() - start_time

                    model_results['total_time'] += elapsed
                    model_results['min_time'] = min(model_results['min_time'], elapsed)
                    model_results['max_time'] = max(model_results['max_time'], elapsed)
                    model_results['count'] += 1

                    log.info(f"Model {model} processed prompt in {elapsed:.2f}s")
                except Exception as e:
                    log.error(f"Error testing model {model} with prompt: {e}")
                    continue

            if model_results['count'] > 0:
                model_results['avg_time'] = model_results['total_time'] / model_results['count']
                results[model] = model_results

        return results

    async def compare_with_experiment_data(self, experiment_ids: List[int]) -> Dict[int, float]:
        """
        Compare router latency with historical experiment data.

        Args:
            experiment_ids: List of experiment IDs to compare against

        Returns:
            Dictionary mapping experiment IDs to their average latency
        """
        return await self.latency_dataloader.load_many(experiment_ids)

    def generate_recommendations(self, results: Dict[str, Dict[str, float]]) -> List[str]:
        """
        Generate tuning recommendations based on latency analysis.

        Args:
            results: Analysis results from analyze_latency()

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Identify slowest models
        if results:
            slowest_model = max(results.items(), key=lambda x: x[1]['avg_time'])
            recommendations.append(
                f"Consider reducing keep_alive for {slowest_model[0]} "
                f"as it has the highest average latency ({slowest_model[1]['avg_time']:.2f}s)"
            )

            # Check for significant variance
            variances = {
                model: data['max_time'] - data['min_time']
                for model, data in results.items()
            }
            high_variance_models = [m for m, v in variances.items() if v > 2.0]  # 2s threshold
            if high_variance_models:
                recommendations.append(
                    f"Investigate concurrency issues for models with high latency variance: "
                    f"{', '.join(high_variance_models)}"
                )

        return recommendations

async def run_analysis(db_session_factory: DbSessionFactory):
    """
    Example usage of the ModelRouterLatencyAnalyzer.
    """
    analyzer = ModelRouterLatencyAnalyzer(db_session_factory)

    # Sample test prompts
    test_prompts = [
        "Analyze the performance characteristics of the model router",
        "What are the key factors affecting response latency?",
        "Compare the execution times of local vs cloud models"
    ]

    # Models to test (should include both local and cloud endpoints)
    models_to_test = [
        "ollama:local-model-1",
        "openrouter:cloud-model-1",
        "ollama:local-model-2",
        "openrouter:cloud-model-2"
    ]

    # Run latency analysis
    latency_results = await analyzer.analyze_latency(test_prompts, models_to_test)
    print("Latency Analysis Results:")
    for model, metrics in latency_results.items():
        print(f"\nModel: {model}")
        print(f"  Average Time: {metrics['avg_time']:.2f}s")
        print(f"  Min Time: {metrics['min_time']:.2f}s")
        print(f"  Max Time: {metrics['max_time']:.2f}s")
        print(f"  Total Time: {metrics['total_time']:.2f}s")
        print(f"  Requests: {metrics['count']}")

    # Generate recommendations
    recommendations = analyzer.generate_recommendations(latency_results)
    print("\nRecommendations:")
    for rec in recommendations:
        print(f"- {rec}")

    # Compare with historical data (example experiment IDs)
    experiment_data = await analyzer.compare_with_experiment_data([1, 2, 3])
    print("\nHistorical Experiment Data Comparison:")
    for exp_id, avg_latency in experiment_data.items():
        print(f"Experiment {exp_id}: {avg_latency:.2f}ms average latency")
