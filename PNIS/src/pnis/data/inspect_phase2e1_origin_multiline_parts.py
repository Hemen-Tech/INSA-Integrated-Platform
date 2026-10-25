
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"

ROADS_FILE = PROCESSED / "phase2c_v2_sidama_buffered_roads.gpkg"
ROADS_LAYER = "sidama_buffered_roads_v2"
OUTPUT_CSV = PROCESSED / "phase2e1_origin_multiline_parts.csv"

TARGET_OSM_ID = 620921089
ORIGIN_X = 474953.3436867579
ORIGIN_Y = 699988.2860505662
CRS = "EPSG:32637"
SEARCH_RADIUS_M = 1500

origin = Point(ORIGIN_X, ORIGIN_Y)

print("=" * 72)
print("PHASE 2E.1 — MULTILINESTRING PART INSPECTION")
print("=" * 72)

roads = gpd.read_file(ROADS_FILE, layer=ROADS_LAYER)

if roads.crs is None:
    raise ValueError("Source road layer has no CRS.")

if roads.crs.to_string() != CRS:
    roads = roads.to_crs(CRS)

osm_ids = pd.to_numeric(roads["osm_id"], errors="coerce")
matches = roads.loc[osm_ids == TARGET_OSM_ID]

if matches.empty:
    raise ValueError(f"OSM ID {TARGET_OSM_ID} was not found.")

feature = matches.iloc[0]
geometry = feature.geometry

print(f"\nOSM ID: {TARGET_OSM_ID}")
print(f"Road class: {feature.get('fclass', 'unknown')}")
print(f"Geometry type: {geometry.geom_type}")
print(f"Total geometry length: {geometry.length:.3f} m")
print(f"Distance from origin to feature: {geometry.distance(origin):.3f} m")

if geometry.geom_type == "MultiLineString":
    parts = list(geometry.geoms)
elif geometry.geom_type == "LineString":
    parts = [geometry]
else:
    raise ValueError(f"Unexpected geometry type: {geometry.geom_type}")

print(f"\nNumber of line parts: {len(parts)}")

rows = []

for i, part in enumerate(parts, start=1):
    coords = list(part.coords)
    start = Point(coords[0])
    end = Point(coords[-1])

    rows.append({
        "part_number": i,
        "length_m": part.length,
        "distance_part_to_origin_m": part.distance(origin),
        "start_endpoint_distance_m": start.distance(origin),
        "end_endpoint_distance_m": end.distance(origin),
        "start_x": start.x,
        "start_y": start.y,
        "end_x": end.x,
        "end_y": end.y,
        "coordinate_count": len(coords),
        "within_search_radius": (
            part.distance(origin) <= SEARCH_RADIUS_M
        ),
        "part_bounds": str(part.bounds),
    })

result = pd.DataFrame(rows).sort_values(
    "distance_part_to_origin_m"
)

result.to_csv(OUTPUT_CSV, index=False)

print("\n=== CLOSEST LINE PARTS ===")
print(
    result.head(30).to_string(
        index=False,
        formatters={
            "length_m": "{:.2f}".format,
            "distance_part_to_origin_m": "{:.2f}".format,
            "start_endpoint_distance_m": "{:.2f}".format,
            "end_endpoint_distance_m": "{:.2f}".format,
        },
    )
)

print("\n=== SUMMARY ===")
print(f"Total parts: {len(result)}")
print(
    "Parts within 15 m of origin:",
    int((result["distance_part_to_origin_m"] <= 15).sum()),
)
print(
    "Parts within 100 m of origin:",
    int((result["distance_part_to_origin_m"] <= 100).sum()),
)
print(
    f"Parts within {SEARCH_RADIUS_M} m of origin:",
    int(result["within_search_radius"].sum()),
)
print(f"\nFull results saved to:\n{OUTPUT_CSV}")
print("\nNo source data or graph files were modified.")
