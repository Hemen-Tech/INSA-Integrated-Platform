
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"

ROADS_FILE = PROCESSED / "phase2c_v2_sidama_buffered_roads.gpkg"
ROADS_LAYER = "sidama_buffered_roads_v2"
OUTPUT_CSV = PROCESSED / "phase2e1_origin_source_roads_1500m.csv"

ORIGIN_X = 474953.3436867579
ORIGIN_Y = 699988.2860505662
RADIUS_M = 1500
CRS = "EPSG:32637"

VEHICLE_CLASSES = {
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link", "residential", "unclassified",
    "living_street", "service", "road",
    "track", "track_grade1", "track_grade2",
    "track_grade3", "track_grade4", "track_grade5",
}

print("=" * 72)
print("PHASE 2E.1 — ORIGIN SOURCE-ROAD INVESTIGATION")
print("=" * 72)

roads = gpd.read_file(ROADS_FILE, layer=ROADS_LAYER)

if roads.crs is None:
    raise ValueError("The source roads have no CRS.")

if roads.crs.to_string() != CRS:
    roads = roads.to_crs(CRS)

origin = Point(ORIGIN_X, ORIGIN_Y)

print(f"Source roads loaded: {len(roads):,}")
print(f"CRS: {roads.crs}")

# First filter by a bounding box for efficiency, then calculate
# the true distance from the origin to each candidate geometry.
minx = ORIGIN_X - RADIUS_M
miny = ORIGIN_Y - RADIUS_M
maxx = ORIGIN_X + RADIUS_M
maxy = ORIGIN_Y + RADIUS_M

candidates = roads.loc[
    roads.geometry.bounds.apply(
        lambda row: (
            row["minx"] <= maxx
            and row["maxx"] >= minx
            and row["miny"] <= maxy
            and row["maxy"] >= miny
        ),
        axis=1,
    )
].copy()

candidates["distance_to_origin_m"] = candidates.geometry.distance(origin)
nearby = candidates.loc[
    candidates["distance_to_origin_m"] <= RADIUS_M
].copy()

nearby["geometry_type"] = nearby.geometry.geom_type
nearby["feature_length_m"] = nearby.geometry.length

if "fclass" in nearby.columns:
    nearby["provisionally_graph_eligible"] = (
        nearby["fclass"].astype(str).isin(VEHICLE_CLASSES)
    )
else:
    nearby["provisionally_graph_eligible"] = False

preferred = [
    "osm_id", "name", "fclass", "oneway", "maxspeed",
    "bridge", "tunnel", "layer", "geometry_type",
    "feature_length_m", "distance_to_origin_m",
    "provisionally_graph_eligible",
]
columns = [col for col in preferred if col in nearby.columns]

nearby[columns].sort_values("distance_to_origin_m").to_csv(
    OUTPUT_CSV, index=False
)

print(f"\nRoad features within {RADIUS_M} m: {len(nearby):,}")
print(f"CSV saved: {OUTPUT_CSV}")

if nearby.empty:
    print("No source roads found within the search radius.")
else:
    print("\n=== NEAREST 30 SOURCE ROAD FEATURES ===")
    print(
        nearby[columns]
        .sort_values("distance_to_origin_m")
        .head(30)
        .to_string(index=False)
    )

    print("\n=== ROAD CLASS COUNTS ===")
    if "fclass" in nearby.columns:
        print(
            nearby.groupby(
                ["fclass", "provisionally_graph_eligible"],
                dropna=False,
            )
            .size()
            .reset_index(name="feature_count")
            .sort_values("feature_count", ascending=False)
            .to_string(index=False)
        )

    print("\n=== DISTANCE BANDS ===")
    for radius in [5, 15, 30, 100, 250, 500, 1000, 1500]:
        count = int((nearby["distance_to_origin_m"] <= radius).sum())
        print(f"Within {radius:4d} m: {count:5d} features")

print("\nNo source data or graph files were modified.")
