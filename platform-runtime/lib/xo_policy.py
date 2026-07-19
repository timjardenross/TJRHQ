"""XO system policy decision point.

This module evaluates engineering approval requests as a system governance
decision, not as a human authorization check.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


_SLACK_BOT_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SLACK_BOT_DIR.parent


@dataclass
class XOPolicyDecision:
    """Structured XO decision result."""

    approved: bool
    policy_decision: str
    decision_reason: str
    resulting_state: str
    system_actor: str = "XO"
    requesting_user: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    policy_trace: list[str] = field(default_factory=list)
    policy_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict."""
        return asdict(self)


def _read_text_if_exists(path: Path) -> str | None:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
    except OSError:
        return None
    return None


def _context_value(context: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = context.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _load_policy_sources(context: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Load governance sources referenced by the XO policy context.

    Returns a tuple of (source_labels, trace_entries). Missing context or
    unreadable sources are treated as policy failures upstream.
    """
    source_labels: list[str] = []
    trace_entries: list[str] = []

    source_paths = context.get("policy_source_paths") or {
        "adr_0001": "architecture/decisions/ADR-0001-Validation-Standard.md",
        "mission_registry": "governance/Phase-1.1-Mission-Registry-Schema.md",
        "capability_registry": "knowledge/Capability-Management/Capability-Registry.md",
        "decision_registry": "core/governance/decision-register.txt",
        "architecture_records": "knowledge/architecture/Architecture-Vision.md",
        "workflow_policy": "Missions/Active/MSN-0015A-Work-Lifecycle-Architecture.txt",
    }
    if isinstance(source_paths, dict):
        for label, raw_path in source_paths.items():
            if not raw_path:
                continue
            label_text = str(label).strip()
            path = Path(str(raw_path))
            if not path.is_absolute():
                path = (_REPO_ROOT / path).resolve()
            content = _read_text_if_exists(path)
            if content is None:
                trace_entries.append(f"{label_text}: missing or unreadable")
                continue
            source_labels.append(label_text)
            trace_entries.append(f"{label_text}: loaded")

    return source_labels, trace_entries


def _required_context_fields(context: dict[str, Any]) -> tuple[bool, str]:
    required = (
        "requesting_user",
        "mission_title",
        "record_path",
        "thread_ts",
        "current_status",
        "current_batch_status",
        "batch_group",
        "priority",
        "decision_id",
    )
    missing = [field for field in required if not _context_value(context, field)]
    if missing:
        return False, f"Missing required policy context fields: {', '.join(missing)}"
    return True, ""


def _evaluate_governance_state(context: dict[str, Any], policy_trace: list[str]) -> tuple[bool, str]:
    """Minimal artifact-driven policy evaluation.

    This is intentionally conservative: missing governance state fails secure.
    """
    current_status = _context_value(context, "current_status")
    current_batch_status = _context_value(context, "current_batch_status")
    batch_group = _context_value(context, "batch_group")
    assigned_by = _context_value(context, "assigned_by")
    guard_rails_ok = _context_value(context, "guard_rails_ok").lower()
    validation_evidence = _context_value(context, "validation_evidence")

    if current_status != "APPROVED_FOR_ENGINEERING":
        return False, f"Handoff status is {current_status!r}; expected APPROVED_FOR_ENGINEERING"

    if current_batch_status != "PENDING":
        return False, f"Batch status is {current_batch_status!r}; XO only approves pending handoffs"

    if batch_group not in ("", "unassigned"):
        return False, f"Batch group is already assigned as {batch_group!r}; XO cannot emit SUBMITTED"

    if assigned_by:
        return False, "Assignment already present; XO does not own assignment transitions"

    if guard_rails_ok not in ("true", "1", "yes", "ok"):
        return False, "Guard rail status not confirmed"

    if not validation_evidence:
        return False, "Validation evidence missing"

    policy_trace.append("governance: status/batch/guard rails validated")
    return True, "Governance sources satisfy XO policy"


def xo_can_approve(context: dict[str, Any]) -> XOPolicyDecision:
    """Evaluate whether XO should approve a handoff.

    Approval output is intentionally constrained to:
      - APPROVED_FOR_ENGINEERING + PENDING

    There is no SUBMITTED output path in this policy decision point.
    """
    policy_trace: list[str] = []

    if not isinstance(context, dict):
        return XOPolicyDecision(
            approved=False,
            policy_decision="REJECTED",
            decision_reason="Invalid policy context type",
            resulting_state="DENIED",
            policy_trace=["context: invalid type"],
        )

    requesting_user = _context_value(context, "requesting_user", "user_id")
    policy_trace.append(f"requesting_user={requesting_user or 'unknown'}")

    ok, reason = _required_context_fields(context)
    if not ok:
        policy_trace.append("context: incomplete")
        return XOPolicyDecision(
            approved=False,
            policy_decision="REJECTED",
            decision_reason=reason,
            resulting_state="DENIED",
            requesting_user=requesting_user,
            policy_trace=policy_trace,
            policy_sources=[],
        )

    policy_sources, source_trace = _load_policy_sources(context)
    policy_trace.extend(source_trace)

    if not policy_sources:
        return XOPolicyDecision(
            approved=False,
            policy_decision="REJECTED",
            decision_reason="Required governance artefacts missing or unreadable",
            resulting_state="DENIED",
            requesting_user=requesting_user,
            policy_trace=policy_trace,
            policy_sources=[],
        )

    ok, reason = _evaluate_governance_state(context, policy_trace)
    if not ok:
        return XOPolicyDecision(
            approved=False,
            policy_decision="REJECTED",
            decision_reason=reason,
            resulting_state="DENIED",
            requesting_user=requesting_user,
            policy_trace=policy_trace,
            policy_sources=policy_sources,
        )

    policy_trace.append("decision: APPROVED_FOR_ENGINEERING")
    policy_trace.append("state: PENDING")
    return XOPolicyDecision(
        approved=True,
        policy_decision="APPROVED",
        decision_reason=reason,
        resulting_state="APPROVED_FOR_ENGINEERING + PENDING",
        requesting_user=requesting_user,
        policy_trace=policy_trace,
        policy_sources=policy_sources,
    )
