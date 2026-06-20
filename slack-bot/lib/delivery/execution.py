"""EDO — Execution activation (MSN-EDO-002 WP2 / EDO-006).

Completes the execution bridge between an *approved* mission and engineering
delivery. This module is the pure, testable core: it converts an approved mission
into a structured, governance-bounded ExecutionPackage and the dispatch payload
for the execution workflow.

It does NOT merge, deploy, or close anything. Governance invariants are encoded
in the package and cannot be bypassed:
  - execution requires an explicit plan approval (gate);
  - the package may only advance to in_progress → in_review;
  - merge stays with XO; closure stays with XO; both are recorded as required.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import lifecycle


def _slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:limit] or "mission").strip("-")


@dataclass
class ExecutionPackage:
    mission_id: str
    title: str
    branch: str
    base: str
    objective: str
    plan_steps: list[str] = field(default_factory=list)
    target_state: str = "in_progress"
    dispatch_inputs: dict = field(default_factory=dict)
    governance: dict = field(default_factory=dict)
    transitions: list[tuple[str, str]] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"*Execution Package — {self.mission_id}*",
            f"_{self.title}_",
            "",
            f"• Branch: `{self.branch}` (base `{self.base}`)",
            f"• Target state: {self.target_state}",
            "",
            "*Plan steps:*",
        ]
        lines += [f"{i}. {s}" for i, s in enumerate(self.plan_steps or ["(plan to be attached)"], 1)]
        lines += [
            "",
            "*Governance (non-bypassable):*",
            "• No autonomous merge — XO approves the PR merge.",
            "• No autonomous closure — XO closure authority unchanged.",
            "• Validation gate mandatory before review.",
        ]
        return "\n".join(lines)


# Governance invariants stamped on every package.
_GOVERNANCE = {
    "no_autonomous_merge": True,
    "no_autonomous_closure": True,
    "requires_validation_gate": True,
    "requires_xo_merge_approval": True,
    "number_one_assignment_unchanged": True,
}


def build_execution_package(
    mission: dict,
    *,
    plan_approved: bool,
    approver: str | None = None,
    base: str = "main",
) -> tuple[ExecutionPackage | None, str]:
    """Build an ExecutionPackage from an approved mission.

    Returns (package, "ok") or (None, reason). The plan-approval gate and the
    eligible-state check are the two governance gates to dispatch.
    """
    mission_id = str(mission.get("mission_id") or mission.get("id") or "").strip()
    if not mission_id:
        return None, "mission has no id"

    # Gate 1 — explicit plan approval is mandatory (governance).
    if not plan_approved:
        return None, "plan not approved — execution blocked (plan-approval gate)"

    # Gate 2 — mission must be eligible to start.
    state = lifecycle.canonical_state(mission.get("status"))
    if state not in ("proposed", "planned"):
        return None, f"mission is '{state}', not eligible to start execution"

    title = str(mission.get("title") or mission_id)
    branch = f"edo/{_slug(mission_id)}-{_slug(title)}"
    objective = str(mission.get("description") or title)
    plan_steps = mission.get("plan_steps") or []

    package = ExecutionPackage(
        mission_id=mission_id,
        title=title,
        branch=branch,
        base=base,
        objective=objective,
        plan_steps=list(plan_steps),
        target_state="in_progress",
        dispatch_inputs={"mission_id": mission_id, "branch": branch},
        governance=dict(_GOVERNANCE),
        transitions=[(state, "in_progress")],
    )
    return package, "ok"


def dispatch_payload(package: ExecutionPackage) -> dict:
    """The workflow_dispatch inputs for the EDO execution workflow."""
    return {
        "ref": package.base,
        "inputs": dict(package.dispatch_inputs),
    }


def render_pr_body(package: ExecutionPackage, mission: dict | None = None) -> str:
    """The draft-PR description for an execution package (governance-bounded)."""
    steps = package.plan_steps or ["(plan to be attached by the executor)"]
    lines = [
        f"## EDO Execution — {package.mission_id}",
        f"**{package.title}**",
        "",
        f"Objective: {package.objective}",
        "",
        "### Plan",
        *[f"- [ ] {s}" for s in steps],
        "",
        "### Governance (non-bypassable)",
        "- [ ] Validation gate passed (tests/evidence recorded)",
        "- [ ] XO approval obtained before merge",
        "- This PR is a **draft**. Do not merge without XO closure authority.",
        "- No autonomous merge or closure — Number One assignment unchanged.",
        "",
        f"_Branch `{package.branch}` · target state `{package.target_state}`._",
    ]
    return "\n".join(lines)


def render_manifest(package: ExecutionPackage) -> dict:
    """A machine-readable execution manifest committed to the branch."""
    return {
        "mission_id": package.mission_id,
        "title": package.title,
        "branch": package.branch,
        "base": package.base,
        "target_state": package.target_state,
        "governance": package.governance,
        "transitions": [{"from": f, "to": t} for f, t in package.transitions],
    }


def prepare_dispatch(
    mission: dict,
    *,
    plan_approved: bool,
    base: str = "main",
) -> tuple[dict | None, str]:
    """Build the full dispatch artifact set for the execution workflow.

    Returns (artifacts, "ok") or (None, reason). ``artifacts`` carries everything
    the workflow needs to create a branch + draft PR + record the transition,
    with governance invariants attached. Enforces the plan-approval gate.
    """
    package, reason = build_execution_package(mission, plan_approved=plan_approved, base=base)
    if package is None:
        return None, reason
    frm, to = package.transitions[0]
    artifacts = {
        "mission_id": package.mission_id,
        "branch": package.branch,
        "base": package.base,
        "draft": True,
        "pr_title": f"[EDO] {package.mission_id}: {package.title}",
        "pr_body": render_pr_body(package, mission),
        "manifest": render_manifest(package),
        "transition": {
            "mission_id": package.mission_id,
            "from_state": frm, "to_state": to, "actor": "edo-execute",
        },
        "governance": dict(package.governance),
    }
    return artifacts, "ok"
