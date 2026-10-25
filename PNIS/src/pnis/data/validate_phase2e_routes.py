
from __future__ import annotations

import json
import math
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import pandas as pd


# ============================================================
# PHASE 2E.1 — VEHICLE ROAD-GRAPH ROUTE VALIDATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

NODES_FILE = PROCESSED_DIR / "phase2e_vehicle_graph_nodes.csv"
EDGES_FILE = PROCESSED_DIR / "phase2e_vehicle_graph_edges.csv"

OUTPUT_PAIRS = PROCESSED_DIR / "phase2e1_route_pair_results.csv"
OUTPUT_DETAILS = PROCESSED_DIR / "phase2e1_route_details.csv"
OUTPUT_COMPONENTS = PROCESSED_DIR / "phase2e1_component_summary.csv"
OUTPUT_REPORT_JSON = PROCESSED_DIR / "phase2e1_route_validation_audit.json"
OUTPUT_REPORT_TXT = PROCESSED_DIR / "phase2e1_route_validation_audit.txt"

RANDOM_SEED = 42
GRID_SIZE = 4
MAX_TEST_NODES = 16
MAX_ROUTE_PAIRS = 40
MAX_DETAILED_ROUTES = 12

# Screening threshold only; this is not a road-engineering standard.
DETOUR_RATIO_WARNING = 3.0

TRACK_CLASSES = {
    "track",
    "track_grade1",
    "track_grade2",
    "track_grade3",
    "track_grade4",
    "track_grade5",
}


def log(message: str) -> None:
    print(message, flush=True)


def haversine_projected_distance(x1, y1, x2, y2) -> float:
    """Euclidean distance in meters for nodes in the same projected CRS."""
    return math.hypot(float(x2) - float(x1), float(y2) - float(y1))


def choose_spatially_distributed_nodes(
    nodes: pd.DataFrame,
    eligible_node_ids: set[str],
) -> list[str]:
    """Choose up to 16 existing graph nodes spread across the study area."""
    candidates = nodes[nodes["node_id"].astype(str).isin(eligible_node_ids)].copy()

    if candidates.empty:
        return []

    candidates["node_id"] = candidates["node_id"].astype(str)
    candidates["x_utm_m"] = pd.to_numeric(candidates["x_utm_m"], errors="coerce")
    candidates["y_utm_m"] = pd.to_numeric(candidates["y_utm_m"], errors="coerce")
    candidates = candidates.dropna(subset=["x_utm_m", "y_utm_m"])

    if candidates.empty:
        return []

    xmin, xmax = candidates["x_utm_m"].min(), candidates["x_utm_m"].max()
    ymin, ymax = candidates["y_utm_m"].min(), candidates["y_utm_m"].max()

    xspan = max(xmax - xmin, 1.0)
    yspan = max(ymax - ymin, 1.0)

    candidates["grid_x"] = (
        ((candidates["x_utm_m"] - xmin) / xspan * GRID_SIZE)
        .astype(int)
        .clip(upper=GRID_SIZE - 1)
    )
    candidates["grid_y"] = (
        ((candidates["y_utm_m"] - ymin) / yspan * GRID_SIZE)
        .astype(int)
        .clip(upper=GRID_SIZE - 1)
    )

    # For each occupied grid cell, select the node closest to its center.
    selected = []
    for _, group in candidates.groupby(["grid_x", "grid_y"], sort=True):
        if len(selected) >= MAX_TEST_NODES:
            break

        gx = int(group["grid_x"].iloc[0])
        gy = int(group["grid_y"].iloc[0])

        center_x = xmin + (gx + 0.5) * xspan / GRID_SIZE
        center_y = ymin + (gy + 0.5) * yspan / GRID_SIZE

        distances = (
            (group["x_utm_m"] - center_x) ** 2
            + (group["y_utm_m"] - center_y) ** 2
        )
        best = group.loc[distances.idxmin(), "node_id"]
        if best not in selected:
            selected.append(best)

    # Fallback if the spatial grid produced too few nodes.
    if len(selected) < min(4, len(candidates)):
        remaining = candidates.loc[~candidates["node_id"].isin(selected)]
        for node_id in remaining["node_id"].head(MAX_TEST_NODES - len(selected)):
            selected.append(node_id)

    return selected[:MAX_TEST_NODES]


