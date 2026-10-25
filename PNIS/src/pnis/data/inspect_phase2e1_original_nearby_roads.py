
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "processed"
SOURCE = OUT / "geographic" / "ethiopia.gpkg"
CLIPPED = OUT / "phase2c_v2_sidama_buffered_roads.gpkg"

OSM_ID = "620921089"
CRS = "EPSG:32637"
ORIGIN = Point(474953.3436867579, 699988.2860505662)

# A generous geographic query window around the route origin.
# The national source layer uses WGS84 longitude/latitude.
LON = 38.7731404
LAT = 6.3324316
DEGREE_RADIUS = 0.025
SEARCH_RADIUS_M = 2000.0

CSV_OUT = OUT / "phase2e1_original_nearby_roads.csv"
TXT_OUT = OUT / "phase2e1_original_nearby_roads.txt"


def main():
    if not SOURCE.exists() or not CLIPPED.exists():
        raise FileNotFoundError("A required GeoPackage is missing.")

    print("Reading original roads in a small geographic window...")
    roads = pyogrio.read_dataframe(
        SOURCE,
        layer="gis_osm_roads_free",
        bbox=(
            LON - DEGREE_RADIUS,
            LAT - DEGREE_RADIUS,
            LON + DEGREE_RADIUS,
            LAT + DEGREE_RADIUS,
        ),
    )

    if roads.empty:
        raise RuntimeError("No original roads found in the search window.")

    roads = roads.to_crs(CRS)
    roads["distance_to_origin_m"] = roads.geometry.distance(ORIGIN)
    roads = roads.loc[
        roads["distance_to_origin_m"] <= SEARCH_RADIUS_M
    ].copy()

    clipped = pyogrio.read_dataframe(
        CLIPPED,
        layer="sidama_buffered_roads_v2",
    )

    # Use the OSM ID to identify roads present in the buffered dataset.
    clipped_ids = set(clipped["osm_id"].astype(str))
    roads["osm_id_text"] = roads["osm_id"].astype(str)
    roads["present_in_phase2c_v2"] = roads["osm_id_text"].isin(clipped_ids)

    # Distances and intersection status for the route origin.
    roads["geometry_type"] = roads.geometry.geom_type
    roads["intersects_origin"] = roads.geometry.apply(
        lambda geom: bool(geom.covers(ORIGIN))
    )

    columns = [
        c for c in [
            "osm_id",
            "fclass",
            "name",
            "ref",
            "oneway",
            "maxspeed",
            "bridge",
            "tunnel",
            "layer",
            "distance_to_origin_m",
            "present_in_phase2c_v2",
            "intersects_origin",
            "geometry_type",
        ]
        if c in roads.columns
    ]

    result = roads[columns].sort_values("distance_to_origin_m")
    result.to_csv(CSV_OUT, index=False, encoding="utf-8-sig")

    lines = [
        "=" * 76,
        "PHASE 2E.1 — ORIGINAL NEARBY ROAD INSPECTION",
        "=" * 76,
        f"Original road features within {SEARCH_RADIUS_M:.0f} m: {len(result)}",
        f"Present in Phase 2C v2 by OSM ID: "
        f"{int(result['present_in_phase2c_v2'].sum())}",
        f"Not present in Phase 2C v2 by OSM ID: "
        f"{int((~result['present_in_phase2c_v2']).sum())}",
        f"Features whose geometry covers route origin: "
        f"{int(result['intersects_origin'].sum())}",
        "",
        "NEAREST 30 ROADS",
        "-" * 76,
        result.head(30).to_string(index=False),
        "",
        "Output CSV:",
        str(CSV_OUT),
        "",
        "This is a proximity audit, not permission to connect roads.",
        "Nearby features may be disconnected for valid reasons.",
    ]

    TXT_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nReport saved: {TXT_OUT}")


if __name__ == "__main__":
    main()
