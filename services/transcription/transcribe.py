"""
Local voice transcription using faster-whisper.
USS-TJR Unified Capture Pipeline — CPU-only, no external API.

Usage:
    python transcribe.py /path/to/audio.ogg
    python transcribe.py /path/to/audio.ogg --language en

Importable:
    from transcribe import transcribe_file
    result = transcribe_file("/path/to/audio.ogg")
"""

import json
import sys
import time
from pathlib import Path

SUPPORTED_EXTENSIONS = {".ogg", ".oga", ".mp3", ".m4a", ".wav", ".webm"}

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("base", device="cpu", compute_type="int8")
    return _model


def transcribe_file(audio_path: str, language: str | None = None) -> dict:
    path = Path(audio_path)

    if not path.exists():
        return {"ok": False, "audio_path": audio_path, "error": f"File not found: {audio_path}"}

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return {
            "ok": False,
            "audio_path": audio_path,
            "error": f"Unsupported format '{path.suffix}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        }

    try:
        model = _get_model()
        t0 = time.monotonic()
        segments_iter, info = model.transcribe(
            str(path),
            language=language,
            beam_size=5,
        )
        segments = []
        full_text_parts = []
        for seg in segments_iter:
            segments.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip()})
            full_text_parts.append(seg.text.strip())

        elapsed = round(time.monotonic() - t0, 2)
        return {
            "ok": True,
            "audio_path": audio_path,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "duration": round(info.duration, 2),
            "transcription_seconds": elapsed,
            "text": " ".join(full_text_parts),
            "segments": segments,
        }
    except Exception as exc:
        return {"ok": False, "audio_path": audio_path, "error": str(exc)}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Transcribe an audio file locally with faster-whisper.")
    parser.add_argument("audio_path", help="Path to audio file (.ogg .oga .mp3 .m4a .wav .webm)")
    parser.add_argument("--language", default=None, help="Force language code (e.g. en). Auto-detect if omitted.")
    args = parser.parse_args()

    result = transcribe_file(args.audio_path, language=args.language)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
