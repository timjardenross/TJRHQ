#!/usr/bin/env python3
"""
MSN-0060B Phase B1E: Quality Forecasting Service

Forecasts provider effectiveness and detects anomalies.

Design: Minimal MVP
- Time-series effectiveness forecasting (5-10 decisions ahead)
- Statistical trend analysis (linear regression, confidence bands)
- Anomaly detection (z-score based)
- Forecast confidence levels

Authority Model:
- Forecasts are advisory (inform routing, not enforce)
- Confidence levels communicated in all routing decisions
- Anomalies trigger alerts but don't block operations
- Extensible for B1F predictive automation

Public API:
    forecasting = QualityForecasting(supabase_client)
    forecast = forecasting.forecast_effectiveness(provider_name)
    anomaly = forecasting.detect_anomalies(provider_name, recent_score)
    routing = forecasting.suggest_proactive_routing()
"""

from __future__ import annotations

import os
import logging
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from enum import Enum

log = logging.getLogger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================

class ConfidenceLevel(Enum):
    """Forecast confidence based on data volume."""
    LOW = "low"        # <10 decisions
    MEDIUM = "medium"  # 10-20 decisions
    HIGH = "high"      # 20+ decisions


class AnomalyType(Enum):
    """Types of anomalies detected."""
    OUTLIER = "outlier"              # Single unusual score
    DEGRADATION = "degradation"      # Sustained quality drop
    TREND_CHANGE = "trend_change"    # Direction reversal


class AnomalySeverity(Enum):
    """Anomaly severity levels."""
    LOW = "low"        # |z| 2.0-2.5 (95% confidence)
    MEDIUM = "medium"  # |z| 2.5-3.0 (99% confidence)
    HIGH = "high"      # |z| > 3.0 (99.7% confidence)


class TrendDirection(Enum):
    """Quality trend direction."""
    UP = "up"          # Improving
    DOWN = "down"      # Declining
    STABLE = "stable"  # Consistent


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class EffectivenessForecast:
    """Forecast of provider effectiveness."""
    provider_name: str
    model_name: Optional[str]
    provider_route: Optional[str]

    # Forecast details
    forecast_horizon: int              # Decisions ahead (e.g., 5)
    predicted_effectiveness: float     # Forecasted score (1.0-5.0)
    confidence_level: str              # high, medium, low
    confidence_band_lower: float       # Lower bound (1.0-5.0)
    confidence_band_upper: float       # Upper bound (1.0-5.0)

    # Trend information
    trend_direction: str               # up, down, stable
    trend_persistence: float           # 0-1, likelihood trend continues

    # Quality metrics
    forecast_accuracy: float           # R² from regression
    decisions_used: int                # Data points in forecast

    # Metadata
    forecast_id: str = field(default_factory=lambda: "")
    forecast_timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_at: Optional[str] = None


@dataclass
class AnomalyDetection:
    """Detected anomaly in quality scores."""
    provider_name: str
    model_name: Optional[str]
    provider_route: Optional[str]

    # Anomaly details
    score_id: str
    score_value: float
    anomaly_type: str           # outlier, trend_change, degradation
    z_score: float              # Standard deviations from mean
    severity: str               # low, medium, high

    # Metadata
    anomaly_id: str = field(default_factory=lambda: "")
    detected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_at: Optional[str] = None


@dataclass
class TrendPersistence:
    """Trend persistence analysis."""
    provider_name: str
    trend_direction: str           # up, down, stable
    persistence_score: float       # 0-1
    consecutive_decisions: int     # Decisions moving with trend
    likelihood_continues: float    # 0-1 probability trend continues


@dataclass
class ProviderForecast:
    """Complete forecast for a provider."""
    provider_name: str
    effectiveness_forecast: EffectivenessForecast
    trend_persistence: TrendPersistence
    recent_anomalies: list = field(default_factory=list)

    def is_high_confidence(self) -> bool:
        """Check if forecast has high confidence."""
        return self.effectiveness_forecast.confidence_level == "high"

    def forecast_direction(self) -> str:
        """Determine if forecast shows improvement/decline vs. current."""
        if self.effectiveness_forecast.predicted_effectiveness > 4.0:
            return "improving"
        elif self.effectiveness_forecast.predicted_effectiveness < 3.0:
            return "declining"
        else:
            return "stable"


# ============================================================================
# Quality Forecasting Service
# ============================================================================

