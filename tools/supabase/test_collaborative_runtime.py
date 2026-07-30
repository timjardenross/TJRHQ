#!/usr/bin/env python3
"""Local validation for MSN-0008A collaborative specialist runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path

from collaboration_logger import LOG_DIR
from collaboration_router import select_specialists
from collaborative_specialist_runtime import run


def assert_selected(question: str, expected: set[str]) -> None:
    selected = {route.specialist for route in select_specialists(question)}
    missing = expected - selected
    if missing:
        raise AssertionError(f"{question!r} missing specialists {missing}; got {selected}")
    if not 1 <= len(selected) <= 4:
        raise AssertionError(f"{question!r} selected invalid count {len(selected)}")


def main() -> int:
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    assert_selected("How should we build Voice Core?", {"Chief Engineer", "Chief of Staff"})
    assert_selected("How should we plan the next mission roadmap?", {"Chief of Staff"})
    assert_selected("How should this knowledge be documented?", {"Knowledge Manager"})
    assert_selected("How should we improve the Notion Command Centre?", {"Knowledge Manager", "UX Design Officer"})
    # MSN-0312: "Design Officer" is the canonical retitle of "UX Design Officer"
    # (same specialist, same registry ID). Note: the underlying routing rules
    # registry (core/crew/registry/retrieval-routing-rules.txt, owned by a
    # parallel MSN-0312 agent) now has duplicate "workflow/dashboard/..."
    # entries for both "Design Officer" and "UX Design Officer", so a question
    # matching those terms directly selects *both* names as separate routes.
    # That is out of scope for these files (collaboration_router.py only
    # consumes load_routing_rules(), it does not own the registry data), so we
    # just assert the canonical alias is reachable via that path — this does
    # not assert exclusivity, matching assert_selected's existing subset check.
    assert_selected("How should we improve the dashboard workflow experience?", {"Design Officer"})
    assert_selected("Who should review this implementation?", {"Code Review Specialist"})

    before = set(LOG_DIR.glob("*.json")) if LOG_DIR.exists() else set()
    run("How should we build Voice Core?", "USS-TJR-MSN-0008A", True, 2, 0.0)
    after = set(LOG_DIR.glob("*.json"))
    created = sorted(after - before)
    if not created:
        raise AssertionError("collaboration log was not created")
    payload = json.loads(Path(created[-1]).read_text(encoding="utf-8"))
    required = {"question", "selected_specialists", "routing_reasons", "retrieval_mode", "source_paths", "synthesis_summary", "latency_ms"}
    missing = required - set(payload)
    if missing:
        raise AssertionError(f"log missing fields {missing}")
    print("collaborative runtime tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
