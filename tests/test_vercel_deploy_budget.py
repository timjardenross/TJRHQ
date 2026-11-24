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
