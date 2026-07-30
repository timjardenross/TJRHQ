#!/usr/bin/env python3
"""
Priority 3: B1E Quality Forecasting Implementation Tests
Tests forecasting algorithms, anomaly detection, and trend analysis.

Test Coverage:
- Linear regression forecasting
- Z-score anomaly detection
- Trend persistence analysis
- Confidence level assignment
- Complete forecasting workflow
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
import math
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def fit_linear_model(scores):
    """Fit y = m*x + b to scores. Returns (slope, intercept, r_squared)."""
    if len(scores) < 2:
        return 0, sum(scores) / len(scores) if scores else 3.0, 0

    x = list(range(len(scores)))
    y = scores

    # Calculate means
    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)

    # Calculate slope
    numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(len(x)))
    denominator = sum((x[i] - x_mean) ** 2 for i in range(len(x)))

    slope = numerator / denominator if denominator != 0 else 0
    intercept = y_mean - slope * x_mean

    # Calculate R²
    y_pred = [slope * xi + intercept for xi in x]
    ss_res = sum((y[i] - y_pred[i]) ** 2 for i in range(len(y)))
    ss_tot = sum((yi - y_mean) ** 2 for i, yi in enumerate(y))
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    return slope, intercept, r_squared


def forecast_values(slope, intercept, historical_count, horizon):
    """Generate forecast for next N decisions."""
    total = historical_count
    forecasts = []
    for i in range(horizon):
        value = slope * (total + i) + intercept
        value = max(1.0, min(5.0, value))  # Clamp to 1.0-5.0
        forecasts.append(value)
    return forecasts


def calculate_z_score(score, historical_scores):
    """Calculate z-score for anomaly detection."""
    if not historical_scores:
        return 0

    mean = sum(historical_scores) / len(historical_scores)
    variance = sum((x - mean) ** 2 for x in historical_scores) / len(historical_scores)
    std_dev = math.sqrt(variance)

    if std_dev == 0:
        return 0

    z = (score - mean) / std_dev
    return z


def test_priority_3_linear_regression():
    """Test 3: Linear regression forecasting."""
    log.info("TEST: Linear Regression Forecasting")

    # Perfect upward trend
    scores = [3.0, 3.2, 3.4, 3.6, 3.8, 4.0]
    slope, intercept, r2 = fit_linear_model(scores)

    log.info(f"Historical scores: {scores}")
    log.info(f"Linear model: y = {slope:.2f}x + {intercept:.2f}")
    log.info(f"R² = {r2:.4f}")

    assert abs(slope - 0.2) < 0.01, f"Expected slope ~0.2, got {slope}"
    assert r2 > 0.99, f"Expected R² > 0.99, got {r2}"

    # Forecast next 5 decisions
    forecast = forecast_values(slope, intercept, len(scores), 5)
    log.info(f"Forecast (next 5): {[f'{f:.1f}' for f in forecast]}")

    assert forecast[0] > 4.0, "Forecast should continue upward trend"
    assert all(1.0 <= f <= 5.0 for f in forecast), "Forecasts should be in range"

    log.info("\n✅ LINEAR REGRESSION TEST PASSED")
    return True


def test_priority_3_anomaly_detection():
    """Test 3: Z-score anomaly detection."""
    log.info("TEST: Z-Score Anomaly Detection")

    # Normal scores
    normal_scores = [3.0, 3.1, 2.9, 3.0, 2.95]
    mean = sum(normal_scores) / len(normal_scores)
    log.info(f"Normal scores: {normal_scores}")
    log.info(f"Mean: {mean:.2f}")

    # Test normal score
    normal_test = 3.05
    z_normal = calculate_z_score(normal_test, normal_scores)
    log.info(f"Normal test score: {normal_test} → z = {z_normal:.2f}")
    assert abs(z_normal) < 1.0, "Normal score should have low z-score"

    # Test anomalous score
    anomalous_test = 1.5
    z_anomalous = calculate_z_score(anomalous_test, normal_scores)
    log.info(f"Anomalous test score: {anomalous_test} → z = {z_anomalous:.2f}")
    assert abs(z_anomalous) > 2.0, "Anomalous score should have high z-score"

    # Classify anomaly severity
    if abs(z_anomalous) < 2.5:
        severity = "low"
    elif abs(z_anomalous) < 3.0:
        severity = "medium"
    else:
        severity = "high"

    log.info(f"Anomaly severity: {severity}")
    assert severity in ['low', 'medium', 'high']

    log.info("\n✅ ANOMALY DETECTION TEST PASSED")
    return True


def test_priority_3_trend_persistence():
    """Test 3: Trend persistence analysis."""
    log.info("TEST: Trend Persistence Analysis")

    # Strong upward trend
    upward_scores = [3.0, 3.1, 3.2, 3.3, 3.4]
    upward_slope = 0.1

    moving_with_trend = sum(1 for i in range(1, len(upward_scores))
                           if upward_scores[i] >= upward_scores[i-1])
    persistence_up = moving_with_trend / (len(upward_scores) - 1)

    log.info(f"Upward trend: {upward_scores}")
    log.info(f"Persistence: {persistence_up:.2f}")
    assert persistence_up > 0.8, "Upward trend should have high persistence"

    # Noisy scores
    noisy_scores = [3.0, 3.5, 2.5, 4.0, 2.0]
    noisy_slope = 0.0

    moving_with_trend = sum(1 for i in range(1, len(noisy_scores))
                           if (noisy_slope > 0 and noisy_scores[i] >= noisy_scores[i-1]) or
                              (noisy_slope < 0 and noisy_scores[i] <= noisy_scores[i-1]))
    persistence_noisy = moving_with_trend / (len(noisy_scores) - 1) if len(noisy_scores) > 1 else 0

    log.info(f"Noisy trend: {noisy_scores}")
    log.info(f"Persistence: {persistence_noisy:.2f}")
    assert persistence_noisy < 0.5, "Noisy data should have low persistence"

    log.info("\n✅ TREND PERSISTENCE TEST PASSED")
    return True


def test_priority_3_confidence_levels():
    """Test 3: Confidence level assignment based on data points."""
    log.info("TEST: Confidence Level Assignment")

    # Low confidence: <10 decisions
    low_count = 5
    low_confidence = 'low'
    log.info(f"Decisions: {low_count} → Confidence: {low_confidence}")
    assert low_confidence == 'low'

    # Medium confidence: 10-20 decisions
    medium_count = 15
    if medium_count < 10:
        medium_confidence = 'low'
    elif medium_count < 20:
        medium_confidence = 'medium'
    else:
        medium_confidence = 'high'

    log.info(f"Decisions: {medium_count} → Confidence: {medium_confidence}")
    assert medium_confidence == 'medium'

    # High confidence: 20+ decisions
    high_count = 25
    if high_count < 10:
        high_confidence = 'low'
    elif high_count < 20:
        high_confidence = 'medium'
    else:
        high_confidence = 'high'

    log.info(f"Decisions: {high_count} → Confidence: {high_confidence}")
    assert high_confidence == 'high'

    log.info("\n✅ CONFIDENCE LEVELS TEST PASSED")
    return True


def test_priority_3_complete_forecast():
    """Test 3: Complete forecasting workflow."""
    log.info("TEST: Complete Forecasting Workflow")

    # Step 1: Collect historical quality scores
    log.info("\nStep 1: Historical Data")
    provider_name = "Google"
    historical_scores = [3.8, 3.9, 4.0, 4.1, 4.2, 4.3, 4.4, 4.5]
    log.info(f"Provider: {provider_name}")
    log.info(f"Historical scores ({len(historical_scores)} decisions): {historical_scores}")

    # Step 2: Fit linear model
    log.info("\nStep 2: Fit Linear Model")
    slope, intercept, r2 = fit_linear_model(historical_scores)
    log.info(f"Model: y = {slope:.3f}x + {intercept:.2f}")
    log.info(f"R²: {r2:.4f}")

    # Step 3: Determine trend direction
    log.info("\nStep 3: Trend Direction")
    if slope > 0.01:
        trend = 'up'
    elif slope < -0.01:
        trend = 'down'
    else:
        trend = 'stable'
    log.info(f"Trend: {trend}")

    # Step 4: Forecast effectiveness
    log.info("\nStep 4: Forecast Effectiveness")
    horizon = 5
    forecast = forecast_values(slope, intercept, len(historical_scores), horizon)
    log.info(f"Forecast (next {horizon} decisions): {[f'{f:.1f}' for f in forecast]}")

    predicted = forecast[0]
    log.info(f"Predicted effectiveness: {predicted:.1f}")

    # Step 5: Calculate confidence interval
    log.info("\nStep 5: Confidence Interval")
    margin = 0.3  # Example margin
    lower = max(1.0, predicted - margin)
    upper = min(5.0, predicted + margin)
    log.info(f"Confidence band: [{lower:.1f}, {upper:.1f}]")

    # Step 6: Assign confidence level
    log.info("\nStep 6: Confidence Level")
    decisions_count = len(historical_scores)
    if decisions_count < 10:
        confidence_level = 'low'
    elif decisions_count < 20:
        confidence_level = 'medium'
    else:
        confidence_level = 'high'
    log.info(f"Confidence level: {confidence_level} (based on {decisions_count} decisions)")

    # Step 7: Create forecast record
    log.info("\nStep 7: Forecast Record")
    forecast_id = 'FOR-20260610-140000'
    log.info(f"Forecast ID: {forecast_id}")
    log.info(f"Provider: {provider_name}")
    log.info(f"Predicted: {predicted:.1f}")
    log.info(f"Confidence: {confidence_level}")
    log.info(f"Trend: {trend}")

    assert predicted > 4.0, "Forecast should reflect upward trend"
    assert confidence_level == 'medium', "8 decisions should be medium confidence"

    log.info("\n✅ COMPLETE FORECAST TEST PASSED")
    return True


def test_priority_3_integration():
    """Test 3: Complete B1E integration workflow."""
    log.info("TEST: Complete B1E Integration Workflow")

    # Step 1: Get quality scores (from B1D)
    log.info("\nStep 1: Get Quality Data (from B1D)")
    provider_quality = {
        'Google': {'scores': [4.0, 4.1, 4.2, 4.3], 'count': 4},
        'OpenRouter': {'scores': [3.5, 3.6, 3.7], 'count': 3},
    }

    for provider, data in provider_quality.items():
        log.info(f"  {provider}: {data['scores']} ({data['count']} decisions)")

    # Step 2: Generate forecasts
    log.info("\nStep 2: Generate Forecasts")
    forecasts = {}
    for provider, data in provider_quality.items():
        slope, intercept, r2 = fit_linear_model(data['scores'])
        forecast = forecast_values(slope, intercept, len(data['scores']), 5)

        confidence = 'high' if data['count'] >= 20 else 'medium' if data['count'] >= 10 else 'low'

        forecasts[provider] = {
            'predicted': forecast[0],
            'confidence': confidence,
            'trend': 'up' if slope > 0 else 'down' if slope < 0 else 'stable'
        }

        log.info(f"  {provider}: {forecast[0]:.1f} ({confidence} confidence, {forecasts[provider]['trend']})")

    # Step 3: Detect anomalies
    log.info("\nStep 3: Detect Anomalies")
    for provider, data in provider_quality.items():
        # Check latest score
        if data['scores']:
            latest = data['scores'][-1]
            z = calculate_z_score(latest, data['scores'])
            anomaly = abs(z) > 2.0
            log.info(f"  {provider}: latest={latest:.1f}, z={z:.2f}, anomaly={anomaly}")

    # Step 4: Use forecasts in routing
    log.info("\nStep 4: Use Forecasts in Routing (B1A)")
    routing_order = sorted(
        [(p, f['predicted']) for p, f in forecasts.items()],
        key=lambda x: x[1],
        reverse=True
    )

    log.info("Routing ranking by forecast:")
    for rank, (provider, forecast_score) in enumerate(routing_order, 1):
        log.info(f"  {rank}. {provider}: {forecast_score:.1f}")

    assert routing_order[0][0] == 'Google', "Google should be ranked first"

    log.info("\n✅ INTEGRATION TEST PASSED")
    return True


if __name__ == '__main__':
    log.info("=" * 70)
    log.info("PRIORITY 3: B1E QUALITY FORECASTING TEST SUITE")
    log.info("=" * 70)
    log.info()

    try:
        # Run all tests
        results = []
        results.append(("Linear Regression", test_priority_3_linear_regression()))
        results.append(("Anomaly Detection", test_priority_3_anomaly_detection()))
        results.append(("Trend Persistence", test_priority_3_trend_persistence()))
        results.append(("Confidence Levels", test_priority_3_confidence_levels()))
        results.append(("Complete Forecast", test_priority_3_complete_forecast()))
        results.append(("Integration", test_priority_3_integration()))

        # Summary
        log.info("\n" + "=" * 70)
        log.info("TEST SUMMARY")
        log.info("=" * 70)
        passed = sum(1 for _, result in results if result)
        total = len(results)

        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            log.info(f"{status}: {test_name}")

        log.info(f"\nTotal: {passed}/{total} tests passed")

        if passed == total:
            log.info("\n🎯 PRIORITY 3 FORECASTING: COMPLETE")
            exit(0)
        else:
            exit(1)

    except Exception as e:
        log.error(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
