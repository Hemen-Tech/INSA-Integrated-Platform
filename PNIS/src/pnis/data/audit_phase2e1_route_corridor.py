
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"

ROADS_FILE = PROCESSED / "phase2c_v2_sidama_buffered_roads.gpkg"
ROADS_LAYER = "sidama_buffered_roads_v2"
NODES_FILE = PROCESSED / "phase2e_vehicle_graph_nodes.csv"
ROUTE_FILE = PROCESSED / "phase2e1_route_details.csv"

OUTPUT_DETAILS = PROCESSED / "phase2e1_route_corridor_audit.csv"
OUTPUT_SUMMARY = PROCESSED / "phase2e1_route_corridor_summary.txt"

ROUTE_ID = 5
CRS = "EPSG:32637"
SEARCH_RADIUS_M = 30
DISTANCE_BANDS_M = [5, 15, 30]

print("=" * 76)
print("PHASE 2E.1 — ROUTE CORRIDOR CONNECTIVITY AUDIT")
print("=" * 76)

# Load source road features.
print("\nLoading source roads...")
roads = gpd.read_file(ROADS_FILE, layer=ROADS_LAYER)

if roads.crs is None:
    raise ValueError("Source road layer has no CRS.")

if roads.crs.to_string() != CRS:
    roads = roads.to_crs(CRS)

required_road_columns = {"osm_id", "fclass", "geometry"}
missing = required_road_columns - set(roads.columns)
if missing:
    raise ValueError(f"Missing source road columns: {sorted(missing)}")

roads["_osm_numeric"] = pd.to_numeric(
    roads["osm_id"], errors="coerce"
)

print(f"Source road features: {len(roads):,}")
print(f"Source CRS: {roads.crs}")

# Load graph nodes.
print("\nLoading graph nodes and route details...")
nodes = pd.read_csv(NODES_FILE)
route_details = pd.read_csv(ROUTE_FILE)

nodes.columns = nodes.columns.str.strip()
route_details.columns = route_details.columns.str.strip()

node_id_col = next(
    (c for c in ["node_id", "node", "id"] if c in nodes.columns),
    None,
)
x_col = next(
    (c for c in [
        "x_utm_m", "x_utm", "x", "easting", "X"
    ] if c in nodes.columns),
    None,
)
y_col = next(
    (c for c in [
        "y_utm_m", "y_utm", "y", "northing", "Y"
    ] if c in nodes.columns),
    None,
)

if not all([node_id_col, x_col, y_col]):
    raise ValueError(
        "Could not identify graph node ID and projected coordinates. "
        f"Available columns: {nodes.columns.tolist()}"
    )

required_route_columns = {
    "route_id", "step_number", "from_node", "to_node"
}
missing = required_route_columns - set(route_details.columns)
if missing:
    raise ValueError(f"Missing route-detail columns: {sorted(missing)}")

route = route_details.loc[
    pd.to_numeric(route_details["route_id"], errors="coerce")
    == ROUTE_ID
].copy()

if route.empty:
    raise ValueError(
        f"Route ID {ROUTE_ID} not found in {ROUTE_FILE.name}"
    )

route = route.sort_values("step_number").reset_index(drop=True)

node_xy = {}
for _, row in nodes.iterrows():
    node_xy[str(row[node_id_col])] = (
        float(row[x_col]),
        float(row[y_col]),
    )

road_sindex = roads.sindex

print(f"Graph nodes: {len(nodes):,}")
print(f"Route ID: {ROUTE_ID}")
print(f"Route steps: {len(route):,}")
print(f"Node coordinate columns: {x_col}, {y_col}")

# Inspect other source roads within 30 m of each route segment.
audit_rows = []
missing_node_steps = 0
zero_length_steps = 0