def get_edge_attributes(graph: nx.MultiDiGraph, u: str, v: str) -> dict:
    """Return the shortest-distance parallel edge for one path step."""
    parallel = graph.get_edge_data(u, v)
    if not parallel:
        raise ValueError(f"Path step has no corresponding edge: {u} -> {v}")

    return min(parallel.values(), key=lambda attrs: attrs["length_m"])


def main() -> None:
    started = datetime.now(timezone.utc)
    log("=" * 72)
    log("PHASE 2E.1 — VEHICLE ROUTE-GRAPH VALIDATION")
    log("=" * 72)
    log(f"Project root: {PROJECT_ROOT}")

    for path in (NODES_FILE, EDGES_FILE):
        if not path.exists():
            raise FileNotFoundError(f"Required Phase 2E file not found: {path}")

    log("\nLoading node and edge CSV files...")
    nodes = pd.read_csv(NODES_FILE, dtype={"node_id": str})
    edges = pd.read_csv(
        EDGES_FILE,
        dtype={
            "edge_id": str,
            "segment_id": str,
            "osm_id": str,
            "from_node": str,
            "to_node": str,
            "fclass": str,
            "oneway": str,
            "direction": str,
        },
    )

    required_nodes = {"node_id", "x_utm_m", "y_utm_m"}
    required_edges = {
        "edge_id", "from_node", "to_node", "length_m", "fclass",
        "osm_id", "direction",
    }

    if not required_nodes.issubset(nodes.columns):
        raise ValueError(f"Node file missing columns: {required_nodes - set(nodes.columns)}")
    if not required_edges.issubset(edges.columns):
        raise ValueError(f"Edge file missing columns: {required_edges - set(edges.columns)}")

    nodes["node_id"] = nodes["node_id"].astype(str)
    edges["from_node"] = edges["from_node"].astype(str)
    edges["to_node"] = edges["to_node"].astype(str)
    edges["length_m"] = pd.to_numeric(edges["length_m"], errors="coerce")
    edges["fclass"] = edges["fclass"].fillna("").astype(str)

    invalid_costs = int(
        (edges["length_m"].isna() | ~edges["length_m"].map(math.isfinite) |
         (edges["length_m"] <= 0)).sum()
    )
    known_node_ids = set(nodes["node_id"])
    missing_endpoint_rows = int(
        (
            ~edges["from_node"].isin(known_node_ids)
            | ~edges["to_node"].isin(known_node_ids)
        ).sum()
    )

    log(f"Node rows: {len(nodes):,}")
    log(f"Directed edge rows: {len(edges):,}")
    log(f"Invalid edge-cost rows: {invalid_costs:,}")
    log(f"Rows with unknown edge endpoints: {missing_endpoint_rows:,}")

    if invalid_costs or missing_endpoint_rows:
        raise ValueError(
            "Input graph failed basic validation. Fix invalid costs or endpoints "
            "before route testing."
        )

    log("\nBuilding directed graph...")
    graph = nx.MultiDiGraph()
    graph.add_nodes_from(nodes["node_id"].tolist())

    for row in edges.itertuples(index=False):
        graph.add_edge(
            str(row.from_node),
            str(row.to_node),
            key=str(row.edge_id),
            edge_id=str(row.edge_id),
            length_m=float(row.length_m),
            fclass=str(row.fclass),
            osm_id=str(row.osm_id),
            direction=str(row.direction),
        )

    node_lookup = nodes.set_index("node_id")[["x_utm_m", "y_utm_m"]].to_dict("index")

    log("\nCalculating components...")
    weak_components = list(nx.weakly_connected_components(graph))
    strong_components = list(nx.strongly_connected_components(graph))
    weak_components.sort(key=len, reverse=True)
    strong_components.sort(key=len, reverse=True)

    component_rows = []
    for component_type, components in (
        ("weakly_connected", weak_components),
        ("strongly_connected", strong_components),
    ):
        for rank, component in enumerate(components, start=1):
            component_rows.append(
                {
                    "component_type": component_type,
                    "component_rank_by_size": rank,
                    "node_count": len(component),
                    "share_of_all_nodes": len(component) / max(graph.number_of_nodes(), 1),
                    "is_largest_component": rank == 1,
                }
            )

    pd.DataFrame(component_rows).to_csv(OUTPUT_COMPONENTS, index=False)

    largest_scc = set(strong_components[0]) if strong_components else set()
    log(f"Weakly connected components: {len(weak_components):,}")
    log(f"Strongly connected components: {len(strong_components):,}")
    log(f"Largest strongly connected component: {len(largest_scc):,} nodes")

    # These are existing network nodes, not real collection locations.
    test_nodes = choose_spatially_distributed_nodes(nodes, largest_scc)
    if len(test_nodes) < 2:
        raise RuntimeError("Could not select at least two test nodes from the largest SCC.")

    log(f"Selected spatially distributed test nodes: {len(test_nodes)}")

    # Create deterministic unique node pairs.
    rng = random.Random(RANDOM_SEED)
    all_pairs = [
        (test_nodes[i], test_nodes[j])
        for i in range(len(test_nodes))
        for j in range(i + 1, len(test_nodes))
    ]
    rng.shuffle(all_pairs)
    pairs = all_pairs[:MAX_ROUTE_PAIRS]

    # Add a few reverse-direction checks where possible.
    reverse_pairs = [(destination, origin) for origin, destination in pairs[:5]]
    pairs = list(dict.fromkeys(pairs + reverse_pairs))

    # Calculate shortest-path distances once per unique origin.
    log("\nCalculating shortest-path distances...")
    distances_by_origin = {}
    for origin in sorted({origin for origin, _ in pairs}):
        distances_by_origin[origin] = nx.single_source_dijkstra_path_length(
            graph, origin, weight="length_m"
        )

    pair_rows = []
    for pair_number, (origin, destination) in enumerate(pairs, start=1):
        origin_xy = node_lookup.get(origin, {})
        destination_xy = node_lookup.get(destination, {})

        straight_line = float("nan")
        if all(
            pd.notna(value)
            for value in (
                origin_xy.get("x_utm_m"),
                origin_xy.get("y_utm_m"),
                destination_xy.get("x_utm_m"),
                destination_xy.get("y_utm_m"),
            )
        ):
            straight_line = haversine_projected_distance(
                origin_xy["x_utm_m"],
                origin_xy["y_utm_m"],
                destination_xy["x_utm_m"],
                destination_xy["y_utm_m"],
            )

        route_distance = distances_by_origin[origin].get(destination)
        reachable = route_distance is not None
        detour_ratio = (
            float(route_distance) / straight_line
            if reachable and straight_line > 0
            else float("nan")
        )

        pair_rows.append(
            {
                "pair_id": pair_number,
                "origin_node": origin,
                "destination_node": destination,
                "reachable_by_directed_edges": reachable,
                "straight_line_distance_m": straight_line,
                "shortest_path_distance_m": (
                    float(route_distance) if reachable else float("nan")
                ),
                "shortest_path_distance_km": (
                    float(route_distance) / 1000 if reachable else float("nan")
                ),
                "detour_ratio": detour_ratio,
                "detour_warning": (
                    bool(detour_ratio > DETOUR_RATIO_WARNING)
                    if math.isfinite(detour_ratio)
                    else False
                ),
                "test_node_type": "existing_network_nodes_not_real_facilities",
            }
        )

    pair_results = pd.DataFrame(pair_rows)
    pair_results.to_csv(OUTPUT_PAIRS, index=False)

    log(f"Route-pair tests: {len(pair_results):,}")
    log(f"Reachable pairs: {int(pair_results['reachable_by_directed_edges'].sum()):,}")
    log(f"Unreachable pairs: {int((~pair_results['reachable_by_directed_edges']).sum()):,}")

    # Trace detailed paths for a smaller reproducible subset.
    log("\nTracing detailed routes and checking track-road dependence...")
    detail_rows = []
    detailed_pairs = pair_results[
        pair_results["reachable_by_directed_edges"]
    ].head(MAX_DETAILED_ROUTES)

    for route_number, row in enumerate(detailed_pairs.itertuples(index=False), start=1):
        origin = row.origin_node
        destination = row.destination_node
        path = nx.shortest_path(graph, origin, destination, weight="length_m")

        route_distance = 0.0
        track_distance = 0.0
        track_edge_count = 0
        road_class_counts = Counter()
        osm_ids = []

        for step_number, (u, v) in enumerate(zip(path[:-1], path[1:]), start=1):
            attrs = get_edge_attributes(graph, u, v)
            length = float(attrs["length_m"])
            road_class = attrs["fclass"]
            route_distance += length
            road_class_counts[road_class] += 1
            osm_ids.append(attrs["osm_id"])

            if road_class in TRACK_CLASSES:
                track_distance += length
                track_edge_count += 1

            detail_rows.append(
                {
                    "route_id": route_number,
                    "step_number": step_number,
                    "from_node": u,
                    "to_node": v,
                    "edge_id": attrs["edge_id"],
                    "osm_id": attrs["osm_id"],
                    "road_class": road_class,
                    "direction": attrs["direction"],
                    "segment_length_m": length,
                    "is_provisional_track": road_class in TRACK_CLASSES,
                }
            )

        # Add a route-level summary row to the pair-results file separately below.
        track_share = track_distance / route_distance if route_distance > 0 else 0.0
        pair_results.loc[
            (pair_results["origin_node"] == origin)
            & (pair_results["destination_node"] == destination),
            "track_distance_m",
        ] = track_distance
        pair_results.loc[
            (pair_results["origin_node"] == origin)
            & (pair_results["destination_node"] == destination),
            "track_distance_share",
        ] = track_share
        pair_results.loc[
            (pair_results["origin_node"] == origin)
            & (pair_results["destination_node"] == destination),
            "track_dependent_route_warning",
        ] = bool(track_distance > 0)

    pd.DataFrame(detail_rows).to_csv(OUTPUT_DETAILS, index=False)
    pair_results.to_csv(OUTPUT_PAIRS, index=False)

    reachable = pair_results[pair_results["reachable_by_directed_edges"]]
    ratios = reachable["detour_ratio"].dropna()
    track_checked = pair_results.get(
        "track_dependent_route_warning", pd.Series(dtype=bool)
    ).fillna(False)

    report = {
        "status": "completed",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(
            (datetime.now(timezone.utc) - started).total_seconds(), 2
        ),
        "method": {
            "edge_cost": "projected distance in meters",
            "route_direction": "directed edges respected",
            "test_locations": (
                "existing graph nodes only; not real markets, farms, warehouses, "
                "or collection points"
            ),
            "test_node_selection": (
                f"Up to {MAX_TEST_NODES} spatially distributed nodes from the "
                "largest strongly connected component"
            ),
            "random_seed": RANDOM_SEED,
            "detour_ratio_warning_threshold": DETOUR_RATIO_WARNING,
            "detour_threshold_note": (
                "Configurable screening heuristic, not a validated transport standard"
            ),
            "track_classes_flagged": sorted(TRACK_CLASSES),
            "detailed_route_count": int(pair_results["track_distance_share"].notna().sum())
            if "track_distance_share" in pair_results.columns
            else 0,
        },
        "input": {
            "nodes_file": str(NODES_FILE),
            "edges_file": str(EDGES_FILE),
            "node_rows": int(len(nodes)),
            "directed_edge_rows": int(len(edges)),
            "invalid_edge_cost_rows": invalid_costs,
            "unknown_endpoint_rows": missing_endpoint_rows,
        },
        "connectivity": {
            "weakly_connected_components": len(weak_components),
            "strongly_connected_components": len(strong_components),
            "largest_scc_nodes": len(largest_scc),
            "largest_scc_share": len(largest_scc) / max(graph.number_of_nodes(), 1),
        },
        "routing_tests": {
            "selected_test_nodes": len(test_nodes),
            "pairs_tested": int(len(pair_results)),
            "reachable_pairs": int(pair_results["reachable_by_directed_edges"].sum()),
            "unreachable_pairs": int((~pair_results["reachable_by_directed_edges"]).sum()),
            "median_shortest_path_km": (
                float(reachable["shortest_path_distance_km"].median())
                if len(reachable) else None
            ),
            "max_shortest_path_km": (
                float(reachable["shortest_path_distance_km"].max())
                if len(reachable) else None
            ),
            "median_detour_ratio": float(ratios.median()) if len(ratios) else None,
            "detour_warning_count": int(pair_results["detour_warning"].sum()),
            "detailed_routes_with_track_use": int(track_checked.sum()),
        },
        "limitations": [
            "Test nodes are technical network nodes, not verified real-world facilities.",
            "Graph validation does not establish actual road passability or truck suitability.",
            "Distance is optimized; travel time, traffic, road condition, and seasonality are not modeled.",
            "Track roads remain provisional and require field or authoritative source validation.",
            "The detour ratio threshold is a configurable screening heuristic.",
            "Snapping real facilities cannot be evaluated until verified facility coordinates are supplied.",
        ],
        "outputs": [
            str(OUTPUT_PAIRS),
            str(OUTPUT_DETAILS),
            str(OUTPUT_COMPONENTS),
            str(OUTPUT_REPORT_JSON),
            str(OUTPUT_REPORT_TXT),
        ],
    }

    OUTPUT_REPORT_JSON.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "PHASE 2E.1 — VEHICLE ROUTE-GRAPH VALIDATION",
        "=" * 72,
        f"Generated UTC: {report['generated_utc']}",
        f"Status: {report['status']}",
        "",
        "INPUT AND BASIC VALIDATION",
        "-" * 72,
        f"Node rows: {len(nodes):,}",
        f"Directed edge rows: {len(edges):,}",
        f"Invalid edge-cost rows: {invalid_costs:,}",
        f"Rows with unknown endpoints: {missing_endpoint_rows:,}",
        "",
        "CONNECTIVITY",
        "-" * 72,
        f"Weakly connected components: {len(weak_components):,}",
        f"Strongly connected components: {len(strong_components):,}",
        f"Largest strongly connected component nodes: {len(largest_scc):,}",
        f"Largest SCC share: {report['connectivity']['largest_scc_share']:.4%}",
        "",
        "ROUTE TESTS",
        "-" * 72,
        f"Selected test nodes: {len(test_nodes):,}",
        f"Directed node pairs tested: {len(pair_results):,}",
        f"Reachable pairs: {int(pair_results['reachable_by_directed_edges'].sum()):,}",
        f"Unreachable pairs: {int((~pair_results['reachable_by_directed_edges']).sum()):,}",
        f"Median shortest-path distance: {report['routing_tests']['median_shortest_path_km']}",
        f"Maximum shortest-path distance: {report['routing_tests']['max_shortest_path_km']}",
        f"Median detour ratio: {report['routing_tests']['median_detour_ratio']}",
        f"Detour warnings (> {DETOUR_RATIO_WARNING:g}): {int(pair_results['detour_warning'].sum()):,}",
        f"Detailed routes traced: {len(detailed_pairs):,}",
        f"Detailed routes using tracks: {int(track_checked.sum()):,}",
        "",
        "INTERPRETATION",
        "-" * 72,
        "These are graph-level tests between existing network nodes, not real facilities.",
        "They verify computational reachability and distance calculations, not road passability.",
        "A detour warning is a screening flag, not proof of an invalid route.",
        "Track use is flagged because track passability for loaded collection vehicles is unverified.",
        "Real facility snapping and operational route validation require actual coordinates.",
        "",
        "OUTPUTS",
        "-" * 72,
    ]
    lines.extend(str(path) for path in report["outputs"])
    OUTPUT_REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    log("\n" + "=" * 72)
    log("PHASE 2E.1 COMPLETED")
    log("=" * 72)
    log(f"Route-pair results: {OUTPUT_PAIRS}")
    log(f"Detailed route edges: {OUTPUT_DETAILS}")
    log(f"Component summary: {OUTPUT_COMPONENTS}")
    log(f"Text audit: {OUTPUT_REPORT_TXT}")
    log(f"JSON audit: {OUTPUT_REPORT_JSON}")


if __name__ == "__main__":
    main()
