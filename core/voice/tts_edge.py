"""edge-tts wrapper for XO voice output. Falls back silently if unavailable.

Uses Microsoft Edge's cloud-based neural TTS — no API key required.
Voice: en-AU-WilliamNeural (formal Australian male, matching the XO persona).

Callers should always send the text reply first, then call send_voice_reply
as a bonus layer. Any TTS or Telegram audio send failure is logged and
swallowed so the bot never crashes on an optional voice path.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile

log = logging.getLogger(__name__)

XO_VOICE = "en-AU-WilliamNeural"


async def speak_to_file(text: str) -> str | None:
    """Convert text to MP3 via Microsoft Edge TTS.

    Returns the temp file path on success, or None on any failure.
    The caller is responsible for deleting the file after use.
    """
    try:
        import edge_tts
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        communicate = edge_tts.Communicate(text, XO_VOICE)
        await communicate.save(tmp.name)
        return tmp.name
    except ImportError:
        log.warning("edge-tts not installed — voice output disabled")
        return None
    except Exception as exc:
        log.warning("TTS synthesis failed: %s", exc)
        return None


async def send_voice_reply(bot, chat_id: int, text: str) -> bool:
    """Send text as a voice audio message via the Telegram bot.

    Synthesises the text to a temporary MP3, sends it as a Telegram audio
    message, then deletes the temp file.

    Returns True if the audio was sent successfully, False if TTS synthesis
    or the Telegram send failed. The caller is expected to have already sent
    a text reply — this is always additive, never a replacement.
    """
    path = await speak_to_file(text)
    if not path:
        return False
    try:
        with open(path, "rb") as f:
            await bot.send_audio(chat_id=chat_id, audio=f)
        return True
    except Exception as exc:
        log.warning("Telegram audio send failed: %s", exc)
        return False
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass
