#!/usr/bin/env python3
"""Fetch Boston (and surrounding) bike infrastructure data from OpenStreetMap (Overpass API) and write bikelanes.geojson."""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

# Public Overpass servers, tried in order; the main one often returns 504 under load.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
OUTPUT = "bikelanes.geojson"

# The bbox keeps out other towns with these names.
QUERY = """
[out:json][timeout:180][bbox:42.17,-71.33,42.54,-70.95];
area["boundary"="administrative"]["admin_level"="8"]["name"~"^(Arlington|Bedford|Boston|Brookline|Cambridge|Lexington|Milton|Newton|Somerville|Watertown)$"]->.towns;
(
  way["highway"="cycleway"](area.towns);
  way["highway"~"^(path|footway|pedestrian|track)$"]["bicycle"="designated"](area.towns);
  way[~"^cycleway(:both|:left|:right)?$"~"^(lane|track|shared_lane|share_busway|opposite_lane|opposite_track|opposite_share_busway)$"](area.towns);
);
out geom;
"""

SIDE_TYPES = {
    "lane": "lane", "opposite_lane": "lane",
    "track": "track", "opposite_track": "track",
    "shared_lane": "shared", "share_busway": "shared", "opposite_share_busway": "shared",
}
CYCLEWAY_TAGS = ("cycleway", "cycleway:both", "cycleway:left", "cycleway:right")
# Tags the map needs to work out which way each lane runs (e.g. contraflow lanes on one-way streets).
DIRECTION_TAGS = ("oneway", "oneway:bicycle", "cycleway:both:oneway", "cycleway:left:oneway", "cycleway:right:oneway")


def side(tags, which):
    """Bike facility on one side of a road: cycleway:<side>, else cycleway:both, else cycleway."""
    for key in (f"cycleway:{which}", "cycleway:both", "cycleway"):
        if key in tags:
            return SIDE_TYPES.get(tags[key])
    return None


def overpass(query):
    data = urllib.parse.urlencode({"data": query}).encode()
    for url in OVERPASS_URLS:
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "bostonopen-bikelanes"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                elements = json.load(resp)["elements"]
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"{url} failed: {e}", file=sys.stderr)
            continue
        # Some mirrors lack area data and silently return nothing.
        if elements:
            return elements
        print(f"{url} returned no data", file=sys.stderr)
    sys.exit("All Overpass servers failed")


def main():
    elements = overpass(QUERY)

    features = []
    for el in elements:
        if el["type"] != "way" or "geometry" not in el:
            continue
        tags = el.get("tags", {})
        if tags.get("highway") == "cycleway":
            kind = "cycleway"
        elif tags.get("highway") in ("path", "footway", "pedestrian", "track"):
            kind = "path"
        else:
            kind = "road"
        features.append({
            "type": "Feature",
            "properties": {
                "id": el["id"],
                "kind": kind,
                "left": side(tags, "left") if kind == "road" else None,
                "right": side(tags, "right") if kind == "road" else None,
                "name": tags.get("name"),
                "tags": {k: tags[k] for k in ("highway", *CYCLEWAY_TAGS, *DIRECTION_TAGS) if k in tags},
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[round(p["lon"], 6), round(p["lat"], 6)] for p in el["geometry"]],
            },
        })

    with open(OUTPUT, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, separators=(",", ":"))
    print(f"Wrote {len(features)} features to {OUTPUT}")


if __name__ == "__main__":
    main()
