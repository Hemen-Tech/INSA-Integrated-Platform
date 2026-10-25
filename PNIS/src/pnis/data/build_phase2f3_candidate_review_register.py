from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "data" / "processed" / (
    "phase2f2_osm_facility_candidates_spatially_classified_v1.csv"
)
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

SUMMARY_OUT = OUT / "phase2f3_candidate_category_summary.csv"
REGISTER_OUT = OUT / "phase2f3_manual_verification_register.csv"
AUDIT_OUT = OUT / "phase2f3_candidate_review_audit.txt"

REQUIRED = [
    "candidate_record_id", "osm_id", "source_layer", "fclass",
    "review_group", "longitude", "latitude",
    "spatial_classification", "verification_status",
    "operational_facility_confirmed", "routing_eligibility",
]

def clean(series):
    return series.fillna("").astype(str).str.strip()

def priority(row):
    spatial = row["spatial_classification"]
    group = row["review_group"]
    fclass = row["fclass"]

    if spatial == "BOUNDARY_REVIEW":
        return 0, "BOUNDARY_REVIEW_REQUIRED"

    if spatial != "INSIDE_SIDAMA":
        return 9, "OUTSIDE_SIDAMA_NOT_IN_INITIAL_REVIEW"

    if group in {
        "MARKET_CANDIDATE",
        "RETAIL_OR_FOOD_MARKET_CANDIDATE",
    }:
        return 1, "VERIFY_MARKET_AND_PERISHABLES_FUNCTION"

    if group == "INDUSTRIAL_SITE_CANDIDATE":
        return 2, "VERIFY_WAREHOUSE_STORAGE_OR_OTHER_USE"

    if group == "BUILDING_CANDIDATE":
        return 3, "VERIFY_BUILDING_FUNCTION"

    if group == "AGRICULTURAL_LAND_ONLY" or fclass in {
        "farmland", "farmyard"
    }:
        return 4, "VERIFY_FARM_OR_COLLECTION_POINT"

    if group == "SETTLEMENT_REFERENCE":
        return 5, "VERIFY_SETTLEMENT_AND_LOCAL_MARKET_REFERENCES"

    return 6, "GENERAL_MANUAL_REVIEW"

