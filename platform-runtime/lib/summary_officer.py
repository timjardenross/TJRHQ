#!/usr/bin/env python3
"""Compatibility wrapper for the summary officer workflow.

This keeps the live bot wiring simple while reusing the richer research
briefing structures already present in the repo.
"""

from __future__ import annotations

import logging
from typing import Any

from briefing_officer import generate_captains_brief

log = logging.getLogger(__name__)


def call_summary_officer(research_package: dict[str, Any]) -> dict[str, Any]:
    """Return a structured summary package.

    This is intentionally non-blocking and conservative. It uses the existing
    CaptainBriefGenerator to produce a concise executive summary that can be
    fed into later challenge/briefing stages.
    """
    try:
        brief = generate_captains_brief(research_package)
        if not brief:
            raise RuntimeError("brief generation returned no content")
        return {
            "status": "success",
            "summary": brief,
            "key_findings": [],
            "implications": "",
            "research_package": research_package,
        }
    except Exception as exc:
        log.warning("[summary-officer] summary generation failed: %s", exc)
        return {
            "status": "error",
            "summary": "",
            "key_findings": [],
            "implications": "",
            "research_package": research_package,
            "error": type(exc).__name__,
        }
