#!/usr/bin/env python3
"""Tests for the 2026-09-07 "stamp MERGED on the handoff file" fix to
core/coordination/delivery_reconciler.py.

Bug: engineering_handoff_reader.py (which feeds the Engineering Handoffs
page and the Captain's review reminders) only ever trusts a handoff's own
`Batch Status` stamp — it never checks GitHub. delivery_reconciler.py
already reconciles missions against live PR state and mechanically closes
them out on merge (apply=True), but never did the equivalent for
engineering handoffs: their `.md` files were left un-stamped forever, so
a handoff whose PR the Captain had already merged kept nagging as
"Awaiting Review" indefinitely.

Never touches real GitHub or Supabase: `_github_prs` and `_supabase` are
monkeypatched in every test; handoff files live under a scratch tmp_path,
never the real `Missions/Engineering-Handoffs/`.

Runnable under pytest or directly:
`python3 tests/test_delivery_reconciler.py` from the repo root.
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.coordination.delivery_reconciler as dr


def _write_handoff(tmp_path: Path, name: str, lines: list[str]) -> Path:
    p = tmp_path / f"{name}.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _reconcile_with(tmp_path, prs, apply: bool):
    with patch.object(dr, "HANDOFF_DIR", tmp_path), \
         patch.object(dr, "INBOX_DIR", tmp_path / "no-such-inbox"), \
         patch.object(dr, "_github_prs", return_value=(prs, "")), \
         patch.object(dr, "_supabase", return_value=None):
        return dr.reconcile(apply=apply)


def test_stamps_merged_batch_status_when_github_shows_the_pr_merged(tmp_path):
    handoff = _write_handoff(tmp_path, "ENG-HANDOFF-SD-FND-001", [
        "# Engineering Handoff",
        "- Batch Status: DELIVERED",
        "- PR Branch: fix/handoff-1",
        "- PR URL: https://github.com/timjardenross/TJRHQ/pull/56",
    ])
    prs = {"fix/handoff-1": {"number": 56, "state": "merged",
                              "url": "https://github.com/timjardenross/TJRHQ/pull/56"}}

    ledger = _reconcile_with(tmp_path, prs, apply=True)

    assert any("Batch Status → MERGED" in a for a in ledger["actions_taken"])
    assert "Batch Status: MERGED" in handoff.read_text(encoding="utf-8")
    item = next(i for i in ledger["items"] if i["id"] == "ENG-HANDOFF-SD-FND-001")
    assert item["bucket"] == "DELIVERED"


def test_report_mode_never_writes_to_the_file(tmp_path):
    handoff = _write_handoff(tmp_path, "ENG-HANDOFF-SD-FND-002", [
        "# Engineering Handoff",
        "- Batch Status: DELIVERED",
        "- PR Branch: fix/handoff-2",
        "- PR URL: https://github.com/timjardenross/TJRHQ/pull/57",
    ])
    prs = {"fix/handoff-2": {"number": 57, "state": "merged",
                              "url": "https://github.com/timjardenross/TJRHQ/pull/57"}}

    ledger = _reconcile_with(tmp_path, prs, apply=False)

    assert ledger["actions_taken"] == []
    assert "Batch Status: DELIVERED" in handoff.read_text(encoding="utf-8")
    assert "MERGED" not in handoff.read_text(encoding="utf-8")
    item = next(i for i in ledger["items"] if i["id"] == "ENG-HANDOFF-SD-FND-002")
    assert item["bucket"] == "DELIVERED"  # still correctly classified for the ledger view


def test_already_stamped_merged_is_left_alone(tmp_path):
    handoff = _write_handoff(tmp_path, "ENG-HANDOFF-SD-FND-003", [
        "# Engineering Handoff",
        "- Batch Status: MERGED",
        "- PR Branch: fix/handoff-3",
        "- PR URL: https://github.com/timjardenross/TJRHQ/pull/58",
    ])
    prs = {"fix/handoff-3": {"number": 58, "state": "merged",
                              "url": "https://github.com/timjardenross/TJRHQ/pull/58"}}

    ledger = _reconcile_with(tmp_path, prs, apply=True)

    assert ledger["actions_taken"] == []  # idempotent — no repeated stamping
    assert handoff.read_text(encoding="utf-8").count("Batch Status:") == 1


def test_still_open_pr_is_not_stamped_or_touched(tmp_path):
    handoff = _write_handoff(tmp_path, "ENG-HANDOFF-SD-FND-004", [
        "# Engineering Handoff",
        "- Batch Status: DELIVERED",
        "- PR Branch: fix/handoff-4",
        "- PR URL: https://github.com/timjardenross/TJRHQ/pull/59",
    ])
    prs = {"fix/handoff-4": {"number": 59, "state": "open",
                              "url": "https://github.com/timjardenross/TJRHQ/pull/59"}}

    ledger = _reconcile_with(tmp_path, prs, apply=True)

    assert ledger["actions_taken"] == []
    assert "Batch Status: DELIVERED" in handoff.read_text(encoding="utf-8")
    item = next(i for i in ledger["items"] if i["id"] == "ENG-HANDOFF-SD-FND-004")
    assert item["bucket"] == "AWAITING_REVIEW"


def test_stamp_handoff_is_idempotent_when_called_directly(tmp_path):
    p = _write_handoff(tmp_path, "ENG-HANDOFF-DIRECT", [
        "# Engineering Handoff",
        "- Batch Status: DELIVERED",
        "## Body",
        "some content",
    ])
    dr._stamp_handoff(p, {"Batch Status": "MERGED"})
    text = p.read_text(encoding="utf-8")
    assert text.count("Batch Status:") == 1
    assert "Batch Status: MERGED" in text
    assert "## Body" in text  # body untouched


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