def main():
    if not INPUT.exists():
        raise FileNotFoundError(f"Input not found: {INPUT}")

    df = pd.read_csv(INPUT, dtype=str, keep_default_na=False)

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Required columns missing: {missing}")

    # Normalize only category/identifier text used in reporting.
    for col in [
        "candidate_record_id", "osm_id", "source_layer", "fclass",
        "review_group", "spatial_classification",
        "verification_status", "operational_facility_confirmed",
        "routing_eligibility",
    ]:
        df[col] = clean(df[col])

    if df["candidate_record_id"].duplicated().any():
        duplicates = df.loc[
            df["candidate_record_id"].duplicated(keep=False),
            "candidate_record_id",
        ].tolist()
        raise ValueError(f"Duplicate candidate IDs: {duplicates[:20]}")

    # Category summary: a single file with an explicit dimension column.
    summaries = []
    for col in ["source_layer", "fclass", "review_group",
                "spatial_classification"]:
        counts = (
            df.groupby(col, dropna=False)
              .size()
              .reset_index(name="count")
              .rename(columns={col: "category"})
        )
        counts.insert(0, "dimension", col)
        summaries.append(counts)

    summary = pd.concat(summaries, ignore_index=True)
    summary.to_csv(SUMMARY_OUT, index=False, encoding="utf-8-sig")

    # Add review priority, without confirming any facility.
    ranked = df.apply(priority, axis=1, result_type="expand")
    ranked.columns = ["review_priority_rank", "recommended_review_action"]
    df = pd.concat([df, ranked], axis=1)

    df["review_priority_rank"] = df["review_priority_rank"].astype(int)
    df["review_priority"] = df["review_priority_rank"].map({
        0: "BOUNDARY_REVIEW",
        1: "HIGH",
        2: "HIGH",
        3: "MEDIUM",
        4: "MEDIUM",
        5: "LOW",
        6: "LOW",
        9: "OUTSIDE_INITIAL_SCOPE",
    })

    # Conservative controls: this script never approves a candidate.
    df["verification_status"] = "UNVERIFIED"
    df["operational_facility_confirmed"] = "NO"
    df["routing_eligibility"] = "NOT_APPROVED_FOR_OPERATIONAL_ROUTING"

    df = df.sort_values(
        ["review_priority_rank", "candidate_record_id"],
        kind="stable",
    )
    df.to_csv(REGISTER_OUT, index=False, encoding="utf-8-sig")

    inside = df[df["spatial_classification"] == "INSIDE_SIDAMA"]
    spatial_counts = df["spatial_classification"].value_counts().to_dict()
    source_inside = inside["source_layer"].value_counts(dropna=False)
    source_inside_total = int(source_inside.sum())

    missing_coords = (
        df["longitude"].str.strip().eq("").sum()
        + df["latitude"].str.strip().eq("").sum()
    )
    invalid_coords = 0
    for col in ["longitude", "latitude"]:
        values = pd.to_numeric(df[col], errors="coerce")
        invalid_coords += int(values.isna().sum())

    bad_unverified = int((df["verification_status"] != "UNVERIFIED").sum())
    bad_confirmed = int(
        (df["operational_facility_confirmed"] != "NO").sum()
    )
    bad_routing = int(
        (df["routing_eligibility"] !=
         "NOT_APPROVED_FOR_OPERATIONAL_ROUTING").sum()
    )

    with AUDIT_OUT.open("w", encoding="utf-8") as f:
        f.write("PHASE 2F.3 — CANDIDATE REVIEW AND PRIORITIZATION\n")
        f.write("=" * 64 + "\n")
        f.write(f"Generated UTC: {datetime.now(timezone.utc).isoformat()}\n")
        f.write("Status: " + (
            "completed" if (
                len(df) == 497
                and df["candidate_record_id"].is_unique
                and bad_unverified == 0
                and bad_confirmed == 0
                and bad_routing == 0
            ) else "review_required"
        ) + "\n\n")

        f.write(f"Input: {INPUT}\n")
        f.write(f"Rows in register: {len(df)}\n")
        f.write(f"Unique candidate IDs: {df['candidate_record_id'].nunique()}\n")
        f.write(f"Inside Sidama: {len(inside)}\n")
        f.write(f"Source-layer counts for inside candidates sum to: "
                f"{source_inside_total}\n")
        f.write(f"Blank coordinate cells (longitude + latitude): "
                f"{missing_coords}\n")
        f.write(f"Non-numeric/missing coordinate values: {invalid_coords}\n\n")

        f.write("SPATIAL CLASSIFICATION COUNTS\n")
        for key, value in sorted(spatial_counts.items()):
            f.write(f"  {key}: {value}\n")

        f.write("\nREVIEW PRIORITY COUNTS\n")
        for key, value in df["review_priority"].value_counts().items():
            f.write(f"  {key}: {value}\n")

        f.write("\nINSIDE-SIDAMA SOURCE LAYER COUNTS\n")
        for key, value in source_inside.items():
            f.write(f"  {key or '[BLANK]'}: {value}\n")

        f.write("\nSAFETY VALIDATION\n")
        f.write(f"Non-UNVERIFIED rows: {bad_unverified}\n")
        f.write(f"Rows confirmed operational: {bad_confirmed}\n")
        f.write(f"Rows approved for operational routing: {bad_routing}\n")

        f.write("\nLIMITATIONS\n")
        f.write("- Priorities are proposed review order, not verified facility status.\n")
        f.write("- OSM tags do not establish actual market, warehouse, farm, or "
                "collection-point function.\n")
        f.write("- Outside-Sidama candidates are retained, not deleted.\n")
        f.write("- Boundary-review candidates remain flagged for review.\n")
        f.write("- No candidate is approved for operational routing.\n")

    print("PHASE 2F.3 — OUTPUTS")
    print(f"Category summary: {SUMMARY_OUT}")
    print(f"Manual review register: {REGISTER_OUT}")
    print(f"Audit: {AUDIT_OUT}")
    print(f"Rows: {len(df)}")
    print(f"Unique IDs: {df['candidate_record_id'].nunique()}")
    print(f"Inside candidates: {len(inside)}")
    print(f"Inside source-layer total: {source_inside_total}")
    print(f"Coordinate issues: {invalid_coords}")
    print(f"Safety flags: unverified={bad_unverified}, "
          f"confirmed={bad_confirmed}, routing-approved={bad_routing}")

if __name__ == "__main__":
    main()
