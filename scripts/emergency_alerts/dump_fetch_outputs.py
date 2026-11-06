#!/usr/bin/env python3
"""Dump every emergency-alert adapter's fetch() output for the committed feed
fixtures, fully offline, as deterministic JSON.

Used for the behavioural-equivalence check (USS-TJR-MSN integrity uplift): run
it against two checkouts (e.g. main and a branch) and diff the files.

    python scripts/emergency_alerts/dump_fetch_outputs.py --repo . --out /tmp/branch.json
    python scripts/emergency_alerts/dump_fetch_outputs.py --repo ../main-checkout --out /tmp/main.json
    diff /tmp/main.json /tmp/branch.json && echo IDENTICAL

Network is blocked: urllib.request.urlopen raises, and each adapter's own HTTP
helper is replaced by a lookup into tests/fixtures/emergency_alerts. cap_* keys
(added to CanonicalAlert later in the same mission) are dropped unless
--keep-cap is given, so a pre-cap checkout and a post-cap checkout compare equal.
"""

from __future__ import annotations

import argparse
import json
import sys
import types
import urllib.request
from dataclasses import asdict
from pathlib import Path

# Frozen "now" for tas_fire (it drops records already expired at the source):
# 2026-11-06T05:52:00Z, the moment the fixtures were captured.
FROZEN_NOW_S = 1793944320


def _load_fixtures(repo: Path) -> dict[str, dict[str, bytes]]:
    root = repo / "tests" / "fixtures" / "emergency_alerts"
    return {d.name: {f.name: f.read_bytes() for f in d.iterdir() if f.is_file()} for d in root.iterdir() if d.is_dir()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="checkout root to import adapters from")
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep-cap", action="store_true", help="keep cap_* keys in the output")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    sys.path.insert(0, str(repo))

    def _no_network(*a, **k):
        raise RuntimeError("network blocked: dump_fetch_outputs is offline")

    urllib.request.urlopen = _no_network  # type: ignore[assignment]

    from intelligence.ingestion.emergency_alert_adapters import (
        act_esa,
        base,
        bom_warnings,
        nsw_rfs,
        qld_fire,
        sa_cfs,
        tas_fire,
        vic_emergency,
        wa_dfes,
    )

    fx = _load_fixtures(repo)
    by_url: dict[str, bytes] = {
        nsw_rfs._FEED_URL: fx["nsw_rfs"]["feed.json"],
        qld_fire._FEED_URL: fx["qld_fire"]["feed.json"],
        act_esa._FEED_URL: fx["act_esa"]["feed.xml"],
        wa_dfes._WARNINGS_URL: fx["wa_dfes"]["warnings.xml"],
        wa_dfes._INCIDENTS_URL: fx["wa_dfes"]["incidents.xml"],
        vic_emergency._FEED_URL: fx["vic_emergency"]["incidents.json"],
        vic_emergency._WARNINGS_URL: fx["vic_emergency"]["warnings.json"],
        sa_cfs._FEED_URL: fx["sa_cfs"]["feed.xml"],
        tas_fire._LAYER_URL: fx["tas_fire"]["feed.json"],
        bom_warnings._STATE_FEEDS["NSW"][1]: fx["bom_nsw"]["feed.xml"],
    }
    detail_html = fx["bom_nsw"]["detail.html"]

    def fake_get(url: str, timeout: int = 20) -> bytes:
        if url in by_url:
            return by_url[url]
        raise RuntimeError(f"unexpected URL in offline dump: {url}")

    def fake_get_json(url: str, timeout: int = 20):
        return json.loads(fake_get(url, timeout))

    def fake_bom_get(url: str) -> bytes:
        return by_url.get(url, detail_html)

    base.http_get = fake_get
    base.http_get_json = fake_get_json
    for mod in (nsw_rfs, qld_fire, act_esa, wa_dfes, vic_emergency, sa_cfs, tas_fire):
        for name, fn in (("http_get", fake_get), ("http_get_json", fake_get_json)):
            if hasattr(mod, name):
                setattr(mod, name, fn)
    bom_warnings._http_get_bom = fake_bom_get
    bom_warnings._detail_cache.clear()
    tas_fire.time = types.SimpleNamespace(time=lambda: FROZEN_NOW_S)

    adapters = {
        "nsw_rfs": nsw_rfs, "qld_fire": qld_fire, "act_esa": act_esa, "wa_dfes": wa_dfes,
        "vic_emergency": vic_emergency, "sa_cfs": sa_cfs, "tas_fire": tas_fire, "bom_nsw": bom_warnings.nsw,
    }
    def dump(adapter) -> list[dict]:
        rows = []
        for alert in adapter.fetch():
            d = asdict(alert)
            if not args.keep_cap:
                d = {k: v for k, v in d.items() if not k.startswith("cap_")}
            rows.append(d)
        return rows

    out: dict[str, list[dict]] = {key: dump(adapter) for key, adapter in adapters.items()}

    # The live ACT snapshot is all (excluded) ambulance calls, so also run the
    # marked-synthetic kept-path supplement through the same fetch().
    live_act = by_url[act_esa._FEED_URL]
    by_url[act_esa._FEED_URL] = fx["act_esa"]["synthetic_kept.xml"]
    out["act_esa_synthetic"] = dump(act_esa)
    by_url[act_esa._FEED_URL] = live_act
    Path(args.out).write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print({k: len(v) for k, v in out.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
