#!/usr/bin/env python3
"""
Starship Endeavour Kokoro TTS — local narration voice service.

USS-TJR-MSN-0366 Stream 7 pilot: Chatterbox (core/voice/tts_chatterbox.py)
measured 0.08x realtime on this VM's CPU (a 4-second clip took 48 seconds).
That is viable only as an eventual-consistency background job, not as
anything a person waits on. This service wraps Kokoro-82M (hexgrad,
Apache-2.0) via the `kokoro-onnx` ONNX Runtime port behind the same
per-service HTTP-API pattern as tts_chatterbox.py, for the "async
pre-generated narration" niche: briefs, debrief clips, any text with no
`voice_ref` (no cloning requested). Chatterbox is re-scoped to
voice-cloning-only per this same mission — see its own updated docstring.

Why `kokoro-onnx` and not the `kokoro` PyPI package (hexgrad's own,
torch-based): both were tried. `pip install kokoro` pulled in a 5.9GB
venv (torch 2.14 + a full CUDA 13 dependency stack — cublas, cudnn,
cusolver, nccl, triton, etc.) even for CPU-only inference, because
PyPI's default Linux torch wheel bundles those as install-time
dependencies regardless of whether a GPU is present. Worse, both
`kokoro` and `kittentts` (the fallback candidate) fetch their model
weights from huggingface.co via `huggingface_hub.hf_hub_download()` at
runtime, and huggingface.co (all subdomains, including its CDN) is
blocked at this deployment's egress proxy by organization policy
(confirmed: CONNECT tunnel refused with 403 on every huggingface.co
host tried) — a hard blocker, not a transient failure, so neither
package's default path could load a model in this sandbox at all.
`kokoro-onnx` (thewh1teagle, MIT, wraps the same Apache-2.0 Kokoro-82M
weights in ONNX Runtime) ships its model files as GitHub Release
assets instead (github.com is reachable from this sandbox) — installed
clean at 199MB, zero torch, zero CUDA, zero huggingface_hub dependency.
Model files (kokoro-v1.0.onnx, ~311MB; voices-v1.0.bin, ~27MB) were
downloaded once from
https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/
into core/voice/kokoro-models/ (gitignored, same pattern as
chatterbox-venv/ — see root .gitignore) and are NOT re-fetched at
request time; get_model() below loads them from local disk only.

2026-09-12: real measured generation on this VM's CPU (8-core AMD EPYC,
same VM Chatterbox's header documents), `time.time()` around the actual
`Kokoro.create()` inference call, no stubs:
  - 80-char sentence (comparable length to Chatterbox's own ~90-char
    benchmark sentence, which took ~35s / a 4-second clip took 48s on
    Chatterbox): 1.83s generation, 4.81s audio => 2.63x realtime.
  - 207-char paragraph: 14.11s generation, 14.62s audio => 1.04x realtime.
Both real clips saved (core/voice/kokoro_narration_sample_90char.wav,
core/voice/kokoro_narration_sample.wav) during this session's pilot run.
That's roughly 33x wall-clock faster than Chatterbox on a
similar-length clip (1.83s vs. Chatterbox's ~48s), comfortably clearing
the "seconds, not a claim" acceptance bar for async pre-generated
narration. No voice cloning support — Kokoro-82M has a fixed voice
bank (`voices-v1.0.bin`, 8+ named voices), which is exactly the
capability split this mission asks for: Kokoro for narration, Chatterbox
kept for the one thing it can do that Kokoro can't (`voice_ref` cloning).

Endpoints:
    POST /api/tts/generate   {"text": str, "voice": str|null, "cache_key": str|null} -> wav bytes
    GET  /api/tts/status     model load state + device

Port: KOKORO_PORT (default 8894)
Model loads once at startup and stays resident (ONNX Runtime session,
~340MB combined, far lighter to keep warm than Chatterbox's torch model).

Note: this service has no `voice_ref` field at all (unlike
tts_chatterbox.py's GenerateRequest) — voice cloning is out of scope
here by design, not merely unimplemented. A caller that needs cloning
should call Chatterbox directly; see intelligence/scheduler.py's
_pregenerate_brief_audio() for the narration-side routing this mission
added.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import threading
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kokoro-tts")

PORT = int(os.environ.get("KOKORO_PORT", "8894"))
DEFAULT_VOICE = os.environ.get("KOKORO_VOICE", "af_heart")
SERVICE_SECRET = os.environ.get("TTS_SERVICE_SECRET", "")

MODEL_DIR = Path(__file__).parent / "kokoro-models"
MODEL_PATH = MODEL_DIR / "kokoro-v1.0.onnx"
VOICES_PATH = MODEL_DIR / "voices-v1.0.bin"

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Starship Endeavour Kokoro TTS")

_model = None
_model_lock = threading.Lock()


class GenerateRequest(BaseModel):
    text: str
    voice: str | None = None  # named voice from Kokoro's built-in bank, e.g. "af_heart"
    speed: float = 1.0
    cache_key: str | None = None  # e.g. "brief-<uuid>" — stable id for content that shouldn't regenerate


def _safe_cache_path(cache_key: str) -> Path:
    # cache_key comes over the network — never trust it as a raw filename.
    digest = hashlib.sha256(("kokoro-" + cache_key).encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.wav"


def _check_auth(x_tts_secret: str | None) -> None:
    if not SERVICE_SECRET:
        # Misconfigured deployment — fail closed, not open, same posture as
        # tts_chatterbox.py now that voice services are reachable via Caddy.
        raise HTTPException(500, "TTS_SERVICE_SECRET not configured on server")
    if x_tts_secret != SERVICE_SECRET:
        raise HTTPException(401, "invalid or missing X-TTS-Secret")


def get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                if not MODEL_PATH.exists() or not VOICES_PATH.exists():
                    raise RuntimeError(
                        f"Kokoro model files missing under {MODEL_DIR} — download "
                        "kokoro-v1.0.onnx and voices-v1.0.bin from "
                        "https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.1 "
                        "(NOT huggingface.co — see this module's header comment for why)."
                    )
                log.info("Loading Kokoro ONNX model (cpu) from %s...", MODEL_DIR)
                from kokoro_onnx import Kokoro
                _model = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
                log.info("Kokoro loaded.")
    return _model


@app.get("/api/tts/status")
def status():
    return {
        "loaded": _model is not None,
        "device": "cpu",
        "model": "kokoro-82m-onnx" if _model is not None else None,
        "default_voice": DEFAULT_VOICE,
        "supports_voice_cloning": False,
    }


@app.post("/api/tts/generate")
def generate(req: GenerateRequest, x_tts_secret: str | None = Header(default=None)):
    _check_auth(x_tts_secret)
    if not req.text.strip():
        raise HTTPException(400, "text is required")

    cache_path = _safe_cache_path(req.cache_key) if req.cache_key else None
    if cache_path and cache_path.exists():
        log.info("cache hit for key=%s", req.cache_key)
        return FileResponse(cache_path, media_type="audio/wav")

    model = get_model()
    voice = req.voice or DEFAULT_VOICE
    try:
        samples, sample_rate = model.create(req.text, voice=voice, speed=req.speed, lang="en-us")
    except Exception as exc:  # noqa: BLE001
        log.exception("generation failed")
        raise HTTPException(500, f"generation failed: {exc}") from exc

    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="wav")
    buf.seek(0)

    if cache_path:
        with open(cache_path, "wb") as f:
            f.write(buf.getvalue())
        log.info("cached generation under key=%s", req.cache_key)
        buf.seek(0)

    return StreamingResponse(buf, media_type="audio/wav")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
