from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"

SOURCE = PROCESSED / "phase2f4_field_verification_shortlist.csv"
OUTPUT = PROCESSED / "phase2f5_verification_evidence_register.csv"
AUDIT = PROCESSED / "phase2f5_verification_evidence_audit.txt"

REQUIRED = [
    "candidate_record_id",
    "osm_id",
    "source_layer",
    "fclass",
    "longitude",
    "latitude",
    "spatial_classification",
    "verification_status",
    "operational_facility_confirmed",
    "routing_eligibility",
]

# New fields are intentionally blank or pending.
# They must be completed using actual evidence, not inferred from OSM tags.
NEW_FIELDS = {
    "actual_facility_type": "",
    "facility_name_verified": "",
    "operating_status_review": "NOT_REVIEWED",
    "facility_function_evidence": "",
    "facility_evidence_reference": "",
    "facility_evidence_date": "",
    "coordinate_verification_status": "NOT_REVIEWED",
    "coordinate_evidence_source": "",
    "coordinate_evidence_reference": "",
    "vehicle_access_review": "NOT_REVIEWED",
    "vehicle_types_supported": "",
    "vehicle_access_restrictions": "",
    "road_access_evidence": "",
    "road_access_evidence_reference": "",
    "reviewer_name_or_id": "",
    "review_date": "",
    "verification_decision": "REVIEW_PENDING",
    "decision_rationale": "",
    "follow_up_required": "YES",
    "follow_up_action": "",
    "review_record_status": "NOT_STARTED",
    "verified_operational_facility": "NO",
    "routing_eligibility_review": "NOT_APPROVED_FOR_OPERATIONAL_ROUTING",
}

