#!/usr/bin/env python3
"""
core/security/_llmsec_worker.py — the ONLY file in this feature that imports
presidio_analyzer / presidio_anonymizer / nemoguardrails directly.

Runs exclusively under platform-runtime/.venv-llmsec (see
core/security/requirements-llmsec.txt for why it's a separate venv, not
platform-runtime/.venv — same reasoning as core/quality/requirements-
garak.txt's isolation of garak). core/security/llm_guardrails.py (the
stdlib-only public API, importable from anywhere including the dependency-
free core/model-router/app.py) invokes this script via subprocess with a
JSON request on stdin and reads a JSON response from stdout — the same
"dedicated venv invoked by absolute path" shape core/quality/garak_gate.py
already uses for garak, just returning structured data over stdio instead
of a shelled-out CLI report file.

Commands (argv[1]):
    redact        {"text": str} -> {"redacted_text": str, "findings": [...]}
    check_input   {"prompt": str, "fake_responses": [str, ...]?}
                      -> {"blocked": bool, "reason": str|None}
    check_output  {"response_text": str, "fake_responses": [str, ...]?}
                      -> {"blocked": bool, "reason": str|None}

`fake_responses` is TEST-ONLY: when present, the checking LLM is replaced
with NeMo Guardrails' own officially-shipped FakeLLMModel
(nemoguardrails.testing.fake_model) scripted to return exactly those
responses in order. It exists because this sandbox has no reachable Ollama
(see the knowledge record) — production calls never set it, so production
always exercises the real Ollama-backed self-check action.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent
_GUARDRAILS_CONFIG_DIR = _HERE / "guardrails" / "config"

# So `from recognizers import build_registered_recognizers` (used by
# guardrails/config's colang actions? no -- used directly below) resolves
# regardless of the caller's cwd.
sys.path.insert(0, str(_HERE / "guardrails"))

REFUSAL_MARKER = "Request blocked by TJR Model Router input/output guardrails"


def _cmd_redact(payload: dict[str, Any]) -> dict[str, Any]:
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine
    from recognizers import build_registered_recognizers

    text = payload.get("text", "")

    # Explicit small spacy model (en_core_web_sm), not presidio's default
    # en_core_web_lg (400MB) -- see knowledge record for why that default
    # was overridden.
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
    ).create_engine()

    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    for recognizer in build_registered_recognizers():
        analyzer.registry.add_recognizer(recognizer)

    results = analyzer.analyze(text=text, language="en")
    anonymizer = AnonymizerEngine()
    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)

    return {
        "redacted_text": anonymized.text,
        "findings": [
            {
                "entity_type": r.entity_type,
                "start": r.start,
                "end": r.end,
                "score": round(r.score, 3),
                "text": text[r.start:r.end],
            }
            for r in results
        ],
    }


def _build_rails(fake_responses: list[str] | None, ollama_base_url: str):
    from nemoguardrails import LLMRails, RailsConfig

    config = RailsConfig.from_path(str(_GUARDRAILS_CONFIG_DIR))
    # Rewrite the main model's base_url from the real OLLAMA_BASE_URL env
    # var (config.yml ships the default http://localhost:11434 for
    # readability) -- see config.yml's own comment.
    for model in config.models:
        if model.type == "main" and model.engine == "ollama":
            params = dict(model.parameters or {})
            params["base_url"] = ollama_base_url.rstrip("/") + "/v1"
            model.parameters = params

    llm = None
    if fake_responses is not None:
        from nemoguardrails.testing.fake_model import FakeLLMModel

        llm = FakeLLMModel(responses=fake_responses)

    return LLMRails(config, llm=llm)


def _run_rail(rail: str, text: str, fake_responses: list[str] | None, ollama_base_url: str) -> dict[str, Any]:
    from nemoguardrails.rails.llm.options import GenerationOptions

    rails = _build_rails(fake_responses, ollama_base_url)

    if rail == "input":
        options = GenerationOptions(rails={"input": True, "output": False, "dialog": False, "retrieval": False})
        messages = [{"role": "user", "content": text}]
    else:
        options = GenerationOptions(rails={"input": False, "output": True, "dialog": False, "retrieval": False})
        # Output rail flows key off $bot_message, which NeMo Guardrails
        # populates from the last assistant turn in the message list.
        messages = [
            {"role": "user", "content": "(preceding user turn, not under test)"},
            {"role": "assistant", "content": text},
        ]

    async def _go():
        return await rails.generate_async(messages=messages, options=options)

    response = asyncio.run(_go())
    content = response.response
    if isinstance(content, list):
        content = "".join(str(m.get("content", "")) for m in content if isinstance(m, dict))
    blocked = REFUSAL_MARKER in (content or "")
    return {"blocked": blocked, "response": content}


def _cmd_check_input(payload: dict[str, Any]) -> dict[str, Any]:
    result = _run_rail("input", payload.get("prompt", ""), payload.get("fake_responses"), payload.get("ollama_base_url", "http://localhost:11434"))
    return {"blocked": result["blocked"], "reason": "input rail (jailbreak/prompt-injection check)" if result["blocked"] else None, "raw_response": result["response"]}


def _cmd_check_output(payload: dict[str, Any]) -> dict[str, Any]:
    result = _run_rail("output", payload.get("response_text", ""), payload.get("fake_responses"), payload.get("ollama_base_url", "http://localhost:11434"))
    return {"blocked": result["blocked"], "reason": "output rail (unsafe-content/credential-leak check)" if result["blocked"] else None, "raw_response": result["response"]}


_COMMANDS = {
    "redact": _cmd_redact,
    "check_input": _cmd_check_input,
    "check_output": _cmd_check_output,
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in _COMMANDS:
        sys.stderr.write(f"usage: {sys.argv[0]} {{{'|'.join(_COMMANDS)}}} < request.json\n")
        return 2
    payload = json.loads(sys.stdin.read() or "{}")
    try:
        result = _COMMANDS[sys.argv[1]](payload)
    except Exception as exc:  # noqa: BLE001 — always report structured failure to the caller
        json.dump({"error": f"{type(exc).__name__}: {exc}"}, sys.stdout)
        return 1
    json.dump(result, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
