"""
core/security/llm_guardrails.py — LLM application security baseline for
every real external-cloud-API dispatch point in this repo (USS-TJR-MSN-0366
Stream 5, "Stage 2A: New Open-Source Tool Adoption").

Covers two OWASP Top 10 for LLM Applications categories, both against the
SAME dispatch points (core/model-router/app.py's _gemini_generate, and the
mistralai cloud client modules — see docs/decisions/ADR-llm-application-
security-baseline.md for the full mapping and the one real gap, the `:cloud`
Ollama-routed models, that this layer does NOT and cannot cover):

    LLM02 Sensitive Information Disclosure  -> Presidio (redact_pii)
    LLM01 Prompt Injection                  -> NeMo Guardrails input rail
    (output-side leakage, defense in depth) -> NeMo Guardrails output rail

Deliberately stdlib-only, like core/model-router/app.py itself ("No external
dependencies — stdlib only." per that file's docstring). The actual PII
detection and Colang rail evaluation happen in
core/security/_llmsec_worker.py, invoked via subprocess under a dedicated
venv (platform-runtime/.venv-llmsec — see requirements-llmsec.txt for why
it's isolated rather than added to platform-runtime/.venv or, worse, this
router's own zero-dependency runtime). This module is safe to import from
any caller, including ones that must stay dependency-free, and degrades to
a documented, fail-CLOSED error (never a silent skip) if the venv/worker
isn't present — see `GuardrailsUnavailableError`.

Typical call site (see core/model-router/app.py's _gemini_generate wrapper,
and the mistralai client modules, for the real integrations):

    from core.security.llm_guardrails import secure_outbound_prompt, BlockedByGuardrailsError

    try:
        safe_prompt, findings = secure_outbound_prompt(prompt)
    except BlockedByGuardrailsError as exc:
        return {"success": False, "error": str(exc)}
    raw = _gemini_generate(model, safe_prompt, ...)
    ...
    checked_response = check_output_safety(raw_text)  # raises if blocked
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("model-router.llm_guardrails")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VENV_PYTHON = _REPO_ROOT / "platform-runtime" / ".venv-llmsec" / "bin" / "python3"
_WORKER = Path(__file__).parent / "_llmsec_worker.py"

# Set truthy to make a missing/broken llmsec venv a silent no-op instead of
# a hard failure. Deliberately OFF by default: per the mission brief, this
# layer exists specifically to stop sensitive data leaving the VM, so an
# unavailable guard should block the cloud call, not wave it through
# unredacted. Only ever meant for a documented, deliberate rollback.
_FAIL_OPEN = os.environ.get("LLM_GUARDRAILS_FAIL_OPEN", "").strip().lower() in ("1", "true", "yes")

_WORKER_TIMEOUT_S = float(os.environ.get("LLM_GUARDRAILS_TIMEOUT_S", "45"))


class GuardrailsUnavailableError(RuntimeError):
    """The llmsec venv/worker couldn't be run at all (missing venv, worker
    crashed, timed out). Distinct from a normal "blocked" result."""


class BlockedByGuardrailsError(RuntimeError):
    """A cloud dispatch was blocked by the input or output rail."""


@dataclass
class PIIFinding:
    entity_type: str
    start: int
    end: int
    score: float
    text: str


@dataclass
class RedactionResult:
    redacted_text: str
    findings: list[PIIFinding] = field(default_factory=list)

    @property
    def had_findings(self) -> bool:
        return bool(self.findings)


def _venv_ready() -> bool:
    return _VENV_PYTHON.exists() and _WORKER.exists()


def _invoke_worker(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not _venv_ready():
        raise GuardrailsUnavailableError(
            f"llmsec venv not found at {_VENV_PYTHON} — run: python3 -m venv "
            f"platform-runtime/.venv-llmsec && platform-runtime/.venv-llmsec/bin/pip "
            f"install -r core/security/requirements-llmsec.txt (see that file for the "
            f"spacy model step too)."
        )
    try:
        proc = subprocess.run(
            [str(_VENV_PYTHON), str(_WORKER), command],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=_WORKER_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GuardrailsUnavailableError(f"llmsec worker timed out on command={command}") from exc

    if not proc.stdout.strip():
        raise GuardrailsUnavailableError(
            f"llmsec worker produced no output on command={command}; stderr={proc.stderr[-2000:]}"
        )
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise GuardrailsUnavailableError(
            f"llmsec worker returned non-JSON output on command={command}: {proc.stdout[:500]!r}"
        ) from exc

    if "error" in result:
        raise GuardrailsUnavailableError(f"llmsec worker error on command={command}: {result['error']}")
    return result


def redact_pii(text: str) -> RedactionResult:
    """Run `text` through Presidio (built-in recognizers + the TJR-specific
    mission-codename/officer-clearance recognizers in
    core/security/guardrails/recognizers.py) and return the redacted text
    plus what was found. Raises GuardrailsUnavailableError (never silently
    returns the original text) if the isolated venv can't be reached and
    LLM_GUARDRAILS_FAIL_OPEN isn't set.
    """
    try:
        result = _invoke_worker("redact", {"text": text})
    except GuardrailsUnavailableError:
        if _FAIL_OPEN:
            log.error("llm_guardrails: redact_pii unavailable, FAIL_OPEN set — sending prompt UNREDACTED")
            return RedactionResult(redacted_text=text, findings=[])
        raise
    findings = [PIIFinding(**f) for f in result.get("findings", [])]
    return RedactionResult(redacted_text=result["redacted_text"], findings=findings)


def check_input_rail(prompt: str, *, fake_responses: list[str] | None = None, ollama_base_url: str | None = None) -> None:
    """Run the NeMo Guardrails input rail (LLM01 prompt-injection/jailbreak
    check) against `prompt`. Raises BlockedByGuardrailsError if blocked;
    returns None (does not modify the prompt) if allowed.

    `fake_responses` is TEST-ONLY (see _llmsec_worker.py's docstring) —
    production callers must never pass it.
    """
    payload: dict[str, Any] = {"prompt": prompt, "ollama_base_url": ollama_base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")}
    if fake_responses is not None:
        payload["fake_responses"] = fake_responses
    try:
        result = _invoke_worker("check_input", payload)
    except GuardrailsUnavailableError:
        if _FAIL_OPEN:
            log.error("llm_guardrails: check_input_rail unavailable, FAIL_OPEN set — allowing prompt unchecked")
            return
        raise
    if result.get("blocked"):
        raise BlockedByGuardrailsError(f"input blocked by {result.get('reason')}")


def check_output_rail(response_text: str, *, fake_responses: list[str] | None = None, ollama_base_url: str | None = None) -> None:
    """Run the NeMo Guardrails output rail (unsafe-content / credential-leak
    check) against a cloud model's `response_text`. Raises
    BlockedByGuardrailsError if blocked; returns None if allowed.
    """
    payload: dict[str, Any] = {"response_text": response_text, "ollama_base_url": ollama_base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")}
    if fake_responses is not None:
        payload["fake_responses"] = fake_responses
    try:
        result = _invoke_worker("check_output", payload)
    except GuardrailsUnavailableError:
        if _FAIL_OPEN:
            log.error("llm_guardrails: check_output_rail unavailable, FAIL_OPEN set — allowing response unchecked")
            return
        raise
    if result.get("blocked"):
        raise BlockedByGuardrailsError(f"output blocked by {result.get('reason')}")


def secure_outbound_prompt(prompt: str, *, _input_rail_fake_responses: list[str] | None = None) -> tuple[str, RedactionResult]:
    """The single call every cloud-egress dispatch point should make before
    sending `prompt` to an external provider: input-rail check (raises
    BlockedByGuardrailsError on a jailbreak/injection attempt) THEN PII
    redaction (raises GuardrailsUnavailableError on failure unless
    LLM_GUARDRAILS_FAIL_OPEN is set). Order matters: an attacker's own
    injection payload shouldn't get a free redaction pass before being
    judged.

    Returns (redacted_prompt, redaction_result) — send `redacted_prompt`,
    not the original, to the cloud provider.

    `_input_rail_fake_responses` is TEST-ONLY (see check_input_rail) —
    production callers must never pass it.
    """
    check_input_rail(prompt, fake_responses=_input_rail_fake_responses)
    redaction = redact_pii(prompt)
    if redaction.had_findings:
        log.info(
            "llm_guardrails: redacted %d PII/identifier finding(s) before cloud dispatch (%s)",
            len(redaction.findings),
            ", ".join(sorted({f.entity_type for f in redaction.findings})),
        )
    return redaction.redacted_text, redaction
