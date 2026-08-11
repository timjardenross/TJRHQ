import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from src.agents.article_agent import ArticleAgent
from src.agents.poster_agent import PosterAgent
from src.agents.podcast_agent import PodcastAgent
from src.agents.presentation_agent import PresentationAgent
from src.agents.social_agent import SocialAgent
from src.agents.video_agent import VideoAgent
from src.agents.worksheet_agent import WorksheetAgent
from src.parsing.brief_parser import parse_brief

load_dotenv()

# VideoAgent must run after PosterAgent/SocialAgent/PodcastAgent - it reuses
# their output files instead of regenerating images/narration.
AGENTS = [
    ArticleAgent(), PosterAgent(), SocialAgent(), WorksheetAgent(),
    PresentationAgent(), PodcastAgent(), VideoAgent(),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="REVS Content Creation Agents")
    parser.add_argument("--brief", required=True, help="Path to a design brief Markdown file")
    parser.add_argument("--output-dir", default="outputs", help="Directory to write generated assets into")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    brief = parse_brief(args.brief)

    manifest = {"concept_id": brief.concept_id, "source": brief.source_path, "outputs": []}
    for agent in AGENTS:
        manifest["outputs"].append(agent.generate(brief, output_dir))

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "asset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Generated {len(manifest['outputs'])} format(s) for {brief.concept_id} -> {manifest_path}")


if __name__ == "__main__":
    main()
