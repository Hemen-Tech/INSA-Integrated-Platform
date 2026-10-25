
from pathlib import Path
import json

import networkx as nx
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"

ORIGIN = "N47495334_69998829"
DESTINATION = "N50091508_68964365"

NODES_FILE = PROCESSED / "phase2e_vehicle_graph_nodes.csv"
EDGES_FILE = PROCESSED / "phase2e_vehicle_graph_edges.csv"
DETAILS_FILE = PROCESSED / "phase2e1_route_details.csv"
PAIRS_FILE = PROCESSED / "phase2e1_route_pair_results.csv"

OUTPUT_JSON = PROCESSED / "phase2e1_detour_diagnostic.json"
OUTPUT_TXT = PROCESSED / "phase2e1_detour_diagnostic.txt"


def main():
    print("=" * 72)
    print("PHASE 2E.1 — FOCUSED DETOUR DIAGNOSTIC")
    print("=" * 72)

    for path in [NODES_FILE, EDGES_FILE, DETAILS_FILE, PAIRS_FILE]:
        if not path.exists():
            raise FileNotFoundError(f"Required input not found: {path}")

    nodes = pd.read_csv(NODES_FILE, dtype={"node_id": str})
    edges = pd.read_csv(
        EDGES_FILE,
        dtype={
            "from_node": str,
            "to_node": str,
            "fclass": str,
            "direction": str,
        },
    )
    details = pd.read_csv(
        DETAILS_FILE,
        dtype={
            "from_node": str,
            "to_node": str,
            "route_id": str,
        },
    )
    pairs = pd.read_csv(
        PAIRS_FILE,
        dtype={
            "origin_node": str,
            "destination_node": str,
        },
    )

    pair = pairs[
        (pairs["origin_node"] == ORIGIN)
        & (pairs["destination_node"] == DESTINATION)
    ]

    if pair.empty:
        raise ValueError("The flagged origin/destination pair was not found.")

    route = details[details["route_id"].astype(str) == "5"].copy()

    if route.empty:
        raise ValueError("Detailed route_id 5 was not found.")

    route_first = str(route.iloc[0]["from_node"])
    route_last = str(route.iloc[-1]["to_node"])
    route_matches = (
        route_first == ORIGIN and route_last == DESTINATION
    )

    # Build the directed graph using the same length-based cost as the audit.
    graph = nx.DiGraph()

    for row in edges.itertuples(index=False):
        graph.add_edge(
            str(row.from_node),
            str(row.to_node),
            weight=float(row.length_m),
            fclass=str(row.fclass),
        )

    # Confirm the detailed route connects continuously.
    continuity_errors = []
    for i in range(len(route) - 1):
        current_to = str(route.iloc[i]["to_node"])
        next_from = str(route.iloc[i + 1]["from_node"])
        if current_to != next_from:
            continuity_errors.append(
                {
                    "segment_index": i,
                    "current_to": current_to,
                    "next_from": next_from,
                }
            )

    route_distance_km = (
        pd.to_numeric(route["segment_length_m"], errors="coerce").sum()
        / 1000
    )

    # Summarize road classes on the detailed route.
    class_summary = []
    if "fclass" in route.columns:
        lengths = pd.to_numeric(
            route["segment_length_m"], errors="coerce"
        )
        temp = route.assign(_length_m=lengths)
        grouped = (
            temp.groupby("fclass", dropna=False)["_length_m"]
            .agg(["size", "sum"])
            .reset_index()
        )
        for row in grouped.to_dict("records"):
            class_summary.append(
                {
                    "road_class": str(row["fclass"]),
                    "segment_rows": int(row["size"]),
                    "distance_km": round(float(row["sum"]) / 1000, 3),
                }
            )

    node_lookup = nodes.set_index("node_id", drop=False)

    # Inspect nodes near each endpoint in projected UTM coordinates.
    endpoint_neighborhoods = {}
    for endpoint in [ORIGIN, DESTINATION]:
        if endpoint not in node_lookup.index:
            endpoint_neighborhoods[endpoint] = {
                "found": False,
                "message": "Endpoint missing from node CSV",
            }
            continue

        base = node_lookup.loc[endpoint]
        x = float(base["x_utm_m"])
        y = float(base["y_utm_m"])

        dx = pd.to_numeric(nodes["x_utm_m"], errors="coerce") - x
        dy = pd.to_numeric(nodes["y_utm_m"], errors="coerce") - y
        distance = (dx**2 + dy**2) ** 0.5

        nearby = nodes.loc[distance <= 500].copy()
        nearby["distance_from_endpoint_m"] = distance[distance <= 500]
        nearby = nearby.sort_values("distance_from_endpoint_m").head(15)

        endpoint_neighborhoods[endpoint] = {
            "found": True,
            "x_utm_m": x,
            "y_utm_m": y,
            "in_degree": int(base["in_degree"]),
            "out_degree": int(base["out_degree"]),
            "nodes_within_500m": [
                {
                    "node_id": str(r["node_id"]),
                    "distance_m": round(
                        float(r["distance_from_endpoint_m"]), 2
                    ),
                    "in_degree": int(r["in_degree"]),
                    "out_degree": int(r["out_degree"]),
                }
                for r in nearby.to_dict("records")
            ],
        }

    # Compare direct/reverse pair entries and graph reachability.
    reverse_pair = pairs[
        (pairs["origin_node"] == DESTINATION)
        & (pairs["destination_node"] == ORIGIN)
    ]

    if ORIGIN not in graph or DESTINATION not in graph:
        reachable = False
        shortest_km = None
        graph_error = "One or both endpoints are absent from the edge graph."
    else:
        reachable = nx.has_path(graph, ORIGIN, DESTINATION)
        shortest_km = (
            round(
                nx.shortest_path_length(
                    graph, ORIGIN, DESTINATION, weight="weight"
                ) / 1000,
                3,
            )
            if reachable
            else None
        )
        graph_error = None

    result = {
        "origin": ORIGIN,
        "destination": DESTINATION,
        "pair_result_rows": pair.to_dict("records"),
        "reverse_pair_result_rows": reverse_pair.to_dict("records"),
        "detailed_route_id": "5",
        "detailed_route_first_node": route_first,
        "detailed_route_last_node": route_last,
        "detailed_route_matches_pair": route_matches,
        "detailed_route_segment_rows": int(len(route)),
        "detailed_route_distance_km": round(float(route_distance_km), 3),
        "detailed_route_continuity_error_count": len(continuity_errors),
        "detailed_route_continuity_errors_first_10": continuity_errors[:10],
        "road_class_summary": class_summary,
        "graph_reachable": reachable,
        "graph_shortest_path_distance_km": shortest_km,
        "graph_error": graph_error,
        "endpoint_neighborhoods_500m": endpoint_neighborhoods,
        "interpretation": (
            "Diagnostic evidence only. Nearby nodes and graph topology do not "
            "by themselves establish real-world road passability."
        ),
    }

    OUTPUT_JSON.write_text(
        json.dumps(result, indent=2, default=str),
        encoding="utf-8",
    )

    lines = [
        "PHASE 2E.1 — FOCUSED DETOUR DIAGNOSTIC",
        "=" * 72,
        f"Origin: {ORIGIN}",
        f"Destination: {DESTINATION}",
        f"Detailed route ID 5 matches pair: {route_matches}",
        f"Detailed route segments: {len(route)}",
        f"Detailed route distance: {route_distance_km:.3f} km",
        f"Continuity errors: {len(continuity_errors)}",
        f"Graph reachable: {reachable}",
        f"Graph shortest path: {shortest_km} km",
        "",
        "ROAD CLASS SUMMARY",
        "-" * 72,
    ]

    for item in class_summary:
        lines.append(
            f"{item['road_class']}: {item['segment_rows']} rows, "
            f"{item['distance_km']:.3f} km"
        )

    lines.extend(
        [
            "",
            "ENDPOINT NEIGHBORHOODS (within 500 m)",
            "-" * 72,
        ]
    )

    for endpoint, info in endpoint_neighborhoods.items():
        lines.append(f"{endpoint}:")
        lines.append(json.dumps(info, indent=2))

    lines.extend(
        [
            "",
            "Interpretation: this is a network-data diagnostic, not proof of",
            "real-world road passability.",
        ]
    )

    OUTPUT_TXT.write_text("\n".join(lines), encoding="utf-8")

    print(f"Detailed route matches flagged pair: {route_matches}")
    print(f"Detailed route distance: {route_distance_km:.3f} km")
    print(f"Route continuity errors: {len(continuity_errors)}")
    print(f"Graph shortest path: {shortest_km} km")
    print("\nRoad class summary:")
    for item in class_summary:
        print(
            f"  {item['road_class']}: {item['segment_rows']} rows, "
            f"{item['distance_km']:.3f} km"
        )

    print("\nOutputs:")
    print(OUTPUT_TXT)
    print(OUTPUT_JSON)


if __name__ == "__main__":
    main()
