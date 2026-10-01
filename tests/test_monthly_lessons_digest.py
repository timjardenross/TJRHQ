"""`intelligence.proactive_cadences._generate_lessons_digest()` tests.

The digest used to look for inline `Mission:` / `Outcome:` lines that no
register writer produces, so every lesson rendered as "unknown: see record",
and it counted an entry as recent if a `YYYY-MM` string appeared anywhere in
its body. These pin the real register shape (`## LL-NNN` + `### Title` /
`### Date` / optional `### Mission` sections) and date-based filtering.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence import proactive_cadences  # noqa: E402

REGISTER = """# Lessons Learned

Intro text mentioning 2026-09 that must not count as a lesson.

---
## LL-200
### Title
September lesson with a real title
### Date
2026-09-12
### Lesson
Body text.
---
## LL-201

### Title

Captured-format lesson with a mission

### Date

2026-10-01

### Mission

USS-TJR-MSN-0400

---
## LL-150
### Title
Old lesson whose body mentions 2026-09-30 but is dated earlier
### Date
2026-07-02
---
## LL-202
### Title
Lesson with no usable date
### Date
TBD
---
"""


def _digest(tmp_path, monkeypatch, today, register=REGISTER):
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "Lessons-Learned.md").write_text(register, encoding="utf-8")
    monkeypatch.setattr(proactive_cadences, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(proactive_cadences, "_today", lambda: today)
    return proactive_cadences._generate_lessons_digest()


def test_renders_title_date_and_mission_not_placeholders(tmp_path, monkeypatch):
    out = _digest(tmp_path, monkeypatch, date(2026, 10, 1))
    assert "unknown" not in out
    assert "see record" not in out
    assert "2 lesson(s) recorded since 1 September 2026:" in out
    assert "LL-200 (2026-09-12) — September lesson with a real title" in out
    assert "LL-201 (2026-10-01) — Captured-format lesson with a mission [USS-TJR-MSN-0400]" in out


def test_filters_on_date_section_not_body_text(tmp_path, monkeypatch):
    out = _digest(tmp_path, monkeypatch, date(2026, 10, 1))
    assert "LL-150" not in out
    assert "LL-202" not in out


def test_previous_month_lessons_drop_out_next_month(tmp_path, monkeypatch):
    out = _digest(tmp_path, monkeypatch, date(2026, 11, 1))
    assert "LL-200" not in out
    assert "LL-201 (2026-10-01)" in out
    assert "1 lesson(s) recorded since 1 October 2026:" in out


def test_no_recent_lessons_reports_register_total(tmp_path, monkeypatch):
    out = _digest(tmp_path, monkeypatch, date(2027, 3, 1))
    assert "No new lessons recorded this period. 4 total in register." in out


def test_long_period_is_capped(tmp_path, monkeypatch):
    register = "".join(
        f"## LL-{n:03d}\n### Title\nLesson {n}\n### Date\n2026-09-15\n---\n"
        for n in range(300, 345)
    )
    out = _digest(tmp_path, monkeypatch, date(2026, 10, 1), register)
    assert "45 lesson(s)" in out
    assert "…and 15 more" in out
    assert out.count("  • LL-") == proactive_cadences._DIGEST_MAX_LESSONS
