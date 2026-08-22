import wave
from pathlib import Path

import pytest
from PIL import Image

from src.agents.video_agent import VideoAgent


def _write_silent_wav(path: Path, duration_s: float = 2.0, rate: int = 24000) -> None:
    n_frames = int(duration_s * rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * n_frames)


def test_generate_video_muxes_images_and_narration(brief, tmp_path):
    (tmp_path / "posters").mkdir()
    (tmp_path / "social").mkdir()
    (tmp_path / "podcasts").mkdir()

    Image.new("RGB", (300, 400), "blue").save(tmp_path / "posters" / f"{brief.concept_id}_hero.jpg")
    Image.new("RGB", (300, 300), "green").save(tmp_path / "social" / f"{brief.concept_id}_instagram.png")
    _write_silent_wav(tmp_path / "podcasts" / f"{brief.concept_id}.wav", duration_s=2.0)

    result = VideoAgent().generate(brief, tmp_path)
    video_path = Path(result["files"][0])
    assert video_path.exists()
    assert video_path.stat().st_size > 0


def test_generate_video_raises_clear_error_when_poster_missing(brief, tmp_path):
    with pytest.raises(FileNotFoundError, match="PosterAgent"):
        VideoAgent().generate(brief, tmp_path)
