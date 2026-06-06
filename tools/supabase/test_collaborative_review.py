#!/usr/bin/env python3
"""Local validation for MSN-0008B collaborative review mode."""

from __future__ import annotations

import json
import os
from pathlib import Path

from collaboration_logger import LOG_DIR
from collaborative_specialist_runtime import run
from review_specialist_selector import select_review_specialist


def assert_reviewer(question: str, primary: str, expected: str) -> None:
    selection = select_review_specialist(question, primary)
    if selection.reviewer != expected:
        raise AssertionError(f"{question!r}: expected {expected}, got {selection.reviewer}")


def main() -> int:
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    assert_reviewer("Should we build Voice Core next?", "Chief Engineer", "Chief of Staff")
    assert_reviewer("How should we plan mission priority?", "Chief of Staff", "Chief Engineer")
    assert_reviewer("Where should Notion sync sit in the architecture?", "Knowledge Manager", "Chief of Staff")
    assert_reviewer("How should the dashboard workflow work?", "UX Design Officer", "Chief Engineer")
    assert_reviewer("Who should review this implementation?", "Code Review Specialist", "Chief Engineer")

    before = set(LOG_DIR.glob("*.json")) if LOG_DIR.exists() else set()
    run("Should we build Voice Core next?", "USS-TJR-MSN-0008B", True, 2, 0.0, True, None, False)
    created = [
        path for path in sorted(set(LOG_DIR.glob("*.json")) - before)
        if "0008B" in path.read_text(encoding="utf-8")
    ]
    if not created:
        raise AssertionError("challenge mode did not create a log")
    payload = json.loads(Path(created[-1]).read_text(encoding="utf-8"))
    assert payload["challenge_mode"] is True
    assert payload["reviewer_selected"] == "Chief of Staff"
    assert payload["assumptions_challenged"]
    assert payload["risks_identified"]
    assert payload["final_recommendation_summary"]
    print("collaborative review tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
