"""
Shared cloud/local LLM call primitives — ADR-024 (Resilience Intelligence
Convergence), consolidating the Gemini/Mistral/Ollama request mechanics that
were previously implemented twice: intelligence/brief/llm_provider.py
(RESIL-EXT) and core/health/health_llm.py (RESIL-HUMAN).

Each function performs exactly one provider call and raises RuntimeError on
any failure (missing key, empty response, transport error) — callers are
responsible for the try/except-and-fall-through provider chain, retry
policy, and domain-specific system prompt / token-budget choices. This
module owns none of that; it only owns "how do you actually talk to Gemini /
Mistral / Ollama."

Cloud egress is guarded (USS-TJR-MSN-0412 Stream 5). call_gemini and
call_mistral run the same core.security.llm_guardrails checks the model
router runs before it dispatches to Gemini — input rail (prompt injection),
then Presidio PII/PHI redaction — and the output rail on the response, and
they FAIL CLOSED like the router: an unavailable guard, a blocked prompt or
response, or text too long to redact raises (GuardrailsUnavailableError /
BlockedByGuardrailsError, both RuntimeError subclasses, so callers'
existing fall-through to the next provider still works) and nothing is sent.
call_ollama is local and unguarded by design. Cost: roughly 45-90s per call
on this CPU-only host, because the NeMo rails run on the local Ollama.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
import time
import urllib.request
from dataclasses import dataclass

from core.llm.call_log import log_direct_call
from core.security.llm_guardrails import (
    BlockedByGuardrailsError,
    GuardrailsUnavailableError,
    check_input_rail,
    check_output_rail,
    redact_pii,
)

try:
    import sys as _sys
    # append, not insert(0): callers (e.g. telegram bots) run under their own
    # venv, which may pin different versions of packages platform-runtime's
    # venv also has (supabase/httpx/gotrue). insert(0) shadowed the caller's
    # own site-packages for any name collision, breaking bots whose eager
    # imports pulled this module in before their own supabase client was
    # built (tg-revs crash-loop, 2026-09-15: TypeError on gotrue's httpx.Client
    # from platform-runtime's newer supabase/httpx being picked up instead of
    # the bot's pinned 2.3.4). append() makes this path a fallback used only
    # for names absent from the caller's own venv (opentelemetry, platform_runtime.lib).
    _sys.path.append('/opt/starship-endeavour/platform-runtime/.venv/lib/python3.12/site-packages')
    from opentelemetry import trace as _trace

    from platform_runtime.lib.telemetry import configure_tracing as _configure_tracing
    _configure_tracing("provider-chain")
    _TRACING_AVAILABLE = True
except Exception:  # noqa: BLE001 - availability/optional-dependency guard; only ImportError-vs-not matters, sentinel value signals unavailability to callers
    _TRACING_AVAILABLE = False


@dataclass
class LLMCallResult:
    """Text plus whatever token-usage the provider's own response reported.
    input_tokens/output_tokens are None when a provider's response doesn't
    carry usage data — callers must treat that as "unknown", not zero."""
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


def _llm_span(provider: str, model: str, task_type: str = ""):
    """
    Return an OTel span context manager for a provider LLM call, or a
    no-op context manager when tracing is not available.

    Args:
        provider:  LLM provider name (e.g. "gemini", "mistral", "ollama")
        model:     Model identifier being called
        task_type: Optional task label for additional span attribute richness
    """
    if not _TRACING_AVAILABLE:
        return contextlib.nullcontext()
    tracer = _trace.get_tracer("provider_chain")
    return tracer.start_as_current_span(
        f"llm.{provider}",
        attributes={"llm.provider": provider, "llm.model": model, "llm.task_type": task_type}
    )


# --- cloud-egress guard (USS-TJR-MSN-0412 Stream 5) --------------------------

# Presidio's spaCy model rejects text over 1,000,000 characters (error E088), and redaction
# time grows with length (about 190s for 200,000 characters on this host, measured), so the
# worker's own timeout would fire first. Refuse above this cap instead of chunking: an
# entity split across a chunk boundary could escape redaction.
_MAX_GUARDED_CHARS = int(os.environ.get("LLM_PROVIDER_CHAIN_MAX_GUARDED_CHARS", "150000"))

# system_prompt and prompt are redacted in ONE Presidio call (each call starts a worker that
# loads spaCy), joined by this marker. If redaction changes the marker, refuse to send.
_PART_BOUNDARY = "\n\n<<<provider-chain-part-boundary-7f3a9c>>>\n\n"

# The NeMo rails call the local CPU Ollama. The model router serializes its own guard calls with
# an in-process lock; direct callers run in separate processes, so they serialize with a file
# lock (otherwise concurrent guard runs thrash the CPU and time out, as in the Sept 15-19 incident).
_GUARD_LOCK_WAIT_S = float(os.environ.get("LLM_PROVIDER_CHAIN_GUARD_LOCK_WAIT_S", "900"))


def _guard_lock_path() -> str:
    explicit = os.environ.get("LLM_PROVIDER_CHAIN_GUARD_LOCK")
    if explicit:
        return explicit
    return "/run/llm-guardrails-provider-chain.lock" if os.access("/run", os.W_OK) else os.path.join(
        tempfile.gettempdir(), "llm-guardrails-provider-chain.lock"
    )


@contextlib.contextmanager
def _guard_lock():
    """Exclusive inter-process lock around guard calls. Failing to get it within
    _GUARD_LOCK_WAIT_S raises GuardrailsUnavailableError: fail closed, never skip the guard."""
    fd = os.open(_guard_lock_path(), os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + _GUARD_LOCK_WAIT_S
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise GuardrailsUnavailableError(
                        f"guard busy: could not take the guard lock within {_GUARD_LOCK_WAIT_S:.0f}s"
                    ) from None
                time.sleep(0.5)
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the flock


def _guard_outbound(system_prompt: str, prompt: str) -> tuple[str, str]:
    """Input rail then redaction over everything that would leave this host. Returns the
    (system_prompt, prompt) pair to send. Raises, so nothing is sent, if the text is too long,
    the guard is unavailable or busy, the rail blocks, or redaction mangles the part boundary."""
    total = len(system_prompt) + len(prompt)
    if total > _MAX_GUARDED_CHARS:
        raise BlockedByGuardrailsError(
            f"prompt is {total} characters, over the {_MAX_GUARDED_CHARS}-character limit the "
            "redaction guard can check; refusing to send it unredacted"
        )
    with _guard_lock():
        check_input_rail(f"{system_prompt}\n\n{prompt}")
        redacted = redact_pii(f"{system_prompt}{_PART_BOUNDARY}{prompt}").redacted_text
    parts = redacted.split(_PART_BOUNDARY)
    if len(parts) != 2:
        raise BlockedByGuardrailsError("redaction altered the system/user prompt boundary; refusing to send")
    return parts[0], parts[1]


def _guard_inbound(text: str) -> None:
    """Output rail on a cloud response. Raises (the text is then never returned) if blocked."""
    with _guard_lock():
        check_output_rail(text)


def call_gemini(
    system_prompt: str,
    prompt: str,
    *,
    api_key: str,
    max_output_tokens: int = 2048,
    temperature: float = 0.3,
    timeout: int = 30,
) -> LLMCallResult:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    system_prompt, prompt = _guard_outbound(system_prompt, prompt)

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-3.5-flash-lite:generateContent?key={api_key}"
    )
    body = json.dumps({
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": prompt}]}],
        # 2026-08-22: thinkingConfig.thinkingBudget=0 (added for Gemini 2.5's
        # hidden-reasoning-token truncation behavior) is REJECTED outright by
        # gemini-3.5-flash-lite with HTTP 400 INVALID_ARGUMENT — confirmed
        # live, this was silently failing every call in every pipeline using
        # this module (100% Mistral-fallback rate, never actually reaching
        # Gemini). Removed rather than reworked: live-verified this model
        # doesn't need it — finishReason=STOP, full untruncated text, well
        # under maxOutputTokens, with no thinkingConfig at all.
        "generationConfig": {
            "maxOutputTokens": max_output_tokens, "temperature": temperature,
        },
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _llm_span("gemini", "gemini-3.5-flash-lite"), urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - url is a hardcoded generativelanguage.googleapis.com literal constant, not user input - reviewed 2026-09-12
        data = json.loads(resp.read())

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    usage = data.get("usageMetadata", {})
    result = LLMCallResult(
        text=candidates[0]["content"]["parts"][0]["text"].strip(),
        model="gemini-3.5-flash-lite",
        input_tokens=usage.get("promptTokenCount"),
        output_tokens=usage.get("candidatesTokenCount"),
    )
    _guard_inbound(result.text)
    return result


def call_mistral(
    system_prompt: str,
    prompt: str,
    *,
    api_key: str,
    model: str = "mistral-small-latest",
    max_tokens: int = 2048,
    temperature: float = 0.3,
    timeout: int = 30,
) -> LLMCallResult:
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY not set")

    system_prompt, prompt = _guard_outbound(system_prompt, prompt)

    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        "https://api.mistral.ai/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with _llm_span("mistral", model), urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - url is a hardcoded api.mistral.ai literal constant, not user input - reviewed 2026-09-12
        data = json.loads(resp.read())

    usage = data.get("usage", {})
    result = LLMCallResult(
        text=data["choices"][0]["message"]["content"].strip(),
        model=data.get("model") or model,
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
    )
    _guard_inbound(result.text)
    return result


def call_ollama(
    system_prompt: str,
    prompt: str,
    *,
    base_url: str,
    model: str,
    temperature: float = 0.3,
    num_predict: int = 1200,
    timeout: int = 60,
) -> LLMCallResult:
    body = json.dumps({
        "model": model,
        "prompt": f"{system_prompt}\n\n{prompt}",
        "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    prompt_len = len(system_prompt) + len(prompt)
    try:
        with _llm_span("ollama", model), urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - base_url is a keyword param, but all callers source it from a fixed env-driven OLLAMA base URL constant, not end-user input - reviewed 2026-09-12
            data = json.loads(resp.read())
    except Exception as exc:
        log_direct_call(
            model=model, duration_ms=int((time.monotonic() - started) * 1000), success=False,
            prompt_len=prompt_len, error=type(exc).__name__, task_type="direct-ollama-generate",
        )
        raise

    text = (data.get("response") or "").strip()
    log_direct_call(
        model=model, duration_ms=int((time.monotonic() - started) * 1000), success=bool(text),
        prompt_len=prompt_len, response_len=len(text),
        prompt_eval_count=data.get("prompt_eval_count"), eval_count=data.get("eval_count"),
        error=None if text else "empty response", task_type="direct-ollama-generate",
    )
    if not text:
        raise RuntimeError("Ollama returned an empty response")
    return LLMCallResult(
        text=text,
        model=model,
        input_tokens=data.get("prompt_eval_count"),
        output_tokens=data.get("eval_count"),
    )
