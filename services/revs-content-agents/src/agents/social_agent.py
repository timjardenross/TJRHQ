from pathlib import Path

from src.agents._prompts import hero_art_prompt
from src.integrations.gemini_client import generate_image
from src.parsing.schemas import DesignBrief
from src.renderers.image_renderer import add_headline_banner
from src.utils.config import load_config

_PLATFORMS = {
    "instagram": "1:1",
    "linkedin": "4:5",
    "twitter": "16:9",
}


class SocialAgent:
    format_name = "social"

    def generate(self, brief: DesignBrief, output_dir: Path) -> dict:
        out_dir = output_dir / self.format_name
        out_dir.mkdir(parents=True, exist_ok=True)
        branding = load_config().get("branding", {})
        prompt = hero_art_prompt(brief, "a social media graphic")

        files = []
        for platform, aspect_ratio in _PLATFORMS.items():
            image = generate_image(prompt, aspect_ratio=aspect_ratio, resolution="1K")
            image = add_headline_banner(image, brief.headline, branding.get("primary_color", "#0052CC"))
            path = out_dir / f"{brief.concept_id}_{platform}.png"
            image.save(path)
            files.append(str(path))

        return {"format": self.format_name, "files": files}
