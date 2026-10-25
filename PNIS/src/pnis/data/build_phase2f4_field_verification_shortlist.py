from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"

SOURCE = PROCESSED / "phase2f3_manual_verification_register.csv"

SHORTLIST = PROCESSED / "phase2f4_field_verification_shortlist.csv"
BOUNDARY = PROCESSED / "phase2f4_boundary_review_register.csv"
AUDIT = PROCESSED / "phase2f4_verification_audit.txt"

REQUIRED = [
    "candidate_record_id",
    "osm_id",
    "source_layer",
    "fclass",
    "review_group",
    "longitude",
    "latitude",
    "spatial_classification",
    "review_priority_rank",
    "recommended_review_action",
    "review_priority",
    "verification_status",
    "operational_facility_confirmed",
    "routing_eligibility",
]

SHORTLIST_COLUMNS = [
    "candidate_record_id",
    "osm_id",
    "code",
    "name",
    "fclass",
    "source_layer",
    "candidate_match_text",
    "review_group",
    "longitude",
    "latitude",
    "spatial_classification",
    "review_priority_rank",
    "review_priority",
    "recommended_review_action",
    "verification_status",
    "verification_source",
    "reviewer_notes",
    "coordinate_review_status",
    "operational_facility_confirmed",
    "routing_eligibility",
    "boundary_osm_id",
    "boundary_admin_level",
    "boundary_name",
    "boundary_source",
]

def clean_text(series):
    return series.fillna("").astype(str).str.strip()

