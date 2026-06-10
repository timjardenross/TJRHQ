#!/usr/bin/env python3
"""Local routing checks for MSN-0006 specialist-aware retrieval."""

from __future__ import annotations

from specialist_router import route_question


CASES = [
    ("Who manages mission prioritisation?", "Chief of Staff"),
    ("Where is Supabase used?", "Chief Engineer"),
    ("How should this knowledge be documented?", "Knowledge Manager"),
    ("How should the dashboard workflow work?", "UX Design Officer"),
    ("Who should review this implementation?", "Code Review Specialist"),
]


def main() -> int:
    failures = 0
    for question, expected in CASES:
        route = route_question(question)
        status = "PASS" if route.specialist.name == expected else "FAIL"
        print(f"{status}: {question} -> {route.specialist.name} (expected {expected}, confidence {route.confidence})")
        if status == "FAIL":
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
