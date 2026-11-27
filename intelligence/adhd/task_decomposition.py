"""
ADHD Task Decomposition — break overwhelming tasks into tiny first steps.

Issue 23: Decompose a captured task into a single, concrete micro-action.
Uses grounded LLM call following the same "only use provided text" discipline as brief_generator.

Local model only: task text is private or unclassified, so there is no router, cloud provider or
cloud fallback in this component.

On failure: returns None (UI degrades gracefully, no micro-action suggested).
"""

import logging

from core.llm.provider_chain import call_ollama
from intelligence.config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a task decomposition specialist helping someone with ADHD break down overwhelming tasks into tiny, startable first steps.

Your job: given a task description, propose ONE concrete, small, specific action that could be taken RIGHT NOW to make progress. This action should:
- Be completable in 5–15 minutes
- Require no setup, research, or decision-making
- Be concrete and specific, not abstract
- Not repeat the original task description

Example transformations:
  Input: "Organize the closet"
  Output: "Pull out all the shoes and put them in a pile on the floor"

  Input: "Fix the tax situation"
  Output: "Open the folder labeled '2025 Tax' and read the email from the accountant"

  Input: "Update the project status"
  Output: "Write down three things that happened this week in a text file"

Respond with ONLY the micro-action, nothing else. No preamble, no explanation."""

_FALLBACK_SYSTEM_PROMPT = """You are helping break down an overwhelming task into a concrete first step.
Respond with a single, specific action that could be done in 5-15 minutes."""


class TaskDecomposer:
    """Breaks a task down to one tiny first action. Never raises — returns None on failure."""

    def decompose(self, task_text: str) -> str | None:
        """
        Given task text, returns a single concrete micro-action string, or None if all LLM providers fail.
        """
        if not task_text or not task_text.strip():
            log.warning("TaskDecomposer: empty task text")
            return None

        text = task_text.strip()[:2000]  # Bound to 2k chars like brief_generator

        providers = [
            (OLLAMA_MODEL, self._ollama),
        ]

        for name, fn in providers:
            try:
                result = fn(text)
                if result:
                    log.info("Task decomposed via %s", name)
                    return result
            except Exception as exc:  # noqa: BLE001 - per-provider attempt inside a fallback chain — one provider failing must not abort the chain; already logged
                log.warning("TaskDecomposer %s failed: %s", name, exc)

        log.warning("All decomposition providers failed — no micro-action suggested")
        return None

    # ─── Model Router (tier-0 — local, preferred) ────────────────────────────

    # ─── Ollama (local) ──────────────────────────────────────────────────────

    def _ollama(self, task_text: str) -> str | None:
        """Call Ollama (local fallback)."""
        if not OLLAMA_BASE_URL or not OLLAMA_MODEL:
            raise RuntimeError("OLLAMA_BASE_URL or OLLAMA_MODEL not set")
        return call_ollama(
            local_only=True,
            system_prompt=_FALLBACK_SYSTEM_PROMPT,
            prompt=f"Task: {task_text}",
            base_url=OLLAMA_BASE_URL,
            model=OLLAMA_MODEL,
            temperature=0.5,
            timeout=15,
        ).text


# ── Singleton ─────────────────────────────────────────────────────────────────

_decomposer: TaskDecomposer | None = None


def get_decomposer() -> TaskDecomposer:
    global _decomposer
    if _decomposer is None:
        _decomposer = TaskDecomposer()
    return _decomposer


def decompose_task(task_text: str) -> str | None:
    """Convenience function: decompose a task text string to a micro-action."""
    return get_decomposer().decompose(task_text)
