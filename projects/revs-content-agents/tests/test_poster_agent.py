from pathlib import Path
from unittest.mock import patch

from PIL import Image

from src.agents.poster_agent import PosterAgent


def test_generate_poster_uses_gemini_hero_art_and_overlays_headline(brief, tmp_path):
    fake_hero = Image.new("RGB", (768, 1024), "white")

    with patch("src.agents.poster_agent.generate_image", return_value=fake_hero) as mock_gen:
        result = PosterAgent().generate(brief, tmp_path)

    assert mock_gen.call_count == 1
    hero_path, poster_path = (Path(f) for f in result["files"])
    assert hero_path.exists() and poster_path.exists()
    assert Image.open(poster_path).size == (768, 1024)
