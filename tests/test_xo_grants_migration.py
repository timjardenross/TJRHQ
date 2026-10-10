"""Guard: migration 0232 grants xo_bot exactly the operations XO's code performs
on the follow-through / conversation / rate-limit / debrief tables."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XO = ROOT / "telegram-bots" / "xo"
MIG = ROOT / "core/infrastructure/supabase/migrations/0232_xo_bot_followthrough_conversation_grants.sql"

# supabase-py sends return=representation, so insert/upsert/update also need SELECT.
EXPECTED = {
    "personal_tasks": {"select", "update"},
    "follow_through_events": {"select", "insert"},
    "follow_through_sends": {"select"},
    "conversation_turns": {"select", "insert"},
    "bot_rate_limits": {"select", "insert", "update"},
    "debrief_sessions": {"select", "insert", "update"},
    "debrief_logs": {"select", "insert"},
}


def _code_ops():
    found = {}
    for f in XO.glob("*.py"):
        if f.name.startswith("test_"):
            continue
        s = f.read_text()
        for m in re.finditer(r'\.table\(\s*"(\w+)"\s*\)((?:(?!\.table\().){0,2000}?)\.execute', s, re.DOTALL):
            ops = set(re.findall(r"\.(select|insert|update|upsert|delete)\(", m.group(2)))
            found.setdefault(m.group(1), set()).update(ops)
    return found


def _granted():
    sql = MIG.read_text()
    sql = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    out = {}
    for m in re.finditer(r"grant\s+(.+?)\s+on\s+public\.(\w+)\s+to\s+xo_bot", sql, re.DOTALL | re.IGNORECASE):
        privs = re.sub(r"\([^)]*\)", "", m.group(1))
        out.setdefault(m.group(2), set()).update(p.strip().lower() for p in privs.split(","))
    return out


def test_grants_match_expected():
    assert _granted() == EXPECTED


def test_code_ops_are_covered_and_nothing_extra_needed():
    code = _code_ops()
    for table, granted in EXPECTED.items():
        needed = {"insert", "update"} if "upsert" in code[table] else set()
        needed |= code[table] - {"upsert"}
        assert needed <= granted, (table, needed - granted)
        assert "delete" not in granted
        # anything granted beyond the code's ops must be the RETURNING select
        assert granted - needed <= {"select"}, (table, granted - needed)


def test_no_blanket_all():
    sql = MIG.read_text().lower()
    code = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    assert not re.search(r"grant\s+all", code)
    assert " delete" not in code.replace("revoke", "")
