import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

from src.agents.article_agent import ArticleAgent
from src.agents.podcast_agent import PodcastAgent
from src.agents.poster_agent import PosterAgent
from src.agents.presentation_agent import PresentationAgent
from src.agents.social_agent import SocialAgent
from src.agents.video_agent import VideoAgent
from src.agents.worksheet_agent import WorksheetAgent
from src.parsing.brief_parser import parse_brief
from src.utils.config import load_config
from src.utils.logging import get_logger

load_dotenv()
log = get_logger("main")

# VideoAgent must run after PosterAgent/SocialAgent/PodcastAgent - it reuses
# their output files instead of regenerating images/narration.
_AGENT_ORDER = ["article", "poster", "social", "worksheet", "presentation", "podcast", "video"]
_AGENT_CLASSES = {
    "article": ArticleAgent, "poster": PosterAgent, "social": SocialAgent,
    "worksheet": WorksheetAgent, "presentation": PresentationAgent,
    "podcast": PodcastAgent, "video": VideoAgent,
}


def _next_version(concept_dir: Path) -> int:
    existing = [int(p.name[1:]) for p in concept_dir.glob("v*") if p.name[1:].isdigit()]
    return max(existing, default=0) + 1


def _update_latest_pointer(concept_dir: Path, version_dir: Path) -> None:
    latest = concept_dir / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(version_dir.name)


def generate(brief_path: str, output_dir: Path, formats: list[str] | None = None) -> dict:
    """Run one brief through the selected agents. Each agent's failure is isolated -
    it's recorded in the manifest but doesn't stop the remaining agents from running."""
    brief = parse_brief(brief_path)
    selected = [name for name in _AGENT_ORDER if not formats or name in formats]

    concept_dir = output_dir / brief.concept_id
    concept_dir.mkdir(parents=True, exist_ok=True)
    version = _next_version(concept_dir)
    version_dir = concept_dir / f"v{version}"

    run_started = time.time()
    manifest = {
        "concept_id": brief.concept_id,
        "status": brief.status,
        "target_audiences": brief.target_audiences,
        "source": brief.source_path,
        "version": version,
        "started_at": run_started,
        "outputs": [],
    }

    for name in selected:
        agent = _AGENT_CLASSES[name]()
        agent_started = time.time()
        try:
            result = agent.generate(brief, version_dir)
            result["status"] = "success"
            log.info(f"{brief.concept_id}: {name} done in {round(time.time() - agent_started, 2)}s")
        except Exception as exc:
            result = {"format": agent.format_name, "status": "failed", "error": str(exc)}
            log.error(f"{brief.concept_id}: {name} failed: {exc}")
        result["duration_seconds"] = round(time.time() - agent_started, 2)
        manifest["outputs"].append(result)

    manifest["finished_at"] = time.time()
    manifest["duration_seconds"] = round(manifest["finished_at"] - run_started, 2)

    version_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / "asset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _update_latest_pointer(concept_dir, version_dir)

    with open(concept_dir / "runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "version": version,
            "started_at": run_started,
            "duration_seconds": manifest["duration_seconds"],
            "succeeded": [o["format"] for o in manifest["outputs"] if o["status"] == "success"],
            "failed": [o["format"] for o in manifest["outputs"] if o["status"] == "failed"],
        }) + "\n")

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="REVS Content Creation Agents")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--brief", help="Path to a single design brief Markdown file")
    source.add_argument("--input-dir", help="Directory of design brief Markdown files to batch-process")
    parser.add_argument("--output-dir", default="outputs", help="Directory to write generated assets into")
    parser.add_argument("--formats", help=f"Comma-separated subset of {{{','.join(_AGENT_ORDER)}}} (default: all)")
    parser.add_argument("--parallel", type=int, default=None,
                         help="Concurrent briefs in batch mode (default: config.yml processing.max_workers)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    formats = args.formats.split(",") if args.formats else None
    if formats:
        unknown = set(formats) - set(_AGENT_ORDER)
        if unknown:
            parser.error(f"unknown format(s): {', '.join(sorted(unknown))} (choices: {', '.join(_AGENT_ORDER)})")

    if args.brief:
        brief_paths = [args.brief]
    else:
        brief_paths = sorted(str(p) for p in Path(args.input_dir).glob("*.md"))
        if not brief_paths:
            parser.error(f"no .md briefs found in {args.input_dir}")

    max_workers = args.parallel or load_config().get("processing", {}).get("max_workers", 1)

    results = []
    if len(brief_paths) == 1:
        results.append(generate(brief_paths[0], output_dir, formats))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(generate, path, output_dir, formats): path for path in brief_paths}
            for future in as_completed(futures):
                path = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    log.error(f"{path}: brief-level failure: {exc}")

    for manifest in results:
        ok = sum(1 for o in manifest["outputs"] if o["status"] == "success")
        total = len(manifest["outputs"])
        version_dir = output_dir / manifest["concept_id"] / f"v{manifest['version']}"
        print(f"{manifest['concept_id']} v{manifest['version']}: {ok}/{total} format(s) -> {version_dir}")


if __name__ == "__main__":
    main()
