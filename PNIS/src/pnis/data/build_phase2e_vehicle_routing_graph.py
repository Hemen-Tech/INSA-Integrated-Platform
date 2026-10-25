from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd
from shapely.geometry import LineString, Point


# ============================================================
# PHASE 2E - VEHICLE ROUTING GRAPH
# ============================================================

ROOT = Path.cwd()

INPUT_GPKG = ROOT / "data/processed/phase2c_v2_sidama_buffered_roads.gpkg"
INPUT_LAYER = "sidama_buffered_roads_v2"

OUT_DIR = ROOT / "data/processed"
SCRIPT_DIR = ROOT / "src/pnis/data"

CRS_METRIC = "EPSG:32637"

OUTPUT_ROADS = OUT_DIR / "phase2e_vehicle_eligible_roads.gpkg"
OUTPUT_EDGES = OUT_DIR / "phase2e_vehicle_graph_edges.gpkg"
OUTPUT_NODES_CSV = OUT_DIR / "phase2e_vehicle_graph_nodes.csv"
OUTPUT_EDGES_CSV = OUT_DIR / "phase2e_vehicle_graph_edges.csv"
OUTPUT_CLASS_SUMMARY = OUT_DIR / "phase2e_vehicle_road_class_summary.csv"
OUTPUT_EXCLUDED = OUT_DIR / "phase2e_excluded_roads.csv"
OUTPUT_REVIEW = OUT_DIR / "phase2e_road_review_flags.csv"
OUTPUT_JSON = OUT_DIR / "phase2e_vehicle_graph_audit.json"
OUTPUT_TXT = OUT_DIR / "phase2e_vehicle_graph_audit.txt"


# Initial conservative vehicle-road filter.
# Tracks are retained as provisional access roads because rural
# collection vehicles may need them. Their passability is unverified.
VEHICLE_CLASSES = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "residential",
    "unclassified",
    "living_street",
    "service",
    "road",
    "track",
    "track_grade1",
    "track_grade2",
    "track_grade3",
    "track_grade4",
    "track_grade5",
}

NON_VEHICLE_CLASSES = {
    "footway",
    "path",
    "pedestrian",
    "steps",
    "cycleway",
    "bridleway",
}


def node_key(x: float, y: float) -> str:
    """Stable node key, rounded to the nearest centimetre."""
    ix = round(x * 100)
    iy = round(y * 100)
    return f"N{ix}_{iy}"


def is_true(value) -> bool:
    return str(value).strip().upper() in {"T", "TRUE", "1", "YES"}


