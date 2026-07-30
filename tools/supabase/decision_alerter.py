#!/usr/bin/env python3
"""Decision Alerter for USS-TJR-MSN-0010.

Generates a structured notification whenever a strategic decision is
written to the Decision Register. Operational decisions are ignored.

Alert is:
  1. Printed to stdout immediately (Captain sees it in the terminal).
  2. Written to logs/alerts/ as a persistent record.
  3. Optionally sent to a Slack webhook if DECISION_ALERT_SLACK_WEBHOOK
     is set in the environment (future capability — skipped silently if
     not configured).

Failure never breaks Commander execution — all errors are caught and
printed as warnings.

Usage (called automatically from collaborative_specialist_runtime.py):
    from decision_alerter import emit_decision_alert
    emit_decision_alert(decision_record, decision_record_path)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ALERT_DIR = ROOT / "logs/alerts"


def emit_decision_alert(
    record: dict[str, Any],
    record_path: Path | None = None,
) -> None:
    """Emit a decision alert for a strategic decision record.

    Non-strategic records are silently ignored.
    All errors are caught so Commander execution is never interrupted.
    """
    try:
        if record.get("decision_mode") != "strategic":
            return
        alert_text = _format_alert(record, record_path)
        _print_alert(alert_text)
        _write_alert(alert_text, record)
        _send_slack_webhook(alert_text)
    except Exception as error:  # noqa: BLE001
        print(f"  Warning: Decision alert could not be emitted: {error}")


# ---------------------------------------------------------------------------
# Alert formatting
# ---------------------------------------------------------------------------

def _format_alert(record: dict[str, Any], record_path: Path | None) -> str:
    """Format the decision alert in the required Slack-ready structure."""
    action = (
        record.get("recommended_action")
        or record.get("final_recommendation")
        or "Not specified."
    )
    # Strip leading "Recommended Action: " prefix if present
    if action.lower().startswith("recommended action:"):
        action = action[len("recommended action:"):].strip()

    bottleneck = record.get("current_bottleneck") or "Not identified."
    ttv = record.get("time_to_value") or "Unknown."
    reversibility = record.get("reversibility") or "Unknown."
    alignment = record.get("strategic_alignment") or "Not assessed."
    decision_id = record.get("decision_id") or "Unknown"
    file_ref = str(record_path) if record_path else decision_id

    lines = [
        "",
        "🧠 Commander Strategic Decision",
        "",
        "Recommended Action:",
        f"  {action}",
        "",
        "Current Bottleneck:",
        f"  {bottleneck}",
        "",
        "Time To Value:",
        f"  {ttv}",
        "",
        "Reversibility:",
        f"  {reversibility}",
        "",
        "Strategic Alignment:",
        f"  {alignment}",
        "",
        "Decision Record:",
        f"  {file_ref}",
        "",
        f"{'─' * 60}",
    ]
    return "\n".join(lines)


def _print_alert(alert_text: str) -> None:
    print(alert_text)


def _write_alert(alert_text: str, record: dict[str, Any]) -> None:
    """Persist the alert to logs/alerts/ as a JSON record."""
    ALERT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S-%f")
    alert_record = {
        "alert_id": f"ALT-{timestamp}",
        "timestamp": now.isoformat(),
        "decision_id": record.get("decision_id"),
        "decision_mode": record.get("decision_mode"),
        "alert_text": alert_text,
        "recommended_action": record.get("recommended_action") or record.get("final_recommendation"),
        "current_bottleneck": record.get("current_bottleneck"),
        "time_to_value": record.get("time_to_value"),
        "reversibility": record.get("reversibility"),
        "channel": "terminal",
        "slack_sent": False,
    }
    path = ALERT_DIR / f"{timestamp}-alert.json"
    path.write_text(json.dumps(alert_record, indent=2), encoding="utf-8")


def _send_slack_webhook(alert_text: str) -> None:
    """Send alert to Slack webhook if configured (future capability).

    Set DECISION_ALERT_SLACK_WEBHOOK in .env to enable.
    Silently skipped if not configured.
    """
    webhook_url = os.environ.get("DECISION_ALERT_SLACK_WEBHOOK", "").strip()
    if not webhook_url:
        return

    payload = json.dumps({"text": alert_text}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    timeout = float(os.environ.get("DECISION_ALERT_TIMEOUT_SECONDS", "10"))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            if resp.status == 200:
                # Update alert record to mark slack_sent=True
                pass  # future: look up latest alert and update flag
    except Exception as error:  # noqa: BLE001
        print(f"  Warning: Slack webhook delivery failed: {error}")


def load_alerts(limit: int = 20) -> list[dict[str, Any]]:
    """Load recent alert records from logs/alerts/."""
    if not ALERT_DIR.exists():
        return []
    records = []
    for path in sorted(ALERT_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return records
