"""Work out which BOM warning areas each of our sites sits inside.

BOM warnings name districts and catchments, not places ("Fire Weather Warning
for the Greater Hunter fire weather district", "Moderate Flood Warning for the
Barcoo River"). BOM publishes those boundaries as shapefiles, so a site's areas
are a point-in-polygon lookup, done once here instead of on every alert:

    IDM00001  Public weather forecast districts   -> forecast_district
    IDM00007  Fire weather districts              -> fire_weather_district
    IDM00017  Flood warning catchment areas       -> flood_catchment

Source: ftp://ftp.bom.gov.au/anon/home/adfd/spatial/ (Bureau of Meteorology,
see its spatial data user guide for licence/attribution).

Usage (not part of the runtime; needs pyshp + shapely):
    uv run --with pyshp --with shapely python tools/emergency_alerts/bom_site_areas.py sites.json

sites.json is a JSON array of {"id", "latitude", "longitude"} for alert_sites.
Writes the same JSON to core/platform/data/bom_site_areas.json (Python matcher)
and lcars-portal/src/lib/data/bomSiteAreas.json (workbench). Re-run when the
site register changes or BOM re-issues its boundaries. A site missing from the
file is reported as "area not known", never as "not affected".
"""

from __future__ import annotations

import io
import json
import sys
import urllib.request
import zipfile

import shapefile  # pyshp
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

_BASE = "ftp://ftp.bom.gov.au/anon/home/adfd/spatial/"
PRODUCTS = {
    "IDM00001": "forecast_district",
    "IDM00007": "fire_weather_district",
    "IDM00017": "flood_catchment",
}


def _load(product_id: str) -> list[tuple[object, dict]]:
    with urllib.request.urlopen(f"{_BASE}{product_id}.zip", timeout=120) as resp:  # nosec B310 - fixed BOM FTP URL constant
        z = zipfile.ZipFile(io.BytesIO(resp.read()))
    base = next(n for n in z.namelist() if n.endswith(".shp"))[:-4]
    reader = shapefile.Reader(shp=io.BytesIO(z.read(base + ".shp")), dbf=io.BytesIO(z.read(base + ".dbf")), shx=io.BytesIO(z.read(base + ".shx")))
    fields = [f[0] for f in reader.fields[1:]]
    return [(shape(sr.shape.__geo_interface__), dict(zip(fields, sr.record))) for sr in reader.shapeRecords()]


OUTPUTS = ("core/platform/data/bom_site_areas.json", "lcars-portal/src/lib/data/bomSiteAreas.json")


def main(sites_path: str) -> None:
    with open(sites_path) as fh:
        sites = json.load(fh)
    areas: dict[str, dict[str, str]] = {}
    by_site: dict[str, list[str]] = {s["id"]: [] for s in sites}
    for product_id, product in PRODUCTS.items():
        features = _load(product_id)
        # Every area is recorded, not just those with one of our sites in: "this
        # warning names an area and none of our sites are in it" needs the name.
        for _, rec in features:
            areas[str(rec.get("AAC"))] = {"product": product, "name": str(rec.get("DIST_NAME") or ""), "state": str(rec.get("STATE_CODE") or "")}
        tree = STRtree([g for g, _ in features])
        for s in sites:
            point = Point(float(s["longitude"]), float(s["latitude"]))
            for idx in tree.query(point, predicate="intersects"):
                _, rec = features[int(idx)]
                by_site[s["id"]].append(str(rec.get("AAC")))
    payload = {
        "source": "Bureau of Meteorology spatial data IDM00001, IDM00007, IDM00017",
        "areas": dict(sorted(areas.items())),
        "sites": {k: sorted(v) for k, v in sorted(by_site.items())},
    }
    for out in OUTPUTS:
        with open(out, "w") as fh:
            json.dump(payload, fh, indent=0, separators=(",", ":"), sort_keys=False)
            fh.write("\n")
    print(f"{len(areas)} areas, {sum(len(v) for v in by_site.values())} site-area links for {len(sites)} sites", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1])