class QualityForecasting:
    """
    Service for forecasting provider effectiveness and detecting anomalies.

    B1E Phase: Enables proactive routing decisions based on forecasts.
    """

    # Thresholds
    ANOMALY_Z_THRESHOLD = 2.0          # 95% confidence threshold
    ANOMALY_Z_SEVERE = 3.0             # 99.7% confidence (high severity)
    MIN_DECISIONS_FOR_FORECAST = 5     # Minimum data points needed
    FORECAST_HORIZON = 5               # Decisions to forecast ahead

    # Confidence levels by decision count
    MIN_DECISIONS_HIGH_CONFIDENCE = 20
    MIN_DECISIONS_MEDIUM_CONFIDENCE = 10

    def __init__(self, supabase_client=None):
        """
        Initialize quality forecasting service.

        Args:
            supabase_client: Supabase client (optional, can be set later)
        """
        self.supabase_client = supabase_client
        log.info("[quality-forecasting] QualityForecasting service initialized")

    def forecast_effectiveness(
        self,
        provider_name: str,
        model_name: Optional[str] = None,
        provider_route: Optional[str] = None,
        horizon: int = FORECAST_HORIZON,
    ) -> Optional[EffectivenessForecast]:
        """
        Forecast provider effectiveness for next N decisions.

        MSN-0060B B1E: Predict future quality based on historical trend.

        Args:
            provider_name: AI provider (Google, OpenRouter, Ollama)
            model_name: Optional model name (Gemini, Mistral, Qwen)
            provider_route: Optional routing strategy (Primary, Fallback, Local)
            horizon: Decisions to forecast ahead (default: 5)

        Returns:
            EffectivenessForecast if successful, None if insufficient data
        """

        if not self.supabase_client:
            log.warning("[quality-forecasting] Supabase client not configured")
            return None

        try:
            # Retrieve quality scores for provider
            response = (
                self.supabase_client.table("quality_scores")
                .select("effectiveness_score, scored_at")
                .eq("provider_name", provider_name)
                .eq("model_name", model_name) if model_name else True
                .eq("provider_route", provider_route) if provider_route else True
                .order("scored_at", desc=False)
                .execute()
            )

            scores_data = response.data or []

            if len(scores_data) < self.MIN_DECISIONS_FOR_FORECAST:
                log.debug(
                    f"[quality-forecasting] Insufficient data for {provider_name}: "
                    f"{len(scores_data)} decisions (need {self.MIN_DECISIONS_FOR_FORECAST})"
                )
                return None

            # Extract effectiveness scores
            scores = [
                s["effectiveness_score"] for s in scores_data
                if s["effectiveness_score"] is not None
            ]

            if len(scores) < self.MIN_DECISIONS_FOR_FORECAST:
                log.debug(f"[quality-forecasting] Not enough valid scores for {provider_name}")
                return None

            # Fit linear regression model
            x = np.arange(len(scores))
            y = np.array(scores)

            # Linear regression: y = m*x + b
            coeffs = np.polyfit(x, y, 1)
            slope = coeffs[0]
            intercept = coeffs[1]

            # Calculate R² (quality of fit)
            y_pred = np.polyval(coeffs, x)
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            # Forecast next N decisions
            total_decisions = len(scores)
            forecast_indices = np.arange(total_decisions, total_decisions + horizon)
            forecast_values = np.polyval(coeffs, forecast_indices)

            # Clamp to effectiveness scale (1.0-5.0)
            forecast_values = np.clip(forecast_values, 1.0, 5.0)

            # Calculate confidence interval
            std_error = np.sqrt(ss_res / (len(scores) - 2)) if len(scores) > 2 else 0
            # Use t-distribution critical value (approximate)
            t_critical = 2.0  # Simplified (normally varies by degrees of freedom)
            margin_of_error = t_critical * std_error

            confidence_lower = np.clip(forecast_values[0] - margin_of_error, 1.0, 5.0)
            confidence_upper = np.clip(forecast_values[0] + margin_of_error, 1.0, 5.0)

            # Determine trend direction
            if slope > 0.1:
                trend_direction = TrendDirection.UP.value
            elif slope < -0.1:
                trend_direction = TrendDirection.DOWN.value
            else:
                trend_direction = TrendDirection.STABLE.value

            # Calculate trend persistence
            trend_persistence = self._calculate_trend_persistence(scores, slope)

            # Determine confidence level
            confidence_level = self._get_confidence_level(len(scores))

            # Create forecast
            forecast_id = self._generate_forecast_id()
            forecast = EffectivenessForecast(
                provider_name=provider_name,
                model_name=model_name,
                provider_route=provider_route,
                forecast_horizon=horizon,
                predicted_effectiveness=round(forecast_values[0], 1),
                confidence_level=confidence_level,
                confidence_band_lower=round(confidence_lower, 1),
                confidence_band_upper=round(confidence_upper, 1),
                trend_direction=trend_direction,
                trend_persistence=round(trend_persistence, 2),
                forecast_accuracy=round(r_squared, 2),
                decisions_used=len(scores),
                forecast_id=forecast_id,
            )

            log.info(
                f"[quality-forecasting] Forecast generated: {forecast_id}, "
                f"provider={provider_name}, predicted={forecast.predicted_effectiveness:.1f}, "
                f"confidence={confidence_level}, trend={trend_direction}"
            )

            return forecast

        except Exception as e:
            log.error(
                f"[quality-forecasting] Failed to forecast effectiveness: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return None

    def detect_anomalies(
        self,
        provider_name: str,
        recent_score: float,
        model_name: Optional[str] = None,
        provider_route: Optional[str] = None,
        score_id: Optional[str] = None,
    ) -> Optional[AnomalyDetection]:
        """
        Detect if recent score is anomalous.

        MSN-0060B B1E: Identify outliers and quality degradation.

        Args:
            provider_name: AI provider
            recent_score: Quality score to check (1.0-5.0)
            model_name: Optional model name
            provider_route: Optional routing strategy
            score_id: Optional quality_scores ID for reference

        Returns:
            AnomalyDetection if anomaly detected, None otherwise
        """

        if not self.supabase_client:
            log.warning("[quality-forecasting] Supabase client not configured")
            return None

        try:
            # Retrieve historical quality scores
            response = (
                self.supabase_client.table("quality_scores")
                .select("effectiveness_score")
                .eq("provider_name", provider_name)
                .execute()
            )

            historical_scores = [
                s["effectiveness_score"] for s in (response.data or [])
                if s["effectiveness_score"] is not None
            ]

            if len(historical_scores) < 3:
                log.debug(
                    f"[quality-forecasting] Insufficient historical data for anomaly detection: "
                    f"{provider_name} ({len(historical_scores)} scores)"
                )
                return None

            # Calculate mean and standard deviation
            mean = np.mean(historical_scores)
            std_dev = np.std(historical_scores)

            if std_dev == 0:
                log.debug(f"[quality-forecasting] No variance in {provider_name} scores")
                return None

            # Calculate z-score
            z_score = (recent_score - mean) / std_dev

            # Check if anomalous
            if abs(z_score) < self.ANOMALY_Z_THRESHOLD:
                return None  # Not anomalous

            # Classify anomaly type and severity
            if z_score < -self.ANOMALY_Z_THRESHOLD:
                anomaly_type = AnomalyType.DEGRADATION.value
            else:
                anomaly_type = AnomalyType.OUTLIER.value

            if abs(z_score) > self.ANOMALY_Z_SEVERE:
                severity = AnomalySeverity.HIGH.value
            elif abs(z_score) > 2.5:
                severity = AnomalySeverity.MEDIUM.value
            else:
                severity = AnomalySeverity.LOW.value

            # Create anomaly record
            anomaly_id = self._generate_anomaly_id()
            anomaly = AnomalyDetection(
                provider_name=provider_name,
                model_name=model_name,
                provider_route=provider_route,
                score_id=score_id or f"UNKNOWN-{datetime.utcnow().isoformat()}",
                score_value=recent_score,
                anomaly_type=anomaly_type,
                z_score=round(z_score, 2),
                severity=severity,
                anomaly_id=anomaly_id,
            )

            log.warning(
                f"[quality-forecasting] Anomaly detected: {anomaly_id}, "
                f"provider={provider_name}, type={anomaly_type}, "
                f"severity={severity}, z_score={z_score:.2f}"
            )

            return anomaly

        except Exception as e:
            log.error(
                f"[quality-forecasting] Failed to detect anomalies: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return None

    def analyze_trend_persistence(
        self,
        provider_name: str,
    ) -> Optional[TrendPersistence]:
        """
        Analyze trend persistence and likelihood.

        MSN-0060B B1E: Determine probability trend continues.

        Args:
            provider_name: AI provider name

        Returns:
            TrendPersistence record with persistence metrics
        """

        if not self.supabase_client:
            log.warning("[quality-forecasting] Supabase client not configured")
            return None

        try:
            # Retrieve quality scores
            response = (
                self.supabase_client.table("quality_scores")
                .select("effectiveness_score")
                .eq("provider_name", provider_name)
                .order("scored_at", desc=False)
                .execute()
            )

            scores_data = response.data or []
            scores = [
                s["effectiveness_score"] for s in scores_data
                if s["effectiveness_score"] is not None
            ]

            if len(scores) < 5:
                log.debug(f"[quality-forecasting] Insufficient data for trend analysis: {provider_name}")
                return None

            # Split into old and recent
            split_point = len(scores) // 2
            old_scores = scores[:split_point]
            recent_scores = scores[split_point:]

            old_avg = np.mean(old_scores)
            recent_avg = np.mean(recent_scores)

            # Determine trend direction
            if recent_avg > old_avg + 0.1:
                trend_direction = TrendDirection.UP.value
            elif recent_avg < old_avg - 0.1:
                trend_direction = TrendDirection.DOWN.value
            else:
                trend_direction = TrendDirection.STABLE.value

            # Calculate persistence
            if trend_direction == TrendDirection.UP.value:
                moving_with_trend = sum(1 for i in range(1, len(recent_scores))
                                       if recent_scores[i] >= recent_scores[i-1])
            elif trend_direction == TrendDirection.DOWN.value:
                moving_with_trend = sum(1 for i in range(1, len(recent_scores))
                                       if recent_scores[i] <= recent_scores[i-1])
            else:
                moving_with_trend = 0

            persistence_score = moving_with_trend / max(1, len(recent_scores) - 1)

            # Confidence based on sample size
            confidence_factor = min(1.0, len(scores) / self.MIN_DECISIONS_HIGH_CONFIDENCE)

            likelihood_continues = persistence_score * confidence_factor

            persistence = TrendPersistence(
                provider_name=provider_name,
                trend_direction=trend_direction,
                persistence_score=round(persistence_score, 2),
                consecutive_decisions=moving_with_trend,
                likelihood_continues=round(likelihood_continues, 2),
            )

            log.info(
                f"[quality-forecasting] Trend persistence analyzed: {provider_name}, "
                f"direction={trend_direction}, persistence={persistence_score:.2f}, "
                f"likelihood={likelihood_continues:.2f}"
            )

            return persistence

        except Exception as e:
            log.error(
                f"[quality-forecasting] Failed to analyze trend: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return None

    def get_quality_forecast(
        self,
        provider_name: str,
    ) -> Optional[ProviderForecast]:
        """
        Get complete forecast for provider.

        Args:
            provider_name: AI provider name

        Returns:
            ProviderForecast with all forecasting data
        """

        forecast = self.forecast_effectiveness(provider_name)
        if not forecast:
            return None

        persistence = self.analyze_trend_persistence(provider_name)
        if not persistence:
            return None

        # Get recent anomalies
        recent_anomalies = []  # TODO: Query quality_anomalies table

        return ProviderForecast(
            provider_name=provider_name,
            effectiveness_forecast=forecast,
            trend_persistence=persistence,
            recent_anomalies=recent_anomalies,
        )

    def suggest_proactive_routing(self) -> list:
        """
        Suggest proactive routing based on forecasts.

        Returns:
            List of (provider_name, forecast_score, confidence) tuples
        """

        if not self.supabase_client:
            log.error("[quality-forecasting] Supabase client not configured")
            return []

        try:
            # Get list of providers from v_provider_quality_trend
            response = (
                self.supabase_client.table("v_provider_quality_trend")
                .select("provider_name")
                .execute()
            )

            providers = list(set(p["provider_name"] for p in (response.data or [])))

            routing_order = []

            for provider in providers:
                forecast = self.forecast_effectiveness(provider)
                if forecast:
                    routing_order.append((provider, forecast.predicted_effectiveness, forecast.confidence_level))

            # Sort by predicted effectiveness (descending)
            routing_order.sort(key=lambda x: x[1], reverse=True)

            log.debug(
                f"[quality-forecasting] Proactive routing suggested: "
                f"{[p[0] for p in routing_order]}"
            )

            return routing_order

        except Exception as e:
            log.error(
                f"[quality-forecasting] Failed to suggest routing: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            return []

    # Private helper methods

    def _calculate_trend_persistence(self, scores: list, slope: float) -> float:
        """Calculate probability trend persists."""
        if len(scores) < 2:
            return 0.0

        if abs(slope) < 0.01:
            return 0.5  # No trend

        # Count decisions moving with trend
        moving = 0
        for i in range(1, len(scores)):
            if slope > 0 and scores[i] >= scores[i-1]:
                moving += 1
            elif slope < 0 and scores[i] <= scores[i-1]:
                moving += 1

        persistence = moving / (len(scores) - 1)
        return min(1.0, persistence * abs(slope) * 10)  # Weight by slope strength

    def _get_confidence_level(self, decisions_count: int) -> str:
        """Determine confidence level based on sample size."""
        if decisions_count >= self.MIN_DECISIONS_HIGH_CONFIDENCE:
            return ConfidenceLevel.HIGH.value
        elif decisions_count >= self.MIN_DECISIONS_MEDIUM_CONFIDENCE:
            return ConfidenceLevel.MEDIUM.value
        else:
            return ConfidenceLevel.LOW.value

    def _generate_forecast_id(self) -> str:
        """Generate forecast ID: FOR-YYYYMMDD-HHMMSS."""
        now = datetime.utcnow()
        return now.strftime("FOR-%Y%m%d-%H%M%S")

    def _generate_anomaly_id(self) -> str:
        """Generate anomaly ID: ANO-YYYYMMDD-HHMMSS."""
        now = datetime.utcnow()
        return now.strftime("ANO-%Y%m%d-%H%M%S")
