from pathlib import Path

from src.agents._prompts import hero_art_prompt
from src.integrations.gemini_client import generate_image
from src.parsing.schemas import DesignBrief
from src.renderers.image_renderer import add_headline_banner
from src.utils.config import load_config


class PosterAgent:
    format_name = "posters"

    def generate(self, brief: DesignBrief, output_dir: Path) -> dict:
        out_dir = output_dir / self.format_name
        out_dir.mkdir(parents=True, exist_ok=True)
        branding = load_config().get("branding", {})

        prompt = hero_art_prompt(brief, "a wellness poster")
        hero = generate_image(prompt, aspect_ratio="3:4", resolution="2K")
        hero_path = out_dir / f"{brief.concept_id}_hero.jpg"
        hero.save(hero_path)

        poster = add_headline_banner(hero, brief.headline, branding.get("primary_color", "#0052CC"))
        poster_path = out_dir / f"{brief.concept_id}.png"
        poster.save(poster_path)

        return {"format": self.format_name, "files": [str(hero_path), str(poster_path)]}
