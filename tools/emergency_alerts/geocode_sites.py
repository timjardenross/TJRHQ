"""Geocode the ANZ site list for the Emergency Alert Hub (migration 0240).

Reads the "ANZ Site List for Automation" workbook (stdlib-only xlsx parse —
no openpyxl dependency on the platform), geocodes each distinct address
against OpenStreetMap Nominatim, and writes a JSON file shaped like the
`alert_sites` table. `--load` then upserts that file into Supabase.

The workbook itself is NOT committed (internal site list); this script only
needs its path. Nominatim's usage policy applies: max 1 request/second, a
real User-Agent, and results cached — the cache file means a re-run only
geocodes addresses it has not seen, and the whole 494-site list is a
one-off job, not a recurring one.

Each result is checked before it is trusted. A hit is accepted only if its
state matches the site's state and it sits inside Australia; otherwise the
next, coarser attempt is tried. The coarseness actually achieved is stored
as `geocode_quality` so the matcher never treats a suburb centroid as if it
were a rooftop:

    address   Nominatim resolved a house number on the street
    street    resolved the street but not the number
    suburb    centroid of the suburb (+postcode/state)
    postcode  centroid of the postcode
    none      nothing usable — the site matches by text/state only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "USS-TJR-EmergencyAlertHub-SiteGeocoder/1.0 (one-off geocode of internal site list)"
_MIN_INTERVAL_S = 1.1  # Nominatim policy: at most 1 request/second

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_STATE_NAMES = {
    "new south wales": "NSW", "victoria": "VIC", "queensland": "QLD", "south australia": "SA",
    "western australia": "WA", "tasmania": "TAS", "northern territory": "NT",
    "australian capital territory": "ACT",
}
# Rough Australia bounding box — rejects a hit that landed overseas.
_AU_LAT = (-44.0, -9.0)
_AU_LON = (112.0, 154.0)

_UNIT_PART_RE = re.compile(r"^(shop|suite|level|lvl|unit|tenancy|kiosk|lot|ground|g\d|store)\b", re.I)
_VENUE_WORDS_RE = re.compile(r"\b(centre|center|plaza|mall|arcade|village|square|market|marketplace)\b", re.I)


def read_sites(xlsx_path: Path) -> list[dict]:
    """Parse the first worksheet into one dict per row, keyed by header."""
    with zipfile.ZipFile(xlsx_path) as z:
        shared = [
            "".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t"))
            for si in ET.fromstring(z.read("xl/sharedStrings.xml"))
        ]
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows: list[dict[str, str]] = []
    for r in sheet.iter(f"{{{_NS['m']}}}row"):
        cells: dict[str, str] = {}
        for c in r:
            col = re.match(r"[A-Z]+", c.get("r")).group()
            v = c.find("m:v", _NS)
            if v is None:
                continue
            cells[col] = shared[int(v.text)] if c.get("t") == "s" else v.text
        rows.append(cells)
    header = rows[0]
    out = []
    for cells in rows[1:]:
        rec = {header[col]: val.strip() for col, val in cells.items() if col in header}
        out.append(rec)
    return out


def clean_postcode(raw: str) -> str:
    """The workbook stores postcodes as numbers ("800.0"), which drops the
    leading zero on every NT postcode — restore 4 digits."""
    digits = re.sub(r"\D", "", raw.split(".")[0])
    return digits.zfill(4) if digits else ""


def street_only(address: str) -> str:
    """Drop shop/suite/level parts and shopping-centre names, keeping the
    street-number part: "The Broadway Shopping Centre, shop G11, 1 Bay
    Street" -> "1 Bay Street"."""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    keep = [
        p for p in parts
        if not _UNIT_PART_RE.match(p) and not (_VENUE_WORDS_RE.search(p) and not re.search(r"\d", p))
    ]
    with_digit = [p for p in keep if re.search(r"\d", p)]
    return (with_digit[-1] if with_digit else (keep[-1] if keep else address)).strip()


