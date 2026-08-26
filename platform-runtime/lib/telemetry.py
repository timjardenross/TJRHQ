"""
Centralised OpenTelemetry / Arize Phoenix tracing configuration for the
Starship Endeavour platform.

Usage — call once at module init in any instrumented service:

    from platform_runtime.lib.telemetry import configure_tracing
    configure_tracing("my-service")

The call is idempotent: repeated invocations with the same or a different
service name are safe to make (subsequent calls return immediately after the
first successful registration).

Phoenix collector endpoint: http://localhost:6006/v1/traces (port 6006 is the
Phoenix default; nothing else in this platform uses that port).

Project name: "starship-endeavour" — all spans appear under this project in
the Phoenix UI regardless of which service emits them; the service_name
attribute distinguishes individual callers.

Auto-instrumentation notes:
    - OpenAI SDK calls are auto-instrumented via OpenAIInstrumentor.
    - MistralAI SDK: openinference-instrumentation-mistralai v2.x expects the
      old mistralai v0.x module layout (mistralai.client.agents) which does not
      exist in mistralai v1.x. Auto-instrumentation for Mistral is therefore
      skipped; manual spans in mistral_agent_client.py cover the
      beta.conversations.start() call path instead.

Side effects:
    - Registers a global OTel TracerProvider pointed at Phoenix.
    - Activates OpenAI auto-instrumentation.
    - Emits a single INFO log line confirming setup.
    - If Phoenix packages are absent the function logs a warning and returns
      without raising — tracing is a cross-cutting concern, not a correctness
      requirement, so its absence must not crash callers.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_PHOENIX_ENDPOINT = "http://localhost:6006/v1/traces"
_PROJECT_NAME = "starship-endeavour"

# Guard flag — set to True on first successful registration so subsequent
# calls skip the (non-idempotent) SDK setup steps.
_tracing_configured = False


def configure_tracing(service_name: str) -> None:
    """
    Register an OTel TracerProvider that exports spans to a local Arize Phoenix
    instance and activate OpenInference auto-instrumentation for OpenAI SDK calls.

    Args:
        service_name: Logical name for this service as it will appear in spans
                      (e.g. "provider-chain", "mistral-agent-client",
                      "model-router").

    The function is idempotent — once the provider is registered the global
    ``_tracing_configured`` flag is set and all subsequent calls return
    immediately.

    If the ``phoenix`` or ``openinference`` packages are not installed this
    function logs a WARNING and returns without raising so that services
    continue to function without observability rather than crashing.

    MistralAI auto-instrumentation is intentionally excluded: the installed
    openinference-instrumentation-mistralai v2.x targets the mistralai v0.x
    module path (``mistralai.client.agents``) which does not exist in the
    platform's mistralai v1.x installation. Manual OTel spans in
    mistral_agent_client.py cover the beta.conversations.start() path instead.
    """
    global _tracing_configured
    if _tracing_configured:
        return

    try:
        from phoenix.otel import register
        from openinference.instrumentation.openai import OpenAIInstrumentor
    except ImportError as exc:
        log.warning(
            "telemetry: Phoenix / OpenInference packages not available (%s) — "
            "tracing disabled. Install arize-phoenix and openinference-instrumentation-* "
            "packages to enable.",
            exc,
        )
        return

    tracer_provider = register(
        endpoint=_PHOENIX_ENDPOINT,
        project_name=_PROJECT_NAME,
        batch=True,
        set_global_tracer_provider=True,
        verbose=False,
    )

    # Auto-instrument any OpenAI SDK calls in the platform.
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)

    _tracing_configured = True
    log.info(
        "telemetry: tracing configured service=%s endpoint=%s project=%s",
        service_name,
        _PHOENIX_ENDPOINT,
        _PROJECT_NAME,
    )
