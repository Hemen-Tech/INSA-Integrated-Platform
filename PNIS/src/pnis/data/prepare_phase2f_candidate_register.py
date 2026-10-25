
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path.cwd()
PROCESSED = ROOT / "data" / "processed"

INPUT = PROCESSED / "phase2f_osm_facility_candidates.csv"
OUTPUT = PROCESSED / "phase2f_candidate_review_register.csv"
SUMMARY_TXT = PROCESSED / "phase2f_candidate_review_summary.txt"
SUMMARY_JSON = PROCESSED / "phase2f_candidate_review_summary.json"


def classify(row: pd.Series) -> tuple[str, str]:
    layer = str(row.get("source_layer", "")).lower()
    fclass = str(row.get("fclass", "")).strip().lower()
    name = str(row.get("name", "")).strip()

    if fclass in {"marketplace"}:
        return (
            "MARKET_CANDIDATE",
            "Review market identity, activity, and exact operating location.",
        )

    if fclass in {"farmyard"}:
        return (
            "AGRICULTURAL_SITE_CANDIDATE",
            "Verify whether this is an active farm or collection location.",
        )

    if fclass in {"farmland"}:
        return (
            "AGRICULTURAL_LAND_ONLY",
            "Land-use polygon; do not treat as an operational facility without evidence.",
        )

    if fclass in {"industrial"}:
        return (
            "INDUSTRIAL_SITE_CANDIDATE",
            "Verify site purpose; do not assume warehouse or food-processing use.",
        )

    if fclass in {"warehouse", "storage", "cold_storage"}:
        return (
            "STORAGE_CANDIDATE",
            "Verify that this is a real, active storage facility.",
        )

    if fclass in {"supermarket", "convenience", "greengrocer", "kiosk"}:
        return (
            "RETAIL_OR_FOOD_MARKET_CANDIDATE",
            "Verify whether it is relevant to the perishable supply chain.",
        )

    if fclass in {"farm", "agricultural", "agriculture"}:
        return (
            "AGRICULTURAL_FACILITY_CANDIDATE",
            "Verify the site type and operational status.",
        )

    if fclass in {"village", "town", "city", "hamlet", "locality"}:
        return (
            "SETTLEMENT_REFERENCE",
            "Geographic reference only; not an operational facility.",
        )

    if "places_free" in layer:
        return (
            "PLACE_OR_POI_REVIEW",
            "Review the feature class and evidence before assigning a role.",
        )

    if "buildings" in layer or fclass == "building":
        return (
            "BUILDING_CANDIDATE",
            "Building footprint alone does not establish facility use.",
        )

    return (
        "OTHER_POI_REVIEW",
        "Review category, name, and source evidence before use.",
    )


def main() -> None:
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Candidate file not found: {INPUT}\n"
            "Run the Phase 2F source inventory first."
        )

    PROCESSED.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(INPUT, dtype=str, keep_default_na=False)

    required = {"source_layer", "osm_id", "fclass", "name"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Input is missing required columns: {sorted(missing)}"
        )

    # Keep every source row; flag duplicate IDs instead of deleting them.
    df["osm_id"] = df["osm_id"].astype(str).str.strip()
    df["source_layer"] = df["source_layer"].astype(str).str.strip()

    df["duplicate_osm_id"] = df["osm_id"].duplicated(keep=False)
    df["duplicate_layer_and_osm_id"] = df.duplicated(
        subset=["source_layer", "osm_id"],
        keep=False,
    )

    classifications = df.apply(classify, axis=1)
    df["review_group"] = [item[0] for item in classifications]
    df["review_guidance"] = [item[1] for item in classifications]

    df["verification_status"] = "UNVERIFIED"
    df["operational_facility_confirmed"] = "NO"
    df["verification_source"] = ""
    df["reviewer_notes"] = ""

    df["coordinate_review_status"] = (
        "NOT_YET_REVIEWED"
    )
    df["routing_eligibility"] = (
        "NOT_APPROVED_FOR_OPERATIONAL_ROUTING"
    )

    # Stable review ordering; original records and fields remain intact.
    df = df.sort_values(
        ["review_group", "source_layer", "fclass", "name", "osm_id"],
        kind="stable",
    ).reset_index(drop=True)

    df.insert(0, "candidate_record_id", [
        f"PNIS2F-{i:05d}" for i in range(1, len(df) + 1)
    ])

    df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")

    group_counts = (
        df.groupby("review_group", dropna=False)
        .size()
        .sort_values(ascending=False)
        .to_dict()
    )
    layer_counts = (
        df.groupby("source_layer", dropna=False)
        .size()
        .sort_values(ascending=False)
        .to_dict()
    )
    class_counts = (
        df.groupby("fclass", dropna=False)
        .size()
        .sort_values(ascending=False)
        .to_dict()
    )

    duplicate_id_rows = int(df["duplicate_osm_id"].sum())
    duplicate_layer_id_rows = int(
        df["duplicate_layer_and_osm_id"].sum()
    )

    report = [
        "PHASE 2F — CANDIDATE REVIEW REGISTER",
        "=" * 72,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Input: {INPUT}",
        f"Output: {OUTPUT}",
        "",
        f"Input rows: {len(df)}",
        f"Output rows: {len(df)}",
        f"Rows with repeated OSM ID across input: {duplicate_id_rows}",
        f"Rows repeated within same layer and OSM ID: {duplicate_layer_id_rows}",
        "",
        "REVIEW GROUP COUNTS",
        "-" * 72,
    ]

    for key, count in group_counts.items():
        report.append(f"{key}: {count}")

    report += ["", "SOURCE LAYER COUNTS", "-" * 72]
    for key, count in layer_counts.items():
        report.append(f"{key}: {count}")

    report += ["", "FEATURE CLASS COUNTS", "-" * 72]
    for key, count in class_counts.items():
        report.append(f"{key or '(blank)'}: {count}")

    report += [
        "",
        "CONTROL NOTES",
        "-" * 72,
        "All candidates remain UNVERIFIED.",
        "No candidate is approved for operational routing.",
        "Farmland is not equivalent to a farm facility.",
        "Industrial land is not equivalent to a warehouse.",
        "Settlement references are not operational facilities.",
        "Duplicate IDs are flagged, not automatically deleted.",
        "No source GeoPackage or Phase 2C/2E output was modified.",
    ]

    SUMMARY_TXT.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )

    summary_json = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "input": str(INPUT),
        "output": str(OUTPUT),
        "input_rows": len(df),
        "output_rows": len(df),
        "review_group_counts": group_counts,
        "source_layer_counts": layer_counts,
        "feature_class_counts": class_counts,
        "rows_with_repeated_osm_id": duplicate_id_rows,
        "rows_repeated_within_layer_and_osm_id": duplicate_layer_id_rows,
        "all_candidates_unverified": True,
        "approved_for_operational_routing": 0,
        "source_and_phase2c_phase2e_outputs_modified": False,
    }

    SUMMARY_JSON.write_text(
        json.dumps(summary_json, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("PHASE 2F REVIEW REGISTER CREATED")
    print(f"Input rows: {len(df)}")
    print(f"Output rows: {len(df)}")
    print(f"Repeated OSM ID rows: {duplicate_id_rows}")
    print(f"Review register: {OUTPUT}")
    print(f"Summary: {SUMMARY_TXT}")
    print(f"JSON summary: {SUMMARY_JSON}")


if __name__ == "__main__":
    main()
