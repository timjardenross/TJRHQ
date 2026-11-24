"""Run the longitudinal trend measures over a read-only export and write the JSON result and the weekly Trends markdown.

Offline only: reads a JSONL export (one row per report: id, source, geography, collected_at, published_at, title, summary, suppressed,
event_type, sector), never touches a database, and sets nothing live.

Usage:
  longitudinal_trends.py EXPORT.jsonl --window 2026-07-13 2026-11-16 --week 2026-11-16 --out DIR
                         [--data-start 2026-07-12] [--data-end 2026-11-24] [--generated-on 2026-11-24]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from intelligence import longitudinal_trends as lt
from intelligence import trends_product as tp


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return lt.events_from_rows(json.loads(line) for line in fh if line.strip())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export")
    ap.add_argument("--window", nargs=2, required=True, metavar=("FIRST_MONDAY", "LAST_MONDAY"))
    ap.add_argument("--week", required=True, help="Monday of the week the Trends product is written for")
    ap.add_argument("--out", required=True)
    ap.add_argument("--data-start", default="2026-07-12")
    ap.add_argument("--data-end", default="2026-11-24")
    ap.add_argument("--generated-on", default=None)
    ap.add_argument("--markdown-only-path", default=None, help="also write the markdown here (e.g. under docs/)")
    a = ap.parse_args(argv)
    events = load(a.export)
    res = lt.build_trends(events, window=tuple(a.window), data_start=a.data_start, data_end=a.data_end, force=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    slim = {k: v for k, v in res.items()}
    for basis in ("all", "constant"):
        slim[basis] = {k: v for k, v in res[basis].items() if k != "incidents"}
        (out / f"incidents_{basis}_{a.window[0]}_{a.window[1]}.json").write_text(json.dumps(res[basis]["incidents"], indent=1), encoding="utf-8")
    (out / f"trends_{a.window[0]}_{a.window[1]}.json").write_text(json.dumps(slim, indent=1, default=str), encoding="utf-8")
    md = tp.render_trends_markdown(res, week=a.week, generated_on=a.generated_on)
    (out / f"trends_{a.week}.md").write_text(md, encoding="utf-8")
    if a.markdown_only_path:
        Path(a.markdown_only_path).write_text(md, encoding="utf-8")
    print(f"events={len(events)} incidents_all={len(res['all']['incidents'])} incidents_constant={len(res['constant']['incidents'])} "
          f"emerging_all={len(res['all']['emerging'])} emerging_constant={len(res['constant']['emerging'])} "
          f"repeats_all={len(res['all']['repeats'])} repeats_constant={len(res['constant']['repeats'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