def safe_number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def write_text_report(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    if not INPUT_GPKG.exists():
        raise FileNotFoundError(
            f"Required Phase 2C v2 input is missing: {INPUT_GPKG}"
        )

    print("=" * 72)
    print("PHASE 2E - VEHICLE ROUTING GRAPH CONSTRUCTION")
    print("=" * 72)
    print(f"Input: {INPUT_GPKG}")
    print(f"Layer: {INPUT_LAYER}")

    roads = gpd.read_file(
        INPUT_GPKG,
        layer=INPUT_LAYER,
        engine="pyogrio",
    )

    if roads.empty:
        raise ValueError("Input road layer is empty.")

    if roads.crs is None:
        raise ValueError("Input road layer has no CRS.")

    required = {
        "osm_id", "fclass", "oneway", "maxspeed",
        "bridge", "tunnel", "layer", "geometry",
    }
    missing = required.difference(roads.columns)
    if missing:
        raise ValueError(
            f"Required input fields are missing: {sorted(missing)}"
        )

    if roads["osm_id"].isna().any():
        raise ValueError("Some input roads have missing OSM IDs.")

    roads = roads.loc[
        roads.geometry.notna()
        & ~roads.geometry.is_empty
    ].copy()

    if roads.crs.to_epsg() != 32637:
        roads = roads.to_crs(CRS_METRIC)

    source_count = len(roads)
    roads["fclass"] = roads["fclass"].astype(str).str.strip().str.lower()
    roads["oneway"] = roads["oneway"].astype(str).str.strip().str.upper()

    print(f"Valid source features: {source_count:,}")
    print(f"Analysis CRS: {roads.crs}")

    # --------------------------------------------------------
    # 1. Classify roads and retain excluded-road reasons.
    # --------------------------------------------------------

    eligible_mask = roads["fclass"].isin(VEHICLE_CLASSES)
    non_vehicle_mask = roads["fclass"].isin(NON_VEHICLE_CLASSES)

    roads["eligibility_reason"] = "excluded_unrecognized_road_class"
    roads.loc[non_vehicle_mask, "eligibility_reason"] = (
        "excluded_non_vehicle_class"
    )
    roads.loc[eligible_mask, "eligibility_reason"] = "eligible"

    eligible = roads.loc[eligible_mask].copy()
    excluded = roads.loc[~eligible_mask].copy()

    excluded.drop(columns="geometry").to_csv(
        OUTPUT_EXCLUDED, index=False, encoding="utf-8"
    )

    if eligible.empty:
        raise ValueError("No eligible vehicle roads remain after filtering.")

    print(f"Eligible vehicle-road features: {len(eligible):,}")
    print(f"Excluded features: {len(excluded):,}")

    # Keep an untouched copy of the eligible source geometries.
    eligible.drop(columns="eligibility_reason").to_file(
        OUTPUT_ROADS,
        layer="vehicle_eligible_roads",
        driver="GPKG",
        engine="pyogrio",
    )

    # --------------------------------------------------------
    # 2. Audit source features before building the graph.
    # --------------------------------------------------------

    feature_review = []
    for _, row in roads.iterrows():
        flags = []
        fclass = row["fclass"]
        direction = row["oneway"]
        speed = safe_number(row["maxspeed"])
        layer_value = safe_number(row["layer"])
        geom = row.geometry

        if fclass not in VEHICLE_CLASSES | NON_VEHICLE_CLASSES:
            flags.append("unrecognized_road_class")

        if fclass in {"track", "track_grade1", "track_grade2",
                      "track_grade3", "track_grade4", "track_grade5"}:
            flags.append("track_passability_unverified")

        if direction not in {"B", "F", "T"}:
            flags.append("unrecognized_oneway_code")

        if speed is not None and speed > 130:
            flags.append("maxspeed_above_130_review")

        if speed is not None and speed < 0:
            flags.append("negative_maxspeed_review")

        if is_true(row["bridge"]) and layer_value == 0:
            flags.append("bridge_layer_zero_review")

        if is_true(row["tunnel"]) and layer_value == 0:
            flags.append("tunnel_layer_zero_review")

        if geom.geom_type not in {"LineString", "MultiLineString"}:
            flags.append("unexpected_geometry_type")

        if geom.length < 5:
            flags.append("feature_length_under_5m")

        if flags:
            feature_review.append({
                "osm_id": str(row["osm_id"]),
                "fclass": fclass,
                "oneway": direction,
                "maxspeed": row["maxspeed"],
                "bridge": row["bridge"],
                "tunnel": row["tunnel"],
                "layer": row["layer"],
                "geometry_length_m": round(geom.length, 3),
                "eligible_for_vehicle_graph": bool(eligible_mask.loc[row.name]),
                "review_flags": ";".join(flags),
            })

    review_df = pd.DataFrame(
        feature_review,
        columns=[
            "osm_id", "fclass", "oneway", "maxspeed", "bridge",
            "tunnel", "layer", "geometry_length_m",
            "eligible_for_vehicle_graph", "review_flags",
        ],
    )
    review_df.to_csv(OUTPUT_REVIEW, index=False, encoding="utf-8")

    # --------------------------------------------------------
    # 3. Build a directed multigraph from existing line vertices.
    #
    # We do NOT unary-union/node every crossing. That could create
    # false junctions between roads crossing at different heights.
    # Connections are made only where line vertices coincide within
    # the centimetre-rounded node key.
    # --------------------------------------------------------

    graph = nx.MultiDiGraph()
    node_coordinates = {}
    node_feature_ids = Counter()
    edge_rows = []
    edge_geometries = []

    physical_segment_id = 0
    directed_edge_id = 0
    skipped_short_segments = 0
    skipped_unknown_directions = 0
    malformed_geometries = 0

    for _, row in eligible.iterrows():
        geom = row.geometry
        direction = row["oneway"]

        # Do not guess the direction of an unrecognized code.
        if direction not in {"B", "F", "T"}:
            skipped_unknown_directions += 1
            continue

        if geom.geom_type == "LineString":
            parts = [geom]
        elif geom.geom_type == "MultiLineString":
            parts = list(geom.geoms)
        else:
            malformed_geometries += 1
            continue

        for part_index, part in enumerate(parts):
            coords = list(part.coords)
            if len(coords) < 2:
                malformed_geometries += 1
                continue

            for vertex_index in range(len(coords) - 1):
                x1, y1 = coords[vertex_index][:2]
                x2, y2 = coords[vertex_index + 1][:2]

                length_m = math.hypot(x2 - x1, y2 - y1)

                if not math.isfinite(length_m) or length_m <= 0.01:
                    skipped_short_segments += 1
                    continue

                u = node_key(x1, y1)
                v = node_key(x2, y2)

                if u == v:
                    skipped_short_segments += 1
                    continue

                node_coordinates.setdefault(u, (x1, y1))
                node_coordinates.setdefault(v, (x2, y2))

                node_feature_ids[u] += 1
                node_feature_ids[v] += 1

                physical_segment_id += 1

                # F = digitized direction; T = reverse direction;
                # B = both directions.
                directions = [("forward", u, v)]
                if direction == "B":
                    directions.append(("reverse", v, u))
                elif direction == "T":
                    directions = [("reverse", v, u)]

                for direction_label, source_node, target_node in directions:
                    directed_edge_id += 1

                    edge_data = {
                        "edge_id": directed_edge_id,
                        "segment_id": physical_segment_id,
                        "osm_id": str(row["osm_id"]),
                        "fclass": row["fclass"],
                        "oneway": direction,
                        "direction": direction_label,
                        "length_m": length_m,
                        "bridge": str(row["bridge"]),
                        "tunnel": str(row["tunnel"]),
                        "layer": row["layer"],
                        "maxspeed": row["maxspeed"],
                    }

                    graph.add_edge(
                        source_node,
                        target_node,
                        key=directed_edge_id,
                        **edge_data,
                    )

                    edge_rows.append({
                        **edge_data,
                        "from_node": source_node,
                        "to_node": target_node,
                    })

                    edge_geometries.append(
                        LineString([(x1, y1), (x2, y2)])
                        if direction_label == "forward"
                        else LineString([(x2, y2), (x1, y1)])
                    )

    if graph.number_of_edges() == 0:
        raise ValueError(
            "No graph edges were built. Review road eligibility and geometry."
        )

    # --------------------------------------------------------
    # 4. Export graph nodes and directed edges.
    # --------------------------------------------------------

    node_rows = []
    for node_id, (x, y) in node_coordinates.items():
        node_rows.append({
            "node_id": node_id,
            "x_utm_m": x,
            "y_utm_m": y,
            "incident_directed_edges": node_feature_ids[node_id],
            "in_degree": graph.in_degree(node_id),
            "out_degree": graph.out_degree(node_id),
        })

    nodes_df = pd.DataFrame(node_rows).sort_values("node_id")
    edges_df = pd.DataFrame(edge_rows)

    nodes_df.to_csv(
        OUTPUT_NODES_CSV, index=False, encoding="utf-8"
    )
    edges_df.to_csv(
        OUTPUT_EDGES_CSV, index=False, encoding="utf-8"
    )

    edges_gdf = gpd.GeoDataFrame(
        edges_df,
        geometry=edge_geometries,
        crs=CRS_METRIC,
    )
    edges_gdf.to_file(
        OUTPUT_EDGES,
        layer="vehicle_graph_edges",
        driver="GPKG",
        engine="pyogrio",
    )

    # --------------------------------------------------------
    # 5. Connectivity and distance validation.
    # --------------------------------------------------------

    undirected = graph.to_undirected()
    component_sizes = sorted(
        (len(component) for component in nx.connected_components(undirected)),
        reverse=True,
    )

    node_count = graph.number_of_nodes()
    edge_count = graph.number_of_edges()
    total_directed_length_km = sum(
        data["length_m"]
        for _, _, data in graph.edges(data=True)
    ) / 1000.0

    physical_length_km = edges_df.drop_duplicates(
        subset=["segment_id"]
    )["length_m"].sum() / 1000.0

    class_summary = (
        eligible.groupby("fclass", dropna=False)
        .agg(
            feature_count=("osm_id", "count"),
            unique_osm_ids=("osm_id", "nunique"),
            total_clipped_length_km=(
                "geometry",
                lambda s: s.length.sum() / 1000.0,
            ),
        )
        .reset_index()
        .sort_values("feature_count", ascending=False)
    )
    class_summary.to_csv(
        OUTPUT_CLASS_SUMMARY, index=False, encoding="utf-8"
    )

    # Directed reachability is distinct from undirected connectivity.
    weak_components = nx.number_weakly_connected_components(graph)
    strong_components = nx.number_strongly_connected_components(graph)

    zero_in_degree = sum(
        1 for n in graph.nodes if graph.in_degree(n) == 0
    )
    zero_out_degree = sum(
        1 for n in graph.nodes if graph.out_degree(n) == 0
    )
    isolated_nodes = list(nx.isolates(undirected))

    # Verify all edge costs are finite and positive.
    edge_lengths = [d["length_m"] for _, _, d in graph.edges(data=True)]
    invalid_cost_edges = sum(
        1 for length in edge_lengths
        if not math.isfinite(length) or length <= 0
    )

    audit = {
        "phase": "2E",
        "status": "completed",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(INPUT_GPKG),
        "input_layer": INPUT_LAYER,
        "analysis_crs": CRS_METRIC,
        "routing_scope": "vehicle-oriented preliminary graph",
        "initial_route_cost": "distance_m",
        "source_features": source_count,
        "eligible_vehicle_features": len(eligible),
        "excluded_features": len(excluded),
        "eligible_road_classes": sorted(VEHICLE_CLASSES),
        "excluded_non_vehicle_classes": sorted(NON_VEHICLE_CLASSES),
        "direction_encoding": {
            "B": "both directions",
            "F": "digitized direction",
            "T": "reverse of digitized direction",
        },
        "node_key_rounding_m": 0.01,
        "topology_method": (
            "Uses existing line vertices and centimetre-rounded coordinates; "
            "does not automatically node every 2D crossing."
        ),
        "graph_nodes": node_count,
        "directed_graph_edges": edge_count,
        "physical_segments": int(edges_df["segment_id"].nunique()),
        "undirected_connected_components": len(component_sizes),
        "weakly_connected_components": weak_components,
        "strongly_connected_components": strong_components,
        "largest_component_nodes": component_sizes[0] if component_sizes else 0,
        "largest_component_share": (
            component_sizes[0] / node_count if node_count else 0
        ),
        "top_20_component_sizes": component_sizes[:20],
        "isolated_nodes": len(isolated_nodes),
        "zero_in_degree_nodes": zero_in_degree,
        "zero_out_degree_nodes": zero_out_degree,
        "physical_segment_length_km": round(physical_length_km, 3),
        "directed_edge_length_sum_km": round(total_directed_length_km, 3),
        "skipped_short_or_collapsed_segments": skipped_short_segments,
        "skipped_unknown_direction_features": skipped_unknown_directions,
        "malformed_geometry_parts": malformed_geometries,
        "invalid_edge_costs": invalid_cost_edges,
        "review_flagged_source_features": len(review_df),
        "track_features_included_but_unverified": int(
            eligible["fclass"].isin({
                "track", "track_grade1", "track_grade2",
                "track_grade3", "track_grade4", "track_grade5",
            }).sum()
        ),
        "limitations": [
            "This is a preliminary graph, not a field-validated routing network.",
            "Vehicle eligibility is inferred from road class; private access, "
            "width, surface, seasonal passability, and truck restrictions "
            "are not fully available in the input.",
            "Track roads are included provisionally and may not support "
            "loaded collection vehicles.",
            "Road connections are made at coincident existing vertices only. "
            "Some legitimate junctions may remain disconnected.",
            "Centimetre coordinate rounding can merge extremely close vertices.",
            "Crossings without shared vertices are not automatically connected; "
            "this reduces false junctions but may miss real intersections.",
            "Bridge, tunnel, and layer tags are retained for review; "
            "they do not by themselves validate every junction.",
            "Distance costs use projected geometry lengths, not travel time.",
            "The graph is based on the Sidama plus 5 km buffer extract.",
            "A connected component does not establish real-world passability."
        ],
        "outputs": {
            "eligible_roads_gpkg": str(OUTPUT_ROADS),
            "graph_edges_gpkg": str(OUTPUT_EDGES),
            "nodes_csv": str(OUTPUT_NODES_CSV),
            "edges_csv": str(OUTPUT_EDGES_CSV),
            "road_class_summary_csv": str(OUTPUT_CLASS_SUMMARY),
            "excluded_roads_csv": str(OUTPUT_EXCLUDED),
            "review_flags_csv": str(OUTPUT_REVIEW),
            "audit_json": str(OUTPUT_JSON),
            "audit_text": str(OUTPUT_TXT),
        },
    }

    OUTPUT_JSON.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    report = [
        "PHASE 2E - VEHICLE ROUTING GRAPH AUDIT",
        "=" * 72,
        f"Status: {audit['status']}",
        f"Generated UTC: {audit['generated_utc']}",
        f"Input features: {source_count:,}",
        f"Eligible vehicle-road features: {len(eligible):,}",
        f"Excluded features: {len(excluded):,}",
        "",
        "GRAPH",
        "-" * 72,
        f"CRS: {CRS_METRIC}",
        f"Nodes: {node_count:,}",
        f"Directed edges: {edge_count:,}",
        f"Physical segments: {audit['physical_segments']:,}",
        f"Undirected components: {len(component_sizes):,}",
        f"Weakly connected components: {weak_components:,}",
        f"Strongly connected components: {strong_components:,}",
        f"Largest component nodes: {audit['largest_component_nodes']:,}",
        f"Largest component share: {audit['largest_component_share']:.4%}",
        f"Isolated nodes: {len(isolated_nodes):,}",
        f"Zero in-degree nodes: {zero_in_degree:,}",
        f"Zero out-degree nodes: {zero_out_degree:,}",
        "",
        "DISTANCE VALIDATION",
        "-" * 72,
        f"Physical segment length: {physical_length_km:,.3f} km",
        f"Directed-edge length sum: {total_directed_length_km:,.3f} km",
        f"Invalid edge costs: {invalid_cost_edges:,}",
        f"Skipped short/collapsed segments: {skipped_short_segments:,}",
        f"Unknown-direction features skipped: {skipped_unknown_directions:,}",
        "",
        "ROAD CLASS COUNTS",
        "-" * 72,
    ]

    for road_class, count in eligible["fclass"].value_counts().items():
        report.append(f"{road_class}: {count:,}")

    report += [
        "",
        "IMPORTANT LIMITATIONS",
        "-" * 72,
        *[f"- {item}" for item in audit["limitations"]],
        "",
        "OUTPUTS",
        "-" * 72,
        *[f"{key}: {value}" for key, value in audit["outputs"].items()],
    ]

    write_text_report(OUTPUT_TXT, report)

    print("\n" + "=" * 72)
    print("PHASE 2E COMPLETED")
    print("=" * 72)
    print(f"Eligible roads: {len(eligible):,}")
    print(f"Graph nodes: {node_count:,}")
    print(f"Directed edges: {edge_count:,}")
    print(f"Physical segments: {audit['physical_segments']:,}")
    print(f"Undirected components: {len(component_sizes):,}")
    print(f"Largest component share: {audit['largest_component_share']:.2%}")
    print(f"Physical segment length: {physical_length_km:,.3f} km")
    print(f"Invalid edge costs: {invalid_cost_edges}")
    print(f"JSON audit: {OUTPUT_JSON}")
    print(f"Text audit: {OUTPUT_TXT}")
    print("\nReview the audit before using the graph for operational routing.")


if __name__ == "__main__":
    main()
