
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import geopandas as gpd
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

INPUT_GPKG = PROCESSED_DIR / "phase2c_v2_sidama_buffered_roads.gpkg"
INPUT_LAYER = "sidama_buffered_roads_v2"

OUTPUT_CSV = PROCESSED_DIR / "phase2g3_road_suitability_review_register.csv"
OUTPUT_AUDIT = PROCESSED_DIR / "phase2g3_road_suitability_review_audit.txt"


def road_review_profile(value: object) -> tuple[str, str, str]:
    """Classify a mapped road for manual review, not actual passability."""
    road_class = "" if pd.isna(value) else str(value).strip().lower()

    restrictive_classes = {
        "path", "footway", "steps", "cycleway", "bridleway",
        "pedestrian", "corridor", "platform",
    }
    uncertain_classes = {
        "track", "service", "living_street", "road",
        "unclassified",
    }
    ordinary_classes = {
        "residential", "tertiary", "tertiary_link",
        "secondary", "secondary_link", "primary", "primary_link",
        "trunk", "trunk_link", "motorway", "motorway_link",
    }

    if not road_class:
        return (
            "ROAD_CLASS_MISSING",
            "P1_CLASSIFICATION_REVIEW",
            "Road class is missing; vehicle suitability cannot be inferred.",
        )

    if road_class in restrictive_classes:
        return (
            "POTENTIALLY_RESTRICTIVE",
            "P1_RESTRICTIVE_CLASS_REVIEW",
            "Mapped class may be unsuitable for some collection/delivery vehicles; verify in the field.",
        )

    if road_class in uncertain_classes:
        return (
            "VEHICLE_SUITABILITY_UNCERTAIN",
            "P2_SURFACE_AND_ACCESS_REVIEW",
            "Verify surface, width, seasonal passability, and vehicle access.",
        )

    if road_class in ordinary_classes:
        return (
            "CLASS_NOT_OBVIOUSLY_RESTRICTIVE",
            "P3_STANDARD_FIELD_REVIEW",
            "Class alone does not confirm surface quality, legal access, or vehicle passability.",
        )

    return (
        "UNCLASSIFIED_FOR_VEHICLE_USE",
        "P1_CLASSIFICATION_REVIEW",
        "Unrecognized road class; review before assigning vehicle suitability.",
    )


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def main() -> int:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if not INPUT_GPKG.exists():
        print(f"ERROR: Required input GeoPackage not found:\n{INPUT_GPKG}")
        return 1

    generated_utc = datetime.now(timezone.utc).isoformat()
    checks: list[tuple[str, bool, str]] = []

    def add_check(name: str, passed: bool, detail: str) -> None:
        checks.append((name, bool(passed), detail))

    try:
        roads = gpd.read_file(INPUT_GPKG, layer=INPUT_LAYER)
    except Exception as exc:
        print(f"ERROR: Could not read road layer: {exc}")
        return 1

    if roads.empty:
        print("ERROR: Input road layer is empty.")
        return 1

    original_columns = list(roads.columns)
    geometry_column = roads.geometry.name

    # Keep the original source attributes and geometry-derived length where possible.
    if roads.crs is not None and roads.crs.is_geographic:
        roads_metric = roads.to_crs("EPSG:32637")
    else:
        roads_metric = roads

    roads["road_length_m"] = roads_metric.geometry.length.to_numpy()

    # Preserve all available source attributes in the review CSV, excluding geometry.
    df = pd.DataFrame(roads.drop(columns=[geometry_column], errors="ignore")).copy()

    # Use the source OSM identifier when available, with a row-based suffix so
    # separate source features never collapse just because an OSM ID repeats.
    if "osm_id" in df.columns:
        osm_ids = df["osm_id"].map(clean_text)
    else:
        osm_ids = pd.Series([""] * len(df), index=df.index, dtype="string")

    if "fid" in df.columns:
        source_ids = df["fid"].map(clean_text)
    else:
        source_ids = pd.Series([""] * len(df), index=df.index, dtype="string")

    df.insert(
        0,
        "road_review_id",
        [
            f"PH2G3-{i + 1:06d}"
            for i in range(len(df))
        ],
    )
    df["source_osm_id"] = osm_ids.to_numpy()
    df["source_fid"] = source_ids.to_numpy()

    # Read known fields defensively; missing optional fields are left blank.
    def source_field(name: str) -> pd.Series:
        if name in df.columns:
            return df[name].map(clean_text)
        return pd.Series([""] * len(df), index=df.index, dtype="string")

    df["review_road_class"] = source_field("fclass").str.lower()
    profiles = df["review_road_class"].map(road_review_profile)
    df["vehicle_suitability_screen"] = [x[0] for x in profiles]
    df["review_priority"] = [x[1] for x in profiles]
    df["review_reason"] = [x[2] for x in profiles]

    # Keep source fields where present; these additional normalized columns make
    # manual review easier without treating blank values as verified facts.
    df["mapped_name_for_review"] = source_field("name")
    df["mapped_reference_for_review"] = source_field("ref")
    df["mapped_oneway_for_review"] = source_field("oneway")
    df["mapped_maxspeed_for_review"] = source_field("maxspeed")
    df["mapped_surface_for_review"] = source_field("surface")
    df["mapped_bridge_for_review"] = source_field("bridge")
    df["mapped_tunnel_for_review"] = source_field("tunnel")

    # Manual verification fields. No road is automatically approved.
    df["surface_condition_field_result"] = ""
    df["road_width_field_result"] = ""
    df["seasonal_passability_field_result"] = ""
    df["vehicle_restriction_field_result"] = ""
    df["legal_access_field_result"] = ""
    df["field_verification_status"] = "PENDING"
    df["vehicle_suitability_decision"] = "REVIEW_PENDING"
    df["review_evidence_reference"] = ""
    df["reviewer"] = ""
    df["review_date"] = ""
    df["review_notes"] = ""
    df["vehicle_suitability_verified"] = "NO"
    df["routing_eligible"] = "NO"
    df["eligibility_reason"] = (
        "Mapped road attributes are not field verification; routing approval withheld."
    )

    # Validate output content.
    road_classes = df["review_road_class"]
    distances = pd.to_numeric(df["road_length_m"], errors="coerce")
    priorities = df["review_priority"]

    add_check(
        "input_features_loaded",
        len(df) > 0,
        f"road_features={len(df)}",
    )
    add_check(
        "review_ids_unique",
        df["road_review_id"].notna().all()
        and df["road_review_id"].is_unique,
        f"unique_review_ids={df['road_review_id'].nunique()}",
    )
    add_check(
        "road_class_review_field_present",
        "review_road_class" in df.columns,
        f"field_present={'review_road_class' in df.columns}",
    )
    add_check(
        "review_priority_assigned",
        priorities.notna().all() and priorities.astype(str).str.len().gt(0).all(),
        f"assigned={int(priorities.astype(str).str.len().gt(0).sum())}",
    )
    add_check(
        "road_lengths_nonnegative",
        distances.notna().all() and distances.ge(0).all(),
        f"valid_lengths={int(distances.notna().sum())}",
    )
    add_check(
        "field_verification_pending",
        df["field_verification_status"].eq("PENDING").all(),
        f"non_pending={int((~df['field_verification_status'].eq('PENDING')).sum())}",
    )
    add_check(
        "vehicle_decisions_pending",
        df["vehicle_suitability_decision"].eq("REVIEW_PENDING").all(),
        f"non_pending={int((~df['vehicle_suitability_decision'].eq('REVIEW_PENDING')).sum())}",
    )
    add_check(
        "no_roads_marked_verified",
        df["vehicle_suitability_verified"].eq("NO").all(),
        f"verified_yes={int(df['vehicle_suitability_verified'].eq('YES').sum())}",
    )
    add_check(
        "no_roads_routing_eligible",
        df["routing_eligible"].eq("NO").all(),
        f"routing_eligible_yes={int(df['routing_eligible'].eq('YES').sum())}",
    )
    add_check(
        "manual_review_fields_present",
        all(
            c in df.columns
            for c in [
                "surface_condition_field_result",
                "seasonal_passability_field_result",
                "vehicle_restriction_field_result",
                "review_evidence_reference",
                "reviewer",
                "review_date",
                "review_notes",
            ]
        ),
        "required manual review fields checked",
    )
    add_check(
        "output_paths_are_phase2g3",
        OUTPUT_CSV.name.startswith("phase2g3_")
        and OUTPUT_AUDIT.name.startswith("phase2g3_"),
        f"csv={OUTPUT_CSV.name}; audit={OUTPUT_AUDIT.name}",
    )

    # Write CSV and audit, even if a validation check fails, so the failure can
    # be inspected. No source data or earlier-phase output is modified.
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    class_counts = (
        df["review_road_class"]
        .replace("", "(blank)")
        .value_counts(dropna=False)
        .sort_index()
    )
    profile_counts = df["vehicle_suitability_screen"].value_counts().sort_index()
    priority_counts = df["review_priority"].value_counts().sort_index()

    audit_lines = [
        "PNIS PHASE 2G.3 - ROAD SUITABILITY REVIEW REGISTER",
        "=" * 72,
        f"Generated UTC: {generated_utc}",
        f"Project root: {PROJECT_ROOT}",
        "",
        "INPUT",
        "-" * 72,
        f"Source GeoPackage: {INPUT_GPKG}",
        f"Source layer: {INPUT_LAYER}",
        f"Source CRS: {roads.crs}",
        f"Original source columns: {len(original_columns)}",
        "",
        "METHOD AND SAFETY LIMITS",
        "-" * 72,
        "This register screens mapped road classes and attributes for manual review.",
        "It does not establish physical road condition, width, legal access,",
        "seasonal passability, bridge capacity, or vehicle suitability.",
        "No road is automatically approved or rejected for operational routing.",
        "All road records remain unverified and routing-ineligible.",
        "",
        "SUMMARY",
        "-" * 72,
        f"Road features: {len(df)}",
        f"Unique review IDs: {df['road_review_id'].nunique()}",
        f"CRS used for length calculation: EPSG:32637 when source was geographic; otherwise source CRS",
        f"Total mapped length (km): {distances.sum() / 1000:.3f}",
        f"Road classes available: {int(road_classes.replace('', pd.NA).nunique())}",
        "",
        "ROAD CLASS COUNTS",
        "-" * 72,
    ]
    audit_lines.extend(
        f"  {label}: {count}" for label, count in class_counts.items()
    )
    audit_lines.extend(
        [
            "",
            "VEHICLE-SUITABILITY SCREEN COUNTS",
            "-" * 72,
        ]
    )
    audit_lines.extend(
        f"  {label}: {count}" for label, count in profile_counts.items()
    )
    audit_lines.extend(
        [
            "",
            "REVIEW PRIORITY COUNTS",
            "-" * 72,
        ]
    )
    audit_lines.extend(
        f"  {label}: {count}" for label, count in priority_counts.items()
    )
    audit_lines.extend(
        [
            "",
            "VALIDATION CHECKS",
            "-" * 72,
        ]
    )
    for name, passed, detail in checks:
        audit_lines.append(
            f"{'PASS' if passed else 'FAIL'} - {name}: {detail}"
        )

    passed_count = sum(1 for _, passed, _ in checks if passed)
    failed_count = len(checks) - passed_count
    audit_lines.extend(
        [
            "",
            f"Checks passed: {passed_count}",
            f"Checks failed: {failed_count}",
            f"Overall status: {'PASS' if failed_count == 0 else 'FAIL'}",
            "",
            "OUTPUTS",
            "-" * 72,
            f"Review register CSV: {OUTPUT_CSV}",
            f"Audit TXT: {OUTPUT_AUDIT}",
        ]
    )
    OUTPUT_AUDIT.write_text("\n".join(audit_lines) + "\n", encoding="utf-8")

    print("\n".join(audit_lines))

    return 0 if failed_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
