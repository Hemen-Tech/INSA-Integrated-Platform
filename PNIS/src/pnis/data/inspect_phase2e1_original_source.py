
from pathlib import Path
import json
import sys

import geopandas as gpd
import pandas as pd
import pyogrio

ROOT = Path(__file__).resolve().parents[3]
GPKG = ROOT / "data" / "processed" / "geographic" / "ethiopia.gpkg"
OUT = ROOT / "data" / "processed"

TARGET_OSM_ID = "620921089"
REPORT = OUT / "phase2e1_original_source_inspection.txt"
ROAD_CSV = OUT / "phase2e1_original_road_620921089.csv"

def write_report(lines):
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

def main():
    lines = [
        "=" * 72,
        "PHASE 2E.1 — ORIGINAL SOURCE INSPECTION",
        "=" * 72,
        f"Source GeoPackage: {GPKG}",
        f"Target road OSM ID: {TARGET_OSM_ID}",
        "",
    ]

    if not GPKG.exists():
        raise FileNotFoundError(f"GeoPackage not found: {GPKG}")

    layers = pyogrio.list_layers(GPKG)
    lines.append("AVAILABLE LAYERS")
    lines.append("-" * 72)

    for row in layers:
        layer_name = str(row[0])
        geom_type = str(row[1]) if len(row) > 1 else "unknown"
        lines.append(f"{layer_name} | geometry={geom_type}")

    # Inspect the source road by OSM ID.
    road_layer = "gis_osm_roads_free"
    layer_names = {str(row[0]) for row in layers}

    if road_layer not in layer_names:
        lines.append("")
        lines.append(f"Expected road layer not found: {road_layer}")
        write_report(lines)
        print("\n".join(lines))
        return

    road_info = pyogrio.read_info(GPKG, layer=road_layer)
    road_fields = list(road_info.get("fields", []))

    lines.extend([
        "",
        "SOURCE ROAD LAYER",
        "-" * 72,
        f"Layer: {road_layer}",
        f"CRS: {road_info.get('crs')}",
        f"Fields: {road_fields}",
    ])

    if "osm_id" not in road_fields:
        lines.append("ERROR: osm_id field is missing.")
    else:
        # Filter in the GeoPackage rather than loading all national roads.
        query = f'"osm_id" = \'{TARGET_OSM_ID}\''
        try:
            road = pyogrio.read_dataframe(
                GPKG,
                layer=road_layer,
                where=query,
            )
        except Exception as exc:
            lines.append(f"SQL filter failed: {exc}")
            road = gpd.GeoDataFrame()

        # Fallback for databases that store OSM IDs as numeric values.
        if road.empty:
            try:
                road = pyogrio.read_dataframe(
                    GPKG,
                    layer=road_layer,
                    where=f'"osm_id" = {int(TARGET_OSM_ID)}',
                )
            except Exception as exc:
                lines.append(f"Numeric filter failed: {exc}")

        lines.extend([
            "",
            "TARGET ROAD RESULT",
            "-" * 72,
            f"Matching records: {len(road)}",
        ])

        if not road.empty:
            attrs = road.drop(columns="geometry").copy()
            attrs.to_csv(ROAD_CSV, index=False, encoding="utf-8-sig")
            lines.append(f"Road attributes CSV: {ROAD_CSV}")

            for idx, row in road.iterrows():
                geom = row.geometry
                lines.append("")
                lines.append(f"Feature index: {idx}")
                lines.append(
                    json.dumps(
                        {k: str(v) for k, v in row.items()
                         if k != "geometry"},
                        ensure_ascii=False,
                    )
                )

                if geom is None:
                    lines.append("Geometry: None")
                    continue

                lines.append(f"Geometry type: {geom.geom_type}")
                lines.append(f"Empty: {geom.is_empty}")
                lines.append(f"Length in source CRS units: {geom.length}")
                lines.append(f"Bounds: {geom.bounds}")

                # Extract endpoints from every line part.
                if geom.geom_type == "LineString":
                    parts = [geom]
                elif geom.geom_type == "MultiLineString":
                    parts = list(geom.geoms)
                else:
                    parts = []

                lines.append(f"Line parts: {len(parts)}")

                for part_num, part in enumerate(parts, start=1):
                    coords = list(part.coords)
                    lines.append(
                        f"Part {part_num}: vertices={len(coords)}"
                    )
                    lines.append(f"  First coordinate: {coords[0]}")
                    lines.append(f"  Last coordinate:  {coords[-1]}")

    # Inspect administrative boundary layer schema and Sidama candidates.
    admin_layer = "gis_osm_adminareas_a_free"
    lines.extend(["", "ADMINISTRATIVE BOUNDARY LAYER", "-" * 72])

    if admin_layer not in layer_names:
        lines.append(f"Expected admin layer not found: {admin_layer}")
    else:
        admin_info = pyogrio.read_info(GPKG, layer=admin_layer)
        admin_fields = list(admin_info.get("fields", []))
        lines.append(f"Layer: {admin_layer}")
        lines.append(f"CRS: {admin_info.get('crs')}")
        lines.append(f"Fields: {admin_fields}")

        # Load only the admin polygons; this is much smaller than roads.
        admin = pyogrio.read_dataframe(GPKG, layer=admin_layer)
        lines.append(f"Administrative features loaded: {len(admin)}")

        text_fields = [
            c for c in admin.columns
            if c != "geometry"
            and (
                "name" in c.lower()
                or "admin" in c.lower()
                or "boundary" in c.lower()
            )
        ]
        lines.append(f"Name/admin candidate fields: {text_fields}")

        matches = pd.Series(False, index=admin.index)
        for col in text_fields:
            matches |= admin[col].astype(str).str.contains(
                "Sidama", case=False, na=False
            )

        sidama = admin.loc[matches].copy()
        lines.append(f"Rows containing 'Sidama': {len(sidama)}")

        if not sidama.empty:
            lines.append("Sidama candidate attributes:")
            lines.append(
                sidama.drop(columns="geometry").head(20).to_string(
                    index=False
                )
            )

            boundary_csv = OUT / "phase2e1_sidama_boundary_candidates.csv"
            sidama.drop(columns="geometry").to_csv(
                boundary_csv, index=False, encoding="utf-8-sig"
            )
            lines.append(f"Boundary candidate CSV: {boundary_csv}")

    lines.extend([
        "",
        "INTERPRETATION",
        "-" * 72,
        "This inspection identifies source features and boundary candidates.",
        "It does not yet determine whether the route origin is on the buffer",
        "boundary. That requires comparing projected geometries.",
        "No source data or existing Phase 2 outputs were modified.",
    ])

    write_report(lines)
    print("\n".join(lines))
    print(f"\nReport saved: {REPORT}")

if __name__ == "__main__":
    main()
