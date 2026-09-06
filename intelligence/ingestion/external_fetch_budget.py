"""
Shared hard-cap circuit breaker for paid external fetch-path APIs.

2026-08-10 (Captain-directed follow-up to the same night's Firecrawl +
Bright Data provisioning — see
.claude/skills/bot-reviews/fixes-2026-08-09/firecrawl-production-provisioning.md
and .../brightdata-provisioning.md). Both fetch paths
(intelligence/ingestion/firecrawl_client.py, .../brightdata_fetch.py) were
sized against their real monthly quota by MATH (projected call volume vs.
known cap) — not by anything that actually stops a call once a safe
ceiling is reached. This module is the real enforcement: an ENFORCED,
DB-backed hard cap that refuses further calls once a safe ceiling is hit
within the current billing cycle, regardless of what changes to
cadence/source count happen later (a new source added, a cron
misconfiguration, a retry-loop bug, etc.).

── What "real call" means here (billing-consumption verification) ─────────
Both clients call `check_and_increment()` immediately before the real
outbound HTTP request to their provider, and count it whether that request
ultimately succeeds or fails. This was verified per-provider rather than
assumed:

  - Firecrawl: the vendor's own docs claim failed requests aren't billed,
    but independently reported real-world experience says otherwise for
    mid-request failures (timeouts, render errors) — genuinely mixed
    signal, not a confirmed "failures are free" guarantee.
  - Bright Data Web Unlocker: default billing is success-only, EXCEPT that
    enabling any Custom Web Unlocker API feature (custom headers/cookies/
    expect-elements) flips billing to 100% of requests, success or
    failure. This module's caller (brightdata_fetch.py) doesn't currently
    enable those features, so today's real Bright Data usage is likely
    success-only-billed — but that's a zone-config detail that can change
    without this module knowing.

Given that ambiguity, this circuit breaker counts every real outbound
attempt for BOTH providers, uniformly. That is deliberately conservative,
never permissive: worst case it costs a little of the safety margin baked
into the ceiling below; it can never let real spend outrun what's counted.

── Fail-safe, not fail-open ────────────────────────────────────────────────
core/platform/infra_narrative.py established this codebase's rule for
exactly this situation: never treat an inability to observe real state as
evidence that the state is healthy (there, a verification-state read
failure is never narrated as "platform healthy"; here, a usage-check
failure is never treated as "must be under budget, go ahead"). If this
module cannot complete the atomic check-and-increment (Supabase
unreachable, credentials missing, RPC error), it raises — the SAME way it
raises when the ceiling is genuinely exceeded — rather than silently
letting the real call through unmetered. Both firecrawl_client.py and
brightdata_fetch.py let that exception propagate; they do not catch it and
retry unmetered.

That said, this module itself never crashes the scheduler: raising a clean
exception from here is caught by intelligence/ingestion/base_adapter.py's
`run()` (every adapter's collect() failure is captured into SourceHealth,
never propagated) and, one layer further out, by
intelligence/ingestion/collection_engine.py's per-source try/except in
`collect_all()`. This module relies on — and does not duplicate — that
existing two-layer safety net; it only needs to log clearly and raise.

── Ceilings (real headroom, not a number that only works if everything else
   about the projection stays perfect) ─────────────────────────────────────
  - Firecrawl:   cap 1,000/month (Free plan, hard) -> ceiling 850  (85%)
  - Bright Data: cap 5,000/month (Free tier)        -> ceiling 4,500 (90%)

Firecrawl gets a slightly larger safety margin (85% vs. 90%) because it's
shared across every Firecrawl caller on the Captain's account, including ad
hoc interactive `firecrawl` CLI use this module has no visibility into —
Bright Data's account is dedicated to this pipeline alone.

── Billing-cycle boundaries (provider-specific, NOT calendar-month) ────────
  - Firecrawl:   anchor day 9  -> e.g. 2026-08-09 .. 2026-09-09
  - Bright Data: anchor day 1  -> e.g. 2026-08-01 .. 2026-09-01
See `_cycle_bounds()` — computed from each provider's real anchor day, never
a generic "resets on the 1st" assumption.
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ─── Env loading (this module has no dependency on intelligence.config so
# it stays usable from anywhere, including tools/external_fetch_usage_check.py.
# 2026-08-29: migrated onto core/platform/configuration_service.py's
# load_dotenv_files() — see tools/check_config_loaders.py; that module has
# no heavy deps either, so this doesn't reintroduce the coupling being
# avoided.) ──────────────────────────────────────────────────────────────


def _load_dotenv() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from core.platform.configuration_service import load_dotenv_files

    load_dotenv_files([repo_root / ".env"])


_load_dotenv()

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
_RPC_ENDPOINT = "external_fetch_try_increment"


@dataclass(frozen=True)
class ProviderBudget:
    cap: int          # real vendor hard cap for the billing cycle
    ceiling: int       # safe ceiling this circuit breaker enforces (< cap)
    anchor_day: int    # day-of-month the billing cycle starts on


PROVIDERS: dict[str, ProviderBudget] = {
    "firecrawl":  ProviderBudget(cap=1000, ceiling=850,  anchor_day=9),
    "brightdata": ProviderBudget(cap=5000, ceiling=4500, anchor_day=1),
    # 2026-09-06: the second Firecrawl account (FIRECRAWL_API_KEY_2,
    # firecrawl_client.py's automatic failover target once the primary
    # account's ceiling is hit). Tracked as its own independent provider key
    # so usage against each account is counted separately — falling over to
    # key 2 must never borrow against key 1's already-exhausted budget.
    # Same Free-plan numbers assumed as key 1; anchor_day=9 is a placeholder
    # until the second account's real billing-cycle start date is confirmed
    # (it's a free plan, so this only affects which calendar dates the
    # cycle boundary falls on, not whether the cap is enforced).
    "firecrawl_2": ProviderBudget(cap=1000, ceiling=850, anchor_day=9),
}


class FetchBudgetExceeded(RuntimeError):
    """Raised when making this call would put the provider at/over its safe
    ceiling for the current billing cycle. Callers must NOT retry through
    an alternate path that still spends the same provider's quota."""


