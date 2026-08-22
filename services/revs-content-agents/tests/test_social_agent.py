from pathlib import Path
from unittest.mock import patch

from PIL import Image

from src.agents.social_agent import SocialAgent, _PLATFORMS


def test_generate_social_makes_one_image_per_platform(brief, tmp_path):
    fake_image = Image.new("RGB", (512, 512), "white")

    with patch("src.agents.social_agent.generate_image", return_value=fake_image) as mock_gen:
        result = SocialAgent().generate(brief, tmp_path)

    assert mock_gen.call_count == len(_PLATFORMS)
    files = [Path(f) for f in result["files"]]
    assert len(files) == len(_PLATFORMS)
    assert all(f.exists() for f in files)
