
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point


ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"

ROADS_FILE = PROCESSED / "phase2c_v2_sidama_buffered_roads.gpkg"
ROADS_LAYER = "sidama_buffered_roads_v2"
NODES_FILE = PROCESSED / "phase2e_vehicle_graph_nodes.csv"
EDGES_FILE = PROCESSED / "phase2e_vehicle_graph_edges.csv"
DETAILS_FILE = PROCESSED / "phase2e1_route_details.csv"

OUTPUT_CSV = PROCESSED / "phase2e1_route5_connectivity_candidates.csv"
OUTPUT_TXT = PROCESSED / "phase2e1_route5_connectivity_audit.txt"

ROUTE_ID = 5
SEARCH_RADIUS_M = 100.0
ENDPOINT_RADIUS_M = 30.0


def first_existing_column(
    frame: pd.DataFrame, candidates: list[str], label: str
) -> str:
    for column in candidates:
        if column in frame.columns:
            return column
    raise ValueError(
        f"Could not identify {label} column. "
        f"Available columns: {list(frame.columns)}"
    )


def clean_id(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def main() -> None:
    print("=" * 76)
    print("PHASE 2E.1 — ROUTE 5 SOURCE-CONNECTIVITY AUDIT")
    print("=" * 76)

    for path in [ROADS_FILE, NODES_FILE, EDGES_FILE, DETAILS_FILE]:
        if not path.exists():
            raise FileNotFoundError(f"Required input file not found: {path}")

    print("\nLoading source roads...")
    roads = gpd.read_file(ROADS_FILE, layer=ROADS_LAYER)
    if roads.crs is None:
        raise ValueError("Source road layer has no CRS.")
    if roads.crs.is_geographic:
        raise ValueError(
            f"Expected projected metric CRS; received {roads.crs}"
        )

    osm_col = first_existing_column(
        roads, ["osm_id", "osm_way_id", "id"], "OSM ID"
    )
    class_col = first_existing_column(
        roads, ["fclass", "road_class", "highway"], "road class"
    )

    print(f"Road features: {len(roads):,}")
    print(f"CRS: {roads.crs}")
    print(f"OSM ID field: {osm_col}")
    print(f"Road class field: {class_col}")

    print("\nLoading graph data...")
    nodes = pd.read_csv(NODES_FILE, dtype={"node_id": str})
    edges = pd.read_csv(EDGES_FILE, dtype=str)
    details = pd.read_csv(DETAILS_FILE, dtype=str)

    node_id_col = first_existing_column(
        nodes, ["node_id", "id"], "node ID"
    )
    x_col = first_existing_column(
        nodes, ["x_utm_m", "x_utm", "x", "easting"], "node X"
    )
    y_col = first_existing_column(
        nodes, ["y_utm_m", "y_utm", "y", "northing"], "node Y"
    )

    route_col = first_existing_column(
        details, ["route_id"], "route ID"
    )
    step_col = first_existing_column(
        details, ["step_number"], "step number"
    )
    from_col = first_existing_column(
        details, ["from_node"], "route from-node"
    )
    to_col = first_existing_column(
        details, ["to_node"], "route to-node"
    )
    route_osm_col = first_existing_column(
        details, ["osm_id", "route_osm_id"], "route OSM ID"
    )

    route = details[details[route_col].astype(str) == str(ROUTE_ID)].copy()
    if route.empty:
        raise ValueError(f"No route details found for route {ROUTE_ID}.")

    route["step_num"] = pd.to_numeric(route[step_col], errors="coerce")
    route = route.sort_values("step_num")

    node_lookup: dict[str, tuple[float, float]] = {}
    for _, row in nodes.iterrows():
        key = clean_id(row[node_id_col])
        try:
            x = float(row[x_col])
            y = float(row[y_col])
        except (TypeError, ValueError):
            continue
        if key:
            node_lookup[key] = (x, y)

    edge_columns = list(edges.columns)
    edge_from_col = next(
        (c for c in ["from_node", "u", "source"] if c in edge_columns),
        None,
    )
    edge_to_col = next(
        (c for c in ["to_node", "v", "target"] if c in edge_columns),
        None,
    )
    edge_osm_col = next(
        (c for c in ["osm_id", "route_osm_id"] if c in edge_columns),
        None,
    )

    if edge_from_col is None or edge_to_col is None:
        print(
            "WARNING: Could not identify edge endpoint columns; "
            "graph-edge connectivity comparison will be limited."
        )

    graph_edge_pairs: set[tuple[str, str]] = set()
    graph_node_neighbors: dict[str, set[str]] = {}

    if edge_from_col and edge_to_col:
        for _, row in edges.iterrows():
            u = clean_id(row[edge_from_col])
            v = clean_id(row[edge_to_col])
            if not u or not v:
                continue
            graph_edge_pairs.add((u, v))
            graph_node_neighbors.setdefault(u, set()).add(v)

    print(f"Graph nodes: {len(nodes):,}")
    print(f"Directed graph edges: {len(edges):,}")
    print(f"Route {ROUTE_ID} steps: {len(route):,}")
    print(f"Node coordinates indexed: {len(node_lookup):,}")

    # Identify the actual route's start and end points.
    first_step = route.iloc[0]
    last_step = route.iloc[-1]
    start_id = clean_id(first_step[from_col])
    end_id = clean_id(last_step[to_col])

    if start_id not in node_lookup or end_id not in node_lookup:
        raise ValueError(
            f"Route endpoint coordinates missing: start={start_id}, end={end_id}"
        )

    start_point = Point(node_lookup[start_id])
    end_point = Point(node_lookup[end_id])

    # Build route-step geometries using the graph node coordinates.
    route_segments: list[dict] = []
    for _, row in route.iterrows():
        u = clean_id(row[from_col])
        v = clean_id(row[to_col])
        if u not in node_lookup or v not in node_lookup:
            continue

        line = LineString([node_lookup[u], node_lookup[v]])
        if line.length == 0:
            continue

        route_segments.append(
            {
                "step_number": int(row["step_num"]),
                "from_node": u,
                "to_node": v,
                "route_osm_id": clean_id(row[route_osm_col]),
                "route_geometry": line,
            }
        )

    # Inspect all road features in a radius around each route endpoint.
    endpoint_records: list[dict] = []
    for endpoint_name, endpoint_node, endpoint_point in [
        ("route_start", start_id, start_point),
        ("route_end", end_id, end_point),
    ]:
        candidate_indexes = list(
            roads.sindex.query(
                endpoint_point.buffer(SEARCH_RADIUS_M),
                predicate="intersects",
            )
        )

        for idx in candidate_indexes:
            road = roads.iloc[idx]
            geom = road.geometry
            if geom is None or geom.is_empty:
                continue

            distance = float(geom.distance(endpoint_point))
            if distance > SEARCH_RADIUS_M:
                continue

            road_osm = clean_id(road[osm_col])
            road_class = str(road[class_col])
            bridge = str(road.get("bridge", ""))
            tunnel = str(road.get("tunnel", ""))
            layer = str(road.get("layer", ""))
            oneway = str(road.get("oneway", ""))

            endpoint_distances = []
            for part in getattr(geom, "geoms", [geom]):
                if part.geom_type == "LineString" and len(part.coords) >= 2:
                    endpoint_distances.append(
                        (
                            float(Point(part.coords[0]).distance(endpoint_point)),
                            "line_start",
                        )
                    )
                    endpoint_distances.append(
                        (
                            float(Point(part.coords[-1]).distance(endpoint_point)),
                            "line_end",
                        )
                    )

            nearest_line_endpoint_m = (
                min(endpoint_distances)[0] if endpoint_distances else None
            )

            endpoint_records.append(
                {
                    "route_id": ROUTE_ID,
                    "endpoint": endpoint_name,
                    "route_endpoint_node": endpoint_node,
                    "candidate_osm_id": road_osm,
                    "candidate_road_class": road_class,
                    "distance_to_route_endpoint_m": distance,
                    "nearest_source_line_endpoint_m": nearest_line_endpoint_m,
                    "feature_length_m": float(geom.length),
                    "bridge": bridge,
                    "tunnel": tunnel,
                    "layer": layer,
                    "oneway": oneway,
                    "geometry_type": geom.geom_type,
                    "endpoint_node_graph_degree": len(
                        graph_node_neighbors.get(endpoint_node, set())
                    ),
                    "candidate_osm_is_route_endpoint_feature": road_osm
                    in {
                        clean_id(first_step[route_osm_col]),
                        clean_id(last_step[route_osm_col]),
                    },
                    "review_status": (
                        "MANUAL_GRADE_SEPARATION_REVIEW"
                        if bridge not in ("", "F", "False", "0")
                        or tunnel not in ("", "F", "False", "0")
                        or layer not in ("", "0", "0.0")
                        else (
                            "NEAR_ENDPOINT_NOT_PROOF_OF_CONNECTION"
                            if distance > 0.01
                            else "GEOMETRY_TOUCHES_ENDPOINT_REVIEW_TOPOLOGY"
                        )
                    ),
                }
            )

    # For each route segment, find source roads within the chosen radius.
    corridor_records: list[dict] = []
    sindex = roads.sindex

    for step in route_segments:
        route_line = step["route_geometry"]
        search_area = route_line.buffer(SEARCH_RADIUS_M)

        candidate_indexes = list(
            sindex.query(search_area, predicate="intersects")
        )

        for idx in candidate_indexes:
            road = roads.iloc[idx]
            geom = road.geometry
            if geom is None or geom.is_empty:
                continue

            candidate_osm = clean_id(road[osm_col])
            route_osm = step["route_osm_id"]
            if candidate_osm == route_osm:
                continue

            distance = float(geom.distance(route_line))
            if distance > SEARCH_RADIUS_M:
                continue

            intersection = route_line.intersection(geom)
            if intersection.is_empty:
                geometry_relation = "NEARBY_NO_INTERSECTION"
            elif intersection.geom_type in ("Point", "MultiPoint"):
                geometry_relation = "GEOMETRIC_CROSSING_OR_TOUCH"
            elif intersection.geom_type in (
                "LineString",
                "MultiLineString",
                "GeometryCollection",
            ):
                geometry_relation = "OVERLAP_OR_COMPLEX_INTERSECTION"
            else:
                geometry_relation = "INTERSECTION_REVIEW"

            bridge = str(road.get("bridge", ""))
            tunnel = str(road.get("tunnel", ""))
            layer = str(road.get("layer", ""))

            grade_review = (
                bridge not in ("", "F", "False", "0")
                or tunnel not in ("", "F", "False", "0")
                or layer not in ("", "0", "0.0")
            )

            corridor_records.append(
                {
                    "route_id": ROUTE_ID,
                    "step_number": step["step_number"],
                    "from_node": step["from_node"],
                    "to_node": step["to_node"],
                    "route_osm_id": route_osm,
                    "candidate_osm_id": candidate_osm,
                    "candidate_road_class": str(road[class_col]),
                    "distance_to_route_segment_m": distance,
                    "intersection_length_or_measure_m": float(
                        intersection.length
                    ),
                    "geometry_relation": geometry_relation,
                    "candidate_oneway": str(road.get("oneway", "")),
                    "candidate_bridge": bridge,
                    "candidate_tunnel": tunnel,
                    "candidate_layer": layer,
                    "candidate_feature_length_m": float(geom.length),
                    "candidate_geometry_type": geom.geom_type,
                    "grade_separation_review": grade_review,
                    "review_status": (
                        "MANUAL_GRADE_SEPARATION_REVIEW"
                        if grade_review
                        else geometry_relation
                    ),
                }
            )

    endpoint_df = pd.DataFrame(endpoint_records)
    corridor_df = pd.DataFrame(corridor_records)

    if not corridor_df.empty:
        corridor_df = corridor_df.sort_values(
            ["distance_to_route_segment_m", "step_number"]
        )

    if not endpoint_df.empty:
        endpoint_df = endpoint_df.sort_values(
            ["endpoint", "distance_to_route_endpoint_m"]
        )

    # Write separate, explicit outputs to avoid mixing endpoint and corridor rows.
    corridor_path = OUTPUT_CSV
    endpoint_path = PROCESSED / "phase2e1_route5_endpoint_candidates.csv"
    corridor_df.to_csv(corridor_path, index=False)
    endpoint_df.to_csv(endpoint_path, index=False)

    report_lines = [
        "PHASE 2E.1 — ROUTE 5 SOURCE-CONNECTIVITY AUDIT",
        "=" * 72,
        f"Source CRS: {roads.crs}",
        f"Source road features: {len(roads)}",
        f"Route ID: {ROUTE_ID}",
        f"Route steps in details file: {len(route)}",
        f"Route segment geometries constructed: {len(route_segments)}",
        f"Start node: {start_id}",
        f"End node: {end_id}",
        f"Start graph degree: {len(graph_node_neighbors.get(start_id, set()))}",
        f"End graph degree: {len(graph_node_neighbors.get(end_id, set()))}",
        f"Endpoint candidate rows: {len(endpoint_df)}",
        f"Route corridor candidate rows: {len(corridor_df)}",
        "",
        "ENDPOINT CANDIDATES BY ENDPOINT",
        "-" * 72,
    ]

    if endpoint_df.empty:
        report_lines.append("No source roads found within endpoint search radius.")
    else:
        for endpoint_name in ["route_start", "route_end"]:
            subset = endpoint_df[endpoint_df["endpoint"] == endpoint_name]
            report_lines.append(
                f"{endpoint_name}: {len(subset)} candidate source features"
            )
            for _, row in subset.head(15).iterrows():
                report_lines.append(
                    f"  OSM {row['candidate_osm_id']} "
                    f"class={row['candidate_road_class']} "
                    f"distance={row['distance_to_route_endpoint_m']:.3f}m "
                    f"nearest_source_endpoint="
                    f"{row['nearest_source_line_endpoint_m']}m "
                    f"bridge={row['bridge']} tunnel={row['tunnel']} "
                    f"layer={row['layer']} status={row['review_status']}"
                )

    report_lines.extend(
        [
            "",
            "CORRIDOR GEOMETRY RELATIONS",
            "-" * 72,
        ]
    )

    if corridor_df.empty:
        report_lines.append("No nearby source-road candidates found.")
    else:
        for relation, count in (
            corridor_df["geometry_relation"].value_counts().items()
        ):
            report_lines.append(f"{relation}: {count}")

        report_lines.append("")
        report_lines.append("CLOSEST 20 NON-ROUTE SOURCE ROAD CANDIDATES")
        for _, row in corridor_df.head(20).iterrows():
            report_lines.append(
                f"step={row['step_number']} "
                f"route_osm={row['route_osm_id']} "
                f"candidate_osm={row['candidate_osm_id']} "
                f"class={row['candidate_road_class']} "
                f"distance={row['distance_to_route_segment_m']:.3f}m "
                f"relation={row['geometry_relation']} "
                f"bridge={row['candidate_bridge']} "
                f"tunnel={row['candidate_tunnel']} "
                f"layer={row['candidate_layer']}"
            )

    report_lines.extend(
        [
            "",
            "INTERPRETATION LIMITS",
            "-" * 72,
            "Geometric proximity or intersection does not prove a routable junction.",
            "Bridge, tunnel, layer, one-way direction, and source topology need review.",
            "No source roads or graph files were modified.",
            "",
            f"Corridor CSV: {corridor_path}",
            f"Endpoint CSV: {endpoint_path}",
        ]
    )

    OUTPUT_TXT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print("\n".join(report_lines))
    print("\nAudit completed. Existing graph and source data were not modified.")


if __name__ == "__main__":
    main()