class FetchBudgetCheckFailed(RuntimeError):
    """Raised when the usage check itself could not be completed (Supabase
    unreachable, credentials missing, malformed RPC response, etc). Treated
    identically to FetchBudgetExceeded by callers — see module docstring's
    'fail-safe, not fail-open' section. This is a DIFFERENT exception class
    from FetchBudgetExceeded so a human reading logs/metrics can tell
    'refused, quota reached' apart from 'refused, couldn't even check' —
    but both mean the same thing to the caller: do not make the real call."""


def _clamped_date(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _cycle_bounds(today: date, anchor_day: int) -> tuple[date, date]:
    """Return (cycle_start, cycle_end) for the billing cycle containing
    `today`, running from `anchor_day` of one month to `anchor_day` of the
    next (clamped to the last real day of a short month). Provider-specific
    anchor day, not a generic "resets on the 1st" assumption — e.g. with
    anchor_day=9 and today=2026-08-10, returns
    (2026-08-09, 2026-09-09)."""
    if today.day >= anchor_day:
        start = _clamped_date(today.year, today.month, anchor_day)
    else:
        prev_month = today.month - 1 or 12
        prev_year = today.year - 1 if today.month == 1 else today.year
        start = _clamped_date(prev_year, prev_month, anchor_day)

    end_month = start.month + 1
    end_year = start.year + (1 if end_month > 12 else 0)
    end_month = end_month if end_month <= 12 else 1
    end = _clamped_date(end_year, end_month, anchor_day)

    return start, end


def _rpc_try_increment(provider: str, cycle_start: date, cycle_end: date, ceiling: int, timeout: int) -> tuple[bool, int]:
    """POST the atomic check-and-increment RPC. Raises on any failure to
    reach/parse Supabase — never guesses at a result."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise FetchBudgetCheckFailed(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured — cannot "
            "verify external_fetch_usage, refusing the call rather than "
            "assuming it's safe (fail-safe, not fail-open)"
        )

    url = f"{_SUPABASE_URL.rstrip('/')}/rest/v1/rpc/{_RPC_ENDPOINT}"
    payload = json.dumps({
        "p_provider": provider,
        "p_billing_cycle_start": cycle_start.isoformat(),
        "p_billing_cycle_end": cycle_end.isoformat(),
        "p_ceiling": ceiling,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "apikey": _SUPABASE_KEY,
            "Authorization": f"Bearer {_SUPABASE_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise FetchBudgetCheckFailed(
            f"external_fetch_try_increment RPC HTTP {exc.code} for provider={provider}: {detail}"
        ) from exc
    except Exception as exc:
        raise FetchBudgetCheckFailed(
            f"external_fetch_try_increment RPC failed for provider={provider}: {exc}"
        ) from exc

    if not body or not isinstance(body, list) or "allowed" not in body[0]:
        raise FetchBudgetCheckFailed(
            f"external_fetch_try_increment RPC returned an unexpected shape for "
            f"provider={provider}: {body!r}"
        )

    row = body[0]
    # RPC's returned column is named result_call_count, not call_count — the
    # RETURNS TABLE(...) OUT parameter would otherwise shadow the
    # external_fetch_usage.call_count column inside the function body and
    # make every bare reference to it ambiguous (hit this live on the first
    # real RPC call: PostgREST HTTP 400 "column reference call_count is
    # ambiguous" — see migration external_fetch_try_increment_fix_ambiguous_column_v2).
    return bool(row["allowed"]), int(row["result_call_count"])


def check_and_increment(provider: str, *, today: Optional[date] = None, timeout: int = 10) -> int:
    """
    MUST be called immediately before the real outbound HTTP request to
    `provider` ("firecrawl" or "brightdata") — atomically checks current
    billing-cycle usage against that provider's safe ceiling and, if under
    it, increments the counter for the call about to be made.

    Returns the new call_count (post-increment) if the call is allowed.

    Raises FetchBudgetExceeded if the safe ceiling would be reached/exceeded.
    Raises FetchBudgetCheckFailed if the check itself could not be completed.
    Both are RuntimeError subclasses; a caller that only wants "should I
    make the real call?" can catch RuntimeError as one refusal signal.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown external-fetch provider: {provider!r} (known: {sorted(PROVIDERS)})")

    budget = PROVIDERS[provider]
    cycle_start, cycle_end = _cycle_bounds(today or date.today(), budget.anchor_day)

    allowed, call_count = _rpc_try_increment(provider, cycle_start, cycle_end, budget.ceiling, timeout)

    if not allowed:
        log.error(
            "[external-fetch-budget] REFUSED: %s at %d/%d calls for billing cycle "
            "%s..%s (safe ceiling reached, real vendor cap is %d) — this call will "
            "NOT be made.",
            provider, call_count, budget.ceiling, cycle_start, cycle_end, budget.cap,
        )
        raise FetchBudgetExceeded(
            f"{provider} has reached its safe ceiling ({budget.ceiling}/{budget.cap} real "
            f"cap) for billing cycle {cycle_start}..{cycle_end} — refusing this call"
        )

    if call_count >= int(budget.ceiling * 0.9):
        log.warning(
            "[external-fetch-budget] %s approaching safe ceiling: %d/%d for billing "
            "cycle %s..%s",
            provider, call_count, budget.ceiling, cycle_start, cycle_end,
        )
    else:
        log.info(
            "[external-fetch-budget] %s call permitted: %d/%d for billing cycle %s..%s",
            provider, call_count, budget.ceiling, cycle_start, cycle_end,
        )

    return call_count


