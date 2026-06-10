#!/usr/bin/env python3
"""Captain's Briefing Officer Module

Converts ResearchPackage output into a short Captain's Brief for Slack.

Agent: Mistral Captain's Briefing Officer
- agent_id: ag_019eb077b0d47239bebcbabd719a2e7b
- agent_version: 0

Public API:
    generate_captains_brief(research_package: dict) -> str

Behavior:
- Takes ResearchPackage as input
- Calls Mistral briefing agent
- Returns short brief (max ~150 words)
- Fails gracefully if Mistral unavailable
"""

import os
import json
import logging
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)

# Mistral agent configuration
BRIEFING_AGENT_ID = "ag_019eb077b0d47239bebcbabd719a2e7b"
BRIEFING_AGENT_VERSION = 0


def generate_captains_brief(research_package: Dict[str, Any]) -> Optional[str]:
    """Generate a Captain's Brief from a ResearchPackage.

    Args:
        research_package: ResearchPackage dict with findings, recommendation, etc.

    Returns:
        Brief text (max ~150 words), or None if generation fails.

    Non-blocking: Returns None if Mistral unavailable, does not crash mission.
    """
    try:
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            log.warning("[briefing] MISTRAL_API_KEY not set; briefing unavailable")
            return None

        from mistralai.client import Mistral

        client = Mistral(api_key=api_key)

        # Build briefing prompt from research package
        brief_prompt = _build_briefing_prompt(research_package)

        log.info(f"[briefing] Calling Mistral agent {BRIEFING_AGENT_ID}...")

        response = client.beta.conversations.start(
            agent_id=BRIEFING_AGENT_ID,
            agent_version=BRIEFING_AGENT_VERSION,
            inputs=[{"role": "user", "content": brief_prompt}],
        )

        if response and hasattr(response, 'messages') and response.messages:
            brief_text = response.messages[-1].content
            brief_length = len(brief_text.split())
            log.info(f"[briefing] SUCCESS - Brief generated ({brief_length} words)")
            return brief_text
        else:
            log.error("[briefing] FAILED - Empty response from Mistral")
            return None

    except Exception as e:
        log.error(f"[briefing] FAILED - {type(e).__name__}: {e}", exc_info=True)
        return None


def _build_briefing_prompt(research_package: Dict[str, Any]) -> str:
    """Build structured prompt for Mistral briefing agent.

    Extracts key information from ResearchPackage for the agent.
    """
    try:
        topic = research_package.get("topic", "Unknown topic")
        research_type = research_package.get("request_type", "unclear")
        key_findings = research_package.get("key_findings", "")
        recommendation = research_package.get("recommendation", "")
        confidence = research_package.get("confidence_score", 0)
        timestamp = research_package.get("timestamp", "")

        # Build structured input for briefing agent
        brief_input = f"""
Research Package Summary
=======================

Topic: {topic}
Type: {research_type}
Confidence: {confidence}
Timestamp: {timestamp}

Key Findings:
{key_findings}

{"Recommendation:\n" + recommendation if recommendation else ""}

Task: Generate a Captain's Brief in ~150 words.

Format:
🚀 CAPTAIN'S BRIEF

STATUS
[Current situation in 1-2 sentences]

WHY IT MATTERS
[Business/operational impact in 1-2 sentences]

ATTENTION REQUIRED
[Any critical issues, risks, or blockers]

{"RECOMMENDATION\n[What Captain should do next]" if research_type == "decision" and recommendation else "KEY INSIGHTS\n[Key findings for decision-making]"}

CONFIDENCE
[High/Medium/Low based on research confidence]

Keep it brief. Captain needs direction, not details.
"""
        return brief_input

    except Exception as e:
        log.error(f"[briefing] Failed to build prompt: {e}")
        return "Generate a brief summary of the attached research."


def format_brief_for_slack(brief_text: Optional[str], mission_id: str) -> str:
    """Format brief for Slack display.

    Args:
        brief_text: Brief output from Mistral, or None if unavailable
        mission_id: Research mission ID for log reference

    Returns:
        Slack-formatted message
    """
    if brief_text:
        return f"""{brief_text}

---
Mission ID: `{mission_id}`
Full research available in research log."""
    else:
        return f"""Captain's Brief unavailable; showing standard research output.

Mission ID: `{mission_id}`
Full research available in research log."""
