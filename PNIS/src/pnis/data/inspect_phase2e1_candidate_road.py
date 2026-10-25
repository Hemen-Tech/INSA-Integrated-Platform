
from pathlib import Path
import json

import geopandas as gpd
import pyogrio
from shapely.geometry import Point
from shapely.ops import nearest_points

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "processed"
SOURCE = OUT / "geographic" / "ethiopia.gpkg"
BUFFERED = OUT / "phase2c_v2_sidama_buffered_roads.gpkg"

ROAD_A = "620921089"  # Road ending at the route origin
ROAD_B = "620913992"  # Nearby tertiary-road candidate
CRS = "EPSG:32637"
BUFFER_M = 5000.0

ORIGIN = Point(474953.3436867579, 699988.2860505662)

REPORT = OUT / "phase2e1_candidate_road_inspection.txt"
JSON_REPORT = OUT / "phase2e1_candidate_road_inspection.json"


def load_road(osm_id):
    result = pyogrio.read_dataframe(
        SOURCE,
        layer="gis_osm_roads_free",
        where=f'"osm_id" = \'{osm_id}\'',
    )
    if result.empty:
        result = pyogrio.read_dataframe(
            SOURCE,
            layer="gis_osm_roads_free",
            where=f'"osm_id" = {int(osm_id)}',
        )
    if result.empty:
        raise RuntimeError(f"Original road {osm_id} was not found.")
    return result.to_crs(CRS)


def endpoints(geom):
    if geom.geom_type == "LineString":
        parts = [geom]
    elif geom.geom_type == "MultiLineString":
        parts = list(geom.geoms)
    else:
        parts = []

    points = []
    for part_index, part in enumerate(parts, start=1):
        coords = list(part.coords)
        points.append({
            "part": part_index,
            "start": Point(coords[0]),
            "end": Point(coords[-1]),
            "vertices": len(coords),
            "length_m": part.length,
        })
    return points


def point_dict(point):
    return {"x": float(point.x), "y": float(point.y)}