def current_usage(provider: str, *, today: Optional[date] = None, timeout: int = 10) -> dict:
    """Read-only current-cycle usage lookup — does NOT increment. Used by
    tools/external_fetch_usage_check.py. Raises FetchBudgetCheckFailed on
    any read failure (no silent zero — an unreadable count must never be
    displayed as "0 used, plenty of headroom")."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown external-fetch provider: {provider!r} (known: {sorted(PROVIDERS)})")
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise FetchBudgetCheckFailed(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured"
        )

    budget = PROVIDERS[provider]
    cycle_start, cycle_end = _cycle_bounds(today or date.today(), budget.anchor_day)

    url = (
        f"{_SUPABASE_URL.rstrip('/')}/rest/v1/external_fetch_usage"
        f"?provider=eq.{provider}&billing_cycle_start=eq.{cycle_start.isoformat()}"
        f"&select=call_count,billing_cycle_start,billing_cycle_end,updated_at"
    )
    req = urllib.request.Request(
        url,
        headers={
            "apikey": _SUPABASE_KEY,
            "Authorization": f"Bearer {_SUPABASE_KEY}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rows = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        raise FetchBudgetCheckFailed(f"Failed to read external_fetch_usage for {provider}: {exc}") from exc

    call_count = int(rows[0]["call_count"]) if rows else 0
    return {
        "provider": provider,
        "billing_cycle_start": cycle_start.isoformat(),
        "billing_cycle_end": cycle_end.isoformat(),
        "call_count": call_count,
        "ceiling": budget.ceiling,
        "cap": budget.cap,
        "headroom": budget.ceiling - call_count,
        "pct_of_ceiling": round(100 * call_count / budget.ceiling, 1) if budget.ceiling else None,
        "updated_at": rows[0].get("updated_at") if rows else None,
    }
