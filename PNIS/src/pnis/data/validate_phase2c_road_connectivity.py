
from __future__ import annotations

import json
import math
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd
import shapely
from shapely.geometry import LineString, MultiLineString, GeometryCollection


# ============================================================
# PHASE 2C V2: SIDAMA BUFFERED ROAD CONNECTIVITY AUDIT
# ============================================================
# Main correction:
#   Select candidate roads from the FULL Ethiopia road layer,
#   not only roads previously selected for intersecting Sidama.
#
# Important limitations:
#   - This is a preliminary geometric graph, not a validated
#     navigation/routing network.
#   - Bridge/tunnel/road-level separation is not fully resolved.
#   - Road access, one-way rules, speed, surface and seasonality
#     are not used for routing.
#
# Original phase2c_* outputs are preserved.
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
GEOGRAPHIC_DIR = DATA_DIR / "geographic"

SOURCE_GPKG = GEOGRAPHIC_DIR / "ethiopia.gpkg"
ADMIN_LAYER = "gis_osm_adminareas_a_free"
ROAD_LAYER = "gis_osm_roads_free"

ANALYSIS_CRS = "EPSG:32637"
BUFFER_METRES = 5000

OUTPUT_GPKG = DATA_DIR / "phase2c_v2_sidama_buffered_roads.gpkg"
NODES_CSV = DATA_DIR / "phase2c_v2_road_nodes.csv"
EDGES_CSV = DATA_DIR / "phase2c_v2_road_edges.csv"
REPORT_JSON = DATA_DIR / "phase2c_v2_road_connectivity_audit.json"
REPORT_TXT = DATA_DIR / "phase2c_v2_road_connectivity_audit.txt"


def extract_lines(geometry):
    """Return all non-empty LineString parts in a geometry."""
    if geometry is None or geometry.is_empty:
        return []

    if geometry.geom_type == "LineString":
        return [geometry] if len(geometry.coords) >= 2 else []

    if geometry.geom_type in ("MultiLineString", "GeometryCollection"):
        output = []
        for part in geometry.geoms:
            output.extend(extract_lines(part))
        return output

    return []


def find_name_column(frame):
    """Find the likely administrative name field."""
    candidates = ("name", "NAME", "name_en", "NAME_EN", "admin_name")
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate

    for column in frame.columns:
        if "name" in str(column).lower():
            return column

    raise ValueError(
        "Could not identify an administrative name field. "
        f"Available columns: {list(frame.columns)}"
    )


