
from pathlib import Path
import json

import geopandas as gpd
import pyogrio
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "processed"

SOURCE_GPKG = OUT / "geographic" / "ethiopia.gpkg"
CLIPPED_GPKG = OUT / "phase2c_v2_sidama_buffered_roads.gpkg"
CLIPPED_LAYER = "sidama_buffered_roads_v2"

OSM_ID = "620921089"
CRS = "EPSG:32637"
BUFFER_M = 5000.0

ORIGIN = Point(474953.3436867579, 699988.2860505662)

REPORT = OUT / "phase2e1_clipped_road_comparison.txt"
JSON_REPORT = OUT / "phase2e1_clipped_road_comparison.json"


def read_road(gpkg, layer):
    result = pyogrio.read_dataframe(
        gpkg, layer=layer, where=f'"osm_id" = \'{OSM_ID}\''
    )
    if result.empty:
        result = pyogrio.read_dataframe(
            gpkg, layer=layer, where=f'"osm_id" = {int(OSM_ID)}'
        )
    return result


def line_parts(geom):
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type == "MultiLineString":
        return list(geom.geoms)
    if geom.geom_type == "GeometryCollection":
        parts = []
        for subgeom in geom.geoms:
            parts.extend(line_parts(subgeom))
        return parts
    return []


def describe_geometry(label, geom):
    data = {
        "label": label,
        "geometry_type": None if geom is None else geom.geom_type,
        "empty": True if geom is None else geom.is_empty,
        "length_m": 0.0 if geom is None or geom.is_empty else geom.length,
        "bounds": None if geom is None or geom.is_empty else list(geom.bounds),
        "origin_distance_m": None if geom is None or geom.is_empty
        else geom.distance(ORIGIN),
        "parts": [],
    }

    for i, part in enumerate(line_parts(geom), start=1):
        coords = list(part.coords)
        start = Point(coords[0])
        end = Point(coords[-1])
        data["parts"].append({
            "part": i,
            "vertices": len(coords),
            "length_m": part.length,
            "start_xy": list(coords[0]),
            "end_xy": list(coords[-1]),
            "start_to_origin_m": start.distance(ORIGIN),
            "end_to_origin_m": end.distance(ORIGIN),
        })

    return data


