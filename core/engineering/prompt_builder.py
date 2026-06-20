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
            "TASK: Produce the proposed code changes as a SINGLE unified diff that applies "
            "cleanly with `git apply`.\n"
            "Strict output contract:\n"
            "1. Output EXACTLY ONE fenced block: ```diff ... ``` containing standard git "
            "unified-diff syntax — and nothing else inside the fence.\n"
            "2. Start each file with `diff --git a/<path> b/<path>`, then `--- a/<path>` and "
            "`+++ b/<path>` (use `--- /dev/null` for a brand-new file). Paths are "
            "repo-relative. Do NOT write `File:` or any other label line.\n"
            "3. Use real `@@ -start,len +start,len @@` hunk headers with accurate line numbers, "
            "and include at least 3 lines of surrounding context copied verbatim from the "
            "current file. Every line in a hunk body must start with a space, '+', or '-'.\n"
            "4. Put ALL changed files in that one diff block. No prose, comments, or git "
            "commands inside the fence.\n"
            "5. After the closing fence you may add a short plain-text rationale (one line per "
            "file).\n"
            "The Captain reviews before anything is applied — but the diff itself MUST be "
            "apply-clean against the current code."
        )
    elif req.mode == ExecutionMode.FULL_FILE:
        blocks.append(
            "TASK: Implement this mission by returning the COMPLETE final contents of "
            "every file you create or change. We mechanically diff your output against "
            "the current repo — so you must NOT write a diff yourself.\n"
            "\n"
            "OUTPUT FORMAT — follow EXACTLY. For each file, write `FILE: <repo-relative-"
            "path>` on its own line, then the entire file inside a triple-backtick "
            "fence, like this:\n"
            "\n"
            "FILE: slack-bot/commands/example.py\n"
            "```python\n"
            "<the ENTIRE final contents of the file go here>\n"
            "```\n"
            "\n"
            "Hard rules:\n"
            "1. EVERY file MUST be wrapped in its own ``` fence. Any text outside a "
            "fence is treated as commentary and DISCARDED — so put all code inside "
            "fences, and never leave file contents un-fenced.\n"
            "2. Output the ENTIRE file, not a snippet, diff, or ellipsis. If you modify "
            "an existing file shown in CURRENT FILE CONTENTS above, reproduce ALL its "
            "lines verbatim plus your changes — never drop or summarise unrelated code.\n"
            "3. Only include files you actually change. PREFER creating new, self-"
            "contained files over rewriting large existing ones; do not rewrite a file "
            "shown only as context unless the mission truly requires editing it.\n"
            "4. Use exact repo-relative paths. Don't invent paths for files you can't "
            "see — if a registration/wiring point is unknown, create the new module and "
            "describe the manual wiring in prose AFTER the final fence.\n"
            "The Captain reviews the resulting draft PR before anything merges."
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
