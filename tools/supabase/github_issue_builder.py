#!/usr/bin/env python3
"""GitHub Issue Builder for USS-TJR-MSN-0010 D4.

Generates a GitHub issue payload from a mission candidate or decision record.
Operates in dry-run mode only — never calls the GitHub API.

Output format (per mission brief):
    Mission:
    Decision:
    Recommended Action:
    Implementation Scope:
    Success Criteria:
    Owner:
    Priority:

Usage:
    from github_issue_builder import build_github_issue, print_github_issue
    issue = build_github_issue(mission_candidate)
    print_github_issue(issue)

CLI (dry-run only):
    python3 tools/supabase/github_issue_builder.py --mission-id MIS-...
    python3 tools/supabase/github_issue_builder.py --decision-id DEC-...
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class GitHubIssue:
    title: str
    body: str
    labels: list[str]
    assignee_hint: str      # suggested GitHub username hint — never auto-assigned
    priority: str
    mission_candidate_id: str | None
    decision_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "labels": self.labels,
            "assignee_hint": self.assignee_hint,
            "priority": self.priority,
            "mission_candidate_id": self.mission_candidate_id,
            "decision_id": self.decision_id,
        }


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_github_issue(
    source: dict[str, Any],
    priority: str = "Medium",
) -> GitHubIssue:
    """Build a GitHub issue payload from a mission candidate or decision record.

    Args:
        source:   A mission candidate dict (from mission_candidate.py) or a
                  decision register record (from decision_register.py).
        priority: One of High / Medium / Low. Defaults to Medium.

    Returns:
        GitHubIssue with title, body, labels, and ownership hints.
        Never calls the GitHub API.
    """
    # Normalise — accept both mission candidate and raw decision record
    is_mission = "mission_candidate_id" in source
    mission_id = source.get("mission_candidate_id") if is_mission else None
    decision_id = source.get("decision_id") or source.get("decision_id")

    title = _issue_title(source, is_mission)
    body = _issue_body(source, is_mission, priority)
    labels = _issue_labels(source)
    lead = source.get("lead_specialist") or "Chief Engineer"
    assignee_hint = _assignee_hint(lead)

    return GitHubIssue(
        title=title,
        body=body,
        labels=labels,
        assignee_hint=assignee_hint,
        priority=priority,
        mission_candidate_id=mission_id,
        decision_id=decision_id,
    )


def print_github_issue(issue: GitHubIssue) -> None:
    """Print the issue in copy-paste-ready format."""
    print()
    print("=" * 60)
    print("GitHub Issue (DRY RUN — not submitted)")
    print("=" * 60)
    print(f"Title    : {issue.title}")
    print(f"Labels   : {', '.join(issue.labels)}")
    print(f"Assignee : {issue.assignee_hint} (suggestion only — assign manually)")
    print(f"Priority : {issue.priority}")
    print()
    print("Body:")
    print("-" * 60)
    print(issue.body)
    print("-" * 60)


# ---------------------------------------------------------------------------
# Content generation
# ---------------------------------------------------------------------------

def _issue_title(source: dict[str, Any], is_mission: bool) -> str:
    if is_mission and source.get("title"):
        return source["title"]
    action = source.get("recommended_action") or source.get("final_recommendation") or ""
    if action.lower().startswith("recommended action:"):
        action = action[len("recommended action:"):].strip()
    title = action.split(".")[0].strip()
    return title[:100] if title else "Commander Strategic Decision — Implementation Required"


def _issue_body(source: dict[str, Any], is_mission: bool, priority: str) -> str:
    action = source.get("recommended_action") or source.get("final_recommendation") or "See decision record."
    if action.lower().startswith("recommended action:"):
        action = action[len("recommended action:"):].strip()

    question = source.get("question") or "Not recorded."
    bottleneck = source.get("current_bottleneck") or "Not identified."
    ttv = source.get("time_to_value") or "Not assessed."
    reversibility = source.get("reversibility") or "Not assessed."
    alignment = source.get("strategic_alignment") or "Not assessed."
    decision_id = source.get("decision_id") or "N/A"
    decision_summary = source.get("decision_summary") or (
        f"Commander TJR made a strategic recommendation in response to: {question}"
    )

    # Risks
    risks = source.get("risks") or []
    risks_md = "\n".join(f"- {r}" for r in risks) if risks else "- No specific risks identified."

    # Success criteria
    criteria = source.get("success_criteria") or []
    criteria_md = "\n".join(f"- [ ] {c}" for c in criteria) if criteria else "- [ ] Define acceptance criteria before starting."

    # Specialists
    lead = source.get("lead_specialist") or "Chief Engineer"
    supporting = source.get("supporting_specialists") or []
    supporting_str = ", ".join(supporting) if supporting else "TBD"
    rationale = source.get("assignment_rationale") or ""

    # Opportunity cost
    opp = source.get("opportunity_cost") or "Not specified."

    # Options
    options = source.get("options") or []
    options_md = ""
    if options:
        options_md = "\n".join(f"- **{o.get('label')}**: {o.get('description')}" for o in options)
    else:
        options_md = "- Not specified."

    mission_id_line = f"**Mission Candidate:** {source.get('mission_candidate_id', 'N/A')}" if is_mission else ""

    body = f"""## Mission

