
from pathlib import Path
import json

import geopandas as gpd
import pyogrio
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "processed"
GPKG = ROOT / "data" / "processed" / "geographic" / "ethiopia.gpkg"

ADMIN_LAYER = "gis_osm_adminareas_a_free"
ROAD_LAYER = "gis_osm_roads_free"
TARGET_OSM_ID = "620921089"
ANALYSIS_CRS = "EPSG:32637"
BUFFER_METRES = 5000.0

# Origin of the anomalous route, taken from the previous diagnostics.
ORIGIN_X = 474953.3436867579
ORIGIN_Y = 699988.2860505662
ORIGIN = Point(ORIGIN_X, ORIGIN_Y)

REPORT = OUT / "phase2e1_buffer_boundary_check.txt"
JSON_REPORT = OUT / "phase2e1_buffer_boundary_check.json"


def main():
    if not GPKG.exists():
        raise FileNotFoundError(f"Missing GeoPackage: {GPKG}")

    report = [
        "=" * 76,
        "PHASE 2E.1 — BUFFER BOUNDARY CHECK",
        "=" * 76,
        f"Source: {GPKG}",
        f"Analysis CRS: {ANALYSIS_CRS}",
        f"Buffer distance: {BUFFER_METRES:.0f} m",
        f"Route origin: ({ORIGIN_X:.3f}, {ORIGIN_Y:.3f})",
        "",
        "No existing road, graph, or Phase 2C output is modified.",
        "",
    ]

    admin = pyogrio.read_dataframe(GPKG, layer=ADMIN_LAYER)
    roads = pyogrio.read_dataframe(
        GPKG,
        layer=ROAD_LAYER,
        where=f'"osm_id" = \'{TARGET_OSM_ID}\'',
    )

    if roads.empty:
        roads = pyogrio.read_dataframe(
            GPKG,
            layer=ROAD_LAYER,
            where=f'"osm_id" = {int(TARGET_OSM_ID)}',
        )

    if roads.empty:
        raise RuntimeError(
            f"Original road {TARGET_OSM_ID} was not found."
        )

    if admin.crs is None or roads.crs is None:
        raise RuntimeError("A source layer has no declared CRS.")

    sidama_mask = admin["name"].astype(str).str.contains(
        "Sidama", case=False, na=False
    )
    candidates = admin.loc[sidama_mask].copy()

    if candidates.empty:
        raise RuntimeError("No Sidama boundary candidates were found.")

    admin_projected = candidates.to_crs(ANALYSIS_CRS)
    roads_projected = roads.to_crs(ANALYSIS_CRS)

    results = []

    report.extend([
        "BOUNDARY CANDIDATES",
        "-" * 76,
        f"Candidates found: {len(candidates)}",
        "",
    ])

    for idx, (_, boundary_row) in enumerate(
        admin_projected.iterrows(), start=1
    ):
        boundary = boundary_row.geometry

        if boundary is None or boundary.is_empty:
            continue

        name = str(boundary_row.get("name", ""))
        osm_id = str(boundary_row.get("osm_id", ""))
        fclass = str(boundary_row.get("fclass", ""))

        buffered = boundary.buffer(BUFFER_METRES)
        buffer_boundary = buffered.boundary

        origin_inside = buffered.covers(ORIGIN)
        origin_to_boundary = ORIGIN.distance(buffer_boundary)
        origin_to_polygon = ORIGIN.distance(boundary)

        road_geometry = roads_projected.geometry.iloc[0]
        road_start = Point(road_geometry.coords[0])
        road_end = Point(road_geometry.coords[-1])

        start_to_buffer_edge = road_start.distance(buffer_boundary)
        end_to_buffer_edge = road_end.distance(buffer_boundary)

        start_inside = buffered.covers(road_start)
        end_inside = buffered.covers(road_end)

        road_intersects_buffer = road_geometry.intersects(buffered)
        road_intersection_length = (
            road_geometry.intersection(buffered).length
        )

        item = {
            "candidate_number": idx,
            "osm_id": osm_id,
            "name": name,
            "fclass": fclass,
            "projected_bounds": list(boundary.bounds),
            "boundary_area_km2": boundary.area / 1_000_000,
            "origin_inside_buffer": bool(origin_inside),
            "origin_to_buffer_boundary_m": origin_to_boundary,
            "origin_to_sidama_polygon_m": origin_to_polygon,
            "original_road_start_inside_buffer": bool(start_inside),
            "original_road_end_inside_buffer": bool(end_inside),
            "original_road_start_to_buffer_boundary_m":
                start_to_buffer_edge,
            "original_road_end_to_buffer_boundary_m":
                end_to_buffer_edge,
            "original_road_intersects_buffer":
                bool(road_intersects_buffer),
            "original_road_length_inside_buffer_m":
                road_intersection_length,
        }
        results.append(item)

        report.extend([
            f"CANDIDATE {idx}",
            f"  OSM ID: {osm_id}",
            f"  Name: {name}",
            f"  Administrative class: {fclass}",
            f"  Projected bounds: {boundary.bounds}",
            f"  Boundary area: {boundary.area / 1_000_000:.3f} km2",
            f"  Origin inside 5 km buffer: {origin_inside}",
            f"  Origin to buffer boundary: "
            f"{origin_to_boundary:.3f} m",
            f"  Origin to Sidama polygon: "
            f"{origin_to_polygon:.3f} m",
            f"  Original road first coordinate inside buffer: "
            f"{start_inside}",
            f"  Original road last coordinate inside buffer: "
            f"{end_inside}",
            f"  First coordinate to buffer boundary: "
            f"{start_to_buffer_edge:.3f} m",
            f"  Last coordinate to buffer boundary: "
            f"{end_to_buffer_edge:.3f} m",
            f"  Original road intersects buffer: "
            f"{road_intersects_buffer}",
            f"  Road length inside buffer: "
            f"{road_intersection_length:.3f} m",
            "",
        ])

    # Verify the coordinate of the graph origin against the original
    # road geometry, independent of which boundary is correct.
    road_geometry = roads_projected.geometry.iloc[0]
    origin_to_original_road = ORIGIN.distance(road_geometry)
    first_coord = Point(road_geometry.coords[0])
    last_coord = Point(road_geometry.coords[-1])

    report.extend([
        "ORIGINAL ROAD CROSS-CHECK",
        "-" * 76,
        f"Original road records: {len(roads_projected)}",
        f"Original road geometry type: {road_geometry.geom_type}",
        f"Route origin to original road geometry: "
        f"{origin_to_original_road:.6f} m",
        f"Route origin to first original coordinate: "
        f"{ORIGIN.distance(first_coord):.3f} m",
        f"Route origin to last original coordinate: "
        f"{ORIGIN.distance(last_coord):.3f} m",
        "",
        "INTERPRETATION GUIDE",
        "-" * 76,
        "A very small origin-to-buffer-boundary distance suggests the",
        "origin may be at the clipping boundary, but is not proof by itself.",
        "If the origin is far from the buffer boundary and coincides with",
        "an endpoint of the original road, the source road itself ends there.",
        "If the origin is far from the buffer boundary but is not an endpoint",
        "of the original road, investigate clipping or geometry processing.",
        "Confirm which boundary candidate the Phase 2C v2 builder actually",
        "used before making any correction.",
        "",
        "No files from Phase 2C or Phase 2E were modified.",
    ])

    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    JSON_REPORT.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n".join(report))
    print(f"\nText report: {REPORT}")
    print(f"JSON report: {JSON_REPORT}")


if __name__ == "__main__":
    main()
