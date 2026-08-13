#!/usr/bin/env python3
"""
Signal → Opportunity Converter (Phase 1C Communications)

Batch-creates comms_content opportunity rows from top-ranked content_signals.
Mirrors the stdlib PostgREST access pattern used by
intelligence/content_intelligence_service.py — no ORM, no third-party client.

Atomicity: all rows in a batch are sent to PostgREST as a single POST with a
JSON array body. Postgres executes a single INSERT statement for the whole
array, so it is atomic by construction — either every row lands or none do.
No client-side "rollback" step is needed or possible; a failed request simply
writes nothing.

Usage:
    from core.content.signal_opportunity_converter import create_opportunities_from_signals
    result = create_opportunities_from_signals(limit=5, min_rank_score=70.0, domain="health")
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional

log = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Default format per domain (COMMS-UI-REDESIGN-SPEC.md — Settings tab defaults)
DOMAIN_FORMAT_DEFAULT = {
    "health": "case_study",
    "operational": "executive_insight",
}


def _headers() -> dict:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get(path: str) -> list:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        log.warning("Supabase not configured — signal_opportunity_converter returning empty")
        return []
    url = f"{_SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        log.error("Supabase query failed (%s): %s", path, exc)
        return []


def _post_batch(table: str, rows: list) -> Optional[list]:
    """Insert multiple rows as a single atomic statement. Returns None on failure."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return None
    url = f"{_SUPABASE_URL}/rest/v1/{table}"
    headers = _headers()
    headers["Prefer"] = "return=representation"
    body = json.dumps(rows).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        log.error("Batch insert failed (%s): %s %s", table, exc.code, detail)
        return None
    except Exception as exc:
        log.error("Batch insert failed (%s): %s", table, exc)
        return None


def _log_batch_operation(result: dict) -> None:
    """Best-effort audit trail write to staff_autonomy_log. Never raises."""
    row = {
        "actor": "signal_opportunity_converter",
        "action": "batch_create_opportunities",
        "rationale": (
            f"Batch {result['status']}: {result['created']} of "
            f"{result['requested']} opportunities created "
            f"(domain={result['domain']!r}, min_rank_score={result['min_rank_score']})"
        ),
        "mission_ref": "MSN-1C-COMMS",
    }
    try:
        url = f"{_SUPABASE_URL}/rest/v1/staff_autonomy_log"
        req = urllib.request.Request(
            url, data=json.dumps(row).encode(), headers=_headers(), method="POST"
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as exc:
        log.warning("Audit log write failed (non-fatal): %s", exc)


def create_opportunities_from_signals(
    limit: int = 5,
    min_rank_score: float = 70.0,
    domain: Optional[str] = None,
) -> dict:
    """
    Create comms_content opportunities from top-ranked, non-suppressed content_signals.

    Args:
        limit: max opportunities to create (default 5)
        min_rank_score: only signals at or above this score are eligible.
            content_ranker.rank() returns a 0-100 scale score (real production
            distribution: min 36.6, median 66.8, p75 70.3, p90 79.6, max 94.9 —
            checked 2026-07-18). The previous default of 0.7 was a 0-1 scale
            value applied to a 0-100 scale column, so every signal trivially
            cleared it (1200/1200 signals passed) and the "top-ranked" filter
            was not filtering anything. 70.0 targets roughly the top quartile.
        domain: 'health', 'operational', or None for both

    Returns:
        {
            'status': 'completed' | 'failed' | 'no_signals',
            'requested': int,   # signals considered
            'created': int,     # rows actually written (0 unless status == 'completed')
            'domain': str | None,
            'min_rank_score': float,
            'opportunity_ids': list[str],
            'signal_ids': list[str],
            'error': str | None,
        }

    Transaction safety: all-or-nothing. If any candidate signal fails
    pre-flight validation, or the batch insert itself fails, zero rows are
    written and the whole batch is reported as failed.
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")

    domain_filter = ""
    if domain in ("health", "operational"):
        domain_filter = f"&domain=eq.{domain}"

    # 2026-08-13: was unwindowed — pure rank_score.desc lets a months-old
    # high-scoring signal outrank everything scored since, the same "stale
    # dominates forever" defect found in intelligence_events' own consumers.
    # Matches load_recent_events()'s 14-day default elsewhere in the platform.
    from datetime import datetime, timezone, timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()

    signals = _get(
        "content_signals"
        f"?rank_score=gte.{min_rank_score}"
        "&suppressed=eq.false"
        f"&scored_at=gte.{since}"
        f"{domain_filter}"
        "&order=rank_score.desc"
        f"&limit={limit}"
    )

    base_result = {
        "domain": domain,
        "min_rank_score": min_rank_score,
        "opportunity_ids": [],
        "signal_ids": [],
        "error": None,
    }

    if not signals:
        return {**base_result, "status": "no_signals", "requested": 0, "created": 0}

    rows = []
    signal_ids = []
    errors = []
    for signal in signals:
        title = signal.get("raw_title")
        event_id_text = signal.get("event_id_text")
        pillar_key = signal.get("pillar_key")
        signal_domain = signal.get("domain", "operational")

        if not title or not event_id_text:
            errors.append(f"signal {signal.get('id', '?')}: missing raw_title or event_id_text")
            continue

        rows.append({
            "title": title,
            "pillar": pillar_key,
            "source_kind": "signal",
            "source_ref": event_id_text,
            "signal_source_id": event_id_text,
            "classification": "publishable",
            "status": "opportunity",
            "format": DOMAIN_FORMAT_DEFAULT.get(signal_domain, "executive_insight"),
            "notes": signal.get("suggested_angle"),
        })
        signal_ids.append(event_id_text)

    if errors:
        # All-or-nothing: any invalid signal in the batch aborts the whole batch.
        result = {
            **base_result,
            "status": "failed",
            "requested": len(signals),
            "created": 0,
            "error": "; ".join(errors),
        }
        _log_batch_operation(result)
        return result

    created_rows = _post_batch("comms_content", rows)

    if created_rows is None:
        result = {
            **base_result,
            "status": "failed",
            "requested": len(signals),
            "created": 0,
            "signal_ids": signal_ids,
            "error": "batch insert failed — 0 opportunities created, entire batch rolled back",
        }
        _log_batch_operation(result)
        return result

    result = {
        **base_result,
        "status": "completed",
        "requested": len(signals),
        "created": len(created_rows),
        "signal_ids": signal_ids,
        "opportunity_ids": [row["id"] for row in created_rows if "id" in row],
    }
    _log_batch_operation(result)
    log.info(
        "signal_opportunity_converter: created %d/%d opportunities (domain=%s, min_rank_score=%s)",
        result["created"], result["requested"], domain, min_rank_score,
    )
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Batch-create comms opportunities from content_signals")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--min-rank-score", type=float, default=70.0)
    parser.add_argument("--domain", choices=["health", "operational"], default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    out = create_opportunities_from_signals(
        limit=args.limit, min_rank_score=args.min_rank_score, domain=args.domain
    )
    print(json.dumps(out, indent=2))
