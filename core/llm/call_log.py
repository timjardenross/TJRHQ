"""Call log for LOCAL Ollama requests that bypass the model router (USS-TJR-MSN-0412 Stream 6).

The router writes one JSON line per request to core/model-router/call_log.jsonl. About 25 callers
talk to Ollama directly (core.llm.provider_chain.call_ollama, platform-runtime/llm.py) and left no
trace, so the box's real local-inference load could not be seen. This helper writes the same
line shape to the same file, with "source": "direct" and a "caller" so they can be told apart.

Stdlib only. Never raises: a logging failure must not break an LLM call.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "model-router" / "call_log.jsonl"


def _log_path() -> Path:
    return Path(os.environ.get("LLM_DIRECT_CALL_LOG", str(_DEFAULT_PATH)))


def _caller() -> str:
    """Name of the running program, e.g. 'health_signal_curation.py' or a module name."""
    main = sys.modules.get("__main__")
    path = getattr(main, "__file__", None) or (sys.argv[0] if sys.argv else "")
    return os.path.basename(path) or "unknown"


def log_direct_call(
    *,
    model: str,
    duration_ms: int,
    success: bool,
    prompt_len: int,
    response_len: int = 0,
    prompt_eval_count: int | None = None,
    eval_count: int | None = None,
    error: str | None = None,
    task_type: str = "direct-ollama",
) -> None:
    """Append one line in the router's call_log shape. Lengths and counts only, never prompt text."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_type": task_type,
        "model": model,
        "keep_alive": "n/a",
        "duration_ms": duration_ms,
        "escalated": False,
        "escalation_reason": "",
        "route_tier": "n/a",
        "route_reason": "",
        "token_info": {"prompt_eval_count": prompt_eval_count, "eval_count": eval_count},
        "prompt_len": prompt_len,
        "response_len": response_len,
        "success": success,
        "source": "direct",
        "caller": _caller(),
    }
    if error:
        entry["error"] = error[:200]
    try:
        # One write() on an O_APPEND file: lines under PIPE_BUF are not interleaved between processes.
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        fd = os.open(_log_path(), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o664)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception as exc:  # noqa: BLE001 - logging must never break the LLM call it describes
        log.warning("direct call log write failed: %s", exc)
