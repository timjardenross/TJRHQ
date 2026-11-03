"""Drift guard: the good-day rule, the day-plan reasons and the suggestion ranking are implemented twice
(Python here, TypeScript in the portal). Both read the same example days from
core/health/shared_cases/capacity_cases.json; a failure on either side means they have drifted apart."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from telegram_bots.capacitybot.day_plan import day_reasons
from telegram_bots.capacitybot.intervention_engine import rank_interventions
from telegram_bots.capacitybot.test_intervention_engine import _make_db
from core.health.good_day import provisional_good_day

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "core" / "health" / "shared_cases" / "capacity_cases.json").read_text()
)


@pytest.mark.parametrize("case", CASES["good_day"], ids=lambda c: c["name"])
def test_good_day_rule(case):
    assert provisional_good_day(case["input"]) == case["expected"]


@pytest.mark.parametrize("case", CASES["day_reasons"], ids=lambda c: c["name"])
def test_day_reasons(case):
    assert day_reasons(case["input"]) == case["expected"]


@pytest.mark.parametrize("case", CASES["ranking"], ids=lambda c: c["name"])
def test_ranking(case):
    prefs = [{"item_code": k, "preference_state": v} for k, v in case["preferences"].items()]
    db = _make_db(case["candidates"], events=case["events"], preferences=prefs)
    ranked = asyncio.run(rank_interventions(db, limit=case["limit"], **case["context"]))
    assert [r["intervention_id"] for r in ranked] == case["expected_ids"]
