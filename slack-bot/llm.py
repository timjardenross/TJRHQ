from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


DEFAULT_PROVIDER = "auto"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"
DEFAULT_ENGINEER_MODEL = "deepseek-coder:6.7b"
DEFAULT_REASONING_MODEL = "deepseek-r1:14b"
DEFAULT_FAST_MODEL = "gemma3"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_TIMEOUT_SECONDS = 20
EMBEDDING_MODEL_ENV = "OLLAMA_EMBEDDING_MODEL"


class LLMUnavailableError(RuntimeError):
    pass


def get_llm_provider() -> str:
    provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER).lower().strip()
    if provider not in {"auto", "ollama", "openai"}:
        return DEFAULT_PROVIDER
    return provider


def get_ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")


def get_ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL") or os.getenv("OLLAMA_COMMANDER_MODEL", DEFAULT_OLLAMA_MODEL)


def get_commander_model() -> str:
    return os.getenv("OLLAMA_COMMANDER_MODEL") or os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)


def get_engineer_model() -> str:
    return os.getenv("OLLAMA_ENGINEER_MODEL", DEFAULT_ENGINEER_MODEL)


def get_reasoning_model() -> str:
    return os.getenv("OLLAMA_REASONING_MODEL", DEFAULT_REASONING_MODEL)


def get_fast_model() -> str:
    return os.getenv("OLLAMA_FAST_MODEL", DEFAULT_FAST_MODEL)


def get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)


