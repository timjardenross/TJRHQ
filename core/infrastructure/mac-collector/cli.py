#!/usr/bin/env python3
"""Mac File Collector Agent CLI — USS-TJR-MSN-0205A.

Scans configured OneDrive / iCloud Drive local sync folders, fingerprints
files with SHA256, applies ignore rules, tracks new/changed/deleted files
in a local SQLite DB, and exports a manifest of eligible files for secure
transfer to the VM. Does not perform the transfer itself.

Usage:
    cli.py scan [--config config.yaml] [--source NAME ...] [--dry-run]
    cli.py status [--config config.yaml]
    cli.py list-new [--config config.yaml] [--scan-id N]
    cli.py list-changed [--config config.yaml] [--scan-id N]
    cli.py export-manifest [--config config.yaml] [--output PATH] [--source NAME ...]
                            [--include-path PATH ...] [--exclude-path PATH ...]
                            [--max-files N] [--max-total-bytes N]
                            [--allow-ext EXT ...] [--allow-scoliosis-images]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from config import load_config  # noqa: E402
from db import TrackingDB  # noqa: E402
from collector import Collector  # noqa: E402
from path_filters import PathFilter  # noqa: E402
from manifest_guards import ExtensionFilter, check_hard_stops  # noqa: E402

DEFAULT_CONFIG = _HERE / "config.yaml"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _print(data, fmt: str):
    if fmt == "json":
        print(json.dumps(data, indent=2, default=str))
    else:
        print(data)


def cmd_scan(args) -> int:
    config = load_config(args.config)
    collector = Collector(config)
    with TrackingDB(config.db_path) as db:
        result = collector.scan(db, source_names=args.source, dry_run=args.dry_run)

    payload = {
        "dry_run": result.dry_run,
        "scan_id": None if result.dry_run else result.scan_id,
        "files_scanned": result.files_scanned,
        "ignored_count": result.ignored_count,
        "cloud_only_count": result.cloud_only_count,
        "unavailable_count": result.unavailable_count,
        "new_count": len(result.new_files),
        "changed_count": len(result.changed_files),
        "deleted_count": len(result.deleted_files),
        "errors": result.errors,
        "new_files": result.new_files,
        "changed_files": result.changed_files,
        "deleted_files": result.deleted_files,
        "cloud_only_files": result.cloud_only_files,
        "unavailable_files": result.unavailable_files,
    }
    if result.dry_run:
        print("DRY RUN — no changes were persisted to the tracking database.", file=sys.stderr)
    if result.cloud_only_count:
        print(f"{result.cloud_only_count} cloud-only files skipped (not locally available) — "
              f"see cloud_only_files in output.", file=sys.stderr)
    if result.unavailable_count:
        print(f"{result.unavailable_count} unavailable files skipped (stat failed) — "
              f"see unavailable_files in output.", file=sys.stderr)
    _print(payload, args.format)
    return 1 if result.errors else 0


def cmd_status(args) -> int:
    config = load_config(args.config)
    with TrackingDB(config.db_path) as db:
        summary = db.summary()
    _print(summary, args.format)
    return 0


def _resolve_scan_id(db: TrackingDB, scan_id_arg):
    if scan_id_arg is not None:
        return scan_id_arg
    latest = db.latest_scan()
    return latest["id"] if latest else None


def cmd_list_new(args) -> int:
    config = load_config(args.config)
    with TrackingDB(config.db_path) as db:
        scan_id = _resolve_scan_id(db, args.scan_id)
        if scan_id is None:
            _print({"scan_id": None, "files": []}, args.format)
            return 0
        rows = db.changes_for_scan(scan_id, "new")
        files = [dict(r) for r in rows]
    _print({"scan_id": scan_id, "files": files}, args.format)
    return 0


def cmd_list_changed(args) -> int:
    config = load_config(args.config)
    with TrackingDB(config.db_path) as db:
        scan_id = _resolve_scan_id(db, args.scan_id)
        if scan_id is None:
            _print({"scan_id": None, "files": []}, args.format)
            return 0
        rows = db.changes_for_scan(scan_id, "changed")
        files = [dict(r) for r in rows]
    _print({"scan_id": scan_id, "files": files}, args.format)
    return 0


def cmd_export_manifest(args) -> int:
    config = load_config(args.config)
    with TrackingDB(config.db_path) as db:
        rows = []
        if args.source:
            for name in args.source:
                rows.extend(db.active_files(source_name=name))
        else:
            rows = db.active_files()

    path_filter = PathFilter(include=args.include_path, exclude=args.exclude_path)
    ext_filter = ExtensionFilter(allow=args.allow_ext)

    source_roots = {s.name: s.path for s in config.sources}
    files = []
    excluded_files = []
    excluded_by_path = 0
    excluded_by_ext = 0
    for r in rows:
        root = source_roots.get(r["source_name"])
        abs_path = str(root / r["rel_path"]) if root else None
        entry = {
            "source": r["source_name"],
            "rel_path": r["rel_path"],
            "abs_path": abs_path,
            "sha256": r["sha256"],
            "size_bytes": r["size_bytes"],
            "mtime": r["mtime"],
        }

        path_decision = path_filter.decide(r["rel_path"])
        if not path_decision.included:
            excluded_files.append({**entry, "reason": path_decision.reason})
            excluded_by_path += 1
            continue

        ext_decision = ext_filter.decide(r["rel_path"])
        if not ext_decision.included:
            excluded_files.append({**entry, "reason": ext_decision.reason})
            excluded_by_ext += 1
            continue

        files.append(entry)

    hard_stops = check_hard_stops(
        files,
        max_files=args.max_files,
        max_total_bytes=args.max_total_bytes,
        allow_scoliosis_images=args.allow_scoliosis_images,
    )

    if hard_stops.stopped:
        for v in hard_stops.violations:
            print(f"HARD STOP: {v}", file=sys.stderr)
        print("Manifest NOT written — resolve the hard stop(s) above "
              "(adjust --include-path/--exclude-path/--max-files/--max-total-bytes, "
              "or pass the matching --allow-* flag if this is genuinely intended) and re-run.",
              file=sys.stderr)
        _print({
            "output": None,
            "hard_stopped": True,
            "violations": hard_stops.violations,
            "file_count": len(files),
            "total_size_bytes": sum(f["size_bytes"] for f in files),
        }, args.format)
        return 1

    manifest = {
        "generated_at": _now(),
        "config_path": str(config.config_path),
        "include_path": args.include_path,
        "exclude_path": args.exclude_path,
        "allow_ext": args.allow_ext,
        "allow_scoliosis_images": args.allow_scoliosis_images,
        "max_files": args.max_files,
        "max_total_bytes": args.max_total_bytes,
        "file_count": len(files),
        "total_size_bytes": sum(f["size_bytes"] for f in files),
        "excluded_by_path_filter_count": excluded_by_path,
        "excluded_by_extension_filter_count": excluded_by_ext,
        "files": files,
    }

    if args.output:
        output_path = Path(args.output).expanduser()
    else:
        config.manifest_dir.mkdir(parents=True, exist_ok=True)
        stamp = _now().replace(":", "").replace("-", "").split(".")[0]
        output_path = config.manifest_dir / f"manifest-{stamp}.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, default=str))

    print(f"Manifest written: {output_path} ({len(files)} files, "
          f"{manifest['total_size_bytes']} bytes, "
          f"{excluded_by_path} excluded by path filter, "
          f"{excluded_by_ext} excluded by extension filter)", file=sys.stderr)
    _print({"output": str(output_path), "file_count": len(files),
            "total_size_bytes": manifest["total_size_bytes"],
            "excluded_by_path_filter_count": excluded_by_path,
            "excluded_by_extension_filter_count": excluded_by_ext}, args.format)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="USS-TJR-MSN-0205A Mac File Collector Agent")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG),
                         help="Path to config.yaml (default: config.yaml next to this script)")
    parser.add_argument("--format", default="json", choices=["json", "text"])
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan configured sources and update the tracking DB")
    p_scan.add_argument("--source", action="append", default=None,
                         help="Limit scan to this source name (repeatable)")
    p_scan.add_argument("--dry-run", action="store_true",
                         help="Compute the diff but do not persist changes")
    p_scan.set_defaults(func=cmd_scan)

    p_status = sub.add_parser("status", help="Show tracking DB summary")
    p_status.set_defaults(func=cmd_status)

    p_list_new = sub.add_parser("list-new", help="List files marked new in a scan")
    p_list_new.add_argument("--scan-id", type=int, default=None,
                             help="Scan id (default: latest completed scan)")
    p_list_new.set_defaults(func=cmd_list_new)

    p_list_changed = sub.add_parser("list-changed", help="List files marked changed in a scan")
    p_list_changed.add_argument("--scan-id", type=int, default=None,
                                 help="Scan id (default: latest completed scan)")
    p_list_changed.set_defaults(func=cmd_list_changed)

    p_manifest = sub.add_parser("export-manifest",
                                 help="Export a manifest of eligible files for VM transfer")
    p_manifest.add_argument("--output", default=None, help="Output file path")
    p_manifest.add_argument("--source", action="append", default=None,
                             help="Limit manifest to this source name (repeatable)")
    p_manifest.add_argument("--include-path", action="append", default=None,
                             help="Only include files under this folder/path (repeatable). "
                                  "Matched by path component prefix against rel_path, e.g. "
                                  "'Operational Resilience/'. If omitted, all folders pass.")
    p_manifest.add_argument("--exclude-path", action="append", default=None,
                             help="Exclude files under this folder/path or matching this glob "
                                  "(repeatable), e.g. 'Scoliosis Images/' or '*.mp4'. "
                                  "Evaluated after --include-path and always wins.")
    p_manifest.add_argument("--max-files", type=int, default=None,
                             help="Hard stop (refuse to write the manifest) if more than this "
                                  "many files would be included (USS-TJR-MSN-0208).")
    p_manifest.add_argument("--max-total-bytes", type=int, default=None,
                             help="Hard stop (refuse to write the manifest) if the total size "
                                  "of included files would exceed this many bytes "
                                  "(USS-TJR-MSN-0208).")
    p_manifest.add_argument("--allow-ext", action="append", default=None,
                             help="Explicitly allow this file extension (repeatable, e.g. "
                                  "'.jpg' or 'jpg') in addition to the default include list "
                                  "(.pdf/.docx/.txt/.md/.csv/.xlsx/.xls). Without this, files "
                                  "with any other extension — including the default-blocked "
                                  ".jpg/.jpeg/.png/.heic/.mp4/.mov/.epub/.mobi — are excluded.")
    p_manifest.add_argument("--allow-scoliosis-images", action="store_true",
                             help="Explicitly allow files under a 'Scoliosis Images' folder to "
                                  "be included. Without this, their presence in the final "
                                  "candidate list is a hard stop, regardless of how they got "
                                  "there (e.g. no --include-path given at all).")
    p_manifest.set_defaults(func=cmd_export_manifest)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