def write_text_report(report):
    """Write a readable text summary from the JSON report."""
    lines = [
        "PHASE 2C V2 — SIDAMA BUFFERED ROAD CONNECTIVITY AUDIT",
        "=" * 64,
        f"Generated UTC: {report['generated_utc']}",
        f"Status: {report['status']}",
        "",
        "METHOD",
        "-" * 64,
        f"Source GeoPackage: {report['source_gpkg']}",
        f"Road layer: {report['road_layer']}",
        f"Administrative layer: {report['admin_layer']}",
        f"Analysis CRS: {report['analysis_crs']}",
        f"Buffer distance: {report['buffer_metres']} metres",
        "Road selection: full road layer, bounding-box prefilter,",
        "then exact intersection with the projected buffer.",
        "",
        "ROAD SELECTION AND CLIPPING",
        "-" * 64,
    ]

    selection = report.get("road_selection", {})
    for key, value in selection.items():
        lines.append(f"{key}: {value}")

    lines.extend([
        "",
        "ROAD CLASS COUNTS (clipped features)",
        "-" * 64,
    ])

    for road_class, count in report.get("road_class_counts", {}).items():
        lines.append(f"{road_class}: {count}")

    graph = report.get("graph", {})
    lines.extend([
        "",
        "PRELIMINARY GEOMETRIC GRAPH",
        "-" * 64,
    ])

    for key, value in graph.items():
        if key != "component_sizes_top_20":
            lines.append(f"{key}: {value}")

    lines.extend([
        "",
        "Largest connected-component sizes (top 20):",
        str(graph.get("component_sizes_top_20", [])),
        "",
        "LIMITATIONS AND INTERPRETATION",
        "-" * 64,
    ])

    for item in report.get("limitations", []):
        lines.append(f"- {item}")

    lines.extend([
        "",
        "OUTPUT FILES",
        "-" * 64,
    ])

    for key, value in report.get("outputs", {}).items():
        lines.append(f"{key}: {value}")

    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("PHASE 2C V2: FULL-LAYER ROAD SELECTION AND CONNECTIVITY AUDIT")
    print("=" * 72)

    if not SOURCE_GPKG.exists():
        raise FileNotFoundError(f"Source GeoPackage not found: {SOURCE_GPKG}")

    print("\n[1/8] Reading administrative boundary...")
    admin = gpd.read_file(
        SOURCE_GPKG,
        layer=ADMIN_LAYER,
        engine="pyogrio",
    )

    if admin.empty:
        raise ValueError(f"Administrative layer is empty: {ADMIN_LAYER}")

    name_column = find_name_column(admin)
    sidama = admin[
        admin[name_column].astype(str).str.strip().str.casefold() == "sidama"
    ].copy()

    if sidama.empty:
        raise ValueError(
            f"Could not find Sidama in field '{name_column}'. "
            f"Example names: {admin[name_column].dropna().astype(str).unique()[:30]}"
        )

    if sidama.crs is None:
        raise ValueError("Administrative boundary has no CRS.")

    sidama_projected = sidama.to_crs(ANALYSIS_CRS)
    sidama_geometry = shapely.union_all(
        sidama_projected.geometry.dropna().to_numpy()
    )

    if sidama_geometry.is_empty or not sidama_geometry.is_valid:
        raise ValueError("Sidama dissolved boundary is empty or invalid.")

    buffered_geometry = shapely.buffer(sidama_geometry, BUFFER_METRES)

    print(f"Administrative name field: {name_column}")
    print(f"Sidama records selected: {len(sidama)}")
    print(f"Analysis CRS: {ANALYSIS_CRS}")
    print(f"Buffer distance: {BUFFER_METRES:,} metres")

    print("\n[2/8] Preparing a source-CRS bounding box...")
    # Transform the buffered polygon back to the source layer's CRS
    # so the GeoPackage reader can use its spatial bounding-box filter.
    source_crs = admin.crs
    buffered_gdf = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[buffered_geometry],
        crs=ANALYSIS_CRS,
    ).to_crs(source_crs)

    bbox = tuple(float(v) for v in buffered_gdf.total_bounds)
    exact_buffer_source = buffered_gdf.geometry.iloc[0]

    print(f"Source CRS: {source_crs}")
    print(f"Bounding box: {bbox}")

    print("\n[3/8] Reading candidate roads from the FULL Ethiopia road layer...")
    roads_bbox = gpd.read_file(
        SOURCE_GPKG,
        layer=ROAD_LAYER,
        bbox=bbox,
        engine="pyogrio",
    )

    bbox_candidate_count = len(roads_bbox)
    if roads_bbox.empty:
        raise ValueError(
            "No road features were returned in the buffer bounding box. "
            "Check the road layer CRS and source data."
        )

    if roads_bbox.crs is None:
        raise ValueError("Road layer has no CRS.")

    print(f"Features returned by bounding-box filter: {bbox_candidate_count:,}")

    print("\n[4/8] Applying exact buffer intersection and clipping...")
    # Exact intersection in the source CRS avoids retaining roads that
    # fall inside the rectangular bounding box but outside the buffer.
    intersects_mask = roads_bbox.geometry.intersects(exact_buffer_source)
    selected_roads = roads_bbox.loc[intersects_mask].copy()
    exact_intersection_count = len(selected_roads)

    if selected_roads.empty:
        raise ValueError("No road features intersect the Sidama buffer.")

    selected_roads = selected_roads.to_crs(ANALYSIS_CRS)
    clipped_geometries = selected_roads.geometry.intersection(buffered_geometry)

    selected_roads["geometry"] = clipped_geometries
    selected_roads = selected_roads[
        selected_roads.geometry.notna()
        & ~selected_roads.geometry.is_empty
    ].copy()

    # Retain linework only; remove any point-only artifacts.
    line_geometries = []
    kept_indices = []

    for idx, geometry in selected_roads.geometry.items():
        line_parts = extract_lines(geometry)
        if line_parts:
            line_geometries.append(
                line_parts[0]
                if len(line_parts) == 1
                else MultiLineString(line_parts)
            )
            kept_indices.append(idx)

    clipped_roads = selected_roads.loc[kept_indices].copy()
    clipped_roads["geometry"] = line_geometries
    clipped_roads = clipped_roads.set_geometry("geometry")

    if clipped_roads.empty:
        raise ValueError("No clipped line geometries remain after clipping.")

    clipped_roads["geometry"] = clipped_roads.geometry.apply(
        lambda g: g if g.is_valid else shapely.make_valid(g)
    )

    # Compute lengths in the projected metric CRS.
    clipped_length_km = float(clipped_roads.geometry.length.sum() / 1000.0)

    # The source road class field is commonly named fclass.
    road_class_counts = {}
    if "fclass" in clipped_roads.columns:
        counts = (
            clipped_roads["fclass"]
            .fillna("UNKNOWN")
            .astype(str)
            .value_counts()
            .sort_values(ascending=False)
        )
        road_class_counts = {
            str(key): int(value) for key, value in counts.items()
        }

    print(f"Road features intersecting buffer: {exact_intersection_count:,}")
    print(f"Clipped line features: {len(clipped_roads):,}")
    print(f"Total clipped length: {clipped_length_km:,.2f} km")

    print("\n[5/8] Saving clipped roads before graph construction...")
    if OUTPUT_GPKG.exists():
        OUTPUT_GPKG.unlink()

    clipped_roads.to_file(
        OUTPUT_GPKG,
        layer="sidama_buffered_roads_v2",
        driver="GPKG",
        engine="pyogrio",
        index=False,
    )
    print(f"Saved: {OUTPUT_GPKG}")

    print("\n[6/8] Noding linework and constructing a geometric graph...")
    # union_all nodes 2D geometric intersections. It does not preserve
    # bridge/tunnel separation, road attributes, or travel restrictions.
    source_linework = clipped_roads.geometry.to_numpy()
    noded_geometry = shapely.union_all(source_linework)
    noded_lines = extract_lines(noded_geometry)

    graph = nx.MultiGraph()
    edge_rows = []

    # Coordinates are rounded to millimetres, rather than whole metres,
    # to reduce accidental merges of distinct nearby junctions.
    def node_key(x, y):
        return (round(float(x), 3), round(float(y), 3))

    for line in noded_lines:
        coords = list(line.coords)

        for index in range(len(coords) - 1):
            x1, y1 = coords[index][:2]
            x2, y2 = coords[index + 1][:2]

            u = node_key(x1, y1)
            v = node_key(x2, y2)

            if u == v:
                continue

            length_m = math.hypot(x2 - x1, y2 - y1)
            if length_m <= 0:
                continue

            graph.add_node(u, x=u[0], y=u[1])
            graph.add_node(v, x=v[0], y=v[1])
            edge_id = len(edge_rows) + 1
            graph.add_edge(
                u,
                v,
                key=edge_id,
                length_m=length_m,
            )

            edge_rows.append({
                "edge_id": edge_id,
                "u_x_m": u[0],
                "u_y_m": u[1],
                "v_x_m": v[0],
                "v_y_m": v[1],
                "length_m": length_m,
                "length_km": length_m / 1000.0,
            })

    if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
        raise ValueError("Graph construction produced no nodes or edges.")

    print(f"Graph nodes: {graph.number_of_nodes():,}")
    print(f"Graph edges: {graph.number_of_edges():,}")

    print("\n[7/8] Calculating graph diagnostics...")
    components = sorted(
        nx.connected_components(graph),
        key=len,
        reverse=True,
    )
    component_sizes = [len(component) for component in components]
    degree_counts = Counter(dict(graph.degree()).values())

    degree_1 = int(degree_counts.get(1, 0))
    degree_0 = int(degree_counts.get(0, 0))
    degree_2 = int(degree_counts.get(2, 0))
    degree_3 = int(degree_counts.get(3, 0))
    degree_4_plus = int(
        sum(count for degree, count in degree_counts.items() if degree >= 4)
    )

    largest_component_nodes = component_sizes[0] if component_sizes else 0
    largest_component_share = (
        largest_component_nodes / graph.number_of_nodes()
        if graph.number_of_nodes()
        else 0.0
    )

    pd.DataFrame([
        {
            "node_id": i,
            "x_m": float(node[0]),
            "y_m": float(node[1]),
            "degree": int(graph.degree(node)),
        }
        for i, node in enumerate(graph.nodes(), start=1)
    ]).to_csv(NODES_CSV, index=False, encoding="utf-8")

    pd.DataFrame(edge_rows).to_csv(
        EDGES_CSV,
        index=False,
        encoding="utf-8",
    )

    print(f"Saved: {NODES_CSV}")
    print(f"Saved: {EDGES_CSV}")
    print(f"Connected components: {len(components):,}")
    print(f"Largest component share: {largest_component_share:.4%}")

    print("\n[8/8] Writing audit reports...")
    report = {
        "status": "completed",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_gpkg": str(SOURCE_GPKG),
        "admin_layer": ADMIN_LAYER,
        "road_layer": ROAD_LAYER,
        "admin_name_field": name_column,
        "analysis_crs": ANALYSIS_CRS,
        "buffer_metres": BUFFER_METRES,
        "road_selection": {
            "selection_method": (
                "Full road layer spatial bounding-box prefilter followed "
                "by exact intersection with the Sidama buffer"
            ),
            "bbox_candidate_features": int(bbox_candidate_count),
            "features_intersecting_buffer": int(exact_intersection_count),
            "clipped_line_features": int(len(clipped_roads)),
            "clipped_total_length_km": round(clipped_length_km, 4),
            "noded_linework_length_km": round(
                float(sum(line.length for line in noded_lines) / 1000.0),
                4,
            ),
        },
        "road_class_counts": road_class_counts,
        "graph": {
            "nodes": int(graph.number_of_nodes()),
            "edges": int(graph.number_of_edges()),
            "connected_components": int(len(components)),
            "largest_component_nodes": int(largest_component_nodes),
            "largest_component_share": round(largest_component_share, 8),
            "degree_0_isolated_nodes": degree_0,
            "degree_1_endpoints": degree_1,
            "degree_2_nodes": degree_2,
            "degree_3_nodes": degree_3,
            "degree_4_plus_nodes": degree_4_plus,
            "component_sizes_top_20": component_sizes[:20],
        },
        "limitations": [
            "This is a preliminary geometric graph, not a validated routing network.",
            "Two-dimensional geometric noding may connect roads at bridges, tunnels, or grade-separated crossings.",
            "Road-level, bridge, and tunnel semantics have not been used to resolve junctions.",
            "Degree-1 nodes are graph endpoints and are not necessarily physical dead ends.",
            "One-way rules, access restrictions, turn restrictions, and vehicle constraints are not modelled.",
            "Road speed, surface quality, traffic, and seasonal passability are not modelled.",
            "The 5 km buffer is a configurable analysis parameter, not a validated transport catchment.",
            "The bounding-box prefilter is followed by exact geometric intersection; the output is clipped to the buffer.",
            "Coordinates are rounded to 0.001 metre for graph node keys; this tolerance should be reviewed.",
            "The clipped road GeoPackage retains source attributes, but the noded graph CSVs are geometric segment representations and do not retain a reliable one-to-one source-road attribution.",
        ],
        "outputs": {
            "clipped_roads_gpkg": str(OUTPUT_GPKG),
            "nodes_csv": str(NODES_CSV),
            "edges_csv": str(EDGES_CSV),
            "report_json": str(REPORT_JSON),
            "report_txt": str(REPORT_TXT),
        },
    }

    REPORT_JSON.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_text_report(report)

    print(f"JSON report: {REPORT_JSON}")
    print(f"Text report: {REPORT_TXT}")

    print("\n" + "=" * 72)
    print("PHASE 2C V2 COMPLETED")
    print("=" * 72)
    print(f"Candidate roads in bounding box: {bbox_candidate_count:,}")
    print(f"Road features intersecting buffer: {exact_intersection_count:,}")
    print(f"Clipped road features: {len(clipped_roads):,}")
    print(f"Graph nodes: {graph.number_of_nodes():,}")
    print(f"Graph edges: {graph.number_of_edges():,}")
    print(f"Connected components: {len(components):,}")
    print(f"Largest component share: {largest_component_share:.4%}")
    print("\nRemember: geometric connectivity is not proof of real-world routability.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\nPHASE 2C V2 FAILED")
        traceback.print_exc()
        raise
