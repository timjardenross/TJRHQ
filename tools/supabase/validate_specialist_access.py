#!/usr/bin/env python3
"""Run prototype specialist access checks against Supabase."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RETRIEVE = SCRIPT_DIR / "retrieve_knowledge.py"


CASES = [
    ("Chief Engineer can read architecture", ["Command Layer", "--document-type", "Architecture", "--specialist-role", "Chief Engineer"], 0),
    ("UX Designer is blocked from ADR", ["Markdown First", "--document-type", "ADR", "--specialist-role", "UX Designer"], 2),
    ("Knowledge Manager can read crew", ["Chief of Staff", "--document-type", "Crew", "--specialist-role", "Knowledge Manager"], 0),
]


def main() -> int:
    failures = 0
    for label, args, expected in CASES:
        print(f"\n== {label} ==")
        result = subprocess.run([sys.executable, str(RETRIEVE), *args], check=False)
        if result.returncode != expected:
            print(f"Expected exit {expected}, got {result.returncode}")
            failures += 1
    if failures:
        print(f"\n{failures} specialist access validation case(s) failed.")
        return 1
    print("\nSpecialist access validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
