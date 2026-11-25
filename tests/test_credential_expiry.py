"""Credential expiry monitor: 30/14/7/1-day warnings, once per threshold, expired, broken registry."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.platform import credential_expiry as ce

EXP = datetime(2027, 2, 22, 23, 57, tzinfo=timezone.utc)


def _setup(tmp_path):
    reg, st = tmp_path / "reg.json", tmp_path / "state.json"
    reg.write_text(json.dumps([{"name": "idp", "expires_at": EXP.isoformat(), "renewal_hint": "renew it"}]))
    sent = []
    return reg, st, sent, (lambda title, sev, body: sent.append((title, sev, body)))


def _run(tmp_path, days_before, sent_fn, reg, st):
    return ce.run_check(now=EXP - timedelta(days=days_before), notify_fn=sent_fn, registry=reg, state_path=st)


def test_no_alert_outside_30_days(tmp_path):
    reg, st, sent, fn = _setup(tmp_path)
    assert _run(tmp_path, 31, fn, reg, st) == [] and not sent


def test_each_threshold_alerts_exactly_once(tmp_path):
    reg, st, sent, fn = _setup(tmp_path)
    for d in (30, 29, 20, 14, 13, 8, 7, 6, 2, 1, 0.5):
        _run(tmp_path, d, fn, reg, st); _run(tmp_path, d, fn, reg, st)  # twice: no duplicates
    assert len(sent) == 4
    assert [s[1] for s in sent] == ["warning", "warning", "alert", "critical"]
    assert "30 day" in sent[0][2] and "1 day" in sent[3][2]


def test_late_start_sends_only_the_current_threshold(tmp_path):
    reg, st, sent, fn = _setup(tmp_path)
    _run(tmp_path, 5, fn, reg, st)
    assert len(sent) == 1 and "7 day" in sent[0][2]


def test_expired_alerts_once_per_day(tmp_path):
    reg, st, sent, fn = _setup(tmp_path)
    ce.run_check(now=EXP + timedelta(hours=1), notify_fn=fn, registry=reg, state_path=st)
    ce.run_check(now=EXP + timedelta(hours=2), notify_fn=fn, registry=reg, state_path=st)
    ce.run_check(now=EXP + timedelta(days=1, hours=1), notify_fn=fn, registry=reg, state_path=st)
    assert len(sent) == 2 and all(s[1] == "critical" and "EXPIRED" in s[0] for s in sent)


def test_renewal_starts_a_fresh_series(tmp_path):
    reg, st, sent, fn = _setup(tmp_path)
    _run(tmp_path, 7, fn, reg, st)
    new = EXP + timedelta(days=90)
    reg.write_text(json.dumps([{"name": "idp", "expires_at": new.isoformat()}]))
    ce.run_check(now=new - timedelta(days=7), notify_fn=fn, registry=reg, state_path=st)
    assert len(sent) == 2


def test_broken_or_missing_registry_alerts_once_per_day_and_never_raises(tmp_path):
    reg, st, sent, fn = _setup(tmp_path)
    reg.write_text("{not json")
    now = EXP - timedelta(days=100)
    assert ce.run_check(now=now, notify_fn=fn, registry=reg, state_path=st) == []
    ce.run_check(now=now, notify_fn=fn, registry=reg, state_path=st)
    assert len(sent) == 1 and "unreadable" in sent[0][0]
    ce.run_check(now=now, notify_fn=fn, registry=tmp_path / "missing.json", state_path=st)
    assert len(sent) == 1  # same day
    ce.run_check(now=now + timedelta(days=1), notify_fn=fn, registry=tmp_path / "missing.json", state_path=st)
    assert len(sent) == 2


def test_message_contains_no_secret_material(tmp_path):
    reg, st, sent, fn = _setup(tmp_path)
    _run(tmp_path, 1, fn, reg, st)
    assert "renew it" in sent[0][2]