def main():
    for path in [SOURCE_GPKG, CLIPPED_GPKG]:
        if not path.exists():
            raise FileNotFoundError(f"Missing input: {path}")

    source = read_road(SOURCE_GPKG, "gis_osm_roads_free")
    clipped = read_road(CLIPPED_GPKG, CLIPPED_LAYER)

    if source.empty:
        raise RuntimeError(f"Original OSM road {OSM_ID} not found.")
    if clipped.empty:
        raise RuntimeError(
            f"OSM road {OSM_ID} not found in Phase 2C v2 layer."
        )

    source = source.to_crs(CRS)
    clipped = clipped.to_crs(CRS)

    source_geom = source.geometry.iloc[0]
    clipped_geoms = list(clipped.geometry)
    clipped_geom = clipped_geoms[0]

    # Recreate the 5 km buffer using the same admin polygon geometry.
    admin = pyogrio.read_dataframe(
        SOURCE_GPKG, layer="gis_osm_adminareas_a_free"
    )
    mask = admin["name"].astype(str).str.contains(
        "Sidama", case=False, na=False
    )
    sidama = admin.loc[mask].to_crs(CRS)

    if sidama.empty:
        raise RuntimeError("No Sidama administrative polygon found.")

    boundary_geometries = list(sidama.geometry)
    boundary = boundary_geometries[0]
    buffer_geom = boundary.buffer(BUFFER_M)
    buffer_edge = buffer_geom.boundary

    # Geometrically clip the original source road to the recreated buffer.
    expected_clip = source_geom.intersection(buffer_geom)

    # Compare the stored Phase 2C v2 geometry with the recreated clip.
    difference = clipped_geom.symmetric_difference(expected_clip)

    results = {
        "osm_id": OSM_ID,
        "analysis_crs": CRS,
        "buffer_m": BUFFER_M,
        "route_origin_xy": [ORIGIN.x, ORIGIN.y],
        "source_road": describe_geometry("original_source_road", source_geom),
        "stored_phase2c_v2_road": describe_geometry(
            "stored_phase2c_v2_road", clipped_geom
        ),
        "recreated_clipped_road": describe_geometry(
            "recreated_original_road_intersection_buffer", expected_clip
        ),
        "origin_to_buffer_boundary_m": ORIGIN.distance(buffer_edge),
        "source_road_to_buffer_boundary_m": source_geom.distance(buffer_edge),
        "stored_clipped_road_to_buffer_boundary_m":
            clipped_geom.distance(buffer_edge),
        "origin_covered_by_buffer": bool(buffer_geom.covers(ORIGIN)),
        "origin_covered_by_stored_road": bool(clipped_geom.distance(ORIGIN) < 0.01),
        "expected_clip_length_m": expected_clip.length,
        "stored_clip_length_m": clipped_geom.length,
        "symmetric_difference_length_m": difference.length,
        "symmetric_difference_area_m2": difference.area,
        "stored_clip_equals_recreated_clip": bool(
            clipped_geom.hausdorff_distance(expected_clip) < 0.01
        ),
        "source_start_to_buffer_boundary_m":
            Point(source_geom.coords[0]).distance(buffer_edge),
        "source_end_to_buffer_boundary_m":
            Point(source_geom.coords[-1]).distance(buffer_edge),
    }

    report = [
        "=" * 76,
        "PHASE 2E.1 — CLIPPED ROAD COMPARISON",
        "=" * 76,
        f"OSM road: {OSM_ID}",
        f"CRS: {CRS}",
        f"Buffer: {BUFFER_M:.0f} m",
        "",
        "ORIGINAL SOURCE ROAD",
        "-" * 76,
        json.dumps(results["source_road"], indent=2),
        "",
        "STORED PHASE 2C V2 ROAD",
        "-" * 76,
        json.dumps(results["stored_phase2c_v2_road"], indent=2),
        "",
        "RECREATED CLIP",
        "-" * 76,
        json.dumps(results["recreated_clipped_road"], indent=2),
        "",
        "COMPARISON",
        "-" * 76,
        f"Origin to buffer boundary: "
        f"{results['origin_to_buffer_boundary_m']:.6f} m",
        f"Original road to buffer boundary: "
        f"{results['source_road_to_buffer_boundary_m']:.6f} m",
        f"Stored clipped road to buffer boundary: "
        f"{results['stored_clipped_road_to_buffer_boundary_m']:.6f} m",
        f"Origin covered by buffer: {results['origin_covered_by_buffer']}",
        f"Origin on stored road (within 1 cm): "
        f"{results['origin_covered_by_stored_road']}",
        f"Recreated clip length: {results['expected_clip_length_m']:.3f} m",
        f"Stored clip length: {results['stored_clip_length_m']:.3f} m",
        f"Symmetric difference length: "
        f"{results['symmetric_difference_length_m']:.6f} m",
        f"Symmetric difference area: "
        f"{results['symmetric_difference_area_m2']:.6f} m2",
        f"Stored clip matches recreated clip (1 cm tolerance): "
        f"{results['stored_clip_equals_recreated_clip']}",
        f"Original first coordinate to buffer boundary: "
        f"{results['source_start_to_buffer_boundary_m']:.3f} m",
        f"Original last coordinate to buffer boundary: "
        f"{results['source_end_to_buffer_boundary_m']:.3f} m",
        "",
        "No input files were modified.",
    ]

    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    JSON_REPORT.write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )

    print("\n".join(report))
    print(f"\nReport saved: {REPORT}")
    print(f"JSON saved: {JSON_REPORT}")


if __name__ == "__main__":
    main()
