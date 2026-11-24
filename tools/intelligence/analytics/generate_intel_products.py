"""Initial / on-demand generation of the intelligence products (safe, idempotent, default OFF).

Dry run (no database write; writes the previewable product files):
    python tools/intelligence/analytics/generate_intel_products.py --enable --dry-run --out-dir /tmp/intel-products-preview

From exported files (offline):
    python tools/intelligence/analytics/generate_intel_products.py --enable --dry-run --status status.jsonl --context context.jsonl --out-dir out

Live generation (read-only SELECTs, then ONE idempotent upsert per product keyed by (product_key, generated_for); rerun the same day overwrites,
never duplicates; needs the intelligence_products table to exist):
    python tools/intelligence/analytics/generate_intel_products.py --enable

Without --dry-run and without --status/--context the command reads the database using SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY. No LLM,
no Firecrawl, no network other than that Supabase read/upsert.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))

import intel_products as ip
from analytics_common import parse_ts
from product_common import load_rows, require_enabled


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--enable", action="store_true")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="never write to the database; write preview files to --out-dir",
    )
    ap.add_argument("--out-dir", default=None)
    ap.add_argument(
        "--status",
        action="append",
        help="status-feed export (.jsonl/.gz); with --context, skips the database",
    )
    ap.add_argument("--context", action="append")
    ap.add_argument("--as-of", default=None)
    args = ap.parse_args(argv)
    if not require_enabled(args.enable):
        return 2
    as_of = parse_ts(
        args.as_of if not args.as_of or "T" in args.as_of else args.as_of + "T06:00:00Z"
    ) or datetime.now(timezone.utc)
    if args.status or args.context:
        status, context = load_rows(args.status or []), load_rows(args.context or [])
        products = ip.build_products(
            status, context, as_of, "export files given on the command line"
        )
        records = None
    else:
        from intelligence import intel_products_job as job

        if args.dry_run:
            written = []
            products = job.run(as_of, writer=written.append, force=True)
            records = written
        else:
            products = job.run(as_of, force=True)
            records = None
    if args.dry_run or args.out_dir:
        out = Path(args.out_dir or ".")
        out.mkdir(parents=True, exist_ok=True)
        day = as_of.date().isoformat()
        slim = [{k: v for k, v in p.items() if k != "body_md"} for p in products]
        (out / f"portal-product-records-{day}.json").write_text(
            json.dumps(slim, indent=1, default=str), encoding="utf-8"
        )
        for p in products:
            (out / f"{p['product_key']}-{day}.md").write_text(
                p["body_md"], encoding="utf-8"
            )
        print(
            f"wrote {len(products)} products to {out} (dry-run={args.dry_run}; database writes: {0 if args.dry_run or records is not None else len(products)})"
        )
    else:
        print(f"upserted {len(products)} products for {as_of.date().isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
