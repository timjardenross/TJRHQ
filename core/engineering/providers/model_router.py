"""
Model Router backend for the Engineering Workflow Router.

Routes engineering review prompts through the Starship Endeavour Model Router
at port 8891 (/api/model/engineering-review endpoint).

Optional env vars:
    MODEL_ROUTER_URL   (default: http://127.0.0.1:8891)
    MODEL_ROUTER_TIMEOUT_SECONDS (default: 120)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional

log = logging.getLogger(__name__)

_DEFAULT_URL = "http://127.0.0.1:8891"
_CONNECT_TIMEOUT = 5
_REQUEST_TIMEOUT = 120
_ENDPOINT = "/api/model/engineering-review"
_MODEL_LABEL = "model-router:engineering-review"


def _base_url() -> str:
    return os.getenv("MODEL_ROUTER_URL", _DEFAULT_URL).rstrip("/")


def check_connectivity() -> tuple[bool, str]:
    """Return (reachable, message). Never raises."""
    url = f"{_base_url()}/health"
    try:
        req = urllib.request.urlopen(url, timeout=_CONNECT_TIMEOUT)
        data = json.loads(req.read().decode())
        return True, f"Model Router reachable at {_base_url()}. Status: {data.get('status', 'ok')}"
    except Exception as exc:
        return False, f"Model Router not reachable at {_base_url()}: {exc}"


def call(prompt: str, model: Optional[str] = None) -> tuple[str, str]:
    """
    Send prompt to Model Router /api/model/engineering-review.

    Returns (response_text, model_label).
    Raises RuntimeError with a descriptive message on failure.
    """
    url = f"{_base_url()}{_ENDPOINT}"
    timeout = int(os.getenv("MODEL_ROUTER_TIMEOUT_SECONDS", str(_REQUEST_TIMEOUT)))
    payload = json.dumps({"prompt": prompt}).encode("utf-8")

    log.info("[model-router] url=%s prompt_len=%d", url, len(prompt))

    reachable, msg = check_connectivity()
    if not reachable:
        raise RuntimeError(f"Model Router connectivity check failed — cannot run request.\n{msg}")

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Model Router request failed: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Model Router unexpected error: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model Router returned non-JSON: {raw[:200]}") from exc

    text = (data.get("response") or data.get("content") or "").strip()
    model_label = data.get("model") or model or _MODEL_LABEL

    if not text:
        raise RuntimeError(f"Model Router returned an empty response. Raw: {raw[:300]}")

    log.info("[model-router] response_len=%d model=%s", len(text), model_label)
    return text, model_label
