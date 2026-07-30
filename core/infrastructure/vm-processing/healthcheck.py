#!/usr/bin/env python3
"""VM Knowledge Processing Engine health check — USS-TJR-MSN-0207A.

Standalone script and importable module: produces a JSON health report for
the document-processing pipeline without duplicating any of worker.py's
query logic — it calls the worker's existing read methods
(`status_summary()`, `list_failed()`) and derives thresholds from their
output. This is the observability half of "no Captain involvement needed
for normal operations": a human can run it interactively, or a systemd
timer (systemd/vm-processing-healthcheck.timer) can run it unattended and
alert on a non-zero exit.

Threshold defaults (overridable via config.yaml's `healthcheck:` section or
CLI flags — CLI wins over config, config wins over the built-in default):

- `permanently_failed_threshold` (default **0**): any `permanently_failed`
  document means the bounded retry sweep has already given up on it and a
  human decision (`worker.py override`) is now the only path forward — so
  even a single one is worth flagging rather than letting it sit silently.
  A default of 0 with the ">" comparison below means exactly that: 1
  permanently-failed document is already enough to report `healthy: false`.
- `failed_threshold` (default 5): a handful of `failed` documents is
  normal churn that the next retry-sweep timer run will pick up; a bigger
  pile suggests something systemic (model router down, OCR binary broken)
  rather than isolated per-document failures, so it crosses into
  `healthy: false` territory.

`healthy` is False if either count is strictly greater than its threshold
— `failed_threshold`'s default (5) deliberately tolerates a small amount
of expected churn; `permanently_failed_threshold`'s default (0) does not,
by design (see above).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from config import load_config  # noqa: E402
from supabase_client import SupabaseClient  # noqa: E402
from model_router_client import ModelRouterClient  # noqa: E402
from worker import ProcessingWorker  # noqa: E402

DEFAULT_CONFIG = _HERE / "config.yaml"

DEFAULT_PERMANENTLY_FAILED_THRESHOLD = 0
DEFAULT_FAILED_THRESHOLD = 5


@dataclass
class HealthThresholds:
    permanently_failed_threshold: int = DEFAULT_PERMANENTLY_FAILED_THRESHOLD
    failed_threshold: int = DEFAULT_FAILED_THRESHOLD


def compute_health(status_counts: dict, failed_rows: list, thresholds: HealthThresholds) -> dict:
    """Pure function over already-fetched data — no I/O — so tests can
    exercise the threshold logic directly against FakeSupabase-backed
    worker output without any config/env setup."""
    failed_count = sum(1 for row in failed_rows if row["status"] == "failed")
    permanently_failed_count = sum(1 for row in failed_rows if row["status"] == "permanently_failed")
    retry_eligible_count = _retry_eligible_count(failed_rows)

    healthy = (
        permanently_failed_count <= thresholds.permanently_failed_threshold
        and failed_count <= thresholds.failed_threshold
    )

    return {
        "status_counts": dict(status_counts),
        "failed_count": failed_count,
        "permanently_failed_count": permanently_failed_count,
        "retry_eligible_count": retry_eligible_count,
        "thresholds": {
            "permanently_failed_threshold": thresholds.permanently_failed_threshold,
            "failed_threshold": thresholds.failed_threshold,
        },
        "healthy": healthy,
    }


def _retry_eligible_count(failed_rows: list) -> int:
    """`retry_eligible_count`: `failed` documents whose retry_count hasn't
    exhausted them yet. list_failed() doesn't carry max_retries on each row
    (it's a config value, not per-document state), so this counts `failed`
    documents where the document itself hasn't already been moved to
    `permanently_failed` — i.e. every row still in plain `failed` status is
    by definition still under the cap (retry() moves it to
    permanently_failed the moment it isn't)."""
    return sum(1 for row in failed_rows if row["status"] == "failed")


def run_healthcheck(worker: ProcessingWorker, thresholds: HealthThresholds) -> dict:
    status_counts = worker.status_summary()
    failed_rows = worker.list_failed()
    return compute_health(status_counts, failed_rows, thresholds)


def _build_worker(config_path) -> ProcessingWorker:
    config = load_config(config_path)
    db = SupabaseClient(config.supabase.url, config.supabase.service_role_key)
    model_router = ModelRouterClient(config.model_router.url, config.model_router.timeout_seconds)
    return ProcessingWorker(config, db, model_router)


def _load_thresholds(config_path: str, args: argparse.Namespace) -> HealthThresholds:
    thresholds = HealthThresholds()
    try:
        import yaml
        raw = yaml.safe_load(Path(config_path).expanduser().read_text()) or {}
        hc_raw = raw.get("healthcheck", {})
        thresholds.permanently_failed_threshold = int(
            hc_raw.get("permanently_failed_threshold", thresholds.permanently_failed_threshold)
        )
        thresholds.failed_threshold = int(hc_raw.get("failed_threshold", thresholds.failed_threshold))
    except FileNotFoundError:
        pass  # config.yaml is optional here — CLI flags/defaults still apply

    if args.permanently_failed_threshold is not None:
        thresholds.permanently_failed_threshold = args.permanently_failed_threshold
    if args.failed_threshold is not None:
        thresholds.failed_threshold = args.failed_threshold
    return thresholds


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="USS-TJR-MSN-0207A VM Knowledge Processing health check")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--permanently-failed-threshold", type=int, default=None,
                         help=f"override config.yaml healthcheck.permanently_failed_threshold "
                              f"(built-in default {DEFAULT_PERMANENTLY_FAILED_THRESHOLD})")
    parser.add_argument("--failed-threshold", type=int, default=None,
                         help=f"override config.yaml healthcheck.failed_threshold "
                              f"(built-in default {DEFAULT_FAILED_THRESHOLD})")
    return parser


def _record_heartbeat(status: str, detail: str = None, error_message: str = None) -> None:
    """STARSHIP-REDESIGN.md §4.1: internal jobs are domains too. Best-effort."""
    try:
        repo_root = _HERE.parents[2]  # .../vm-processing -> infrastructure -> core -> repo root
        sys.path.insert(0, str(repo_root / "core" / "platform"))
        from heartbeat import record_heartbeat
        record_heartbeat("knowledge_library", status=status, detail=detail, error_message=error_message)
    except Exception:
        pass


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    thresholds = _load_thresholds(args.config, args)
    worker = _build_worker(args.config)
    report = run_healthcheck(worker, thresholds)
    print(json.dumps(report, indent=2))
    if report["healthy"]:
        _record_heartbeat("ok", detail=f"failed={report['failed_count']} permanently_failed={report['permanently_failed_count']}")
        return 0
    _record_heartbeat(
        "failed",
        error_message=f"failed={report['failed_count']} permanently_failed={report['permanently_failed_count']}",
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
