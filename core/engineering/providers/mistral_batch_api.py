"""
Mistral **Batch API** client for the Engineering Workflow Router.

Unlike the (misleadingly named) synchronous ``mistral_batch.py`` provider, this
module talks to Mistral's async Batch API: upload one JSONL of N chat-completion
requests, create one batch job, poll it, then download one JSONL of N results.
Batch runs at ~50% of synchronous cost and is the right tool for the engineering
handoff queue, which is not latency-sensitive.

Auth (in priority order):
    MISTRAL_BATCH_API_KEY   (dedicated key for batch coding)
    MISTRAL_API_KEY         (shared fallback)

This is thin plumbing only: building JSONL, prompt construction, and handoff
bookkeeping live in ``core.engineering.batch_coding``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

log = logging.getLogger(__name__)

DEFAULT_MODEL = "codestral-latest"
CHAT_ENDPOINT = "/v1/chat/completions"


class MistralBatchError(RuntimeError):
    """Raised on any Batch API failure with a descriptive message."""


def _api_key() -> str:
    key = (
        os.getenv("MISTRAL_BATCH_API_KEY")
        or os.getenv("MISTRAL_API_KEY")
        or ""
    ).strip()
    if not key:
        raise MistralBatchError(
            "No Mistral API key. Set MISTRAL_BATCH_API_KEY (preferred) or "
            "MISTRAL_API_KEY."
        )
    return key


def make_client():
    """Construct a Mistral SDK client using the batch/shared key (reusable)."""
    try:
        from mistralai import Mistral
    except ImportError as exc:  # pragma: no cover
        raise MistralBatchError(
            "mistralai SDK not installed. Run: pip install 'mistralai<2'"
        ) from exc
    return Mistral(api_key=_api_key())


# Backwards-compatible private alias.
_client = make_client


def complete(prompt: str, model: str = DEFAULT_MODEL, max_tokens: int = 4096,
             client=None) -> str:
    """Synchronous chat completion — the fallback when Batch API billing is off.

    Works on the standard (non-batch) tier. Returns the response text.
    """
    client = client or make_client()
    resp = client.chat.complete(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    if not getattr(resp, "choices", None):
        raise MistralBatchError("Mistral returned no choices.")
    return (resp.choices[0].message.content or "").strip()


def submit(requests: list[dict[str, Any]], model: str = DEFAULT_MODEL,
           metadata: Optional[dict[str, str]] = None, client=None) -> str:
    """Upload a JSONL batch input and create a job. Returns the job id.

    Each request must be ``{"custom_id": str, "body": {"messages": [...], ...}}``
    — the shape Mistral's Batch API expects per JSONL line.
    """
    if not requests:
        raise MistralBatchError("No requests to submit.")
    client = client or _client()

    jsonl = "\n".join(json.dumps(r, ensure_ascii=False) for r in requests).encode("utf-8")
    log.info("[batch] uploading %d requests (%d bytes)", len(requests), len(jsonl))
    uploaded = client.files.upload(
        file={"file_name": "engineering_batch_input.jsonl", "content": jsonl},
        purpose="batch",
    )

    job = client.batch.jobs.create(
        input_files=[uploaded.id],
        model=model,
        endpoint=CHAT_ENDPOINT,
        metadata=metadata or {},
    )
    log.info("[batch] created job %s (status=%s)", job.id, getattr(job, "status", "?"))
    return job.id


def status(job_id: str, client=None) -> dict[str, Any]:
    """Return a flat status dict for a job (never raises on missing fields)."""
    client = client or _client()
    job = client.batch.jobs.get(job_id=job_id)
    return {
        "id": job.id,
        "status": getattr(job, "status", None),
        "total": getattr(job, "total_requests", None),
        "completed": getattr(job, "completed_requests", None),
        "succeeded": getattr(job, "succeeded_requests", None),
        "failed": getattr(job, "failed_requests", None),
        "output_file": getattr(job, "output_file", None),
        "error_file": getattr(job, "error_file", None),
    }


def _download_text(client, file_id: str) -> str:
    resp = client.files.download(file_id=file_id)  # httpx.Response
    if hasattr(resp, "text"):
        return resp.text
    if hasattr(resp, "read"):
        data = resp.read()
        return data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
    return str(resp)


def results(job_id: str, client=None) -> dict[str, Any]:
    """Fetch a finished job's outputs.

    Returns ``{"status", "outputs": {custom_id: text}, "errors": {custom_id: msg}}``.
    ``outputs`` is empty if the job is not yet done — check ``status``.
    """
    client = client or _client()
    info = status(job_id, client=client)
    outputs: dict[str, str] = {}
    errors: dict[str, str] = {}

    if info.get("output_file"):
        for line in _download_text(client, info["output_file"]).splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            cid = obj.get("custom_id")
            body = (obj.get("response") or {}).get("body") or {}
            choices = body.get("choices") or []
            text = ""
            if choices:
                text = (choices[0].get("message") or {}).get("content") or ""
            outputs[cid] = text

    if info.get("error_file"):
        for line in _download_text(client, info["error_file"]).splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            errors[obj.get("custom_id")] = json.dumps(obj.get("error") or obj, ensure_ascii=False)

    return {"status": info.get("status"), "outputs": outputs, "errors": errors, "info": info}
