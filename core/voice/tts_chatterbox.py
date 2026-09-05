#!/usr/bin/env python3
"""
Starship Endeavour Chatterbox TTS — local Nano-model voice service.

Wraps resemble-ai/chatterbox (Nano, 110M, CPU-friendly) behind a small HTTP
API so workbenches and LifeOS can request local, voice-cloneable speech
without going through edge-tts (cloud).

Endpoints:
    POST /api/tts/generate   {"text": str, "voice_ref": str|null, "cache_key": str|null} -> wav bytes
    GET  /api/tts/status     model load state + device

Port: CHATTERBOX_PORT (default 8893)
Model loads once at startup and stays resident (Nano is small enough
to keep warm; no keep_alive eviction like the Ollama router).

2026-09-05: measured ~35s to generate one ~90-char sentence on this VM's
8-core AMD EPYC — confirmed live (top during a generate() call) the
model only uses ~1.5 cores regardless of torch's 8-thread default; this
is an autoregressive/sequential decode, not thread-starved, so more
cores won't fix it. Two real levers added this session instead of
chasing raw speed: (1) auth, since this is now exposed publicly via
Caddy for Vercel to reach; (2) on-disk caching by `cache_key`, so
predictable content (the daily brief, pre-generated the moment it's
written — see intelligence/scheduler.py) plays back instantly instead of
regenerating on every tap. Live/dynamic content (e.g. the alerts
read-aloud) has no cache_key and still pays the full ~35s each time —
accepted for now (Captain's call, testing phase).
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import threading
from pathlib import Path

import torch
import torchaudio as ta
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("chatterbox-tts")

PORT = int(os.environ.get("CHATTERBOX_PORT", "8893"))
DEFAULT_VOICE_REF = os.environ.get("CHATTERBOX_VOICE_REF")  # optional default cloned voice
SERVICE_SECRET = os.environ.get("TTS_SERVICE_SECRET", "")

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Starship Endeavour Chatterbox TTS")

_model = None
_model_lock = threading.Lock()


class GenerateRequest(BaseModel):
    text: str
    voice_ref: str | None = None  # path to a reference wav for voice cloning
    cache_key: str | None = None  # e.g. "brief-<uuid>" — stable id for content that shouldn't regenerate


def _safe_cache_path(cache_key: str) -> Path:
    # cache_key comes over the network — never trust it as a raw filename.
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.wav"


def _check_auth(x_tts_secret: str | None) -> None:
    if not SERVICE_SECRET:
        # Misconfigured deployment — fail closed, not open, now that this
        # is reachable from the public internet via Caddy.
        raise HTTPException(500, "TTS_SERVICE_SECRET not configured on server")
    if x_tts_secret != SERVICE_SECRET:
        raise HTTPException(401, "invalid or missing X-TTS-Secret")


def get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                log.info("Loading Chatterbox Nano model (cpu)...")
                from chatterbox.tts_turbo import ChatterboxTurboTTS
                _model = ChatterboxTurboTTS.from_pretrained(device="cpu", nano=True)
                log.info("Chatterbox Nano loaded, sample rate=%s", _model.sr)
    return _model


@app.get("/api/tts/status")
def status():
    return {
        "loaded": _model is not None,
        "device": "cpu",
        "model": "chatterbox-nano",
        "default_voice_ref": DEFAULT_VOICE_REF,
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
    voice_ref = req.voice_ref or DEFAULT_VOICE_REF
    try:
        if voice_ref:
            wav = model.generate(req.text, audio_prompt_path=voice_ref)
        else:
            wav = model.generate(req.text)
    except Exception as exc:  # noqa: BLE001
        log.exception("generation failed")
        raise HTTPException(500, f"generation failed: {exc}") from exc

    buf = io.BytesIO()
    ta.save(buf, wav, model.sr, format="wav")
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
