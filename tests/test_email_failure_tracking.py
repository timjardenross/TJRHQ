"""A failed emergency email is recorded (migration 0243) so the workbench can say
'Email FAILED' rather than 'not sent yet'; a successful one is not."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))

import intelligence.emergency_alerts as ea

ROW = {"id": "a1", "headline": "Bush fire Katoomba", "jurisdiction": "NSW", "alert_type": "bushfire", "location": "Katoomba",
       "description": "d", "canonical_url": None, "issued_at": None, "latitude": None, "longitude": None}


def _run(send_ok: bool):
    with patch.object(ea, "supabase_get", return_value=[ROW]), \
         patch.object(ea.alert_silences, "list_active_silences", return_value=[]), \
         patch.object(ea.site_matching, "list_active_sites", return_value=[]), \
         patch.object(ea, "_supabase_request") as req, \
         patch.object(ea, "send_email", return_value=send_ok):
        sent = ea._send_emergency_warning_emails("nsw_rfs")
    return sent, [c.kwargs.get("body") for c in req.call_args_list]


def test_failed_send_stamps_failure_and_not_sent():
    sent, bodies = _run(False)
    assert sent == 0
    assert len(bodies) == 1 and "emergency_email_failed_at" in bodies[0] and "emergency_email_sent_at" not in bodies[0]


def test_successful_send_stamps_sent_only():
    sent, bodies = _run(True)
    assert sent == 1
    assert len(bodies) == 1 and "emergency_email_sent_at" in bodies[0] and "emergency_email_failed_at" not in bodies[0]


def test_failure_write_error_never_raises():
    with patch.object(ea, "_supabase_request", side_effect=RuntimeError("down")):
        ea._record_email_failure("a1")
