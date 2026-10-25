
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"

INPUT_CSV = (
    PROCESSED
    / "phase2g1_candidate_road_proximity_register.csv"
)
OUTPUT_CSV = (
    PROCESSED
    / "phase2g2_access_review_register.csv"
)
OUTPUT_AUDIT = (
    PROCESSED
    / "phase2g2_access_review_audit.txt"
)

EXPECTED_ROWS = 255


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
) -> str:
    lookup = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]

    raise ValueError(
        f"Required column not found: {candidates}\n"
        f"Available columns: {list(df.columns)}"
    )


def main() -> int:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(
            f"Required Phase 2G.1 register not found:\n"
            f"{INPUT_CSV}"
        )

    df = pd.read_csv(INPUT_CSV, low_memory=False)

    if df.empty:
        raise ValueError(
            "Phase 2G.1 register is empty."
        )

    id_col = find_column(
        df,
        [
            "candidate_id",
            "candidate_record_id",
            "record_id",
            "candidate_uid",
            "review_id",
        ],
    )

    distance_col = find_column(
        df,
        ["nearest_mapped_road_distance_m"],
    )

    band_col = find_column(
        df,
        ["road_proximity_band"],
    )

    # Validate candidate identifiers.
    df[id_col] = df[id_col].astype("string").str.strip()

    if df[id_col].isna().any() or df[id_col].eq("").any():
        raise ValueError(
            "Candidate IDs contain missing or blank values."
        )

    if df[id_col].duplicated().any():
        duplicates = (
            df.loc[
                df[id_col].duplicated(keep=False),
                id_col,
            ]
            .astype(str)
            .unique()
            .tolist()[:10]
        )

        raise ValueError(
            f"Duplicate candidate IDs found: {duplicates}"
        )

    # Validate distances.
    df[distance_col] = pd.to_numeric(
        df[distance_col],
        errors="coerce",
    )

    if (
        df[distance_col].isna().any()
        or (df[distance_col] < 0).any()
    ):
        raise ValueError(
            "Road distances must be numeric, nonnegative, "
            "and complete."
        )

    # Review priorities organize fieldwork only.
    # They do not establish physical access or facility validity.
    def assign_priority(distance: float) -> str:
        if distance > 500:
            return "P1_FAR_FROM_MAPPED_ROAD"

        if distance > 250:
            return "P2_MODERATE_DISTANCE"

        if distance > 100:
            return "P3_PROXIMITY_REVIEW"

        return "P4_NEAR_ROAD_STILL_REQUIRES_ACCESS_CHECK"

    df["phase2g2_review_priority"] = (
        df[distance_col].map(assign_priority)
    )

    # Create manual-review fields if they do not exist.
    defaults = {
        "physical_entrance_status": "NOT_REVIEWED",
        "vehicle_access_status": "NOT_VERIFIED",
        "road_surface_suitability_status": "NOT_VERIFIED",
        "seasonal_passability_status": "NOT_VERIFIED",
        "vehicle_restriction_status": "NOT_VERIFIED",
        "field_verification_status": "PENDING",
        "access_decision": "REVIEW_PENDING",
        "access_evidence_reference": "",
        "reviewer_name": "",
        "review_date": "",
        "review_notes": "",
        "physical_vehicle_access_confirmed": "NO",
        "operational_facility_verified": "NO",
        "routing_eligible": "NO",
        "routing_exclusion_reason": (
            "Physical entrance, vehicle suitability, and "
            "operational facility status have not been verified. "
            "Road proximity alone is insufficient."
        ),
        "phase2g2_assessment_timestamp_utc": (
            datetime.now(timezone.utc).isoformat()
        ),
    }

    for column, default_value in defaults.items():
        if column not in df.columns:
            df[column] = default_value

    # Enforce conservative status defaults for this automated build.
    # No candidate is approved by proximity alone.
    df["physical_vehicle_access_confirmed"] = "NO"
    df["operational_facility_verified"] = "NO"
    df["routing_eligible"] = "NO"
    df["access_decision"] = "REVIEW_PENDING"
    df["field_verification_status"] = "PENDING"

    # Write a separate output; never overwrite the source register.
    df.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    # Automated validation.
    checks: list[tuple[str, bool, str]] = []

    def add_check(
        name: str,
        passed: bool,
        detail: str,
    ) -> None:
        checks.append((name, bool(passed), detail))

    add_check(
        "expected_candidate_count",
        len(df) == EXPECTED_ROWS,
        f"rows={len(df)}, expected={EXPECTED_ROWS}",
    )

    add_check(
        "candidate_ids_unique",
        df[id_col].nunique() == len(df),
        f"unique_ids={df[id_col].nunique()}",
    )

    add_check(
        "distance_values_valid",
        (
            df[distance_col].notna().all()
            and (df[distance_col] >= 0).all()
        ),
        f"valid_distances={df[distance_col].notna().sum()}",
    )

    add_check(
        "priority_values_assigned",
        df["phase2g2_review_priority"].notna().all(),
        (
            "assigned="
            f"{df['phase2g2_review_priority'].notna().sum()}"
        ),
    )

    add_check(
        "field_verification_pending",
        (
            df["field_verification_status"]
            .eq("PENDING")
            .all()
        ),
        (
            "non_pending="
            f"{(~df['field_verification_status'].eq('PENDING')).sum()}"
        ),
    )

    add_check(
        "access_decision_pending",
        df["access_decision"].eq("REVIEW_PENDING").all(),
        (
            "non_pending="
            f"{(~df['access_decision'].eq('REVIEW_PENDING')).sum()}"
        ),
    )

    add_check(
        "no_physical_access_confirmed",
        df["physical_vehicle_access_confirmed"].eq("NO").all(),
        (
            "confirmed_yes="
            f"{df['physical_vehicle_access_confirmed'].eq('YES').sum()}"
        ),
    )

    add_check(
        "no_operational_facilities_verified",
        df["operational_facility_verified"].eq("NO").all(),
        (
            "verified_yes="
            f"{df['operational_facility_verified'].eq('YES').sum()}"
        ),
    )

    add_check(
        "no_candidates_routing_eligible",
        df["routing_eligible"].eq("NO").all(),
        (
            "routing_eligible_yes="
            f"{df['routing_eligible'].eq('YES').sum()}"
        ),
    )

    evidence_columns = [
        "access_evidence_reference",
        "reviewer_name",
        "review_date",
        "review_notes",
    ]

    add_check(
        "review_evidence_fields_present",
        all(column in df.columns for column in evidence_columns),
        f"required_review_fields={len(evidence_columns)}",
    )

    add_check(
        "output_paths_are_phase2g2",
        (
            OUTPUT_CSV.name
            == "phase2g2_access_review_register.csv"
            and OUTPUT_AUDIT.name
            == "phase2g2_access_review_audit.txt"
        ),
        f"csv={OUTPUT_CSV.name}",
    )

    failures = [
        name
        for name, passed, _ in checks
        if not passed
    ]

    priority_counts = (
        df["phase2g2_review_priority"]
        .value_counts()
        .to_dict()
    )

    audit_lines = [
        "PNIS PHASE 2G.2 - ACCESS-REVIEW REGISTER BUILD",
        "=" * 72,
        (
            "Generated UTC: "
            f"{datetime.now(timezone.utc).isoformat()}"
        ),
        f"Project root: {ROOT}",
        "",
        "INPUT",
        "-" * 72,
        f"Phase 2G.1 register: {INPUT_CSV}",
        f"Candidate ID column: {id_col}",
        f"Distance column: {distance_col}",
        f"Proximity-band column: {band_col}",
        "",
        "METHOD AND SAFETY LIMITS",
        "-" * 72,
        (
            "Review priority orders manual review workload "
            "by mapped-road distance only."
        ),
        (
            "Road proximity does not confirm a physical entrance, "
            "vehicle access, road surface, seasonal passability, "
            "legal access, or operational facility function."
        ),
        (
            "All candidates remain pending field verification "
            "and routing-ineligible."
        ),
        (
            "No candidate is automatically approved, merged, "
            "deleted, or marked operational."
        ),
        "",
        "SUMMARY",
        "-" * 72,
        f"Candidates: {len(df)}",
        f"Unique candidate IDs: {df[id_col].nunique()}",
        (
            "Minimum mapped-road distance (m): "
            f"{df[distance_col].min():.3f}"
        ),
        (
            "Median mapped-road distance (m): "
            f"{df[distance_col].median():.3f}"
        ),
        (
            "Maximum mapped-road distance (m): "
            f"{df[distance_col].max():.3f}"
        ),
        "Review priority counts:",
        (
            "  P1_FAR_FROM_MAPPED_ROAD: "
            f"{priority_counts.get('P1_FAR_FROM_MAPPED_ROAD', 0)}"
        ),
        (
            "  P2_MODERATE_DISTANCE: "
            f"{priority_counts.get('P2_MODERATE_DISTANCE', 0)}"
        ),
        (
            "  P3_PROXIMITY_REVIEW: "
            f"{priority_counts.get('P3_PROXIMITY_REVIEW', 0)}"
        ),
        (
            "  P4_NEAR_ROAD_STILL_REQUIRES_ACCESS_CHECK: "
            f"{priority_counts.get('P4_NEAR_ROAD_STILL_REQUIRES_ACCESS_CHECK', 0)}"
        ),
        "",
        "VALIDATION CHECKS",
        "-" * 72,
    ]

    for name, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        audit_lines.append(
            f"{status} - {name}: {detail}"
        )

    audit_lines += [
        "",
        f"Checks passed: {sum(p for _, p, _ in checks)}",
        f"Checks failed: {len(failures)}",
        (
            "Overall status: "
            f"{'PASS' if not failures else 'FAIL'}"
        ),
        "",
        "OUTPUTS",
        "-" * 72,
        f"Register CSV: {OUTPUT_CSV}",
        f"Audit TXT: {OUTPUT_AUDIT}",
    ]

    OUTPUT_AUDIT.write_text(
        "\n".join(audit_lines) + "\n",
        encoding="utf-8",
    )

    print("\n".join(audit_lines))

    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"\nPHASE 2G.2 STOPPED: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        print(
            "No Phase 2C, Phase 2E, or Phase 2G.1 inputs were modified.",
            file=sys.stderr,
        )
        raise SystemExit(2)
