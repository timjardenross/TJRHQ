"""
Gemini API client for image (Nano Banana Pro) and speech generation. Replaces
MISSION_BRIEF.md's local Stable Diffusion + Coqui TTS paths - this VM has no
GPU, so both hero art and podcast narration are generated via the Gemini API
instead. Measured on this VM: local CPU Coqui TTS took ~12.5min to narrate a
1,100-word article; Gemini TTS did the same article in 230s for a real 6.5min
narration. See compound-engineering:gemini-imagegen skill for the image half.
"""

import hashlib
import io
import os
import time
import wave
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image as PILImage
from PIL.Image import Image
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.config import load_config
from src.utils.logging import get_logger

_IMAGE_MODEL = "gemini-3-pro-image-preview"
_TTS_MODEL = "gemini-2.5-flash-preview-tts"
_TEXT_MODEL = "gemini-2.5-flash"
_TTS_SAMPLE_RATE = 24000
_CACHE_DIR = Path(__file__).resolve().parents[2] / "outputs" / ".cache"
_client: genai.Client | None = None
_cache_pruned = False
log = get_logger("gemini_client")

_retry_gemini = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    reraise=True,
)


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set (expected in .env at project root)")
        _client = genai.Client(api_key=api_key)
    return _client


def _cache_enabled() -> bool:
    return load_config().get("storage", {}).get("cache_enabled", True)


def _cache_ttl() -> int:
    """Seconds a cache entry stays valid; <=0 means never expire. config.yml declared
    this (storage.cache_ttl) from the start but nothing ever read it - cache grew
    unbounded with no eviction. Wired up here (freshness check + a one-time sweep of
    already-expired files per process, not a background job)."""
    return load_config().get("storage", {}).get("cache_ttl", 3600)


def _cache_fresh(path: Path) -> bool:
    ttl = _cache_ttl()
    return ttl <= 0 or (time.time() - path.stat().st_mtime) < ttl


def _prune_expired_cache_once() -> None:
    global _cache_pruned
    if _cache_pruned or not _CACHE_DIR.exists():
        return
    _cache_pruned = True
    ttl = _cache_ttl()
    if ttl <= 0:
        return
    removed = 0
    for path in _CACHE_DIR.rglob("*"):
        if path.is_file() and not _cache_fresh(path):
            path.unlink()
            removed += 1
    if removed:
        log.info(f"cache prune: removed {removed} expired file(s) (ttl={ttl}s)")


def _cache_path(kind: str, cache_key: str, ext: str) -> Path:
    _prune_expired_cache_once()
    digest = hashlib.sha256(cache_key.encode()).hexdigest()[:24]
    path = _CACHE_DIR / kind / f"{digest}.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@_retry_gemini
def _call_generate_image(prompt: str, aspect_ratio: str, resolution: str) -> bytes:
    response = _get_client().models.generate_content(
        model=_IMAGE_MODEL,
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio, image_size=resolution),
        ),
    )
    for part in response.parts:
        if part.inline_data:
            return part.inline_data.data
    raise RuntimeError(f"Gemini returned no image for prompt: {prompt[:80]!r}")


def generate_image(prompt: str, aspect_ratio: str = "1:1", resolution: str = "1K") -> Image:
    cache_key = f"{_IMAGE_MODEL}|{prompt}|{aspect_ratio}|{resolution}"
    cache_file = _cache_path("images", cache_key, "jpg")

    if _cache_enabled() and cache_file.exists() and _cache_fresh(cache_file):
        log.info(f"image cache hit: {prompt[:60]!r}")
        return PILImage.open(cache_file)

    data = _call_generate_image(prompt, aspect_ratio, resolution)
    if _cache_enabled():
        cache_file.write_bytes(data)
    # Decode fresh from bytes rather than the just-written file, so caching stays a
    # side effect and behaves identically whether cache_enabled is True or False.
    return PILImage.open(io.BytesIO(data))


@_retry_gemini
def _call_generate_text(prompt: str) -> str:
    response = _get_client().models.generate_content(model=_TEXT_MODEL, contents=prompt)
    return response.text


def generate_text(prompt: str) -> str:
    """Plain text completion (e.g. narration rewriting), cached like the other calls."""
    cache_key = f"{_TEXT_MODEL}|{prompt}"
    cache_file = _cache_path("text", cache_key, "txt")

    if _cache_enabled() and cache_file.exists() and _cache_fresh(cache_file):
        log.info(f"text cache hit: {prompt[:60]!r}")
        return cache_file.read_text(encoding="utf-8")

    result = _call_generate_text(prompt)
    if _cache_enabled():
        cache_file.write_text(result, encoding="utf-8")
    return result


@_retry_gemini
def _call_generate_speech(text: str, voice_name: str) -> bytes:
    response = _get_client().models.generate_content(
        model=_TTS_MODEL,
        contents=f"Read this aloud in a warm, clear, podcast-narrator voice: {text}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        ),
    )
    return response.candidates[0].content.parts[0].inline_data.data


def generate_speech(text: str, voice_name: str = "Kore", out_path: str | None = None) -> bytes:
    """Narrate `text` and return 24kHz mono 16-bit PCM WAV bytes. If out_path is
    given, also writes the WAV file there."""
    cache_key = f"{_TTS_MODEL}|{voice_name}|{text}"
    cache_file = _cache_path("speech", cache_key, "wav")

    if _cache_enabled() and cache_file.exists() and _cache_fresh(cache_file):
        log.info(f"speech cache hit: {len(text)} chars")
        wav_bytes = cache_file.read_bytes()
    else:
        pcm = _call_generate_speech(text, voice_name)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(_TTS_SAMPLE_RATE)
            wf.writeframes(pcm)
        wav_bytes = buffer.getvalue()
        if _cache_enabled():
            cache_file.write_bytes(wav_bytes)

    if out_path:
        with open(out_path, "wb") as f:
            f.write(wav_bytes)
    return wav_bytes
