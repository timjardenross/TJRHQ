from pathlib import Path
from unittest.mock import patch

from src.agents.podcast_agent import PodcastAgent


def _fake_generate_speech(text, voice_name="Kore", out_path=None):
    if out_path:
        Path(out_path).write_bytes(b"RIFF____WAVEfmt fake-audio-bytes")
    return b"fake-audio-bytes"


def test_generate_podcast_writes_transcript_and_audio(brief, tmp_path):
    with patch("src.agents.podcast_agent.generate_speech", side_effect=_fake_generate_speech) as mock_gen:
        result = PodcastAgent().generate(brief, tmp_path)

    assert mock_gen.call_count == 1
    transcript_path, audio_path = (Path(f) for f in result["files"])
    assert transcript_path.exists() and audio_path.exists()

    transcript = transcript_path.read_text()
    assert brief.headline in transcript
    assert "**" not in transcript  # markdown bold markers stripped for narration