def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f"Input not found: {SOURCE}")

    df = pd.read_csv(SOURCE, low_memory=False)

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Required columns missing: {missing}")

    if df["candidate_record_id"].isna().any():
        raise ValueError("Missing candidate IDs found.")

    if df["candidate_record_id"].duplicated().any():
        raise ValueError("Duplicate candidate IDs found.")

    # Validate the source state before adding new fields.
    expected_states = {
        "verification_status": "UNVERIFIED",
        "operational_facility_confirmed": "NO",
        "routing_eligibility": "NOT_APPROVED_FOR_OPERATIONAL_ROUTING",
    }

    for column, expected in expected_states.items():
        values = df[column].fillna("").astype(str).str.strip().str.upper()
        if not values.eq(expected).all():
            raise ValueError(
                f"Unexpected source state in {column}; "
                "stop and inspect the input before continuing."
            )

    classification = (
        df["spatial_classification"]
        .fillna("").astype(str).str.strip().str.upper()
    )
    if not classification.eq("INSIDE_SIDAMA").all():
        raise ValueError(
            "The Phase 2F.4 shortlist contains records not classified "
            "INSIDE_SIDAMA. Inspect the input before proceeding."
        )

    coords = df[["longitude", "latitude"]].apply(
        pd.to_numeric, errors="coerce"
    )
    invalid_coords = (
        coords.isna().any(axis=1)
        | ~coords["longitude"].between(-180, 180)
        | ~coords["latitude"].between(-90, 90)
    )

    if invalid_coords.any():
        raise ValueError(
            f"Found {int(invalid_coords.sum())} invalid coordinate rows."
        )

    # Do not overwrite any existing columns.
    conflicts = [c for c in NEW_FIELDS if c in df.columns]
    if conflicts:
        raise ValueError(
            f"New evidence fields already exist in source: {conflicts}"
        )

    for column, initial_value in NEW_FIELDS.items():
        df[column] = initial_value

    # Write a new file; leave Phase 2F.3 and 2F.4 outputs unchanged.
    df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")

    # Reload the actual written file for validation.
    saved = pd.read_csv(OUTPUT, low_memory=False)

    ids_match = (
        set(saved["candidate_record_id"].astype(str))
        == set(pd.read_csv(SOURCE)["candidate_record_id"].astype(str))
    )

    required_evidence_fields = [
        "facility_function_evidence",
        "facility_evidence_reference",
        "coordinate_evidence_source",
        "coordinate_evidence_reference",
        "road_access_evidence",
        "road_access_evidence_reference",
        "reviewer_name_or_id",
        "review_date",
        "decision_rationale",
    ]

    evidence_fields_initially_blank = all(
        saved[c].fillna("").astype(str).str.strip().eq("").all()
        for c in required_evidence_fields
    )

    safety_ok = (
        saved["verification_status"].eq("UNVERIFIED").all()
        and saved["operational_facility_confirmed"].eq("NO").all()
        and saved["routing_eligibility"].eq(
            "NOT_APPROVED_FOR_OPERATIONAL_ROUTING"
        ).all()
        and saved["verified_operational_facility"].eq("NO").all()
        and saved["routing_eligibility_review"].eq(
            "NOT_APPROVED_FOR_OPERATIONAL_ROUTING"
        ).all()
    )

    review_state_ok = (
        saved["verification_decision"].eq("REVIEW_PENDING").all()
        and saved["review_record_status"].eq("NOT_STARTED").all()
        and saved["follow_up_required"].eq("YES").all()
    )

    checks = {
        "row_count_is_255": len(saved) == 255,
        "candidate_ids_unique": saved["candidate_record_id"].is_unique,
        "candidate_ids_match_source": ids_match,
        "coordinates_valid": not invalid_coords.any(),
        "evidence_fields_start_blank": evidence_fields_initially_blank,
        "safety_flags_preserved": safety_ok,
        "review_state_initialization_valid": review_state_ok,
    }

    passed = all(checks.values())

    lines = [
        "PHASE 2F.5 - VERIFICATION EVIDENCE REGISTER AUDIT",
        "=" * 72,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Status: {'completed' if passed else 'failed'}",
        "",
        f"Input: {SOURCE}",
        f"Evidence register: {OUTPUT}",
        "",
        "RECORD SUMMARY",
        "-" * 72,
        f"Input rows: {len(pd.read_csv(SOURCE, low_memory=False))}",
        f"Output rows: {len(saved)}",
        f"Unique candidate IDs: {saved['candidate_record_id'].nunique()}",
        f"Invalid coordinate rows: {int(invalid_coords.sum())}",
        f"New evidence/review fields added: {len(NEW_FIELDS)}",
        "",
        "VALIDATION CHECKS",
        "-" * 72,
    ]

    for name, result in checks.items():
        lines.append(f"{name}: {'PASS' if result else 'FAIL'}")

    lines.extend([
        "",
        "IMPORTANT LIMITATIONS",
        "-" * 72,
        "- This register is a template for collecting evidence.",
        "- No facility has been independently verified by this script.",
        "- Blank evidence fields mean evidence still needs to be collected.",
        "- OSM classifications do not prove actual facility function.",
        "- Vehicle access must be supported by evidence or field review.",
        "- No candidate is approved for operational routing.",
        "- Review decisions must be traceable to supporting evidence.",
        "",
    ])

    AUDIT.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    print("=" * 72)
    print("PHASE 2F.5 - OUTPUTS")
    print("=" * 72)
    print(f"Status: {'completed' if passed else 'FAILED'}")
    print(f"Rows: {len(saved)}")
    print(f"Unique IDs: {saved['candidate_record_id'].nunique()}")
    print(f"Invalid coordinate rows: {int(invalid_coords.sum())}")
    print(f"Safety flags preserved: {safety_ok}")
    print(f"Evidence fields start blank: {evidence_fields_initially_blank}")
    print(f"\nEvidence register: {OUTPUT}")
    print(f"Audit: {AUDIT}")

    if not passed:
        raise SystemExit("Phase 2F.5 validation failed. Inspect the audit.")

if __name__ == "__main__":
    main()
