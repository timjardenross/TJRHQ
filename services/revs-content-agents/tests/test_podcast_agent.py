from pathlib import Path
from unittest.mock import patch

from src.agents.podcast_agent import PodcastAgent


def _fake_generate_speech(text, voice_name="Kore", out_path=None):
    if out_path:
        Path(out_path).write_bytes(b"RIFF____WAVEfmt fake-audio-bytes")
    return b"fake-audio-bytes"


def _fake_generate_text(prompt):
    # Echo back whatever content the prompt wrapped, so we can still assert on it
    # without hitting the real narration-rewrite model in a unit test.
    return prompt.split("Content to adapt:\n", 1)[1]


def test_generate_podcast_writes_transcript_and_audio(brief, tmp_path):
    with patch("src.agents.podcast_agent.generate_speech", side_effect=_fake_generate_speech) as mock_speech, \
         patch("src.agents.podcast_agent.generate_text", side_effect=_fake_generate_text) as mock_text:
        result = PodcastAgent().generate(brief, tmp_path)

    assert mock_text.call_count == 1
    assert mock_speech.call_count == 1
    transcript_path, audio_path = (Path(f) for f in result["files"])
    assert transcript_path.exists() and audio_path.exists()

    transcript = transcript_path.read_text()
    assert brief.headline in transcript
    assert "**" not in transcript  # markdown bold markers stripped before narration rewrite
