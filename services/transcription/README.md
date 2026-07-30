# USS-TJR Local Transcription Service

Local voice transcription via faster-whisper. CPU-only, no external API, no HF_TOKEN.
Part of the XO Unified Capture Pipeline.

## Install

```bash
cd /opt/starship-endeavour/services/transcription
python3 -m venv .venv
source .venv/bin/activate
pip install faster-whisper
```

faster-whisper 1.2.1 is already installed in `.venv`.

## CLI usage

```bash
source .venv/bin/activate
python transcribe.py /path/to/audio.ogg
python transcribe.py /path/to/audio.ogg --language en   # skip auto-detect
```

## Successful output

```json
{
  "ok": true,
  "audio_path": "/path/to/audio.ogg",
  "language": "en",
  "language_probability": 0.998,
  "duration": 12.4,
  "transcription_seconds": 3.2,
  "text": "Full transcribed text joined from all segments.",
  "segments": [
    { "start": 0.0, "end": 2.3, "text": "First sentence." },
    { "start": 2.3, "end": 5.1, "text": "Second sentence." }
  ]
}
```

## Failure output

```json
{
  "ok": false,
  "audio_path": "/path/to/audio.ogg",
  "error": "File not found: /path/to/audio.ogg"
}
```

## Supported formats

`.ogg` `.oga` `.mp3` `.m4a` `.wav` `.webm`

Telegram voice messages arrive as `.oga` (Opus in Ogg container) — supported natively.

## Run tests

```bash
source .venv/bin/activate
python test_transcribe.py              # validation tests only (no audio file needed)
python test_transcribe.py test.ogg     # validation + live transcription
```

## Telegram integration (XO Capture Pipeline)

In `telegram-bots/xo/app.py`, when a voice message arrives:

```python
import subprocess, json, tempfile, os

async def handle_voice(update, context):
    file = await update.message.voice.get_file()
    with tempfile.NamedTemporaryFile(suffix=".oga", delete=False) as f:
        tmp = f.name
    await file.download_to_drive(tmp)

    result = subprocess.run(
        ["/opt/starship-endeavour/services/transcription/.venv/bin/python",
         "/opt/starship-endeavour/services/transcription/transcribe.py",
         tmp, "--language", "en"],
        capture_output=True, text=True, timeout=60
    )
    os.unlink(tmp)

    data = json.loads(result.stdout)
    if data["ok"]:
        text = data["text"]
        # → pass text into unified capture pipeline
    else:
        # → reply with data["error"]
```

The subprocess approach keeps the transcription venv isolated from the bot venv.
