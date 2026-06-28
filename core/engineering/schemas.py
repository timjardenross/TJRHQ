"""
Data schemas for the Engineering Workflow Router.

All inputs and outputs are plain dataclasses — no external dependencies.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ExecutionMode(str, Enum):
    PLAN = "plan"
    PATCH = "patch"
    REVIEW = "review"
    FULL_FILE = "full_file"  # return complete file contents (mechanically diffed/committed)


class Backend(str, Enum):
    ROUTER = "router"     # Model Router :8891 — single gateway (preferred)
    MISTRAL = "mistral"
    VM_OLLAMA = "vm-ollama"
    GEMINI = "gemini"
    GLM = "glm"
    KIMI = "kimi"   # Kimi K2 (Code) via Ollama Cloud — engineering planning
    QWEN = "qwen"   # Qwen3-Coder via Ollama Cloud — patch / code generation


@dataclass
class MissionContext:
    """Minimal mission context extracted from Number One work_queue.json."""
    mission_id: str
    title: str
    priority: str
    status: str
    next_action: str
    assigned_specialist: str
    blockers: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class RouterRequest:
    """Input to the engineering router."""
    mission_id: str
    mode: ExecutionMode
    backend: Backend
    model: Optional[str]        # for vm-ollama; None → default
    mission_context: MissionContext
    extra_context: str = ""     # free-text appended to prompt


@dataclass
class RouterResponse:
    """Output from the engineering router."""
    mission_id: str
    mode: str
    backend: str
    model_used: str
    provider_label: str
    timestamp_utc: str
    prompt_sent: str
    raw_response: str
    output_text: str
    success: bool
    error: Optional[str] = None
    warnings: Optional[list] = None  # anti-hallucination flags

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @staticmethod
    def now_utc() -> str:
        return datetime.now(timezone.utc).isoformat()
