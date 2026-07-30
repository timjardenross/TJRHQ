"""
Issue 18: LLM synthesis layer on top of health-mission correlations.

Turns raw Pearson r-values (Issue 17 output) into grounded narrative insights.
The LLM is given ONLY the correlation numbers (structured input) and must
not invent causal stories the stats don't support.

Blocked on Issue 17 shipping (needs correlation data to synthesize).

Uses the same grounding discipline as brief_generator.py:
  - Input is only structured data (no free prose to poison)
  - Output is structured JSON (never free-form narrative)
  - Prompt explicitly forbids causal claims unsupported by r-values
  - Returns narrative + structured metadata for dashboard display

Public API:
    synthesize_correlation_insights(correlation_data: dict, llm_provider) -> dict
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional, Any

log = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "You are the Health Intelligence Analyst for USS Endeavour's operational resilience team. "
    "Your job is to turn statistical correlation data into grounded, actionable insights for the Captain. "
    "\n\n"
    "CRITICAL RULES:\n"
    "1. CORRELATION IS NOT CAUSATION. Do not claim causal relationships (e.g., 'pain causes mission updates'). "
    "   Use only: 'correlates with', 'associates with', 'precedes', 'follows'.\n"
    "2. Only use the data provided. Do not invent stories, mechanisms, or explanations beyond what the numbers show.\n"
    "3. Cite the r-value and sample size (n) for every claim.\n"
    "4. Flag insufficient data: r-values near 0, small n, or status='insufficient_data'.\n"
    "5. Return ONLY JSON with the structure provided below — no prose outside the JSON."
)

_PROMPT_TEMPLATE = (
    "{system_prompt}\n\n"
    "CORRELATION DATA:\n"
    "{correlation_json}\n\n"
    "Generate a JSON object with this structure. Keep every string field short "
    "(one sentence, under 25 words) — the whole response must fit in 2048 tokens, "
    "so a truncated, unparseable response is worse than a terse one:\n"
    "{{\n"
    '  "insights": [  // Array of 2-3 key insights, shortest strongest first\n'
    '    {{\n'
    '      "dimension": "string",  // e.g., "Pain & Mission Activity"\n'
    '      "finding": "string",    // ONE short sentence, e.g., "Captain updates 2.3 fewer missions on high-pain days (r=-0.45, n=67)"\n'
    '      "confidence": "high|medium|low",  // Based on r-value magnitude and n\n'
    '      "r_value": float,       // Correlation coefficient\n'
    '      "sample_size": int      // Number of paired observations\n'
    '    }}\n'
    "  ],\n"
    '  "operational_implications": [  // 1-2 short implications for mission planning\n'
    '    "string"  // ONE short sentence\n'
    "  ],\n"
    '  "data_quality": {{  // Metadata on data reliability\n'
    '    "status": "ok|insufficient_data",\n'
    '    "notes": "string"  // ONE short sentence\n'
    "  }}\n"
    "}}\n\n"
    "Return ONLY the JSON object above, complete and with the closing brace. "
    "No preamble, no markdown fence, no markdown formatting."
)


def _build_prompt(correlation_data: dict) -> str:
    """Build the grounded synthesis prompt."""
    return _PROMPT_TEMPLATE.format(
        system_prompt=_SYSTEM_PROMPT,
        correlation_json=json.dumps(correlation_data, indent=2),
    )


def synthesize_correlation_insights(
    correlation_data: dict, llm_provider: Optional[Any] = None
) -> dict:
    """
    Issue 18: Synthesize health-mission correlation numbers into narrative insights.

    Args:
        correlation_data: Output from Issue 17 (intelligence_health_correlations row)
        llm_provider: LLMProvider instance (lazy-loads if None)

    Returns:
        dict with structure:
        {
            "status": "ok" | "error",
            "provider": "mistral" | "gemini" | etc,
            "insights": [{dimension, finding, confidence, r_value, sample_size}, ...],
            "operational_implications": ["string", ...],
            "data_quality": {status, notes},
            "raw_response": "full LLM response for audit",
            "parse_error": "error message if JSON parse failed",
        }
    """
    # Lazy-load LLM provider if needed
    if llm_provider is None:
        try:
            from intelligence.brief.llm_provider import LLMProvider
            llm_provider = LLMProvider()
        except Exception as exc:
            log.error(f"Failed to load LLMProvider: {exc}")
            return {
                "status": "error",
                "provider": None,
                "error": f"LLMProvider unavailable: {exc}",
                "insights": [],
                "operational_implications": [],
                "data_quality": {"status": "error", "notes": str(exc)},
            }

    # Sanity check on input
    if correlation_data.get("status") == "insufficient_data":
        return {
            "status": "skipped",
            "provider": None,
            "insights": [],
            "operational_implications": [],
            "data_quality": correlation_data.get("data_quality", {}),
            "reason": "Insufficient health-mission data for synthesis",
        }

    # Build prompt & fire LLM
    prompt = _build_prompt(correlation_data)

    try:
        raw_response, provider = llm_provider.generate(prompt)
    except Exception as exc:
        log.error(f"LLM generation failed: {exc}")
        return {
            "status": "error",
            "provider": None,
            "error": str(exc),
            "insights": [],
            "operational_implications": [],
            "data_quality": {"status": "error"},
            "raw_response": None,
        }

    if not raw_response:
        log.error("LLM returned empty response")
        return {
            "status": "error",
            "provider": provider,
            "error": "Empty LLM response",
            "insights": [],
            "operational_implications": [],
            "data_quality": {"status": "error"},
            "raw_response": raw_response,
        }

    # Parse JSON output
    try:
        # Extract JSON from response (may be wrapped in markdown or text)
        match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in response")
        parsed = json.loads(match.group())
    except (json.JSONDecodeError, ValueError) as exc:
        log.error(f"Failed to parse LLM JSON output: {exc}")
        return {
            "status": "parse_error",
            "provider": provider,
            "error": f"JSON parse failed: {exc}",
            "insights": [],
            "operational_implications": [],
            "data_quality": {"status": "error"},
            "raw_response": raw_response,
            "parse_error": str(exc),
        }

    # Validate structure
    if not isinstance(parsed.get("insights"), list):
        log.warning("LLM output missing or invalid 'insights' field")
        parsed["insights"] = []
    if not isinstance(parsed.get("operational_implications"), list):
        log.warning("LLM output missing or invalid 'operational_implications' field")
        parsed["operational_implications"] = []

    return {
        "status": "ok",
        "provider": provider,
        "insights": parsed.get("insights", []),
        "operational_implications": parsed.get("operational_implications", []),
        "data_quality": parsed.get("data_quality", {"status": "ok"}),
        "raw_response": raw_response,
    }


def display_correlation_brief(synthesis_result: dict) -> str:
    """
    Format synthesis result for display on dashboard or brief.
    Returns human-readable markdown.
    """
    if synthesis_result.get("status") != "ok":
        return f"**Health-Mission Correlations**: Unable to generate insights ({synthesis_result.get('error')})"

    lines = ["## Health-Mission Insights"]

    if synthesis_result.get("insights"):
        lines.append("\n### Key Findings")
        for insight in synthesis_result["insights"]:
            conf = insight.get("confidence", "unknown").upper()
            r = insight.get("r_value", "?")
            n = insight.get("sample_size", "?")
            lines.append(f"- **{insight.get('dimension')}** [{conf}]: {insight.get('finding')}")

    if synthesis_result.get("operational_implications"):
        lines.append("\n### Operational Implications")
        for implication in synthesis_result["operational_implications"]:
            lines.append(f"- {implication}")

    quality = synthesis_result.get("data_quality", {})
    if quality.get("notes"):
        lines.append(f"\n*Note: {quality.get('notes')}*")

    return "\n".join(lines)
