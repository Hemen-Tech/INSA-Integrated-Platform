
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "processed"

INPUT_GPKG = DATA_DIR / "phase2c_v2_sidama_buffered_roads.gpkg"
INPUT_LAYER = "sidama_buffered_roads_v2"

OUTPUT_JSON = DATA_DIR / "phase2d_road_attribute_audit.json"
OUTPUT_TXT = DATA_DIR / "phase2d_road_attribute_audit.txt"
OUTPUT_CLASSES = DATA_DIR / "phase2d_road_class_summary.csv"
OUTPUT_FLAGS = DATA_DIR / "phase2d_road_review_flags.csv"


def main():
    print("=" * 70)
    print("PHASE 2D: ROAD ATTRIBUTE AND ROUTING-READINESS AUDIT")
    print("=" * 70)

    if not INPUT_GPKG.exists():
        raise FileNotFoundError(f"Missing input GeoPackage: {INPUT_GPKG}")

    roads = gpd.read_file(
        INPUT_GPKG,
        layer=INPUT_LAYER,
        engine="pyogrio",
    )

    required = [
        "osm_id", "fclass", "oneway", "maxspeed",
        "layer", "bridge", "tunnel", "name", "ref",
        "geometry",
    ]
    missing_columns = [c for c in required if c not in roads.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    n = len(roads)
    if n == 0:
        raise ValueError("Input road dataset is empty.")

    print(f"Rows: {n:,}")
    print(f"CRS: {roads.crs}")

    # Normalize text fields without changing the source GeoPackage.
    for col in ["fclass", "oneway", "bridge", "tunnel", "name", "ref"]:
        roads[col] = roads[col].fillna("").astype(str).str.strip()

    # Treat zero speed as missing/unspecified.
    speed = pd.to_numeric(roads["maxspeed"], errors="coerce")
    speed_available = speed.notna() & (speed > 0)

    # Geometry diagnostics.
    geom = roads.geometry
    geom_length_m = geom.length
    geometry_empty = geom.is_empty | geom.isna()
    geometry_invalid = ~geom.is_valid
    short_road = geom_length_m < 5
    very_short_road = geom_length_m < 1

    # Attribute review flags. These are investigation flags, not
    # automatic claims that a source record is wrong.
    flags = pd.DataFrame({
        "osm_id": roads["osm_id"].astype(str),
        "fclass": roads["fclass"],
        "oneway": roads["oneway"],
        "maxspeed": speed,
        "layer": pd.to_numeric(roads["layer"], errors="coerce"),
        "bridge": roads["bridge"],
        "tunnel": roads["tunnel"],
        "name": roads["name"],
        "length_m": geom_length_m,
    })

    flags["flag_speed_zero_or_missing"] = ~speed_available
    flags["flag_speed_above_130"] = speed > 130
    flags["flag_very_short_under_1m"] = very_short_road
    flags["flag_short_under_5m"] = short_road
    flags["flag_bridge_with_layer_zero"] = (
        flags["bridge"].eq("T") & flags["layer"].eq(0)
    )
    flags["flag_tunnel_with_layer_zero"] = (
        flags["tunnel"].eq("T") & flags["layer"].eq(0)
    )
    flags["flag_grade_separation_tag"] = (
        flags["bridge"].eq("T")
        | flags["tunnel"].eq("T")
        | flags["layer"].fillna(0).ne(0)
    )
    flags["flag_unrecognized_oneway"] = ~flags["oneway"].isin(
        ["B", "F", "T", "N", "-1", "yes", "no", "1", "0"]
    )

    flag_columns = [c for c in flags.columns if c.startswith("flag_")]
    flags["review_flag_count"] = flags[flag_columns].sum(axis=1)

    # Keep all records with at least one review flag.
    review_flags = flags[flags["review_flag_count"] > 0].copy()
    review_flags.to_csv(OUTPUT_FLAGS, index=False, encoding="utf-8")

    # Road class summary.
    class_summary = (
        roads.groupby("fclass", dropna=False)
        .agg(
            feature_count=("osm_id", "size"),
            total_length_km=("geometry", lambda s: s.length.sum() / 1000),
            median_length_m=("geometry", lambda s: s.length.median()),
            speed_available_count=("maxspeed", lambda s: int(
                (pd.to_numeric(s, errors="coerce") > 0).sum()
            )),
        )
        .reset_index()
        .sort_values("feature_count", ascending=False)
    )

    class_summary["feature_share_pct"] = (
        100 * class_summary["feature_count"] / n
    ).round(3)
    class_summary["total_length_km"] = class_summary["total_length_km"].round(3)
    class_summary["median_length_m"] = class_summary["median_length_m"].round(2)
    class_summary.to_csv(OUTPUT_CLASSES, index=False, encoding="utf-8")

    def counts(column):
        return {
            str(k) if str(k) else "<BLANK>": int(v)
            for k, v in roads[column].value_counts(dropna=False).items()
        }

    positive_speeds = speed[speed_available]

    report = {
        "status": "completed",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "input_gpkg": str(INPUT_GPKG),
        "input_layer": INPUT_LAYER,
        "crs": str(roads.crs),
        "feature_count": int(n),
        "geometry": {
            "geometry_type_counts": {
                str(k): int(v)
                for k, v in roads.geom_type.value_counts().items()
            },
            "empty_or_null_count": int(geometry_empty.sum()),
            "invalid_count": int(geometry_invalid.sum()),
            "length_under_1m_count": int(very_short_road.sum()),
            "length_under_5m_count": int(short_road.sum()),
            "total_length_km": round(float(geom_length_m.sum() / 1000), 3),
            "median_feature_length_m": round(float(geom_length_m.median()), 3),
        },
        "attribute_coverage": {
            "blank_name_count": int(roads["name"].eq("").sum()),
            "blank_ref_count": int(roads["ref"].eq("").sum()),
            "speed_zero_or_missing_count": int((~speed_available).sum()),
            "speed_positive_count": int(speed_available.sum()),
            "speed_positive_share_pct": round(
                float(100 * speed_available.sum() / n), 3
            ),
            "speed_above_130_count": int((speed > 130).sum()),
            "speed_positive_min": (
                float(positive_speeds.min()) if len(positive_speeds) else None
            ),
            "speed_positive_median": (
                float(positive_speeds.median()) if len(positive_speeds) else None
            ),
            "speed_positive_max": (
                float(positive_speeds.max()) if len(positive_speeds) else None
            ),
        },
        "attribute_distributions": {
            col: counts(col)
            for col in ["fclass", "oneway", "bridge", "tunnel", "layer"]
        },
        "review_flags": {
            column: int(flags[column].sum())
            for column in flag_columns
        },
        "records_with_any_review_flag": int(
            (flags["review_flag_count"] > 0).sum()
        ),
        "interpretation": [
            "This audit describes source attributes; it does not validate road passability.",
            "A zero maxspeed value is treated as missing/unspecified, not zero travel speed.",
            "Speed values above 130 are flagged for review, not automatically rejected.",
            "Short geometries may be legitimate connectors or clipping artifacts.",
            "Bridge/tunnel/layer flags require spatial inspection before changing connectivity.",
            "The source oneway codes must be confirmed against the dataset documentation before routing.",
            "Feature lengths describe clipped geometries, not necessarily complete source-road lengths.",
        ],
        "outputs": {
            "json_report": str(OUTPUT_JSON),
            "text_report": str(OUTPUT_TXT),
            "road_class_summary_csv": str(OUTPUT_CLASSES),
            "review_flags_csv": str(OUTPUT_FLAGS),
        },
    }

    OUTPUT_JSON.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "PHASE 2D — ROAD ATTRIBUTE AND ROUTING-READINESS AUDIT",
        "=" * 65,
        f"Generated UTC: {report['generated_utc']}",
        f"Status: {report['status']}",
        f"Input features: {n:,}",
        f"CRS: {roads.crs}",
        "",
        "GEOMETRY",
        "-" * 65,
    ]

    for key, value in report["geometry"].items():
        lines.append(f"{key}: {value}")

    lines.extend(["", "ATTRIBUTE COVERAGE", "-" * 65])
    for key, value in report["attribute_coverage"].items():
        lines.append(f"{key}: {value}")

    lines.extend(["", "ATTRIBUTE DISTRIBUTIONS", "-" * 65])
    for column, distribution in report["attribute_distributions"].items():
        lines.append(f"{column}: {distribution}")

    lines.extend(["", "REVIEW FLAGS", "-" * 65])
    for key, value in report["review_flags"].items():
        lines.append(f"{key}: {value}")

    lines.append(
        f"records_with_any_review_flag: {report['records_with_any_review_flag']}"
    )

    lines.extend(["", "INTERPRETATION AND LIMITATIONS", "-" * 65])
    lines.extend(f"- {item}" for item in report["interpretation"])

    lines.extend(["", "OUTPUTS", "-" * 65])
    lines.extend(f"{key}: {value}" for key, value in report["outputs"].items())

    OUTPUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\nAudit complete.")
    print(f"Positive speed records: {int(speed_available.sum()):,} / {n:,}")
    print(f"Records with review flags: {len(review_flags):,}")
    print(f"Road class summary: {OUTPUT_CLASSES}")
    print(f"Review flags: {OUTPUT_FLAGS}")
    print(f"JSON report: {OUTPUT_JSON}")
    print(f"Text report: {OUTPUT_TXT}")


if __name__ == "__main__":
    main()
