#!/usr/bin/env python3
"""Secure File Transfer to VM CLI — USS-TJR-MSN-0205B.

Moves eligible files from a Mac Collector Agent (MSN-0205A) manifest to
the VM's inbox via rsync-over-SSH, verifies checksums, and reconciles
inbox/pending -> inbox/received (OK) or inbox/failed (mismatch/error).
Does not parse, OCR, or ingest anything — transfer only.

Usage:
    cli.py transfer --manifest manifest.json [--config config.yaml]
    cli.py transfer-dry-run --manifest manifest.json [--config config.yaml]
    cli.py verify-transfer [--status transferred] [--config config.yaml]
    cli.py retry-failed [--max-attempts N] [--config config.yaml]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from config import load_config  # noqa: E402
from transfer_db import TransferDB  # noqa: E402
from remote import RemoteTransport  # noqa: E402
from engine import TransferEngine  # noqa: E402

DEFAULT_CONFIG = _HERE / "config.yaml"


def _print(data, fmt: str):
    if fmt == "json":
        print(json.dumps(data, indent=2, default=str))
    else:
        print(data)


def _build_engine(config_path):
    config = load_config(config_path)
    db = TransferDB(config.db_path)
    transport = RemoteTransport(config.remote)
    return config, db, TransferEngine(config, db, transport)


def cmd_transfer(args) -> int:
    config, db, engine = _build_engine(args.config)
    try:
        summary = engine.run_transfer(args.manifest, dry_run=False)
    finally:
        db.close()
    _print(summary.as_dict(), args.format)
    return 1 if summary.failed_count else 0


def cmd_transfer_dry_run(args) -> int:
    config, db, engine = _build_engine(args.config)
    try:
        summary = engine.run_transfer(args.manifest, dry_run=True)
    finally:
        db.close()
    print("DRY RUN — no files were transferred and no state was persisted.", file=sys.stderr)
    _print(summary.as_dict(), args.format)
    return 0


def cmd_verify_transfer(args) -> int:
    config, db, engine = _build_engine(args.config)
    try:
        summary = engine.verify_transfer(status=args.status)
    finally:
        db.close()
    _print(summary.as_dict(), args.format)
    return 1 if summary.failed_count else 0


def cmd_retry_failed(args) -> int:
    config, db, engine = _build_engine(args.config)
    try:
        summary = engine.retry_failed(max_attempts=args.max_attempts)
    finally:
        db.close()
    _print(summary.as_dict(), args.format)
    return 1 if summary.failed_count else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="USS-TJR-MSN-0205B Secure File Transfer to VM")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG),
                         help="Path to config.yaml (default: config.yaml next to this script)")
    parser.add_argument("--format", default="json", choices=["json", "text"])
    sub = parser.add_subparsers(dest="command", required=True)

    p_transfer = sub.add_parser("transfer", help="Transfer eligible files from a manifest to the VM")
    p_transfer.add_argument("--manifest", required=True,
                             help="Path to a manifest.json from mac-collector's export-manifest")
    p_transfer.set_defaults(func=cmd_transfer)

    p_dry = sub.add_parser("transfer-dry-run",
                            help="Preview a transfer (rsync --dry-run) without persisting or moving anything")
    p_dry.add_argument("--manifest", required=True)
    p_dry.set_defaults(func=cmd_transfer_dry_run)

    p_verify = sub.add_parser("verify-transfer",
                               help="Resume checksum verification + move for an interrupted transfer")
    p_verify.add_argument("--status", default="transferred",
                           help="files_state status to re-verify (default: transferred)")
    p_verify.set_defaults(func=cmd_verify_transfer)

    p_retry = sub.add_parser("retry-failed", help="Retry files currently marked failed")
    p_retry.add_argument("--max-attempts", type=int, default=None,
                          help="Override retry.max_attempts from config")
    p_retry.set_defaults(func=cmd_retry_failed)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
