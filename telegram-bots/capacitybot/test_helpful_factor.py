"""helpful_factor code/label mapping (R2 alignment, Phase 1).

Stored values are never rewritten: old rows hold label text, new rows hold the
code. helpful_factor_code() reads either form; unknown text and None -> None.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from telegram_bots.capacitybot.capacity_today import (
    DAY_WIN_HELPED_CODES,
    DAY_WIN_HELPED_OPTIONS,
    helpful_factor_code,
    write_evening,
)

APPROVED_CODES = [
    "rest", "movement", "reduced_demands", "sensory_control", "structure",
    "connection", "interesting_activity", "pain_management", "nothing_clear",
]


def test_codes_parallel_the_options_and_match_the_approved_set():
    assert DAY_WIN_HELPED_CODES == APPROVED_CODES
    assert len(DAY_WIN_HELPED_CODES) == len(DAY_WIN_HELPED_OPTIONS)


def test_only_two_labels_changed_wording():
    assert "Interesting activity" in DAY_WIN_HELPED_OPTIONS
    assert "Nothing clearly helped" in DAY_WIN_HELPED_OPTIONS


@pytest.mark.parametrize("label,code", list(zip(DAY_WIN_HELPED_OPTIONS, APPROVED_CODES)))
def test_each_known_label_maps_to_its_code(label, code):
    assert helpful_factor_code(label) == code
    assert helpful_factor_code(label.upper()) == code
    assert helpful_factor_code(code) == code  # new-style rows


def test_unknown_text_is_not_guessed():
    assert helpful_factor_code("Coffee") is None
    assert helpful_factor_code("Interesting") is None


def test_null_and_empty():
    assert helpful_factor_code(None) is None
    assert helpful_factor_code("") is None


def test_write_evening_writes_the_code_not_the_label():
    db = MagicMock()
    ok, err = asyncio.run(write_evening(db, {"hf": "6", "dt": "s", "cd": "n"}))
    assert ok and err is None
    payload = db.table.return_value.insert.call_args[0][0]
    assert payload["helpful_factor"] == "interesting_activity"


def test_write_evening_without_choice_writes_null():
    db = MagicMock()
    asyncio.run(write_evening(db, {"dt": "u"}))
    payload = db.table.return_value.insert.call_args[0][0]
    assert payload["helpful_factor"] is None
