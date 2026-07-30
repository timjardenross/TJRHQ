"""
classify_missions.py — Batch Google AI classifier for historical mission files.

Reads all mission files (Active + Completed), sends each to Gemini with the
full initiative taxonomy, and outputs a classification-review.md for Captain review.

Prerequisite: Complete knowledge/hierarchy/Objectives.md and Initiatives.md first.
The classifier quality depends entirely on the taxonomy quality.

Usage:
  python3 tools/hierarchy/classify_missions.py
  python3 tools/hierarchy/classify_missions.py --completed-only
  python3 tools/hierarchy/classify_missions.py --active-only
  python3 tools/hierarchy/classify_missions.py --dry-run   (no API calls, test parse)

Output:
  knowledge/hierarchy/classification-review.md

Environment:
  GOOGLE_API_KEY or GEMINI_API_KEY  — Google AI API key
  GOOGLE_AI_MODEL                   — model override (default: gemini-1.5-flash)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_OBJECTIVES_PATH = _REPO_ROOT / "knowledge" / "hierarchy" / "Objectives.md"
_INITIATIVES_PATH = _REPO_ROOT / "knowledge" / "hierarchy" / "Initiatives.md"
_REVIEW_OUTPUT = _REPO_ROOT / "knowledge" / "hierarchy" / "classification-review.md"

_DEFAULT_MODEL = "gemini-1.5-flash"
_BATCH_PAUSE_S = 0.5  # pause between API calls (rate limit courtesy)

_SYSTEM_PROMPT = """\
You are a knowledge classification assistant for Starship Endeavour, a personal AI operating system.

Your task: classify a mission document into one of the provided Initiatives.

Rules:
- Read the mission's title, objective, and content carefully.
- Choose the SINGLE best matching initiative.
- If the mission clearly does not fit any initiative, output "NONE" for initiative_id.
- Be concise in your reasoning — one sentence maximum.
- Output ONLY valid JSON, no other text.

