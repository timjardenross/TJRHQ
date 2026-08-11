"""
Gemini API client for image (Nano Banana Pro) and speech generation. Replaces
MISSION_BRIEF.md's local Stable Diffusion + Coqui TTS paths - this VM has no
GPU, so both hero art and podcast narration are generated via the Gemini API
instead. Measured on this VM: local CPU Coqui TTS took ~12.5min to narrate a
1,100-word article; Gemini TTS did the same article in 230s for a real 6.5min
narration. See compound-engineering:gemini-imagegen skill for the image half.
"""

import io
import os
import wave

from google import genai
from google.genai import types
from PIL import Image as PILImage
from PIL.Image import Image

_IMAGE_MODEL = "gemini-3-pro-image-preview"
_TTS_MODEL = "gemini-2.5-flash-preview-tts"
_TTS_SAMPLE_RATE = 24000
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set (expected in .env at project root)")
        _client = genai.Client(api_key=api_key)
    return _client


def generate_image(prompt: str, aspect_ratio: str = "1:1", resolution: str = "1K") -> Image:
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
            # part.as_image() returns the SDK's own Image wrapper (has .save()/.show()
            # but not PIL's API); decode its raw bytes into a real PIL.Image instead so
            # downstream renderers can composite/convert/overlay on it.
            return PILImage.open(io.BytesIO(part.inline_data.data))
    raise RuntimeError(f"Gemini returned no image for prompt: {prompt[:80]!r}")


def generate_speech(text: str, voice_name: str = "Kore", out_path: str | None = None) -> bytes:
    """Narrate `text` and return 24kHz mono 16-bit PCM WAV bytes. If out_path is
    given, also writes the WAV file there."""
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
    pcm = response.candidates[0].content.parts[0].inline_data.data

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_TTS_SAMPLE_RATE)
        wf.writeframes(pcm)
    wav_bytes = buffer.getvalue()

    if out_path:
        with open(out_path, "wb") as f:
            f.write(wav_bytes)
    return wav_bytes