for _, step in route.iterrows():
    from_node = str(step["from_node"])
    to_node = str(step["to_node"])

    if from_node not in node_xy or to_node not in node_xy:
        missing_node_steps += 1
        continue

    segment = LineString([
        node_xy[from_node],
        node_xy[to_node],
    ])

    if segment.length == 0:
        zero_length_steps += 1
        continue

    route_osm_value = pd.to_numeric(
        pd.Series([step.get("osm_id")]), errors="coerce"
    ).iloc[0]

    search_area = segment.buffer(SEARCH_RADIUS_M)

    candidate_positions = road_sindex.query(
        search_area,
        predicate="intersects",
    )

    for pos in candidate_positions:
        road = roads.iloc[int(pos)]
        nearby_osm_value = road["_osm_numeric"]

        # Exclude the same OSM road feature as the route segment.
        if (
            pd.notna(route_osm_value)
            and pd.notna(nearby_osm_value)
            and int(route_osm_value) == int(nearby_osm_value)
        ):
            continue

        distance_m = float(segment.distance(road.geometry))
        if distance_m > SEARCH_RADIUS_M:
            continue

        audit_rows.append({
            "route_id": ROUTE_ID,
            "step_number": int(step["step_number"]),
            "from_node": from_node,
            "to_node": to_node,
            "route_osm_id": (
                int(route_osm_value)
                if pd.notna(route_osm_value) else None
            ),
            "route_road_class": step.get(
                "road_class", step.get("fclass", "")
            ),
            "route_segment_length_m": segment.length,
            "nearby_osm_id": (
                int(nearby_osm_value)
                if pd.notna(nearby_osm_value) else None
            ),
            "nearby_road_class": road.get("fclass", ""),
            "nearby_name": road.get("name", ""),
            "nearby_oneway": road.get("oneway", ""),
            "nearby_bridge": road.get("bridge", ""),
            "nearby_tunnel": road.get("tunnel", ""),
            "nearby_layer": road.get("layer", ""),
            "distance_to_route_segment_m": distance_m,
            "geometry_type": road.geometry.geom_type,
            "nearby_feature_length_m": road.geometry.length,
        })

# Deduplicate repeated route-step / nearby-road pairs.
audit_columns = [
    "route_id", "step_number", "from_node", "to_node",
    "route_osm_id", "route_road_class",
    "route_segment_length_m", "nearby_osm_id",
    "nearby_road_class", "nearby_name", "nearby_oneway",
    "nearby_bridge", "nearby_tunnel", "nearby_layer",
    "distance_to_route_segment_m", "geometry_type",
    "nearby_feature_length_m",
]

audit = pd.DataFrame(audit_rows, columns=audit_columns)

if not audit.empty:
    audit = audit.sort_values(
        ["distance_to_route_segment_m", "step_number"]
    ).drop_duplicates(
        subset=["step_number", "nearby_osm_id"],
        keep="first",
    )

audit.to_csv(OUTPUT_DETAILS, index=False)

# Create the summary report.
lines = [
    "PHASE 2E.1 — ROUTE CORRIDOR CONNECTIVITY AUDIT",
    "=" * 68,
    f"Route ID: {ROUTE_ID}",
    f"Route steps in input: {len(route)}",
    f"Steps skipped for missing node coordinates: {missing_node_steps}",
    f"Zero-length route steps skipped: {zero_length_steps}",
    f"Source road features: {len(roads)}",
    f"Search radius: {SEARCH_RADIUS_M} m",
    f"Nearby route-step/source-road pairs: {len(audit)}",
    "",
    "IMPORTANT: Proximity is not proof of a valid junction.",
    "Review bridge, tunnel, layer, geometry and direction before",
    "considering any network correction.",
    "",
]

if audit.empty:
    lines.append(
        "No other source road features were found within 30 m "
        "of the inspected route segments."
    )
else:
    for threshold in DISTANCE_BANDS_M:
        count = int(
            (audit["distance_to_route_segment_m"] <= threshold).sum()
        )
        lines.append(
            f"Nearby feature pairs within {threshold} m: {count}"
        )

    lines.extend(["", "NEAREST CANDIDATE LOCATIONS", "-" * 68])

    nearest = (
        audit.sort_values("distance_to_route_segment_m")
        .drop_duplicates("step_number")
        .head(30)
    )

    for _, row in nearest.iterrows():
        lines.append(
            f"Step {int(row['step_number'])}: "
            f"route OSM {row['route_osm_id']} "
            f"({row['route_road_class']}); "
            f"nearby OSM {row['nearby_osm_id']} "
            f"({row['nearby_road_class']}); "
            f"distance={row['distance_to_route_segment_m']:.2f} m; "
            f"bridge={row['nearby_bridge']}; "
            f"tunnel={row['nearby_tunnel']}; "
            f"layer={row['nearby_layer']}"
        )

    lines.extend(["", "CANDIDATE ROAD CLASS COUNTS", "-" * 68])

    counts = (
        audit.groupby("nearby_road_class", dropna=False)
        .size()
        .sort_values(ascending=False)
    )

    for road_class, count in counts.items():
        lines.append(f"{road_class}: {int(count)}")

lines.extend([
    "",
    f"Detailed CSV: {OUTPUT_DETAILS}",
    "No source roads or graph files were modified.",
])

OUTPUT_SUMMARY.write_text("\n".join(lines), encoding="utf-8")

print("\n" + "\n".join(lines))
print("\nAudit complete.")