Output format:
{
  "initiative_id": "INI-001",
  "confidence": 0.85,
  "reasoning": "One-sentence explanation."
}
"""


def _load_taxonomy() -> str:
    """Load Objectives.md + Initiatives.md as context for the classifier."""
    sections = []
    for path, label in [(_OBJECTIVES_PATH, "OBJECTIVES"), (_INITIATIVES_PATH, "INITIATIVES")]:
        if path.exists():
            sections.append(f"=== {label} ===\n{path.read_text(encoding='utf-8')[:3000]}")
        else:
            sections.append(f"=== {label} ===\n[Not yet authored — run Part 2 first]")
    return "\n\n".join(sections)


def _get_api_key() -> Optional[str]:
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        # Try .env file
        for env_path in ["platform-runtime/.env", ".env"]:
            p = _REPO_ROOT / env_path
            if p.exists():
                for line in p.read_text().splitlines():
                    if "=" in line and not line.strip().startswith("#"):
                        k, _, v = line.partition("=")
                        k = k.strip()
                        if k in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
                            key = v.strip().strip('"').strip("'")
                            if key:
                                break
    return key or None


def _classify_mission(
    mission_text: str,
    taxonomy: str,
    model: str,
    dry_run: bool = False,
) -> dict:
    """Call Gemini to classify a mission. Returns {initiative_id, confidence, reasoning}."""
    if dry_run:
        return {"initiative_id": "DRY-RUN", "confidence": 0.0, "reasoning": "dry run — no API call"}

    try:
        import google.generativeai as genai

        api_key = _get_api_key()
        if not api_key:
            return {"initiative_id": "ERROR", "confidence": 0.0, "reasoning": "GOOGLE_API_KEY not set"}

        genai.configure(api_key=api_key)
        gemini = genai.GenerativeModel(
            model_name=model,
            system_instruction=_SYSTEM_PROMPT,
        )

        prompt = f"""TAXONOMY:\n{taxonomy}\n\nMISSION:\n{mission_text[:2000]}"""
        response = gemini.generate_content(prompt)
        raw = response.text.strip()

        # Strip markdown code blocks if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)

        return json.loads(raw)

    except json.JSONDecodeError as exc:
        return {"initiative_id": "PARSE_ERROR", "confidence": 0.0, "reasoning": f"JSON parse failed: {exc}"}
    except Exception as exc:
        return {"initiative_id": "ERROR", "confidence": 0.0, "reasoning": f"{type(exc).__name__}: {str(exc)[:100]}"}


def _mission_summary(path: Path) -> tuple[str, str, str]:
    """Return (mission_id, title, text_for_classifier) from a mission file."""
    text = path.read_text(encoding="utf-8")

    # ID from filename
    msn_m = re.search(r"(?:USS-TJR-)?MSN-(\d{4}[A-Z]?)", path.stem, re.IGNORECASE)
    mission_id = f"MSN-{msn_m.group(1).zfill(4)}" if msn_m else path.stem

    # Title from H1
    h1 = re.search(r"^#\s+(?:USS-TJR-)?MSN-\S+\s*[—–-]\s*(.+)", text, re.MULTILINE)
    title = h1.group(1).strip() if h1 else path.stem

    # Use first 1500 chars for classification (title + objective + key content)
    classifier_text = f"Title: {title}\n\nContent:\n{text[:1500]}"
    return mission_id, title, classifier_text


def run_classification(
    *,
    include_active: bool = True,
    include_completed: bool = True,
    model: str = _DEFAULT_MODEL,
    dry_run: bool = False,
) -> Path:
    """
    Run classification on all mission files and write classification-review.md.
    Returns the path to the review file.
    """
    taxonomy = _load_taxonomy()
    mission_files: list[Path] = []

    if include_active:
        active_dir = _REPO_ROOT / "Missions" / "Active"
        if active_dir.exists():
            mission_files.extend(sorted(active_dir.glob("*.md")))

    if include_completed:
        completed_dir = _REPO_ROOT / "Missions" / "Completed"
        if completed_dir.exists():
            mission_files.extend(sorted(completed_dir.glob("*.md")))
            # Also check one level deeper (completed missions often in subdirs)
            for subdir in completed_dir.iterdir():
                if subdir.is_dir():
                    mission_files.extend(sorted(subdir.glob("*.md")))

    if not mission_files:
        log.warning("[classify] No mission files found")
        return _REVIEW_OUTPUT

    log.info("[classify] Processing %d mission files with model=%s dry_run=%s",
             len(mission_files), model, dry_run)

    rows: list[dict] = []
    for i, path in enumerate(mission_files):
        mission_id, title, classifier_text = _mission_summary(path)
        log.info("[classify] %d/%d %s", i + 1, len(mission_files), mission_id)

        result = _classify_mission(classifier_text, taxonomy, model, dry_run=dry_run)
        rows.append({
            "mission_id": mission_id,
            "title": title[:80],
            "suggested_initiative": result.get("initiative_id", "ERROR"),
            "confidence": result.get("confidence", 0.0),
            "reasoning": result.get("reasoning", ""),
            "decision": "✓" if result.get("confidence", 0) >= 0.80 else "",
            "source_file": str(path.relative_to(_REPO_ROOT)),
        })

        if not dry_run and i < len(mission_files) - 1:
            time.sleep(_BATCH_PAUSE_S)

    _write_review(rows)
    log.info("[classify] Review written to %s", _REVIEW_OUTPUT)
    return _REVIEW_OUTPUT


def _write_review(rows: list[dict]) -> None:
    """Write classification-review.md."""
    _REVIEW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    high_conf = [r for r in rows if float(r["confidence"]) >= 0.80]
    low_conf  = [r for r in rows if float(r["confidence"]) < 0.80]
    errors    = [r for r in rows if r["suggested_initiative"] in ("ERROR", "PARSE_ERROR")]

    lines = [
        "# Classification Review",
        "",
        "**Generated by:** `tools/hierarchy/classify_missions.py`  ",
        "**Instructions:**",
        "- `✓` in the Decision column = auto-accepted (confidence ≥ 0.80)",
        "- Replace `✓` with the correct INI-XXX if the suggestion is wrong",
        "- Set Decision to `SKIP` for missions that shouldn't be tagged",
        "- Run `python3 tools/hierarchy/approve_classifications.py` when done",
        "",
        f"**Summary:** {len(rows)} missions | {len(high_conf)} high-confidence "
        f"| {len(low_conf)} need review | {len(errors)} errors",
        "",
        "---",
        "",
        "## High Confidence (≥ 0.80) — Review Spot-Check",
        "",
        "| Mission | Title | Suggested | Confidence | Reasoning | Decision |",
        "|---|---|---|---|---|---|",
    ]

    for row in high_conf:
        conf = f"{float(row['confidence']):.2f}"
        lines.append(
            f"| `{row['mission_id']}` | {row['title']} "
            f"| `{row['suggested_initiative']}` | {conf} "
            f"| {row['reasoning']} | {row['decision']} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Needs Review (< 0.80)",
        "",
        "| Mission | Title | Suggested | Confidence | Reasoning | Decision |",
        "|---|---|---|---|---|---|",
    ])

    for row in low_conf:
        conf = f"{float(row['confidence']):.2f}"
        lines.append(
            f"| `{row['mission_id']}` | {row['title']} "
            f"| `{row['suggested_initiative']}` | {conf} "
            f"| {row['reasoning']} |  |"
        )

    if errors:
        lines.extend([
            "",
            "---",
            "",
            "## Errors — Manual Classification Required",
            "",
            "| Mission | Title | Error | Decision |",
            "|---|---|---|---|",
        ])
        for row in errors:
            lines.append(
                f"| `{row['mission_id']}` | {row['title']} "
                f"| {row['reasoning']} |  |"
            )

    _REVIEW_OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Classify missions into initiatives using Gemini")
    parser.add_argument("--active-only",    action="store_true", help="Only classify active missions")
    parser.add_argument("--completed-only", action="store_true", help="Only classify completed missions")
    parser.add_argument("--dry-run",        action="store_true", help="Parse only, no API calls")
    parser.add_argument("--model",          default=_DEFAULT_MODEL, help="Gemini model to use")
    args = parser.parse_args()

    include_active    = not args.completed_only
    include_completed = not args.active_only

    output = run_classification(
        include_active=include_active,
        include_completed=include_completed,
        model=args.model,
        dry_run=args.dry_run,
    )
    print(f"Review written to: {output}")
