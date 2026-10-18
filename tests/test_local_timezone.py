"""The platform's local time zone is Australia/Melbourne (DST-aware), not Brisbane.

Guards the 2026-10 move from Brisbane (fixed UTC+10) to Melbourne: day boundaries and
reminder times must follow daylight saving, and no code may hard-code the old zone.
"""
from __future__ import annotations

import importlib.util
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]


def _load_tz():
    spec = importlib.util.spec_from_file_location("tjr_lib_tz", REPO / "platform-runtime" / "lib" / "tz.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tz_module_is_melbourne():
    tz = _load_tz()
    assert str(tz._LOCAL) == "Australia/Melbourne"


def test_today_rolls_over_at_melbourne_midnight_in_daylight_saving(monkeypatch):
    tz = _load_tz()

    class _Fixed(datetime):
        @classmethod
        def now(cls, tz_=None):
            # 13:30 UTC on 17 Oct = 00:30 on 18 Oct in Melbourne (AEDT), 23:30 on 17 Oct in Brisbane.
            return datetime(2026, 10, 17, 13, 30, tzinfo=timezone.utc).astimezone(tz_)

    monkeypatch.setattr(tz, "datetime", _Fixed)
    assert tz.today_local_iso() == "2026-10-18"


def test_melbourne_offsets_follow_daylight_saving():
    mel = ZoneInfo("Australia/Melbourne")
    assert datetime(2026, 7, 9, 12, tzinfo=mel).utcoffset().total_seconds() == 10 * 3600  # AEST
    assert datetime(2026, 10, 18, 12, tzinfo=mel).utcoffset().total_seconds() == 11 * 3600  # AEDT
    # Daylight saving starts Sun 4 Oct 2026 and ends Sun 4 Apr 2027.
    assert datetime(2026, 10, 3, 12, tzinfo=mel).utcoffset().total_seconds() == 10 * 3600
    assert datetime(2027, 4, 5, 12, tzinfo=mel).utcoffset().total_seconds() == 10 * 3600


_SCAN_DIRS = ("telegram-bots", "intelligence", "platform-runtime", "core", "lcars-portal/src", "services", "scripts", "tools")
_SKIP = re.compile(r"(^|/)(node_modules|graphify-out|migrations|__pycache__)(/|$)|(^|/)test_[^/]*\.py$|\.test\.tsx?$|(^|/)__tests__(/|$)|\.md$")


def test_no_code_hard_codes_brisbane_or_a_fixed_plus_ten_offset():
    offenders = []
    for d in _SCAN_DIRS:
        base = REPO / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix not in {".py", ".ts", ".tsx"}:
                continue
            rel = p.relative_to(REPO).as_posix()
            if _SKIP.search(rel):
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            for n, line in enumerate(text.splitlines(), 1):
                if "Australia/Brisbane" in line or re.search(r"T\d\d:\d\d:\d\d\+10:00", line):
                    offenders.append(f"{rel}:{n}: {line.strip()[:100]}")
    assert not offenders, "Hard-coded Brisbane / +10:00 found:\n" + "\n".join(offenders)