class Geocoder:
    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self.cache: dict[str, list | None] = {}
        if cache_path.exists():
            self.cache = json.loads(cache_path.read_text())
        self._last = 0.0

    def _query(self, params: dict) -> list[dict]:
        key = json.dumps(params, sort_keys=True)
        if key in self.cache:
            return self.cache[key] or []
        wait = _MIN_INTERVAL_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        url = f"{_NOMINATIM}?{urllib.parse.urlencode({**params, 'format': 'jsonv2', 'addressdetails': 1, 'countrycodes': 'au', 'limit': 1})}"
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310 - fixed https Nominatim endpoint, query params URL-encoded
                data = json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"  ! request failed ({exc}); not caching", file=sys.stderr)
            self._last = time.monotonic()
            return []
        self._last = time.monotonic()
        self.cache[key] = data
        self.cache_path.write_text(json.dumps(self.cache))
        return data

    @staticmethod
    def _accept(hit: dict, state: str) -> bool:
        try:
            lat, lon = float(hit["lat"]), float(hit["lon"])
        except (KeyError, ValueError):
            return False
        if not (_AU_LAT[0] <= lat <= _AU_LAT[1] and _AU_LON[0] <= lon <= _AU_LON[1]):
            return False
        got = _STATE_NAMES.get((hit.get("address", {}).get("state") or "").lower())
        # ACT results sometimes carry no state; only reject a clear mismatch.
        return got is None or got == state

    def geocode(self, site: dict) -> dict:
        street, suburb, state, pc = site["address"], site["suburb"], site["state"], site["postcode"]
        attempts = [
            ("structured", {"street": street_only(street), "city": suburb, "state": state, "postalcode": pc}),
            ("freetext", {"q": f"{street}, {suburb} {state} {pc}"}),
        ]
        for _, params in attempts:
            for hit in self._query(params):
                if not self._accept(hit, state):
                    continue
                addr = hit.get("address", {})
                if addr.get("house_number") and addr.get("road"):
                    quality = "address"
                elif addr.get("road"):
                    quality = "street"
                else:
                    break  # an area-level hit here is no better than the suburb attempt below
                return {"latitude": float(hit["lat"]), "longitude": float(hit["lon"]), "geocode_quality": quality}
        for quality, params in (
            ("suburb", {"city": suburb, "state": state, "postalcode": pc}),
            ("suburb", {"q": f"{suburb} {state} {pc}"}),
            ("postcode", {"postalcode": pc, "state": state}),
        ):
            for hit in self._query(params):
                if self._accept(hit, state):
                    return {"latitude": float(hit["lat"]), "longitude": float(hit["lon"]), "geocode_quality": quality}
        return {"latitude": None, "longitude": None, "geocode_quality": "none"}


def build(xlsx: Path, out: Path, cache: Path) -> list[dict]:
    raw = read_sites(xlsx)
    geo = Geocoder(cache)
    sites: list[dict] = []
    seen: dict[tuple, dict] = {}
    for i, r in enumerate(raw, 1):
        site = {
            "site_type": r["Site Type"],
            "name": r["Branch Name"],
            "classification": r.get("Branch Classification") or None,
            "address": r["Address"],
            "suburb": r["Suburb"],
            "state": r["State"],
            "postcode": clean_postcode(r["Post Code"]),
            "priority": r["Priority"],
        }
        addr_key = (site["address"].lower(), site["suburb"].lower(), site["state"], site["postcode"])
        if addr_key not in seen:
            seen[addr_key] = geo.geocode(site)
            g = seen[addr_key]
            print(f"[{i}/{len(raw)}] {site['name']}: {g['geocode_quality']}", flush=True)
        site.update(seen[addr_key])
        site["geocode_source"] = "nominatim" if site["geocode_quality"] != "none" else None
        sites.append(site)
    out.write_text(json.dumps(sites, indent=1))
    counts: dict[str, int] = {}
    for s in sites:
        counts[s["geocode_quality"]] = counts.get(s["geocode_quality"], 0) + 1
    print(f"wrote {len(sites)} sites to {out}: {counts}")
    return sites


def load(sites_json: Path) -> None:
    """Upsert the geocoded file into alert_sites (service-role key)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "core" / "platform"))
    from heartbeat import _KEY, _URL  # noqa: PLC0415

    if not _URL or not _KEY:
        raise SystemExit("Supabase credentials not configured")
    rows = json.loads(sites_json.read_text())
    url = f"{_URL.rstrip('/')}/rest/v1/alert_sites?on_conflict=name,address,site_type"
    for start in range(0, len(rows), 100):
        batch = rows[start:start + 100]
        req = urllib.request.Request(
            url, data=json.dumps(batch).encode(), method="POST",
            headers={
                "apikey": _KEY, "Authorization": f"Bearer {_KEY}", "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        with urllib.request.urlopen(req, timeout=30):  # nosec B310 - url built from SUPABASE_URL env var, https
            pass
        print(f"loaded {start + len(batch)}/{len(rows)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("geocode", help="xlsx -> geocoded JSON")
    g.add_argument("xlsx", type=Path)
    g.add_argument("--out", type=Path, required=True)
    g.add_argument("--cache", type=Path, required=True)
    l = sub.add_parser("load", help="geocoded JSON -> alert_sites")
    l.add_argument("sites_json", type=Path)
    args = ap.parse_args()
    if args.cmd == "geocode":
        build(args.xlsx, args.out, args.cache)
    else:
        load(args.sites_json)


if __name__ == "__main__":
    main()
