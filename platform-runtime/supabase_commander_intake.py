"""MSN-0011A — Supabase Commander Intake for Slack.

Bridges the Slack bot to the full Decision Intelligence pipeline
(tools/supabase/collaborative_specialist_runtime.py) via subprocess.

Design principles:
  - subprocess isolation: the Supabase Commander has its own sys.path,
    Ollama dependencies, and Supabase client — running it as a subprocess
    avoids import conflicts with the Slack bot's own runtime.
  - Silent on startup: no Supabase or Ollama connection is made until a
    Commander-directed message is received.
  - Always returns a string: callers never see an exception.
  - Clear logging on every stage.

Public API:
  is_commander_directed(text: str) -> bool
  run_supabase_commander(question: str, timeout_s: int = ...) -> str
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Path to the collaborative_specialist_runtime.py entry point
_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "tools" / "supabase"
_RUNTIME_SCRIPT = _RUNTIME_DIR / "collaborative_specialist_runtime.py"

# Timeout: Commander synthesis with local LLMs can take 60–120 s
_DEFAULT_TIMEOUT_S = int(os.getenv("COMMANDER_SLACK_TIMEOUT_S", "120"))

# Prefix written at the top of every Commander response in Slack
_SLACK_HEADER = ":ship: *Starship Endeavour — Executive Officer Decision Intelligence*"

# Lines printed by collaborative_specialist_runtime after the synthesis text
_TRAILER_PREFIXES = (
    "Collaboration log:",
    "Decision register:",
    "Runtime latency:",
    "[paperclip]",
    "Warning:",
)


# ---------------------------------------------------------------------------
# Trigger detection
# ---------------------------------------------------------------------------

def is_commander_directed(text: str) -> bool:
    """Return True if the cleaned text starts with the 'commander:' prefix.

    Matches case-insensitively. Leading whitespace is ignored.
    Only the prefix form is matched — e.g. "ask the commander:" (mid-sentence)
    does NOT trigger to avoid false positives.

    Examples:
        "commander: should we prioritise X?"   → True
        "Commander: what is the bottleneck?"   → True
        "COMMANDER:go"                         → True
        "decision: we choose X"                → False
        "what should the commander do?"        → False
    """
    return text.strip().lower().startswith("commander:")


# ---------------------------------------------------------------------------
# Subprocess runner
# ---------------------------------------------------------------------------

def run_supabase_commander(
    question: str,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> str:
    """Invoke collaborative_specialist_runtime.py and return the synthesis text.

    Args:
        question: The cleaned question text (without 'commander:' prefix).
        timeout_s: Subprocess timeout in seconds. Defaults to COMMANDER_SLACK_TIMEOUT_S
                   env var (120s if not set).

    Returns:
        Commander synthesis as a string — always. Never raises.
    """
    if not _RUNTIME_SCRIPT.exists():
        log.error(
            "[commander-intake] Runtime script not found: %s — is tools/supabase/ present?",
            _RUNTIME_SCRIPT,
        )
        return _unavailable_fallback(question, f"Runtime script not found at {_RUNTIME_SCRIPT}")

    python = sys.executable
    cmd = [python, str(_RUNTIME_SCRIPT), question]

    log.info(
        "[commander-intake] Dispatching to Supabase Commander: %r (timeout=%ds)",
        question[:100],
        timeout_s,
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(_RUNTIME_DIR),
            env={**os.environ},
        )
    except subprocess.TimeoutExpired:
        log.error(
            "[commander-intake] Commander runtime timed out after %ds for: %r",
            timeout_s,
            question[:80],
        )
        return _timeout_fallback(question, timeout_s)
    except Exception as exc:
        log.error(
            "[commander-intake] Subprocess launch failed: %s — %s",
            type(exc).__name__,
            exc,
        )
        return _unavailable_fallback(question, f"{type(exc).__name__}: {exc}")

    if result.returncode != 0:
        stderr_excerpt = (result.stderr or "").strip()[:400]
        log.error(
            "[commander-intake] Runtime exited %d. stderr: %s",
            result.returncode,
            stderr_excerpt,
        )
        return _error_fallback(question, result.returncode, stderr_excerpt)

    synthesis = _extract_synthesis(result.stdout)
    log.info(
        "[commander-intake] Synthesis received: %d chars",
        len(synthesis),
    )
    return f"{_SLACK_HEADER}\n\n{synthesis}"


# ---------------------------------------------------------------------------
# Output extraction
# ---------------------------------------------------------------------------

def _extract_synthesis(stdout: str) -> str:
    """Strip trailing runtime metadata lines from subprocess stdout.

    collaborative_specialist_runtime.py prints:
        <synthesis text — can be many lines>

        Collaboration log: /path/to/log.json
        Decision register: /path/to/decision.json   (optional)
        Runtime latency: 1234.56ms

    We drop everything from the first trailer prefix onward.
    """
    if not stdout:
        log.warning("[commander-intake] Runtime produced empty stdout")
        return "_Commander synthesis was empty. Check runtime logs or Ollama availability._"

    lines = stdout.splitlines()
    trimmed: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if any(stripped.startswith(prefix) for prefix in _TRAILER_PREFIXES):
            break
        trimmed.append(line)

    synthesis = "\n".join(trimmed).strip()
    return synthesis or stdout.strip()


# ---------------------------------------------------------------------------
# Fallback messages
# ---------------------------------------------------------------------------

def _unavailable_fallback(question: str, reason: str) -> str:
    q = question[:120]
    return (
        f"{_SLACK_HEADER}\n\n"
        f":warning: Commander is temporarily unavailable.\n"
        f"*Question received:* _{q}_\n"
        f"*Reason:* {reason}\n\n"
        "Retry once Ollama and the Supabase runtime are available, "
        "or escalate to Executive Officer (XO)."
    )


def _timeout_fallback(question: str, timeout_s: int) -> str:
    q = question[:120]
    return (
        f"{_SLACK_HEADER}\n\n"
        f":hourglass: Commander synthesis timed out after *{timeout_s}s*.\n"
        f"*Question:* _{q}_\n\n"
        f"The question may require a longer timeout or a lighter model. "
        f"Set `COMMANDER_SLACK_TIMEOUT_S` (currently {timeout_s}s) in `.env` to adjust."
    )


def _error_fallback(question: str, returncode: int, stderr: str) -> str:
    q = question[:120]
    detail = f"\n*Detail:* `{stderr[:300]}`" if stderr else ""
    return (
        f"{_SLACK_HEADER}\n\n"
        f":x: Commander runtime exited with code *{returncode}*.\n"
        f"*Question:* _{q}_{detail}\n\n"
        "Check runtime logs or run the Commander CLI manually to diagnose:\n"
        f"`python3 tools/supabase/collaborative_specialist_runtime.py \"<question>\"`"
    )
