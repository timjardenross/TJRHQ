"""
Model Warm-up and Keep-Alive Management for Engineering Workflow Router.

Handles pre-loading models and maintaining keep-alive connections to
prevent cold-starts during frequent routing tasks.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional, Dict, List
from datetime import datetime, timedelta

from core.engineering.providers.model_router import call as router_call
from core.platform.operational_state_model import assemble_operational_state
from event_bus import poll_events

log = logging.getLogger(__name__)

# Configuration constants
DEFAULT_WARMUP_INTERVAL = 3600  # 1 hour in seconds
DEFAULT_KEEPALIVE_INTERVAL = 60  # 60 seconds
DEFAULT_WARMUP_PROMPT = "This is a warm-up prompt to initialize the model."

class ModelWarmupManager:
    """Manages model warm-up and keep-alive operations."""

    def __init__(self):
        self.last_warmup: Dict[str, datetime] = {}
        self.keepalive_connections: Dict[str, datetime] = {}
        self.warmup_interval = int(os.getenv("MODEL_WARMUP_INTERVAL", DEFAULT_WARMUP_INTERVAL))
        self.keepalive_interval = int(os.getenv("MODEL_KEEPALIVE_INTERVAL", DEFAULT_KEEPALIVE_INTERVAL))
        self.warmup_prompt = os.getenv("MODEL_WARMUP_PROMPT", DEFAULT_WARMUP_PROMPT)

    def should_warmup(self, model_name: str) -> bool:
        """Determine if a model needs warm-up based on last warm-up time."""
        if model_name not in self.last_warmup:
            return True

        time_since_last = (datetime.now() - self.last_warmup[model_name]).total_seconds()
        return time_since_last >= self.warmup_interval

    def should_keepalive(self, model_name: str) -> bool:
        """Determine if a model needs keep-alive based on last keep-alive time."""
        if model_name not in self.keepalive_connections:
            return True

        time_since_last = (datetime.now() - self.keepalive_connections[model_name]).total_seconds()
        return time_since_last >= self.keepalive_interval

    def warmup_model(self, model_name: str) -> bool:
        """Perform warm-up for a specific model."""
        try:
            log.info(f"Warming up model: {model_name}")
            response, _ = router_call(self.warmup_prompt, model_name)
            self.last_warmup[model_name] = datetime.now()
            log.info(f"Successfully warmed up model: {model_name}")
            return True
        except Exception as e:
            log.error(f"Failed to warm up model {model_name}: {str(e)}")
            return False

    def keepalive_model(self, model_name: str) -> bool:
        """Maintain keep-alive connection for a specific model."""
        try:
            log.debug(f"Sending keep-alive for model: {model_name}")
            response, _ = router_call(self.warmup_prompt, model_name)
            self.keepalive_connections[model_name] = datetime.now()
            return True
        except Exception as e:
            log.error(f"Failed to maintain keep-alive for model {model_name}: {str(e)}")
            return False

    def manage_models(self, models: Optional[List[str]] = None) -> Dict[str, bool]:
        """Manage warm-up and keep-alive for specified models or all active models."""
        results = {}

        if models is None:
            # Get all active models from operational state
            events = poll_events(since=timedelta(hours=24))
            state = assemble_operational_state(events)
            models = [model for model in state.domains.get("engineering-delivery", {}).get("loaded_models", [])]

        for model in models:
            if self.should_warmup(model):
                results[f"warmup_{model}"] = self.warmup_model(model)

            if self.should_keepalive(model):
                results[f"keepalive_{model}"] = self.keepalive_model(model)

        return results

# Singleton instance for global access
model_warmup_manager = ModelWarmupManager()
