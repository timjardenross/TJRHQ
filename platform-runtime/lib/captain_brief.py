"""
Captain Brief Generator (MSN-0055C WP4)

Transforms research mission output into decision-oriented briefs for captain/executive review.

Features:
- Extracts executive summary from consolidated findings
- Structures key findings with bullet points
- Generates implications for decision-makers
- Includes confidence context and success metrics
- Formats for Slack delivery with metadata
"""

import re
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime

# Import logger
import logging
log = logging.getLogger(__name__)


@dataclass
class CaptainBrief:
    """Decision-oriented research briefing for captain."""

    executive_summary: str
    key_findings: list[str]
    implications: str
    recommendation: str
    confidence: float
    research_topic: str
    task_count: int
    successful_tasks: int
    timestamp: str
    mission_id: Optional[str] = None


class CaptainBriefGenerator:
    """Generate captain-facing briefs from research results."""

    def generate_brief(self, research_result) -> CaptainBrief:
        """
        Convert research output to captain brief.

        Args:
            research_result: ResearchMissionResult instance

        Returns:
            CaptainBrief with formatted summary and recommendations
        """

        # Extract executive summary (first 2-3 sentences from consolidated findings)
        summary_lines = self._extract_summary(research_result.consolidated_findings)
        executive_summary = "\n".join(summary_lines)

        # Extract key findings (bullet points from findings)
        key_findings = self._extract_key_findings(research_result.consolidated_findings)

        # Generate implications
        implications = self._generate_implications(
            research_result.consolidated_findings,
            research_result.tasks_completed,
            research_result.task_count,
        )

        # Use existing recommendation or fallback
        recommendation = (
            research_result.recommendation
            or "Further investigation required to form recommendation"
        )

        # Count successful tasks
        successful_tasks = len(
            [t for t in research_result.task_results if t.status == "complete"]
        )

        brief = CaptainBrief(
            executive_summary=executive_summary,
            key_findings=key_findings,
            implications=implications,
            recommendation=recommendation,
            confidence=research_result.confidence,
            research_topic=research_result.research_topic,
            task_count=research_result.task_count,
            successful_tasks=successful_tasks,
            timestamp=research_result.timestamp,
            mission_id=research_result.mission_id,
        )

        log.info(
            f"[captain-brief] Generated brief for {research_result.research_topic} "
            f"({successful_tasks}/{research_result.task_count} tasks, confidence: {research_result.confidence:.2f})"
        )
        return brief

    def format_slack(self, brief: CaptainBrief) -> str:
        """
        Format brief as Slack message.

        Args:
            brief: CaptainBrief instance

        Returns:
            Slack-formatted markdown string
        """

        # Confidence indicator
        confidence_pct = int(brief.confidence * 100)
        confidence_bar = self._confidence_bar(brief.confidence)

        # Key findings (already formatted with bullet points)
        findings_text = "\n".join(brief.key_findings) if brief.key_findings else "_No key findings extracted_"

        # Build Slack message
        slack_msg = f"""*📋 RESEARCH BRIEF*

*Topic:* {brief.research_topic}

*Executive Summary*
{brief.executive_summary}

*Key Findings*
{findings_text}

*Implications*
{brief.implications}

*Recommendation*
{brief.recommendation}

*Confidence:* {confidence_bar} {confidence_pct}%

_Mission ID: {brief.mission_id}_
_Completed: {brief.successful_tasks}/{brief.task_count} research tasks_
_Generated: {brief.timestamp}_"""

        return slack_msg

    def format_html(self, brief: CaptainBrief) -> str:
        """
        Format brief as HTML report.

        Args:
            brief: CaptainBrief instance

        Returns:
            HTML string suitable for email or web display
        """

        findings_html = "\n".join(
            f"<li>{finding}</li>"
            for finding in brief.key_findings
        )

        html = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 20px; }}
        .header {{ border-bottom: 2px solid #333; padding-bottom: 10px; }}
        .section {{ margin: 20px 0; }}
        .section-title {{ font-weight: bold; font-size: 1.1em; margin-bottom: 10px; }}
        .key-findings {{ margin-left: 20px; }}
        .confidence {{ color: #666; font-size: 0.9em; }}
        .metadata {{ color: #999; font-size: 0.85em; margin-top: 20px; padding-top: 10px; border-top: 1px solid #eee; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Research Brief</h1>
        <p><strong>Topic:</strong> {brief.research_topic}</p>
    </div>

    <div class="section">
        <div class="section-title">Executive Summary</div>
        <p>{brief.executive_summary}</p>
    </div>

    <div class="section">
        <div class="section-title">Key Findings</div>
        <ul class="key-findings">
            {findings_html}
        </ul>
    </div>

    <div class="section">
        <div class="section-title">Implications</div>
        <p>{brief.implications}</p>
    </div>

    <div class="section">
        <div class="section-title">Recommendation</div>
        <p><strong>{brief.recommendation}</strong></p>
        <p class="confidence">Confidence Level: {int(brief.confidence * 100)}%</p>
    </div>

    <div class="metadata">
        <p>
            <strong>Research Summary:</strong> {brief.successful_tasks} of {brief.task_count} research tasks completed<br>
            <strong>Mission ID:</strong> {brief.mission_id}<br>
            <strong>Generated:</strong> {brief.timestamp}
        </p>
    </div>
</body>
</html>"""

        return html

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _extract_summary(self, consolidated_findings: str) -> list[str]:
        """
        Extract executive summary from consolidated findings.

        Returns first 2-3 sentences or lines marked as summary.

        Args:
            consolidated_findings: Consolidated research findings text

        Returns:
            List of summary lines (2-3 sentences)
        """

        if not consolidated_findings:
            return ["No findings available."]

        lines = consolidated_findings.split("\n")

        # Look for "Executive Summary" section
        for i, line in enumerate(lines):
            if "executive summary" in line.lower() or "summary:" in line.lower():
                # Extract next 2-3 lines
                summary_lines = []
                for j in range(i + 1, min(i + 4, len(lines))):
                    text = lines[j].strip()
                    if text and not text.startswith("•") and not text.startswith("-"):
                        summary_lines.append(text)
                if summary_lines:
                    return summary_lines

        # Fallback: extract first 2-3 sentences
        sentences = re.split(r"[.!?]+", consolidated_findings)
        summary_lines = []
        for sentence in sentences[:3]:
            text = sentence.strip()
            if text and len(text) > 10:  # Skip very short fragments
                summary_lines.append(text + ".")

        return summary_lines if summary_lines else ["No summary extracted."]

    def _extract_key_findings(self, consolidated_findings: str) -> list[str]:
        """
        Extract key findings from consolidated findings.

        Looks for bullet points (•, -, *) or "Key Findings" section.

        Args:
            consolidated_findings: Consolidated research findings text

        Returns:
            List of key findings (each as a string)
        """

        if not consolidated_findings:
            return []

        findings = []

        lines = consolidated_findings.split("\n")

        # Look for "Key Findings" section
        in_findings_section = False
        for line in lines:
            if "key findings" in line.lower():
                in_findings_section = True
                continue

            if in_findings_section:
                text = line.strip()

                # Stop at next section
                if text and (":" in text) and not text.startswith("•") and not text.startswith("-"):
                    if any(
                        keyword in text.lower()
                        for keyword in [
                            "implications",
                            "recommendation",
                            "sources",
                            "information",
                        ]
                    ):
                        break

                # Extract bullet point
                if text.startswith("•") or text.startswith("-") or text.startswith("*"):
                    clean_text = text.lstrip("•-* ").strip()
                    if clean_text:
                        findings.append(clean_text)

        return findings if findings else ["Research in progress; findings not yet consolidated."]

    def _generate_implications(
        self, consolidated_findings: str, successful_tasks: int, task_count: int
    ) -> str:
        """
        Generate implications for decision-makers.

        Reflects completeness and actionability.

        Args:
            consolidated_findings: Consolidated findings text
            successful_tasks: Number of successfully completed tasks
            task_count: Total number of research tasks

        Returns:
            Implications statement
        """

        if successful_tasks == task_count:
            # All data collected
            return (
                "Research is comprehensive and complete across all planned areas. "
                "Implications are grounded in full evidence base and suitable for decision-making."
            )
        elif successful_tasks >= task_count * 0.75:
            # Most data collected
            return (
                f"Research covers {successful_tasks} of {task_count} planned areas. "
                "While mostly comprehensive, some gaps exist. "
                "Recommend addressing remaining areas before final decision."
            )
        elif successful_tasks >= task_count * 0.5:
            # Moderate coverage
            return (
                f"Research covers {successful_tasks} of {task_count} planned areas. "
                "Coverage is moderate with notable gaps. "
                "Current findings provide directional insight but not sufficient for confident decision."
            )
        else:
            # Limited coverage
            return (
                f"Research covers only {successful_tasks} of {task_count} planned areas. "
                "Evidence is limited and preliminary. "
                "Do not make critical decisions based on this incomplete research."
            )

    def _confidence_bar(self, confidence: float) -> str:
        """
        Generate visual confidence bar for Slack.

        Args:
            confidence: Confidence score (0.0 - 1.0)

        Returns:
            Bar string (e.g., "████░░░░░░")
        """

        filled = int(confidence * 10)
        empty = 10 - filled

        if confidence >= 0.8:
            return "🟩" * filled + "🟨" * empty  # Green for high confidence
        elif confidence >= 0.5:
            return "🟨" * filled + "⬜" * empty  # Yellow for medium
        else:
            return "🟥" * filled + "⬜" * empty  # Red for low confidence