{decision_summary}

{mission_id_line}
**Decision Record:** {decision_id}
**Priority:** {priority}

---

## Decision

**Question:** {question}

**Options Considered:**
{options_md}

---

## Recommended Action

{action}

**Current Bottleneck:** {bottleneck}
**Strategic Alignment:** {alignment}
**Time to Value:** {ttv}
**Reversibility:** {reversibility}

---

## Implementation Scope

This mission implements the Commander recommendation above.

**Opportunity Cost:** {opp}

---

## Success Criteria

{criteria_md}

---

## Owner

**Lead Specialist:** {lead}
**Supporting Specialists:** {supporting_str}
**Assignment Rationale:** {rationale}

---

## Risks

{risks_md}

---

> ⚠️ This issue was generated by Commander TJR in dry-run mode.
> Review before assigning. Do not merge without Captain TJR approval.
"""
    return body.strip()


def _issue_labels(source: dict[str, Any]) -> list[str]:
    labels = ["commander-decision"]
    mode = source.get("decision_mode") or "strategic"
    labels.append(f"decision:{mode}")
    lead = (source.get("lead_specialist") or "").lower().replace(" ", "-")
    if lead:
        labels.append(f"owner:{lead}")
    ttv = (source.get("time_to_value") or "").lower()
    if "short" in ttv:
        labels.append("time-to-value:short")
    elif "medium" in ttv:
        labels.append("time-to-value:medium")
    rev = (source.get("reversibility") or "").lower()
    if "low" in rev:
        labels.append("reversibility:low")
    return labels


def _assignee_hint(lead: str) -> str:
    """Map specialist name to a GitHub username hint (placeholder — configure per project)."""
    _MAP = {
        "Chief Engineer":     "chief-engineer (configure in .env)",
        "Chief of Staff":     "chief-of-staff (configure in .env)",
        "Coder Agent":        "coder-agent (configure in .env)",
        "Knowledge Officer":  "knowledge-officer (configure in .env)",
        "QA & Test Officer":  "qa-officer (configure in .env)",
        "UX Design Officer":  "ux-officer (configure in .env)",
        "Research Officer":   "research-officer (configure in .env)",
    }
    return _MAP.get(lead, "TBD — assign manually")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="GitHub Issue Builder — dry-run only. Never submits to GitHub."
    )
    parser.add_argument("--mission-id", help="Generate issue from this Mission Candidate ID")
    parser.add_argument("--decision-id", help="Generate issue directly from this Decision ID")
    parser.add_argument("--priority", default="Medium", choices=["High", "Medium", "Low"])
    args = parser.parse_args()

    source = None

    if args.mission_id:
        from mission_candidate import _find_mission_path
        path = _find_mission_path(args.mission_id)
        if path is None:
            print(f"Mission candidate {args.mission_id} not found.")
            raise SystemExit(1)
        source = json.loads(path.read_text(encoding="utf-8"))

    elif args.decision_id:
        from decision_register import _find_decision_path
        path = _find_decision_path(args.decision_id)
        if path is None:
            print(f"Decision {args.decision_id} not found.")
            raise SystemExit(1)
        source = json.loads(path.read_text(encoding="utf-8"))
        # Auto-generate mission candidate data before building issue
        from mission_candidate import create_mission_candidate
        candidate = create_mission_candidate(source)
        if candidate:
            source = candidate

    if source is None:
        parser.print_help()
        raise SystemExit(1)

    issue = build_github_issue(source, priority=args.priority)
    print_github_issue(issue)


if __name__ == "__main__":
    main()