def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f"Required input not found: {SOURCE}")

    df = pd.read_csv(SOURCE, low_memory=False)

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Required columns missing: {missing}")

    df["spatial_classification"] = clean_text(
        df["spatial_classification"]
    ).str.upper()

    df["verification_status"] = clean_text(
        df["verification_status"]
    ).str.upper()

    df["operational_facility_confirmed"] = clean_text(
        df["operational_facility_confirmed"]
    ).str.upper()

    df["routing_eligibility"] = clean_text(
        df["routing_eligibility"]
    ).str.upper()

    df["review_priority"] = clean_text(df["review_priority"])
    df["review_group"] = clean_text(df["review_group"])
    df["recommended_review_action"] = clean_text(
        df["recommended_review_action"]
    )

    df["review_priority_rank"] = pd.to_numeric(
        df["review_priority_rank"], errors="coerce"
    )

    if df["candidate_record_id"].isna().any():
        raise ValueError("Missing candidate_record_id values detected.")

    if df["candidate_record_id"].duplicated().any():
        duplicates = df.loc[
            df["candidate_record_id"].duplicated(keep=False),
            "candidate_record_id"
        ].tolist()
        raise ValueError(f"Duplicate candidate IDs detected: {duplicates[:10]}")

    # Keep the source classifications unchanged.
    inside = df[df["spatial_classification"] == "INSIDE_SIDAMA"].copy()
    boundary = df[df["spatial_classification"] == "BOUNDARY_REVIEW"].copy()

    if len(inside) != 255:
        raise ValueError(
            f"Expected 255 INSIDE_SIDAMA candidates; found {len(inside)}."
        )

    if len(boundary) != 3:
        raise ValueError(
            f"Expected 3 BOUNDARY_REVIEW candidates; found {len(boundary)}."
        )

    # Never upgrade verification or routing status in this step.
    unsafe = df[
        (df["verification_status"] != "UNVERIFIED")
        | (df["operational_facility_confirmed"] != "NO")
        | (
            df["routing_eligibility"]
            != "NOT_APPROVED_FOR_OPERATIONAL_ROUTING"
        )
    ]

    if not unsafe.empty:
        raise ValueError(
            "Safety check failed: source has records whose verification, "
            "operational confirmation, or routing status differs from "
            "the expected unverified state."
        )

    # Sort inside-Sidama candidates by proposed review priority.
    inside = inside.sort_values(
        by=[
            "review_priority_rank",
            "review_group",
            "source_layer",
            "fclass",
            "candidate_record_id",
        ],
        ascending=[True, True, True, True, True],
        na_position="last",
        kind="stable",
    )

    # Add a review sequence number; this does not indicate verification.
    inside.insert(
        0,
        "field_review_sequence",
        range(1, len(inside) + 1),
    )

    boundary = boundary.sort_values(
        by=["candidate_record_id"], kind="stable"
    )

    # Include only columns available in the source.
    shortlist_cols = [
        c for c in ["field_review_sequence"] + SHORTLIST_COLUMNS
        if c in inside.columns
    ]
    boundary_cols = [
        c for c in SHORTLIST_COLUMNS if c in boundary.columns
    ]

    inside[shortlist_cols].to_csv(
        SHORTLIST, index=False, encoding="utf-8-sig"
    )
    boundary[boundary_cols].to_csv(
        BOUNDARY, index=False, encoding="utf-8-sig"
    )

    # Reload outputs to validate the files that were actually written.
    saved_shortlist = pd.read_csv(SHORTLIST, low_memory=False)
    saved_boundary = pd.read_csv(BOUNDARY, low_memory=False)

    shortlist_ids = set(saved_shortlist["candidate_record_id"].astype(str))
    boundary_ids = set(saved_boundary["candidate_record_id"].astype(str))
    source_inside_ids = set(inside["candidate_record_id"].astype(str))
    source_boundary_ids = set(boundary["candidate_record_id"].astype(str))

    shortlist_id_match = shortlist_ids == source_inside_ids
    boundary_id_match = boundary_ids == source_boundary_ids

    coords = saved_shortlist[["longitude", "latitude"]].apply(
        pd.to_numeric, errors="coerce"
    )
    invalid_coords = (
        coords.isna().any(axis=1)
        | ~coords["longitude"].between(-180, 180)
        | ~coords["latitude"].between(-90, 90)
    )

    shortlist_safety_ok = (
        saved_shortlist["verification_status"].eq("UNVERIFIED").all()
        and saved_shortlist["operational_facility_confirmed"].eq("NO").all()
        and saved_shortlist["routing_eligibility"].eq(
            "NOT_APPROVED_FOR_OPERATIONAL_ROUTING"
        ).all()
    )

    boundary_safety_ok = (
        saved_boundary["verification_status"].eq("UNVERIFIED").all()
        and saved_boundary["operational_facility_confirmed"].eq("NO").all()
        and saved_boundary["routing_eligibility"].eq(
            "NOT_APPROVED_FOR_OPERATIONAL_ROUTING"
        ).all()
    )

    inside_priority_counts = saved_shortlist[
        "review_priority"
    ].value_counts(dropna=False).to_dict()

    inside_group_counts = saved_shortlist[
        "review_group"
    ].value_counts(dropna=False).to_dict()

    source_layer_counts = saved_shortlist[
        "source_layer"
    ].value_counts(dropna=False).to_dict()

    passed = all([
        len(saved_shortlist) == 255,
        len(saved_boundary) == 3,
        shortlist_id_match,
        boundary_id_match,
        not invalid_coords.any(),
        shortlist_safety_ok,
        boundary_safety_ok,
        len(set(saved_shortlist["candidate_record_id"])) == 255,
        len(set(saved_boundary["candidate_record_id"])) == 3,
        shortlist_ids.isdisjoint(boundary_ids),
    ])

    lines = [
        "PHASE 2F.4 - FIELD VERIFICATION SHORTLIST AUDIT",
        "=" * 72,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Status: {'completed' if passed else 'failed'}",
        "",
        f"Input: {SOURCE}",
        f"Field verification shortlist: {SHORTLIST}",
        f"Separate boundary review register: {BOUNDARY}",
        "",
        "RECORD COUNTS",
        "-" * 72,
        f"Source register rows: {len(df)}",
        f"Inside-Sidama shortlist rows: {len(saved_shortlist)}",
        f"Boundary-review rows: {len(saved_boundary)}",
        f"Outside-Sidama records retained in source: "
        f"{int((df['spatial_classification'] == 'OUTSIDE_SIDAMA').sum())}",
        "",
        "SHORTLIST PRIORITY COUNTS",
        "-" * 72,
    ]

    for key, value in sorted(inside_priority_counts.items()):
        lines.append(f"  {key}: {value}")

    lines.extend([
        "",
        "SHORTLIST REVIEW-GROUP COUNTS",
        "-" * 72,
    ])
    for key, value in sorted(inside_group_counts.items()):
        lines.append(f"  {key}: {value}")

    lines.extend([
        "",
        "SHORTLIST SOURCE-LAYER COUNTS",
        "-" * 72,
    ])
    for key, value in sorted(source_layer_counts.items()):
        lines.append(f"  {key}: {value}")

    lines.extend([
        "",
        "VALIDATION CHECKS",
        "-" * 72,
        f"Shortlist IDs match inside-Sidama source IDs: {shortlist_id_match}",
        f"Boundary IDs match boundary source IDs: {boundary_id_match}",
        f"Shortlist IDs unique: "
        f"{saved_shortlist['candidate_record_id'].is_unique}",
        f"Boundary IDs unique: "
        f"{saved_boundary['candidate_record_id'].is_unique}",
        f"Shortlist and boundary IDs disjoint: "
        f"{shortlist_ids.isdisjoint(boundary_ids)}",
        f"Invalid shortlist coordinates: {int(invalid_coords.sum())}",
        f"Shortlist safety flags intact: {shortlist_safety_ok}",
        f"Boundary safety flags intact: {boundary_safety_ok}",
        "",
        "INTERPRETATION AND LIMITATIONS",
        "-" * 72,
        "- This is a review shortlist, not a verified facility inventory.",
        "- Review priority is a proposed order, not proof of facility function.",
        "- OSM tags alone do not establish operational status or vehicle access.",
        "- Boundary-review records are separate and remain unresolved.",
        "- Outside-Sidama records remain in the original source register.",
        "- No candidate is approved for operational routing by this step.",
        "",
    ])

    AUDIT.write_text("\n".join(lines), encoding="utf-8")

    print("=" * 72)
    print("PHASE 2F.4 - OUTPUTS")
    print("=" * 72)
    print(f"Status: {'completed' if passed else 'FAILED'}")
    print(f"Shortlist rows: {len(saved_shortlist)}")
    print(f"Boundary review rows: {len(saved_boundary)}")
    print(f"Invalid shortlist coordinates: {int(invalid_coords.sum())}")
    print(f"Shortlist IDs match source: {shortlist_id_match}")
    print(f"Boundary IDs match source: {boundary_id_match}")
    print(f"Safety flags intact: {shortlist_safety_ok and boundary_safety_ok}")
    print(f"\nShortlist: {SHORTLIST}")
    print(f"Boundary register: {BOUNDARY}")
    print(f"Audit: {AUDIT}")

    if not passed:
        raise SystemExit("Phase 2F.4 validation failed; inspect the audit.")

if __name__ == "__main__":
    main()