def get_timeout_seconds() -> int:
    raw_value = os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def is_ollama_available() -> bool:
    try:
        request = urllib.request.Request(
            f"{get_ollama_base_url()}/api/tags",
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def is_openai_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY"))


def is_llm_configured() -> bool:
    return is_llm_available()


def is_llm_available() -> bool:
    provider = get_llm_provider()
    if provider == "ollama":
        return is_ollama_available()
    if provider == "openai":
        return is_openai_available()
    return is_ollama_available() or is_openai_available()


def select_ollama_model(
    specialists: list[str] | None = None,
    user_text: str = "",
    priority: str = "",
) -> str:
    text = user_text.lower()
    specialist_set = set(specialists or [])

    if "Research Officer" in specialist_set or any(
        marker in text for marker in ["discovery", "deep analysis", "trade-off", "tradeoff", "strategic analysis"]
    ):
        return get_reasoning_model()

    if "Chief Engineer" in specialist_set or "Coder Agent" in specialist_set or any(
        marker in text for marker in ["code review", "architecture review", "repository analysis", "technical implementation"]
    ):
        return get_engineer_model()

    if "low priority" in text or priority.lower().startswith("p4"):
        return get_fast_model()

    return get_commander_model()


def ollama_model_fallback_chain(selected_model: str) -> list[str]:
    models = [selected_model, get_commander_model(), get_fast_model()]
    embedding_model = os.getenv(EMBEDDING_MODEL_ENV, "")
    deduped = []
    for model in models:
        if model and model != embedding_model and model not in deduped:
            deduped.append(model)
    return deduped


def generate_with_ollama(prompt: str, system_prompt: str | None = None, model: str | None = None) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model or get_ollama_model(),
        "messages": messages,
        "stream": False,
    }
    request = urllib.request.Request(
        f"{get_ollama_base_url()}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=get_timeout_seconds()) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as error:
        raise LLMUnavailableError(f"Ollama unavailable: {type(error).__name__}") from error
    except Exception as error:
        raise LLMUnavailableError(f"Ollama unavailable: {type(error).__name__}") from error

    content = (body.get("message") or {}).get("content", "")
    if not content.strip():
        raise LLMUnavailableError("Ollama returned an empty response.")
    return content.strip()


def generate_with_openai(prompt: str, system_prompt: str | None = None) -> str:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY")
    if not api_key:
        raise LLMUnavailableError("OpenAI credentials are not configured.")

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=get_openai_model(),
            messages=[
                {
                    "role": "system",
                    "content": system_prompt or "",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.3,
        )
        content = response.choices[0].message.content
    except Exception as error:
        raise LLMUnavailableError(f"OpenAI unavailable: {type(error).__name__}") from error

    if not content or not content.strip():
        raise LLMUnavailableError("OpenAI returned an empty response.")
    return content.strip()


def generate_response(
    prompt: str,
    system_prompt: str | None = None,
    context: str | None = None,
    specialists: list[str] | None = None,
    priority: str = "",
) -> str:
    full_system_prompt = system_prompt or context or ""
    success, response = try_generate_response(
        prompt=prompt,
        system_prompt=full_system_prompt,
        specialists=specialists,
        priority=priority,
    )
    if success:
        return response
    return deterministic_fallback(reason=response)


def try_generate_response(
    prompt: str,
    system_prompt: str | None = None,
    specialists: list[str] | None = None,
    priority: str = "",
) -> tuple[bool, str]:
    provider = get_llm_provider()
    attempted: list[str] = []

    if provider in {"auto", "ollama"}:
        selected_model = select_ollama_model(specialists=specialists, user_text=prompt, priority=priority)
        ollama_errors = []
        for model in ollama_model_fallback_chain(selected_model):
            attempted.append(f"ollama:{model}")
            try:
                return True, generate_with_ollama(prompt=prompt, system_prompt=system_prompt, model=model)
            except LLMUnavailableError as error:
                ollama_errors.append(f"{model}: {error}")
        if provider == "ollama":
            return False, "; ".join(ollama_errors)
        ollama_reason = "; ".join(ollama_errors)
    else:
        ollama_reason = ""

    if provider in {"auto", "openai"}:
        attempted.append("openai")
        try:
            return True, generate_with_openai(prompt=prompt, system_prompt=system_prompt)
        except LLMUnavailableError as error:
            if provider == "openai":
                return False, str(error)
            openai_reason = str(error)
    else:
        openai_reason = ""

    reasons = "; ".join(reason for reason in [ollama_reason, openai_reason] if reason)
    attempted_text = ", ".join(attempted) or "none"
    return False, reasons or f"No configured provider succeeded. Attempted: {attempted_text}."


def deterministic_fallback(reason: str) -> str:
    return "\n".join([
        "# COMMANDER RUNTIME RESPONSE",
        "",
        "Commander received the request, but live LLM synthesis is not available.",
        "",
        "The request can still be routed through deterministic Commander paths.",
        "",
        f"Runtime reason: {reason}.",
    ])


def build_client():
    if not is_openai_available():
        raise LLMUnavailableError("OpenAI credentials are not configured.")

    from openai import OpenAI

    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY"),
    )


def ask_commander(system_prompt: str, user_prompt: str) -> str:
    success, response = try_generate_response(prompt=user_prompt, system_prompt=system_prompt)
    if not success:
        raise LLMUnavailableError(response)
    return response


def ask_commander_safe(system_prompt: str, user_prompt: str) -> tuple[bool, str]:
    try:
        return True, ask_commander(system_prompt=system_prompt, user_prompt=user_prompt)
    except LLMUnavailableError as error:
        return False, str(error)
    except Exception as error:
        return False, f"{type(error).__name__}"


def ask_commander_with_sources(system_prompt: str, user_prompt: str) -> str:
    return ask_commander(system_prompt=system_prompt, user_prompt=user_prompt)


def ask_commander_for_specialists(
    system_prompt: str,
    user_prompt: str,
    specialists: list[str] | None = None,
    priority: str = "",
) -> tuple[bool, str]:
    try:
        return True, ask_commander_with_specialists(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            specialists=specialists,
            priority=priority,
        )
    except LLMUnavailableError as error:
        return False, str(error)
    except Exception as error:
        return False, f"{type(error).__name__}"


def ask_commander_with_specialists(
    system_prompt: str,
    user_prompt: str,
    specialists: list[str] | None = None,
    priority: str = "",
) -> str:
    success, response = try_generate_response(
        prompt=user_prompt,
        system_prompt=system_prompt,
        specialists=specialists,
        priority=priority,
    )
    if not success:
        raise LLMUnavailableError(response)
    return response
