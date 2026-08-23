#!/usr/bin/env python3
"""
Starship Endeavour Model Router — on-call Ollama crew dispatcher.

Routes requests to local Ollama models with explicit keep_alive values.
No model stays loaded all day — each task type specifies its own keep_alive.

Endpoints:
    POST /api/model/classify-capture    gemma3:4b      keep_alive 2m
    POST /api/model/summarise-note      gemma3:4b      keep_alive 2m
    POST /api/model/classify-document   gemma3:4b      keep_alive 5m   (MSN-0205C)
    POST /api/model/summarise-document  gemma3:4b      keep_alive 5m   (MSN-0205C)
    POST /api/model/intelligence-brief  gemini-flash-latest  (cloud, GEMINI_API_KEY — moved 2026-08-23, local mistral-small3.2:24b too slow on this CPU-only box)
    POST /api/model/xo-response         mistral-small  keep_alive 15m
    POST /api/model/embed               nomic-embed    keep_alive 1m
    POST /api/model/escalate            mistral-small  keep_alive 15m
    POST /api/model/billing-report       gemini-flash-latest  (cloud, GEMINI_BILLING_API_KEY)
    POST /api/model/self-improvement-analyse   gemini-flash-latest  (cloud, GEMINI_API_KEY)
    POST /api/model/self-improvement-critique  gemini-flash-latest  (cloud, GEMINI_API_KEY)
    POST /api/model/self-improvement-mission   gemini-flash-latest  (cloud, GEMINI_API_KEY)
    GET  /api/model/status              Ollama status + loaded models
    GET  /api/model/recent-calls        Last N calls from log

Port: MODEL_ROUTER_PORT (default 8891)
Ollama: OLLAMA_BASE_URL (default http://localhost:11434)
Gemini: GEMINI_API_KEY (self-improvement routes) and GEMINI_BILLING_API_KEY
(billing-report only, kept separate so its usage/cost stays isolated).

No external dependencies — stdlib only.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [model-router] %(levelname)s %(message)s",
)
log = logging.getLogger("model-router")

# Optional OTel tracing — stdlib-only fallback when platform-runtime venv is
# not available (model-router runs under system Python with no external deps).
try:
    sys.path.insert(0, '/opt/starship-endeavour/platform-runtime/.venv/lib/python3.12/site-packages')
    from platform_runtime.lib.telemetry import configure_tracing as _configure_tracing
    from opentelemetry import trace as _otel_trace
    _configure_tracing("model-router")
    _ROUTER_TRACING_AVAILABLE = True
except Exception:
    _ROUTER_TRACING_AVAILABLE = False


def _emit_router_span(task_type: str, model: str, duration_ms: int, success: bool) -> None:
    """
    Fire a completed OTel span recording one model-router dispatch outcome.

    Called immediately after _log_call() in _run_task() so every routed
    request appears in the trace backend alongside the structured log entry.
    No-ops silently when tracing is unavailable.

    Args:
        task_type:   Router task key (e.g. "classify-capture")
        model:       Model name that served the request
        duration_ms: Wall-clock duration of the full dispatch
        success:     Whether the dispatch returned a non-error result
    """
    if not _ROUTER_TRACING_AVAILABLE:
        return
    try:
        tracer = _otel_trace.get_tracer("model_router")
        with tracer.start_as_current_span(
            f"router.{task_type}",
            attributes={
                "router.task_type": task_type,
                "router.model": model,
                "router.duration_ms": duration_ms,
                "router.success": success,
            },
        ):
            pass  # span closes immediately; timing is recorded in attributes
    except Exception:
        pass

_PORT = int(os.environ.get("MODEL_ROUTER_PORT", 8891))
_HOST = os.environ.get("MODEL_ROUTER_HOST", "127.0.0.1")
_OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_LOG_FILE = Path(__file__).parent / "call_log.jsonl"
_LOG_LIMIT = int(os.environ.get("MODEL_ROUTER_LOG_LIMIT", 200))

# ── Model catalogue ──────────────────────────────────────────────────────────

MODEL_MID   = "gemma3:4b"          # fast classifier / XO chat / summariser
MODEL_LARGE = "mistral-small3.2:24b" # intelligence briefs / synthesis
MODEL_EMBED = "nomic-embed-text"      # embeddings
MODEL_CLOUD = "glm-5.2:cloud"         # cloud fallback (no keep_alive)
MODEL_CODE  = "qwen2.5-coder:7b"      # engineering review
MODEL_GEMINI = "gemini-flash-latest"  # billing reports (Gemini API, not Ollama)

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# keep_alive values per task type
TASK_POLICY: dict[str, dict[str, Any]] = {
    "classify-capture":      {"model": MODEL_MID,   "keep_alive": "5m",  "timeout": 300},
    "summarise-note":        {"model": MODEL_MID,   "keep_alive": "5m",  "timeout": 300},
    # MSN-0205C: document processing pipeline. Deliberately separate task
    # types from classify-capture/summarise-note (not aliases) — capture
    # classification has its own escalation-trigger logic keyed to
    # task_type == "classify-capture" that document prompts should not
    # inherit, and separate task types keep the call log distinguishable.
    # keep_alive raised to 15m (from 5m) and num_predict capped: on this
    # CPU-only box a batch run marches many docs through the same stage in a
    # row (see worker.py process_batch's stage-batched ordering), so the
    # model needs to survive longer gaps than a single interactive call, and
    # the JSON outputs here are short — no need to let decode run unbounded.
    "classify-document":     {"model": MODEL_MID,   "keep_alive": "15m", "timeout": 300, "num_predict": 220},
    # num_predict 400 was too tight — some summaries run past it and get cut
    # off mid-sentence before closing their JSON, so the response fails to
    # parse (observed on Coco_babyVet.pdf). Bumped to 700 to give the model
    # room to actually finish the JSON object; watch for the same truncation
    # symptom if a doc still overruns this.
    "summarise-document":    {"model": MODEL_MID,   "keep_alive": "15m", "timeout": 300, "num_predict": 700},
    "xo-response":           {"model": MODEL_MID,   "keep_alive": "10m", "timeout": 300},
    # 2026-08-23: moved from local MODEL_LARGE (mistral-small3.2:24b) to
    # Gemini — same reasoning as captain-insight-synthesis/
    # captain-reasoning-synthesis below, which were fixed for this exact
    # problem on 2026-08-22 but this sibling task (identical tier: "large
    # model", CPU-only local Ollama, quality-sensitive not latency-
    # sensitive) was missed in that pass. Confirmed live 2026-08-23: a real
    # call took 238870ms — squarely in the 168-238s range that already
    # triggered the other two tasks' migration, and every caller
    # (intelligence/brief/llm_provider.py's _model_router(), used by both
    # captains_brief.py's daily digest and brief_generator.py's ORI brief)
    # only waits 60s before giving up, so this task had NEVER once
    # successfully served a caller in production — every real request fell
    # through to the caller's own cloud fallback chain instead. See
    # `esc_policy` in _run_task() below for classify-capture's escalation
    # path, deliberately decoupled from this entry rather than reused now
    # that the two have different provider shapes.
    "intelligence-brief":    {"model": MODEL_GEMINI, "provider": "gemini", "api_key_env": "GEMINI_API_KEY", "timeout": 120},
    "intelligence-signals":  {"model": MODEL_LARGE, "keep_alive": "10m", "timeout": 300},
    # MSN-0329 Phase 2: Captain Intelligence's Understanding/Insight Engine.
    # Same tier as intelligence-brief: infrequent, quality-sensitive, not
    # latency-sensitive. Per the Captain's resolved hybrid design, this
    # call synthesizes cross-domain meaning ONLY over items the
    # deterministic Attention/Priority gate already surfaced — it never
    # decides surfacing itself. num_predict added MSN-0329 Phase 3 (real
    # production call, 2026-07-07): the unbounded default let a real
    # mistral-small3.2:24b response run past its own JSON object before
    # finishing, producing an unparseable truncated response — same
    # failure mode this file's own summarise-document entry already
    # documents for a different task_type.
    # 2026-08-22: moved from local MODEL_LARGE (mistral-small3.2:24b) to
    # Gemini — same reasoning as self-improvement-* below. Real observed
    # latency on this CPU-only box was 168-238s per call, occasionally
    # exceeding even the 300s timeout outright ("unexpected=timed out" in
    # this service's own log, every ~4h, matching the scheduled job that
    # calls this task type). When that happened the caller gave up and
    # closed its connection before this service finished, so the eventual
    # response write hit a dead socket -- BrokenPipeError, every time,
    # confirmed live via journalctl. Also kept a 15GB model resident in
    # RAM (of 23GB total) for the run's duration, on the very first LLM
    # tier every pipeline on this platform tries before anything else.
    # Uses the shared GEMINI_API_KEY (not the billing-report key -- these
    # aren't billing/cost-report calls).
    "captain-insight-synthesis": {"model": MODEL_GEMINI, "provider": "gemini", "api_key_env": "GEMINI_API_KEY", "timeout": 120},
    # MSN-0329 Phase 2 Step 4: Reasoning Engine. Separate task_type from
    # captain-insight-synthesis (different prompt/purpose) so the call
    # log stays distinguishable, matching this file's own established
    # convention (see classify-document vs summarise-note's comment).
    # Consumes a Step 3 Insight, never the raw event stream directly.
    # Moved to Gemini 2026-08-22 for the same reason as the entry above.
    "captain-reasoning-synthesis": {"model": MODEL_GEMINI, "provider": "gemini", "api_key_env": "GEMINI_API_KEY", "timeout": 120},
    "embed":                 {"model": MODEL_EMBED, "keep_alive": "1m",  "timeout": 30},
    "escalate":              {"model": MODEL_LARGE, "keep_alive": "15m", "timeout": 300},
    "fallback-complex":      {"model": MODEL_CLOUD, "keep_alive": "0",   "timeout": 120},
    "engineering-review":    {"model": MODEL_CODE,  "keep_alive": "10m", "timeout": 300},
    # Gemini API (not Ollama) — separate provider branch in _run_task.
    # Uses GEMINI_BILLING_API_KEY, a dedicated key so billing-report cost
    # tracking stays isolated from the shared GEMINI_API_KEY used elsewhere.
    "billing-report":        {"model": MODEL_GEMINI, "provider": "gemini", "api_key_env": "GEMINI_BILLING_API_KEY", "timeout": 120},
    # Self-improvement system (MSN-0099): moved from local MODEL_MID
    # (gemma3:4b) to Gemini — evidence-analysis quality needs a stronger
    # model than the CPU-only VM can serve locally in reasonable time.
    # Uses the shared GEMINI_API_KEY (not the billing-report key — this
    # isn't a billing/cost-report call, so it doesn't belong on that
    # isolated key).
    "self-improvement-analyse":  {"model": MODEL_GEMINI, "provider": "gemini", "api_key_env": "GEMINI_API_KEY", "timeout": 600},
    "self-improvement-critique": {"model": MODEL_GEMINI, "provider": "gemini", "api_key_env": "GEMINI_API_KEY", "timeout": 600},
    "self-improvement-mission":  {"model": MODEL_GEMINI, "provider": "gemini", "api_key_env": "GEMINI_API_KEY", "timeout": 600},
}

# Escalation triggers — checked against PROMPT ONLY (not response) for classify-capture.
# Narrow and intent-based: matches things the Captain is actually asking to do,
# not words that naturally appear in classification tags/summaries.
ESCALATION_TRIGGERS = [
    "build request",
    "build this",
    "please build",
    "please implement",
    "operational resilience",
    "is this a risk",
    "health risk",
    "mission critical",
    "generate report",
    "low confidence",
    "not sure what",
    "needs research",
    "requires investigation",
]


# ── Ollama client ─────────────────────────────────────────────────────────────

def _ollama_generate(model: str, prompt: str, keep_alive: str, timeout: int, num_predict: int | None = None) -> dict[str, Any]:
    """POST /api/generate. Returns parsed response dict."""
    url = f"{_OLLAMA_BASE}/api/generate"
    options = {"temperature": 0.2}
    if num_predict is not None:
        options["num_predict"] = num_predict
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
        "options": options,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _ollama_embed(model: str, input_text: str, keep_alive: str, timeout: int) -> dict[str, Any]:
    """POST /api/embed. Returns parsed response dict."""
    url = f"{_OLLAMA_BASE}/api/embed"
    payload = json.dumps({
        "model": model,
        "input": input_text,
        "keep_alive": keep_alive,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _gemini_generate(model: str, prompt: str, timeout: int, api_key_env: str = "GEMINI_API_KEY") -> dict[str, Any]:
    """POST /v1beta/models/{model}:generateContent. Returns parsed response dict."""
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"{api_key_env} is not set. Add it to .env before using this Gemini-backed route.")
    url = f"{_GEMINI_BASE}/models/{model}:generateContent"
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "X-goog-api-key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _ollama_status() -> dict[str, Any]:
    """GET /api/ps — loaded models. Returns dict."""
    try:
        with urllib.request.urlopen(f"{_OLLAMA_BASE}/api/ps", timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        return {"error": str(exc)}


def _ollama_tags() -> dict[str, Any]:
    """GET /api/tags — available models."""
    try:
        with urllib.request.urlopen(f"{_OLLAMA_BASE}/api/tags", timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        return {"error": str(exc)}


# ── Call log ──────────────────────────────────────────────────────────────────

def _log_call(entry: dict[str, Any]) -> None:
    try:
        with _LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.warning("call log write failed: %s", exc)


def _recent_calls(n: int = 20) -> list[dict[str, Any]]:
    if not _LOG_FILE.exists():
        return []
    lines = _LOG_FILE.read_text(encoding="utf-8").splitlines()
    out = []
    for ln in reversed(lines[-_LOG_LIMIT:]):
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            pass
        if len(out) >= n:
            break
    return out


# ── Routing logic ─────────────────────────────────────────────────────────────

def _check_escalation_needed(prompt: str, response_text: str) -> tuple[bool, str]:
    """Return (should_escalate, reason). Checks prompt only — not the model response.
    Avoids false-positives from classification tags like 'develop', 'report', 'research'."""
    prompt_lower = prompt.lower()
    for trigger in ESCALATION_TRIGGERS:
        if trigger in prompt_lower:
            return True, f"trigger:{trigger.strip()}"
    return False, ""


def _available_model_names() -> set[str]:
    """Return set of installed model names (without :latest normalisation)."""
    tags = _ollama_tags()
    names: set[str] = set()
    for m in tags.get("models", []):
        n = m.get("name", "")
        names.add(n)
        names.add(n.split(":")[0])  # bare name match too
    return names


def _run_task(task_type: str, prompt: str, extra: dict[str, Any]) -> dict[str, Any]:
    """Execute routing policy and return result dict."""
    policy = TASK_POLICY.get(task_type)
    if not policy:
        return {"success": False, "error": f"unknown task_type: {task_type}"}

    # engineering-review: prefer qwen3-coder:30b, fall back to glm-5.2:cloud
    if task_type == "engineering-review":
        available = _available_model_names()
        if MODEL_CODE not in available and MODEL_CODE.split(":")[0] not in available:
            log.info("engineering-review: %s not installed, falling back to %s", MODEL_CODE, MODEL_CLOUD)
            policy = {**policy, "model": MODEL_CLOUD, "keep_alive": "0"}

    model = policy["model"]
    keep_alive = policy.get("keep_alive", "n/a")
    timeout = policy["timeout"]
    escalated = False
    escalation_reason = ""

    t0 = time.time()
    try:
        if policy.get("provider") == "gemini":
            raw = _gemini_generate(model, prompt, timeout, policy.get("api_key_env", "GEMINI_API_KEY"))
            candidates = raw.get("candidates", [])
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            response_text = "".join(p.get("text", "") for p in parts).strip()
            embeddings = None
            usage = raw.get("usageMetadata", {})
            token_info = {
                "prompt_eval_count": usage.get("promptTokenCount"),
                "eval_count": usage.get("candidatesTokenCount"),
            }
        elif task_type == "embed":
            raw = _ollama_embed(model, prompt, keep_alive, timeout)
            response_text = ""
            embeddings = raw.get("embeddings", raw.get("embedding", []))
            token_info = {"prompt_eval_count": raw.get("prompt_eval_count")}
        else:
            raw = _ollama_generate(model, prompt, keep_alive, timeout, policy.get("num_predict"))
            response_text = raw.get("response", "").strip()
            embeddings = None
            token_info = {
                "prompt_eval_count": raw.get("prompt_eval_count"),
                "eval_count": raw.get("eval_count"),
            }

            # Escalation: classify-capture escalates to the large local model
            # if triggers detected. 2026-08-23: used to read
            # TASK_POLICY["intelligence-brief"] for this — that entry moved
            # to Gemini (see its own comment above) and no longer has a
            # keep_alive value or an Ollama-installed model name, so reusing
            # it here would KeyError and then try to run "gemini-flash-latest"
            # against local Ollama. This escalation genuinely wants the local
            # large model (classify-capture needs an Ollama round-trip, not a
            # cloud one, to stay in the same fast local tier it started in),
            # so it's now its own explicit policy rather than borrowed from a
            # task whose requirements have diverged.
            if task_type == "classify-capture" and not extra.get("skip_escalation"):
                needs_esc, reason = _check_escalation_needed(prompt, response_text)
                if needs_esc:
                    esc_model, esc_keep_alive, esc_timeout = MODEL_LARGE, "15m", 300
                    esc_raw = _ollama_generate(esc_model, prompt, esc_keep_alive, esc_timeout)
                    response_text = esc_raw.get("response", "").strip()
                    model = esc_model
                    keep_alive = esc_keep_alive
                    escalated = True
                    escalation_reason = reason
                    token_info = {
                        "prompt_eval_count": esc_raw.get("prompt_eval_count"),
                        "eval_count": esc_raw.get("eval_count"),
                    }

        duration_ms = int((time.time() - t0) * 1000)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "task_type": task_type,
            "model": model,
            "keep_alive": keep_alive,
            "duration_ms": duration_ms,
            "escalated": escalated,
            "escalation_reason": escalation_reason,
            "token_info": token_info,
            "prompt_len": len(prompt),
            "response_len": len(response_text),
            "success": True,
        }
        _log_call(entry)
        _emit_router_span(task_type, model, duration_ms, True)
        log.info("task=%s model=%s duration_ms=%d escalated=%s", task_type, model, duration_ms, escalated)

        result = {
            "success": True,
            "task_type": task_type,
            "model": model,
            "keep_alive": keep_alive,
            "response": response_text,
            "duration_ms": duration_ms,
            "escalated": escalated,
            "escalation_reason": escalation_reason if escalation_reason else None,
            "token_info": token_info,
        }
        if embeddings is not None:
            result["embeddings"] = embeddings
        return result

    except urllib.error.URLError as exc:
        duration_ms = int((time.time() - t0) * 1000)
        _log_call({"ts": datetime.now(timezone.utc).isoformat(), "task_type": task_type, "model": model,
                   "duration_ms": duration_ms, "success": False, "error": str(exc)})
        log.error("task=%s model=%s error=%s", task_type, model, exc)
        return {"success": False, "task_type": task_type, "model": model, "error": str(exc), "duration_ms": duration_ms}
    except Exception as exc:
        duration_ms = int((time.time() - t0) * 1000)
        _log_call({"ts": datetime.now(timezone.utc).isoformat(), "task_type": task_type, "model": model,
                   "duration_ms": duration_ms, "success": False, "error": str(exc)})
        log.error("task=%s model=%s unexpected=%s", task_type, model, exc)
        return {"success": False, "task_type": task_type, "model": model, "error": str(exc), "duration_ms": duration_ms}


# ── HTTP handler ──────────────────────────────────────────────────────────────

class RouterHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        log.debug(fmt, *args)

    def _send_json(self, code: int, body: dict | list) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            # 2026-08-22: a slow task (captain-insight-synthesis on the old
            # 24b local model, confirmed live, real latency 168-238s
            # sometimes exceeding its own timeout) meant the caller had
            # already given up and closed its connection by the time this
            # response was ready to write -- this raised an unhandled
            # exception through socketserver's request-handling machinery,
            # logging a full traceback every time it happened rather than
            # the one-line "client already gone" this actually is. The
            # slow-task root cause is fixed separately (that task now
            # routes to Gemini), but any task type can still race a client
            # timeout in principle, so this stays as a general guard.
            log.warning("client disconnected before response could be sent")

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode())
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/model/status":
            self._handle_status()
        elif self.path.startswith("/api/model/recent-calls"):
            self._handle_recent_calls()
        elif self.path == "/health":
            self._send_json(200, {"status": "ok", "port": _PORT})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.rstrip("/")
        route_map = {
            "/api/model/classify-capture":     "classify-capture",
            "/api/model/summarise-note":       "summarise-note",
            "/api/model/classify-document":    "classify-document",
            "/api/model/summarise-document":   "summarise-document",
            "/api/model/intelligence-brief":   "intelligence-brief",
            "/api/model/intelligence-signals": "intelligence-signals",
            "/api/model/xo-response":          "xo-response",
            "/api/model/embed":                "embed",
            "/api/model/escalate":             "escalate",
            "/api/model/fallback-complex":     "fallback-complex",
            "/api/model/engineering-review":   "engineering-review",
            "/api/model/captain-insight-synthesis": "captain-insight-synthesis",
            "/api/model/captain-reasoning-synthesis": "captain-reasoning-synthesis",
            "/api/model/billing-report":        "billing-report",
            "/api/model/self-improvement-analyse": "self-improvement-analyse",
            "/api/model/self-improvement-critique": "self-improvement-critique",
            "/api/model/self-improvement-mission": "self-improvement-mission",
        }
        task_type = route_map.get(path)
        if task_type is None:
            self._send_json(404, {"error": f"unknown route: {path}"})
            return
        body = self._read_body()
        prompt = body.get("prompt", "")
        if not prompt:
            self._send_json(400, {"error": "prompt is required"})
            return
        result = _run_task(task_type, prompt, body)
        code = 200 if result.get("success") else 500
        self._send_json(code, result)

    def _handle_status(self) -> None:
        ps = _ollama_status()
        tags = _ollama_tags()
        loaded = []
        for m in ps.get("models", []):
            loaded.append({
                "name": m.get("name"),
                "size_vram": m.get("size_vram"),
                "expires_at": m.get("expires_at"),
            })
        available = [m.get("name") for m in tags.get("models", [])]
        calls = _recent_calls(5)
        avg_ms = None
        if calls:
            times = [c.get("duration_ms", 0) for c in calls if c.get("success")]
            avg_ms = int(sum(times) / len(times)) if times else None
        failed = sum(1 for c in calls if not c.get("success"))
        # Expose the live routing policy so the UI renders the real task→model
        # mapping instead of a hardcoded copy that drifts (MSN-0351). Order is
        # preserved from TASK_POLICY's declaration order.
        routing_policy = [
            {
                "task_type": name,
                "model": policy["model"],
                "keep_alive": policy.get("keep_alive", "n/a"),
            }
            for name, policy in TASK_POLICY.items()
        ]
        self._send_json(200, {
            "ollama_url": _OLLAMA_BASE,
            "ollama_reachable": "error" not in ps,
            "loaded_models": loaded,
            "available_models": available,
            "router_port": _PORT,
            "log_file": str(_LOG_FILE),
            "recent_avg_ms": avg_ms,
            "recent_failed": failed,
            "routing_policy": routing_policy,
        })

    def _handle_recent_calls(self) -> None:
        import urllib.parse
        qs = urllib.parse.urlparse(self.path).query
        params = dict(urllib.parse.parse_qsl(qs))
        n = int(params.get("n", 20))
        self._send_json(200, {"calls": _recent_calls(n)})


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main() -> int:
    # Load .env from repo root or platform-runtime
    _load_dotenv()
    log.info("Model Router starting on %s:%d", _HOST, _PORT)
    log.info("Ollama base: %s", _OLLAMA_BASE)
    log.info("Call log: %s", _LOG_FILE)
    server = HTTPServer((_HOST, _PORT), RouterHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _load_dotenv() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    for candidate in [repo_root / ".env", repo_root / "platform-runtime" / ".env"]:
        if candidate.exists():
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
