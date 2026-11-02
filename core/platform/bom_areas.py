"""Match a BOM warning to our sites by the area it names.

BOM warnings name districts and catchments, not places, and the site matcher
(site_matching.py) cannot place them. BOM publishes those boundaries; which of
them each site sits inside is computed offline by
tools/emergency_alerts/bom_site_areas.py into data/bom_site_areas.json.

Three outcomes, never blended:
  matched     the headline names areas we know and at least one site is inside.
  none_inside the headline names areas we know and no site is inside them.
  unparsed    the headline names nothing we can resolve (a council-area warning,
              a cyclone track map...). Say so; do not call it "not affected".
A site missing from the data file is counted in `unknown_sites`: its area is not
known, which is not the same as "outside".

Keep in step with lcars-portal/src/lib/bomAreas.ts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data" / "bom_site_areas.json"
_STATES = ("NSW", "VIC", "QLD", "WA", "SA", "TAS", "NT", "ACT")
_NSW_ACT = {"NSW", "ACT"}  # BOM's NSW feed carries the ACT too


@dataclass
class AreaResult:
    kind: str  # matched | none_inside | unparsed
    area_names: list[str] = field(default_factory=list)
    sites: list[dict] = field(default_factory=list)
    unknown_sites: int = 0


@lru_cache(maxsize=1)
def load_areas() -> dict:
    try:
        return json.loads(_DATA.read_text())
    except (OSError, ValueError):
        return {"areas": {}, "sites": {}}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _split_names(text: str) -> list[str]:
    """The whole phrase first ("Wide Bay and Burnett" is ONE district), then its
    parts for a list like "East Gippsland and North East"."""
    whole = re.sub(r"(?i)^the\s+", "", text.strip().rstrip("."))
    parts = [re.sub(r"(?i)^the\s+", "", p.strip()) for p in re.split(r",\s*|\s+and\s+", whole) if p.strip()]
    return [whole] + [p for p in parts if p != whole]


def _same_state(area_state: str, wanted: str | None) -> bool:
    if not wanted:
        return True
    return area_state == wanted or (area_state in _NSW_ACT and wanted in _NSW_ACT)


def parse_areas(headline: str, jurisdiction: str | None) -> list[tuple[str, str, str | None]]:
    """(product, name, state) for each area the headline names; [] if none."""
    text = (headline or "").strip()
    if not text or re.match(r"(?i)^cancellation", text):
        return []
    out: list[tuple[str, str, str | None]] = []
    fw = re.search(r"(?i)\bfor (.+?) fire weather districts?\b", text)
    if fw:
        out += [("fire_weather_district", n, jurisdiction) for n in _split_names(fw.group(1))]
    fd = re.search(r"(?i)\bfor (.+?) forecast districts?\b", text)
    if fd:
        out += [("forecast_district", n, jurisdiction) for n in _split_names(fd.group(1))]
    fl = re.search(r"(?i)flood warning for (?:the )?(.+?)\.?$", text)
    if fl:
        name = fl.group(1).strip()
        states = "|".join(_STATES)
        hint = re.search(rf"\(({states})\)\s*$", name)
        state = hint.group(1) if hint else jurisdiction
        name = re.sub(rf"\s*\((?:{states})\)\s*$", "", name)
        name = re.sub(r"(?i)^(upper|lower|middle|mid)\s+", "", name)
        out.append(("flood_catchment", name, state))
    return out


def match_alert(alert: dict, sites: list[dict], data: dict | None = None) -> AreaResult:
    data = data if data is not None else load_areas()
    wanted = parse_areas(alert.get("headline") or "", alert.get("jurisdiction"))
    areas: dict[str, dict] = data.get("areas", {})
    hits: dict[str, str] = {}  # aac -> area name
    for product, name, state in wanted:
        key = _norm(name)
        for aac, area in areas.items():
            if area["product"] != product or not _same_state(area["state"], state):
                continue
            area_key = _norm(area["name"])
            if product == "flood_catchment":
                if re.search(rf"\b{re.escape(key)}\b", area_key):
                    hits[aac] = area["name"]
            elif area_key == key:
                hits[aac] = area["name"]
    if not hits:
        return AreaResult("unparsed")
    by_site: dict[str, list[str]] = data.get("sites", {})
    inside, unknown = [], 0
    for site in sites:
        site_areas = by_site.get(str(site.get("id")))
        if site_areas is None:
            unknown += 1
        elif any(a in hits for a in site_areas):
            inside.append(site)
    order = {"Tier 1": 0, "Tier 2": 1, "Tier 3": 2}
    inside.sort(key=lambda s: (order.get(s.get("priority"), 9), s.get("name") or ""))
    names = sorted(set(hits.values()))
    return AreaResult("matched" if inside else "none_inside", names, inside, unknown)
