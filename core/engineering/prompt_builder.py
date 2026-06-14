"""
Builds structured prompts for the Engineering Workflow Router.

Prompts are mode-specific, include mission context and safety framing,
and are enriched with actual repository context before sending.
"""

from __future__ import annotations

from . import context_enricher
from .schemas import ExecutionMode, MissionContext, RouterRequest

_SAFETY_PREAMBLE = """\
IMPORTANT CONSTRAINTS
- You are operating in read-only analysis mode.
- Do NOT suggest running git commands that push or commit.
- Do NOT suggest production mutations unless the Captain explicitly enables apply mode.
- Produce textual output only. No tool calls. No side effects.
- APPROVED ENGINEERING LIFECYCLE STATUSES (USS TJR standard):
    Pending Triage → Assigned → In Progress → Awaiting Review → Completed
  Do NOT suggest Design Review, Code Complete, Testing, Deployment, ENG_* variants,
  or any parallel lifecycle model. When referencing engineering lifecycle states,
  use only the approved set above.
"""


def build_prompt(req: RouterRequest) -> str:
    ctx = req.mission_context
    blocks: list[str] = []

    blocks.append(_SAFETY_PREAMBLE)
    blocks.append(f"MISSION: {ctx.mission_id}")
    blocks.append(f"Title: {ctx.title}")
    blocks.append(f"Priority: {ctx.priority}  |  Status: {ctx.status}")
    blocks.append(f"Assigned Specialist: {ctx.assigned_specialist}")
    blocks.append(f"Next Action: {ctx.next_action}")

    if ctx.blockers:
        blocks.append(f"Blockers: {', '.join(ctx.blockers)}")
    if ctx.dependencies:
        blocks.append(f"Dependencies: {', '.join(ctx.dependencies)}")
    if req.extra_context:
        blocks.append(f"\nAdditional Context:\n{req.extra_context}")

    # Inject repo-grounded context before the task instruction
    blocks.append(context_enricher.enrich(ctx))

    blocks.append("")

    if req.mode == ExecutionMode.PLAN:
        blocks.append(
            "TASK: Produce a step-by-step implementation plan for this mission.\n"
            "Include:\n"
            "1. Summary of what needs to be done\n"
            "2. Affected files or modules (by path if possible)\n"
            "3. Ordered implementation steps\n"
            "4. Risks or dependencies to validate first\n"
            "5. Suggested acceptance criteria\n"
            "\nDo not write code. Produce a plan only."
        )
    elif req.mode == ExecutionMode.PATCH:
        blocks.append(
            "TASK: Produce proposed code changes for this mission as a unified diff or clearly labelled code blocks.\n"
            "Include:\n"
            "1. File path for each change\n"
            "2. The proposed addition or modification\n"
            "3. A one-line rationale for each change\n"
            "\nLabel every block with the target file. "
            "Do NOT include any git commands. Output text only — the Captain will review before applying."
        )
    elif req.mode == ExecutionMode.REVIEW:
        blocks.append(
            "TASK: Review the mission objectives and assess whether the stated next action is sufficient.\n"
            "Include:\n"
            "1. Whether the next action is clear and actionable\n"
            "2. Any gaps in the mission definition\n"
            "3. Risks not already listed as blockers\n"
            "4. Recommendation: PROCEED / REVISE / DEFER\n"
            "\nProvide a concise assessment only."
        )

    return "\n".join(blocks)
