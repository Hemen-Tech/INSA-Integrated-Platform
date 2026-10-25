
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


BASE = Path("data/processed")
GPKG = BASE / "phase2c_v2_sidama_buffered_roads.gpkg"
OUTPUT = BASE / "phase2e1_origin_nearby_source_roads.csv"

LAYER = "sidama_buffered_roads_v2"

ORIGIN = "N47495334_69998829"
ORIGIN_EASTING = 474953.3436867579
ORIGIN_NORTHING = 699988.2860505662

SEARCH_RADIUS_M = 500

# These are the provisional road classes used by the current graph.
ELIGIBLE_CLASSES = {
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "residential", "unclassified",
    "living_street", "service", "road",
    "track", "track_grade1", "track_grade2",
    "track_grade3", "track_grade4", "track_grade5",
}


def main():
    print("=" * 72)
    print("PHASE 2E.1 — SOURCE ROAD NEIGHBORHOOD DIAGNOSTIC")
    print("=" * 72)

    if not GPKG.exists():
        raise FileNotFoundError(f"GeoPackage not found: {GPKG}")

    roads = gpd.read_file(GPKG, layer=LAYER)

    print(f"Source layer: {GPKG}")
    print(f"Layer: {LAYER}")
    print(f"Rows loaded: {len(roads):,}")
    print(f"CRS: {roads.crs}")
    print(f"Columns: {roads.columns.tolist()}")

    if roads.crs is None:
        raise ValueError("Source road layer has no CRS.")

    # The graph coordinates are in UTM meters, EPSG:32637.
    if roads.crs.to_epsg() != 32637:
        roads = roads.to_crs(epsg=32637)
        print("Reprojected source roads to EPSG:32637.")

    origin_point = Point(ORIGIN_EASTING, ORIGIN_NORTHING)

    # Distance from each original road geometry to the origin.
    roads["distance_to_origin_m"] = roads.geometry.distance(origin_point)

    nearby = roads[
        roads["distance_to_origin_m"] <= SEARCH_RADIUS_M
    ].copy()

    if nearby.empty:
        print("No source road geometries found within 500 m.")
        return

    class_col = "fclass" if "fclass" in nearby.columns else None

    if class_col:
        nearby["provisionally_graph_eligible"] = (
            nearby[class_col].astype(str).isin(ELIGIBLE_CLASSES)
        )

    # Report only columns that actually exist in the source layer.
    wanted = [
        "osm_id",
        "name",
        "fclass",
        "oneway",
        "maxspeed",
        "bridge",
        "tunnel",
        "layer",
        "distance_to_origin_m",
        "provisionally_graph_eligible",
    ]
    display_cols = [c for c in wanted if c in nearby.columns]

    nearby = nearby.sort_values("distance_to_origin_m")
    nearby.to_csv(OUTPUT, index=False)

    print(f"\nSource road features within {SEARCH_RADIUS_M} m: {len(nearby):,}")
    print(f"Full results saved to: {OUTPUT}")

    print("\n=== NEAREST SOURCE ROADS ===")
    print(
        nearby[display_cols]
        .head(40)
        .to_string(index=False)
    )

    if class_col:
        print("\n=== ROAD CLASS COUNTS WITHIN 500 M ===")
        print(
            nearby.groupby(
                [class_col, "provisionally_graph_eligible"],
                dropna=False,
            )
            .size()
            .rename("feature_count")
            .reset_index()
            .sort_values("feature_count", ascending=False)
            .to_string(index=False)
        )

        print("\n=== NEARBY ROADS NOT INCLUDED BY CLASS RULE ===")
        excluded_nearby = nearby[
            ~nearby["provisionally_graph_eligible"]
        ]

        if excluded_nearby.empty:
            print("No nearby roads were excluded by the class rule.")
        else:
            print(
                excluded_nearby[display_cols]
                .head(40)
                .to_string(index=False)
            )

    print("\n=== GEOMETRY RELATION TO ORIGIN ===")
    print(
        "Distance here means distance to the road geometry, "
        "not proof that the road intersects or connects to the origin."
    )

    for radius in [5, 15, 30, 100, 500]:
        count = int((nearby["distance_to_origin_m"] <= radius).sum())
        print(f"Road features within {radius:>3} m: {count:,}")

    print("\nDiagnostic completed. No source data or graph files were modified.")


if __name__ == "__main__":
    main()
