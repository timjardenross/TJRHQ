from pathlib import Path

from src.integrations.gemini_client import generate_image
from src.parsing.schemas import DesignBrief
from src.renderers.image_renderer import add_headline_banner
from src.utils.config import load_config


class PosterAgent:
    format_name = "posters"

    def _hero_prompt(self, brief: DesignBrief) -> str:
        theme = (brief.sections[0].body if brief.sections else brief.intro)[:300]
        return (
            f"A calming, editorial illustration for a wellness poster about: '{brief.headline}'. "
            f"Thematic context: {theme} "
            "Style: soft abstract interlocking shapes suggesting connected systems, muted "
            "therapeutic color palette, no readable text, no visible faces, hopeful and grounded "
            "mood, clear open negative space across the top third for a headline overlay."
        )

    def generate(self, brief: DesignBrief, output_dir: Path) -> dict:
        out_dir = output_dir / self.format_name
        out_dir.mkdir(parents=True, exist_ok=True)
        branding = load_config().get("branding", {})

        hero = generate_image(self._hero_prompt(brief), aspect_ratio="3:4", resolution="2K")
        hero_path = out_dir / f"{brief.concept_id}_hero.jpg"
        hero.save(hero_path)

        poster = add_headline_banner(hero, brief.headline, branding.get("primary_color", "#0052CC"))
        poster_path = out_dir / f"{brief.concept_id}.png"
        poster.save(poster_path)

        return {"format": self.format_name, "files": [str(hero_path), str(poster_path)]}