def main():
    if not SOURCE.exists() or not BUFFERED.exists():
        raise FileNotFoundError("A required input GeoPackage is missing.")

    road_a_gdf = load_road(ROAD_A)
    road_b_gdf = load_road(ROAD_B)
    geom_a = road_a_gdf.geometry.iloc[0]
    geom_b = road_b_gdf.geometry.iloc[0]

    admin = pyogrio.read_dataframe(
        SOURCE,
        layer="gis_osm_adminareas_a_free",
    )
    sidama_mask = admin["name"].astype(str).str.contains(
        "Sidama", case=False, na=False
    )
    sidama = admin.loc[sidama_mask].to_crs(CRS)

    if sidama.empty:
        raise RuntimeError("No Sidama boundary candidate was found.")

    # The two candidates were found to have identical bounds and area.
    # Use the first geometry for this diagnostic.
    sidama_polygon = sidama.geometry.iloc[0]
    study_buffer = sidama_polygon.buffer(BUFFER_M)
    buffer_boundary = study_buffer.boundary

    clipped = pyogrio.read_dataframe(
        BUFFERED,
        layer="sidama_buffered_roads_v2",
    )
    clipped["osm_id_text"] = clipped["osm_id"].astype(str)

    a_near, b_near = nearest_points(geom_a, geom_b)
    pair_distance = geom_a.distance(geom_b)
    intersection = geom_a.intersection(geom_b)

    a_endpoints = endpoints(geom_a)
    b_endpoints = endpoints(geom_b)

    endpoint_pairs = []
    for a in a_endpoints:
        for a_label, a_point in [
            ("start", a["start"]),
            ("end", a["end"]),
        ]:
            for b in b_endpoints:
                for b_label, b_point in [
                    ("start", b["start"]),
                    ("end", b["end"]),
                ]:
                    endpoint_pairs.append({
                        "road_a_part": a["part"],
                        "road_a_endpoint": a_label,
                        "road_b_part": b["part"],
                        "road_b_endpoint": b_label,
                        "distance_m": a_point.distance(b_point),
                        "road_a_xy": point_dict(a_point),
                        "road_b_xy": point_dict(b_point),
                    })

    endpoint_pairs.sort(key=lambda item: item["distance_m"])

    road_b_inside = geom_b.intersection(study_buffer)
    road_a_inside = geom_a.intersection(study_buffer)

    candidate_is_clipped = ROAD_B in set(clipped["osm_id_text"])
    road_a_is_clipped = ROAD_A in set(clipped["osm_id_text"])

    result = {
        "road_a": {
            "osm_id": ROAD_A,
            "fclass": str(road_a_gdf.iloc[0].get("fclass", "")),
            "geometry_type": geom_a.geom_type,
            "length_m": geom_a.length,
            "distance_to_route_origin_m": geom_a.distance(ORIGIN),
            "distance_to_buffer_boundary_m":
                geom_a.distance(buffer_boundary),
            "inside_buffer_length_m": road_a_inside.length,
            "present_in_phase2c_v2": road_a_is_clipped,
            "parts": [
                {
                    "part": item["part"],
                    "vertices": item["vertices"],
                    "length_m": item["length_m"],
                    "start": point_dict(item["start"]),
                    "end": point_dict(item["end"]),
                    "start_to_origin_m": item["start"].distance(ORIGIN),
                    "end_to_origin_m": item["end"].distance(ORIGIN),
                }
                for item in a_endpoints
            ],
        },
        "road_b": {
            "osm_id": ROAD_B,
            "fclass": str(road_b_gdf.iloc[0].get("fclass", "")),
            "geometry_type": geom_b.geom_type,
            "length_m": geom_b.length,
            "distance_to_route_origin_m": geom_b.distance(ORIGIN),
            "distance_to_buffer_boundary_m":
                geom_b.distance(buffer_boundary),
            "inside_buffer_length_m": road_b_inside.length,
            "present_in_phase2c_v2": candidate_is_clipped,
            "parts": [
                {
                    "part": item["part"],
                    "vertices": item["vertices"],
                    "length_m": item["length_m"],
                    "start": point_dict(item["start"]),
                    "end": point_dict(item["end"]),
                    "start_to_origin_m": item["start"].distance(ORIGIN),
                    "end_to_origin_m": item["end"].distance(ORIGIN),
                }
                for item in b_endpoints
            ],
        },
        "road_pair": {
            "geometry_distance_m": pair_distance,
            "intersects": bool(geom_a.intersects(geom_b)),
            "intersection_type": intersection.geom_type,
            "intersection_empty": intersection.is_empty,
            "nearest_point_on_road_a": point_dict(a_near),
            "nearest_point_on_road_b": point_dict(b_near),
            "nearest_point_a_to_origin_m": a_near.distance(ORIGIN),
            "nearest_point_b_to_origin_m": b_near.distance(ORIGIN),
            "endpoint_pairs_sorted_by_distance": endpoint_pairs[:12],
        },
    }

    lines = [
        "=" * 76,
        "PHASE 2E.1 — CANDIDATE ROAD INSPECTION",
        "=" * 76,
        f"Study buffer: {BUFFER_M:.0f} m",
        f"Route origin: {point_dict(ORIGIN)}",
        "",
        "ROAD A — ROUTE-ORIGIN ROAD",
        "-" * 76,
        json.dumps(result["road_a"], indent=2),
        "",
        "ROAD B — CANDIDATE ROAD",
        "-" * 76,
        json.dumps(result["road_b"], indent=2),
        "",
        "ROAD-TO-ROAD GEOMETRY COMPARISON",
        "-" * 76,
        json.dumps(result["road_pair"], indent=2),
        "",
        "INTERPRETATION",
        "-" * 76,
        "A small geometry distance does not establish a valid junction.",
        "Check intersection status, nearest-point locations, endpoint",
        "distances, and whether the candidate lies inside the study buffer.",
        "No automatic snapping or graph modification was performed.",
        "No Phase 2C or Phase 2E input was modified.",
    ]

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    JSON_REPORT.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print("\n".join(lines))
    print(f"\nReport saved: {REPORT}")
    print(f"JSON saved: {JSON_REPORT}")


if __name__ == "__main__":
    main()
