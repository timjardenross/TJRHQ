from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO)]

from tools.ops import vercel_deploy_budget as vb

NOW = 1_795_500_000_000
H = 3600 * 1000


def _d(hours_ago, target=None):
    return {"created": NOW - int(hours_ago * H), "target": target}


def test_counts_only_the_trailing_window_and_splits_preview_from_production():
    c = vb.count_window([_d(1), _d(5, "production"), _d(23.9), _d(25), _d(30, "production")], NOW)
    assert c == {"preview": 2, "production": 1, "total": 3}


def test_preview_budget_stops_nonessential_deployments_but_production_is_separate():
    deps = [_d(i * 0.1) for i in range(10)]                                   # 10 previews in 24h
    assert vb.decide(deps, "preview", now_ms=NOW)[0] is False
    assert vb.decide(deps, "production", now_ms=NOW)[0] is True


def test_emergency_release_is_possible_until_the_platform_allowance_is_gone():
    deps = [_d(i * 0.1) for i in range(60)]
    assert vb.decide(deps, "preview", now_ms=NOW)[0] is False
    assert vb.decide(deps, "production", emergency=True, now_ms=NOW)[0] is True
    assert vb.decide([_d(i * 0.1) for i in range(100)], "production", emergency=True, now_ms=NOW)[0] is False


def test_canceled_deployments_count_like_any_other():
    deps = [dict(_d(i * 0.1), state="CANCELED") for i in range(10)]
    assert vb.decide(deps, "preview", now_ms=NOW)[0] is False


def test_ticket_is_issued_only_within_budget_and_is_single_use(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL_DEPLOY_TICKET_DIR", str(tmp_path))
    ok, _ = vb.issue_ticket([_d(1)], "preview", now_ms=NOW)
    assert ok and vb.consume_ticket("preview", now_ms=NOW + 1000)[0] is True
    assert vb.consume_ticket("preview", now_ms=NOW + 2000)[0] is False          # single use
    full = [_d(i * 0.1) for i in range(10)]
    assert vb.issue_ticket(full, "preview", now_ms=NOW)[0] is False
    assert vb.consume_ticket("preview", now_ms=NOW)[0] is False                  # nothing was issued


def test_ticket_expires(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL_DEPLOY_TICKET_DIR", str(tmp_path))
    vb.issue_ticket([], "production", now_ms=NOW)
    assert vb.consume_ticket("production", now_ms=NOW + 31 * 60 * 1000)[0] is False


def test_gate_hook_classifies_deployment_paths_and_ignores_everything_else():
    sys.path.insert(0, str(_REPO / ".claude" / "hooks"))
    import vercel_deploy_gate as gate
    assert gate.kind_of("mcp__Vercel__create_deployment", {"requestBody": {"target": "production"}}) == "production"
    assert gate.kind_of("mcp__Vercel__create_deployment", {"requestBody": {"name": "x"}}) == "preview"
    assert gate.kind_of("Bash", {"command": "vercel deploy --prod"}) == "production"
    assert gate.kind_of("Bash", {"command": "cd lcars-portal && vercel deploy"}) == "preview"
    assert gate.kind_of("Bash", {"command": "git push origin main"}) is None
    assert gate.kind_of("Bash", {"command": "ls vercel.json"}) is None
    assert gate.kind_of("mcp__Vercel__request_rollback", {}) is None              # rollbacks never need a ticket
    assert gate.kind_of("mcp__Vercel__list_deployments", {}) is None


def _consume_after(barrier, wins):
    barrier.wait()
    wins.append(vb.consume_ticket("preview", now_ms=NOW + 1000)[0])


def test_concurrent_consumers_exactly_one_wins(tmp_path, monkeypatch):
    import threading
    monkeypatch.setenv("VERCEL_DEPLOY_TICKET_DIR", str(tmp_path))
    for _ in range(20):                                   # repeat: races are probabilistic
        vb.issue_ticket([], "preview", now_ms=NOW)
        wins, barrier = [], threading.Barrier(8)
        threads = [threading.Thread(target=_consume_after, args=(barrier, wins)) for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert wins.count(True) == 1
        assert not list(tmp_path.glob("*claimed*"))        # no leftover claimed files


def test_reissue_overwrites_atomically_and_leaves_no_temp_files(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL_DEPLOY_TICKET_DIR", str(tmp_path))
    vb.issue_ticket([], "preview", now_ms=NOW)
    vb.issue_ticket([], "preview", now_ms=NOW + 5)
    assert not list(tmp_path.glob("*.tmp"))
    assert vb.consume_ticket("preview", now_ms=NOW + 6)[0] is True
