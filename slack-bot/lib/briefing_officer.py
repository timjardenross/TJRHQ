#!/usr/bin/env python3
"""Captain's Briefing Officer Module

Converts ResearchPackage output into a short Captain's Brief for Slack.

Uses Mistral Chat Completions API (mistral-large-latest model).
Previous Agents API endpoint returned 404 for all agent IDs.
Switched to direct model API (same pattern as decomposition - verified working).

Public API:
    generate_captains_brief(research_package: dict) -> str

Behavior:
- Takes ResearchPackage as input
- Calls Mistral direct model API
- Returns short brief (max ~150 words)
- Fails gracefully if Mistral unavailable
"""

import os
import logging
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)



def generate_captains_brief(research_package: Dict[str, Any]) -> Optional[str]:
    """Generate a Captain's Brief from a ResearchPackage using direct Mistral API.

    Args:
        research_package: ResearchPackage dict with findings, recommendation, etc.

    Returns:
        Brief text (max ~150 words), or None if generation fails.

    Non-blocking: Returns None if Mistral unavailable, does not crash mission.
    """
    try:
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            log.warning("[briefing-officer] MISTRAL_API_KEY not set; briefing unavailable")
            return None

        # Add downstream outputs if available
        summary_output = research_package.get("summary_officer_output")
        challenge_output = research_package.get("risk_challenge_output")
        has_summary = summary_output is not None
        has_challenge = challenge_output is not None

        log.info(f"[briefing-officer] Calling Captain's Briefing Officer (summary={has_summary} challenge={has_challenge})...")

        briefing_prompt = _build_briefing_prompt(research_package)

        from lib.mistral_agent_client import call_agent, AGENT_BRIEFING
        brief = call_agent(
            stage="brief",
            agent_name=AGENT_BRIEFING,
            prompt=briefing_prompt,
            mission_id=research_package.get("mission_id"),
        )

        if brief:
            log.info(f"[briefing-officer] SUCCESS - Brief generated ({len(brief.split())} words)")
            return brief
        else:
            log.warning("[briefing-officer] Empty response from Mistral agent")
            return None

    except urllib.error.HTTPError as e:
        log.warning(f"[briefing-officer] HTTP {e.code}: {e.reason}")
        return None

    except urllib.error.URLError as e:
        log.warning(f"[briefing-officer] Connection failed: {e}")
        return None

    except Exception as e:
        log.error(f"[briefing-officer] FAILED - {type(e).__name__}: {e}", exc_info=True)
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
        recommendation_section = f"Recommendation:\n{recommendation}" if recommendation else ""
        output_format = "RECOMMENDATION\n[What Captain should do next]" if research_type == "decision" and recommendation else "KEY INSIGHTS\n[Key findings for decision-making]"

        brief_input = f"""Research Package Summary
=======================

Topic: {topic}
Type: {research_type}
Confidence: {confidence}
Timestamp: {timestamp}

Key Findings:
{key_findings}

{recommendation_section}

Task: Generate a Captain's Brief in ~150 words.

Format:
🚀 CAPTAIN'S BRIEF

STATUS
[Current situation in 1-2 sentences]

WHY IT MATTERS
[Business/operational impact in 1-2 sentences]

ATTENTION REQUIRED
[Any critical issues, risks, or blockers]

{output_format}

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
