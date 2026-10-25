
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyogrio
import shapely
from shapely import (
    is_empty,
    is_valid,
    is_valid_reason,
    intersects,
    unary_union,
)


ROOT = Path(__file__).resolve().parents[3]
GPKG = ROOT / "data" / "processed" / "geographic" / "ethiopia.gpkg"
OUT = ROOT / "data" / "processed"

ROAD_LAYER = "gis_osm_roads_free"
ADMIN_LAYER = "gis_osm_adminareas_a_free"

REPORT_JSON = OUT / "phase2b_road_geometry_audit.json"
REPORT_TXT = OUT / "phase2b_road_geometry_audit.txt"
ROAD_GPKG = OUT / "phase2b_sidama_intersecting_roads.gpkg"
ROAD_CSV = OUT / "phase2b_sidama_intersecting_roads.csv"


def log(message: str) -> None:
    print(message, flush=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    if not GPKG.exists():
        raise FileNotFoundError(f"GeoPackage not found: {GPKG}")

    results: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(GPKG),
        "software": {
            "python": sys.version,
            "shapely": shapely.__version__,
            "pyogrio": pyogrio.__version__,
            "pandas": pd.__version__,
        },
        "warnings": [],
        "limitations": [
            "Geometric intersection does not prove that a road is passable.",
            "This script does not establish routable network connectivity.",
            "Roads are selected by intersection with the Sidama polygon; "
            "their complete geometries are retained and are not clipped.",
            "Duplicate or overlapping boundary records are dissolved before "
            "the spatial intersection.",
        ],
    }

    log("=" * 72)
    log("PNIS PHASE 2B — ROAD GEOMETRY VALIDATION")
    log("=" * 72)
    log(f"Source: {GPKG}")

    # ---------------------------------------------------------------
    # 1. Inspect layers and their metadata
    # ---------------------------------------------------------------
    log("\n[1/5] Inspecting GeoPackage layers...")

    layers = pyogrio.list_layers(GPKG)
    layer_names = [str(row[0]) for row in layers]
    results["layers"] = layer_names

    log(f"Layers: {layer_names}")

    if ROAD_LAYER not in layer_names:
        raise ValueError(f"Road layer not found: {ROAD_LAYER}")

    if ADMIN_LAYER not in layer_names:
        raise ValueError(f"Admin layer not found: {ADMIN_LAYER}")

    road_info = pyogrio.read_info(GPKG, layer=ROAD_LAYER)
    admin_info = pyogrio.read_info(GPKG, layer=ADMIN_LAYER)

    results["road_metadata"] = {
        "feature_count_metadata": int(road_info["features"]),
        "geometry_type": str(road_info["geometry_type"]),
        "crs": str(road_info["crs"]),
        "fields": [str(x) for x in road_info["fields"]],
        "dtypes": [str(x) for x in road_info["dtypes"]],
        "bounds": [
            float(x) for x in road_info["total_bounds"]
        ] if road_info.get("total_bounds") is not None else None,
    }

    results["admin_metadata"] = {
        "feature_count_metadata": int(admin_info["features"]),
        "geometry_type": str(admin_info["geometry_type"]),
        "crs": str(admin_info["crs"]),
        "fields": [str(x) for x in admin_info["fields"]],
    }

    road_crs = road_info["crs"]
    admin_crs = admin_info["crs"]

    if road_crs is None or admin_crs is None:
        raise ValueError(
            "CRS is missing from the road or admin layer. "
            "Do not perform spatial comparisons until CRS is established."
        )

    if str(road_crs) != str(admin_crs):
        raise ValueError(
            f"Layer CRS mismatch: roads={road_crs}, admins={admin_crs}. "
            "Reprojection must be handled explicitly before intersection."
        )

    log(f"Road feature count (metadata): {road_info['features']:,}")
    log(f"Road geometry type: {road_info['geometry_type']}")
    log(f"Road CRS: {road_crs}")
    log(f"Admin CRS: {admin_crs}")

    # ---------------------------------------------------------------
    # 2. Read and identify Sidama boundary
    # ---------------------------------------------------------------
    log("\n[2/5] Reading administrative boundaries...")

    admin_fields = set(str(x) for x in admin_info["fields"])
    if "name" not in admin_fields:
        raise ValueError(
            f"No 'name' field in admin layer. Available: {sorted(admin_fields)}"
        )

    admins = pyogrio.read_dataframe(
        GPKG,
        layer=ADMIN_LAYER,
        columns=["name"],
        read_geometry=True,
    )

    if admins.empty:
        raise ValueError("Admin layer returned no records.")

    sidama_mask = (
        admins["name"]
        .astype("string")
        .str.strip()
        .str.casefold()
        .eq("sidama")
        .fillna(False)
    )

    sidama_rows = admins.loc[sidama_mask].copy()

    if sidama_rows.empty:
        names = (
            admins["name"]
            .dropna()
            .astype(str)
            .drop_duplicates()
            .head(40)
            .tolist()
        )
        raise ValueError(
            "Could not find an admin record named Sidama. "
            f"Sample available names: {names}"
        )

    boundary_parts = [
        geom for geom in sidama_rows.geometry
        if geom is not None and not is_empty(geom)
    ]

    if not boundary_parts:
        raise ValueError("Sidama records contain no usable geometry.")

    boundary_validity = [bool(is_valid(g)) for g in boundary_parts]
    if not all(boundary_validity):
        reasons = [
            str(is_valid_reason(g))
            for g in boundary_parts
            if not is_valid(g)
        ]
        raise ValueError(
            "At least one Sidama boundary geometry is invalid. "
            f"Reasons: {reasons[:10]}"
        )

    boundary = unary_union(boundary_parts)

    if boundary.is_empty or not boundary.is_valid:
        raise ValueError("Dissolved Sidama boundary is empty or invalid.")

    results["sidama_boundary"] = {
        "matching_admin_records": int(len(sidama_rows)),
        "source_geometry_types": [
            str(g.geom_type) for g in boundary_parts
        ],
        "dissolved_geometry_type": str(boundary.geom_type),
        "valid": bool(boundary.is_valid),
        "bounds": [float(x) for x in boundary.bounds],
        "area_in_layer_units_squared": float(boundary.area),
        "boundary_records": (
            sidama_rows.drop(columns="geometry")
            .astype("string")
            .fillna("")
            .to_dict(orient="records")
        ),
    }

    log(f"Sidama admin records: {len(sidama_rows)}")
    log(f"Dissolved boundary type: {boundary.geom_type}")
    log(f"Boundary bounds: {boundary.bounds}")

    # ---------------------------------------------------------------
    # 3. Read roads and check geometry integrity
    # ---------------------------------------------------------------
    log("\n[3/5] Reading road geometries...")
    log("This may take a few minutes for the full road layer.")

    roads = pyogrio.read_dataframe(
        GPKG,
        layer=ROAD_LAYER,
        read_geometry=True,
    )

    road_count = len(roads)
    if road_count == 0:
        raise ValueError("Road layer returned no records.")

    geoms = roads.geometry.array

    empty_mask = np.asarray(is_empty(geoms), dtype=bool)
    valid_mask = np.asarray(is_valid(geoms), dtype=bool)
    null_mask = np.asarray([g is None for g in geoms], dtype=bool)

    # Do not call validity on null geometries as a substitute for checking
    # nulls separately.
    invalid_mask = (~valid_mask) & (~null_mask) & (~empty_mask)
    usable_mask = (~null_mask) & (~empty_mask) & valid_mask

    geometry_types = (
        roads.geometry.geom_type
        .fillna("NULL")
        .value_counts()
        .to_dict()
    )

    invalid_indices = np.flatnonzero(invalid_mask)
    invalid_samples = []

    for idx in invalid_indices[:25]:
        geom = roads.geometry.iloc[int(idx)]
        invalid_samples.append({
            "row_position": int(idx),
            "fid": (
                str(roads.iloc[int(idx)]["fid"])
                if "fid" in roads.columns else None
            ),
            "osm_id": (
                str(roads.iloc[int(idx)]["osm_id"])
                if "osm_id" in roads.columns else None
            ),
            "reason": str(is_valid_reason(geom)),
        })

    results["road_geometry_audit"] = {
        "records_read": int(road_count),
        "null_geometries": int(null_mask.sum()),
        "empty_geometries": int(empty_mask.sum()),
        "valid_geometries": int((valid_mask & ~null_mask & ~empty_mask).sum()),
        "invalid_nonempty_geometries": int(invalid_mask.sum()),
        "geometry_type_counts": {
            str(k): int(v) for k, v in geometry_types.items()
        },
        "invalid_geometry_samples": invalid_samples,
    }

    log(f"Road records read: {road_count:,}")
    log(f"Null geometries: {int(null_mask.sum()):,}")
    log(f"Empty geometries: {int(empty_mask.sum()):,}")
    log(f"Invalid nonempty geometries: {int(invalid_mask.sum()):,}")
    log(f"Geometry types: {geometry_types}")

    # ---------------------------------------------------------------
    # 4. Exact intersection with Sidama boundary
    # ---------------------------------------------------------------
    log("\n[4/5] Testing road intersections with Sidama...")

    # Full geometry predicates find boundary-crossing roads even when no
    # road vertex falls inside the polygon.
    spatial_mask = np.zeros(road_count, dtype=bool)
    usable_positions = np.flatnonzero(usable_mask)

    # Chunking bounds temporary memory use and provides progress.
    chunk_size = 25_000
    for start in range(0, len(usable_positions), chunk_size):
        positions = usable_positions[start:start + chunk_size]
        chunk_geoms = geoms[positions]
        spatial_mask[positions] = np.asarray(
            intersects(chunk_geoms, boundary),
            dtype=bool,
        )

        completed = min(start + len(positions), len(usable_positions))
        log(f"  Tested {completed:,} / {len(usable_positions):,} usable roads")

    selected = roads.loc[spatial_mask].copy()

    if selected.empty:
        results["warnings"].append(
            "No roads intersected the Sidama boundary; verify the layer "
            "CRS and the boundary selection."
        )

    # Retain the original full geometry. Do not clip or modify source roads.
    if ROAD_GPKG.exists():
        ROAD_GPKG.unlink()

    if not selected.empty:
        pyogrio.write_dataframe(
            selected,
            ROAD_GPKG,
            layer="sidama_intersecting_roads",
            driver="GPKG",
        )

        csv_frame = selected.drop(columns="geometry").copy()
        csv_frame.to_csv(ROAD_CSV, index=False, encoding="utf-8-sig")

    results["sidama_road_intersection"] = {
        "intersecting_road_count": int(len(selected)),
        "percent_of_all_roads": round(
            len(selected) / road_count * 100, 4
        ),
        "output_geopackage": (
            str(ROAD_GPKG) if not selected.empty else None
        ),
        "output_csv": str(ROAD_CSV) if not selected.empty else None,
        "selection_method": (
            "Exact geometric intersection between each valid, nonempty "
            "road geometry and the dissolved Sidama polygon."
        ),
        "note": (
            "Selected roads retain their original full geometry; they "
            "have not been clipped to the boundary."
        ),
    }

    if "fclass" in selected.columns:
        results["sidama_road_intersection"]["road_class_counts"] = {
            str(k): int(v)
            for k, v in selected["fclass"].fillna("NULL").value_counts().items()
        }

    log(f"Roads intersecting Sidama: {len(selected):,}")
    if not selected.empty:
        log(f"Saved: {ROAD_GPKG}")
        log(f"Saved: {ROAD_CSV}")

    # ---------------------------------------------------------------
    # 5. Write machine-readable and human-readable reports
    # ---------------------------------------------------------------
    log("\n[5/5] Writing audit reports...")

    results["status"] = "completed"
    REPORT_JSON.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "PNIS PHASE 2B — ROAD GEOMETRY VALIDATION",
        "=" * 52,
        f"Generated UTC: {results['generated_utc']}",
        f"Source: {GPKG}",
        "",
        "ROAD LAYER",
        f"Features: {road_count:,}",
        f"Geometry type metadata: {road_info['geometry_type']}",
        f"CRS: {road_crs}",
        f"Geometry types: {geometry_types}",
        "",
        "GEOMETRY INTEGRITY",
        f"Null geometries: {int(null_mask.sum()):,}",
        f"Empty geometries: {int(empty_mask.sum()):,}",
        f"Valid geometries: {int((valid_mask & ~null_mask & ~empty_mask).sum()):,}",
        f"Invalid nonempty geometries: {int(invalid_mask.sum()):,}",
        "",
        "SIDAMA BOUNDARY",
        f"Matching admin records: {len(sidama_rows)}",
        f"Dissolved type: {boundary.geom_type}",
        f"Valid: {boundary.is_valid}",
        f"Bounds: {boundary.bounds}",
        "",
        "ROAD INTERSECTION",
        f"Roads intersecting Sidama: {len(selected):,}",
        f"Percent of full road layer: {len(selected) / road_count * 100:.4f}%",
        f"Road GeoPackage: {ROAD_GPKG if not selected.empty else 'Not created (no roads selected)'}",
        f"Road CSV: {ROAD_CSV if not selected.empty else 'Not created (no roads selected)'}",
        "",
        "INVALID GEOMETRY SAMPLES",
    ]

    if invalid_samples:
        for item in invalid_samples:
            lines.append(
                f"row={item['row_position']}, fid={item['fid']}, "
                f"osm_id={item['osm_id']}, reason={item['reason']}"
            )
    else:
        lines.append("No invalid nonempty geometries detected.")

    lines.extend(["", "WARNINGS"])
    lines.extend(
        [f"- {warning}" for warning in results["warnings"]]
        or ["None recorded."]
    )

    lines.extend(["", "LIMITATIONS"])
    lines.extend(f"- {item}" for item in results["limitations"])
    lines.extend([
        "",
        "This report does not certify routability, connected components,",
        "turn restrictions, travel speeds, or realistic travel times.",
    ])

    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    log(f"Report: {REPORT_TXT}")
    log(f"JSON:   {REPORT_JSON}")
    log("\nPhase 2B geometry audit completed.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\nPHASE 2B FAILED:", flush=True)
        traceback.print_exc()
        raise
