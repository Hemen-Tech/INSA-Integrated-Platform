
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, LineString

ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"

ROADS_FILE = PROCESSED / "phase2c_v2_sidama_buffered_roads.gpkg"
ROADS_LAYER = "sidama_buffered_roads_v2"
NODES_FILE = PROCESSED / "phase2e_vehicle_graph_nodes.csv"
EDGES_FILE = PROCESSED / "phase2e_vehicle_graph_edges.csv"

OUTPUT_VERTICES = PROCESSED / "phase2e1_origin_first_500m_vertices.csv"
OUTPUT_ROADS = PROCESSED / "phase2e1_origin_first_500m_roads.csv"

TARGET_OSM_ID = 620921089
ORIGIN_ID = "N47495334_69998829"
ORIGIN_X = 474953.3436867579
ORIGIN_Y = 699988.2860505662
CRS = "EPSG:32637"

origin = Point(ORIGIN_X, ORIGIN_Y)

print("=" * 72)
print("PHASE 2E.1 — ORIGIN FIRST 500 METRES")
print("=" * 72)

roads = gpd.read_file(ROADS_FILE, layer=ROADS_LAYER)

if roads.crs is None:
    raise ValueError("Source roads have no CRS.")

if roads.crs.to_string() != CRS:
    roads = roads.to_crs(CRS)

osm_ids = pd.to_numeric(roads["osm_id"], errors="coerce")
match = roads.loc[osm_ids == TARGET_OSM_ID]

if match.empty:
    raise ValueError(f"OSM ID {TARGET_OSM_ID} not found.")

geom = match.iloc[0].geometry

if geom.geom_type == "MultiLineString":
    parts = list(geom.geoms)
elif geom.geom_type == "LineString":
    parts = [geom]
else:
    raise ValueError(f"Unexpected geometry type: {geom.geom_type}")

# Find the closest vertex and report the road's initial segment
# in both directions from the origin endpoint.
vertex_rows = []
for part_index, part in enumerate(parts, start=1):
    coords = list(part.coords)

    for index, xy in enumerate(coords):
        point = Point(xy)
        distance = point.distance(origin)

        if distance <= 500:
            previous_distance = None
            next_distance = None

            if index > 0:
                previous_distance = Point(coords[index - 1]).distance(origin)

            if index + 1 < len(coords):
                next_distance = Point(coords[index + 1]).distance(origin)

            vertex_rows.append({
                "part_number": part_index,
                "vertex_index": index,
                "x": xy[0],
                "y": xy[1],
                "distance_to_origin_m": distance,
                "previous_vertex_distance_to_origin_m": previous_distance,
                "next_vertex_distance_to_origin_m": next_distance,
            })

vertices = pd.DataFrame(vertex_rows)
vertices.to_csv(OUTPUT_VERTICES, index=False)

print(f"\nVertices within 500 m: {len(vertices)}")
print(f"Vertex report: {OUTPUT_VERTICES}")

if not vertices.empty:
    print("\n=== NEAREST ROAD VERTICES ===")
    print(
        vertices.sort_values("distance_to_origin_m")
        .head(40)
        .to_string(index=False)
    )

# Check all other source road geometries that come within 100 m
# of the origin road's first 500 m corridor.
# The corridor is a proximity diagnostic, not proof of a junction.
first_500 = geom.interpolate(
    min(500.0, geom.length)
)  # point 500 m along geometry from its first coordinate

coords = list(parts[0].coords)
line = LineString(coords)

# Select the first 500 m from whichever endpoint is nearest the origin.
if Point(coords[0]).distance(origin) <= Point(coords[-1]).distance(origin):
    travelled = 0.0
    selected = [coords[0]]
    for a, b in zip(coords[:-1], coords[1:]):
        segment_length = Point(a).distance(Point(b))
        if travelled + segment_length <= 500:
            selected.append(b)
            travelled += segment_length
        else:
            remaining = 500 - travelled
            if segment_length > 0:
                fraction = remaining / segment_length
                selected.append((
                    a[0] + fraction * (b[0] - a[0]),
                    a[1] + fraction * (b[1] - a[1]),
                ))
            break
else:
    reversed_coords = list(reversed(coords))
    travelled = 0.0
    selected = [reversed_coords[0]]
    for a, b in zip(reversed_coords[:-1], reversed_coords[1:]):
        segment_length = Point(a).distance(Point(b))
        if travelled + segment_length <= 500:
            selected.append(b)
            travelled += segment_length
        else:
            remaining = 500 - travelled
            if segment_length > 0:
                fraction = remaining / segment_length
                selected.append((
                    a[0] + fraction * (b[0] - a[0]),
                    a[1] + fraction * (b[1] - a[1]),
                ))
            break

corridor = LineString(selected).buffer(100)

nearby = roads.loc[
    roads.geometry.intersects(corridor)
    & (osm_ids != TARGET_OSM_ID)
].copy()

if not nearby.empty:
    nearby["distance_to_origin_road_m"] = nearby.geometry.distance(line)
    keep = [
        c for c in [
            "osm_id", "name", "fclass", "oneway",
            "bridge", "tunnel", "layer",
        ] if c in nearby.columns
    ]
    nearby[keep + ["distance_to_origin_road_m"]].to_csv(
        OUTPUT_ROADS, index=False
    )
else:
    pd.DataFrame(
        columns=["osm_id", "name", "fclass", "distance_to_origin_road_m"]
    ).to_csv(OUTPUT_ROADS, index=False)

print("\n=== OTHER SOURCE ROADS NEAR THE FIRST 500 M ===")
print(f"Other road features in 100 m corridor: {len(nearby)}")
print(f"Nearby-road report: {OUTPUT_ROADS}")

if not nearby.empty:
    cols = [
        c for c in [
            "osm_id", "name", "fclass", "oneway",
            "bridge", "tunnel", "layer",
        ] if c in nearby.columns
    ]
    print(nearby[cols].head(40).to_string(index=False))
else:
    print("No other source road features intersect the 100 m corridor.")

# Confirm the origin node's graph connections.
nodes = pd.read_csv(NODES_FILE)
edges = pd.read_csv(EDGES_FILE)

nodes.columns = nodes.columns.str.strip()
edges.columns = edges.columns.str.strip()

print("\n=== ORIGIN GRAPH CONNECTIONS ===")
print("Origin node present:", ORIGIN_ID in set(nodes["node_id"].astype(str)))

incident = edges.loc[
    (edges["from_node"].astype(str) == ORIGIN_ID)
    | (edges["to_node"].astype(str) == ORIGIN_ID)
]
print(incident.to_string(index=False))

print("\nDiagnostic complete. No source or graph files were modified.")
