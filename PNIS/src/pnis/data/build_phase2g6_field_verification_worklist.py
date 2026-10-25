from __future__ import annotations

import csv
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"

SOURCE = PROCESSED / "phase2g5_candidate_access_risk_register_v2.csv"

WORKLIST = PROCESSED / "phase2g6_field_verification_worklist.csv"
EVIDENCE = PROCESSED / "phase2g6_evidence_register.csv"
AUDIT = PROCESSED / "phase2g6_field_verification_audit.txt"

EXPECTED_ROWS = 255

REQUIRED_COLUMNS = [
    "candidate_record_id",
    "phase2g2_distance_priority",
    "phase2g5_access_risk_screen_v2",
    "recalculated_nearest_road_distance_m",
    "nearest_road_fclass",
    "physical_vehicle_access_confirmed",
    "operational_facility_verified",
    "routing_eligible",
]

RISK_ORDER = {
    "HIGH_REVIEW": 1,
    "ELEVATED_REVIEW": 2,
    "STANDARD_REVIEW": 3,
}

DISTANCE_PRIORITY_ORDER = {
    "P1": 1,
    "P2": 2,
    "P3": 3,
    "P4": 4,
}

# These are new Phase 2G.6 fields. They record pending work,
# not findings about actual facility or road conditions.
FIELD_FIELDS = {
    "phase2g6_review_sequence": "",
    "phase2g6_review_status": "PENDING_FIELD_VERIFICATION",
    "phase2g6_facility_identity_result": "NOT_REVIEWED",
    "phase2g6_facility_operational_status": "NOT_REVIEWED",
    "phase2g6_coordinate_check_result": "NOT_REVIEWED",
    "phase2g6_physical_entrance_result": "NOT_REVIEWED",
    "phase2g6_vehicle_types_checked": "",
    "phase2g6_road_surface_result": "NOT_REVIEWED",
    "phase2g6_seasonal_passability_result": "NOT_REVIEWED",
    "phase2g6_vehicle_restrictions_found": "NOT_REVIEWED",
    "phase2g6_access_evidence_description": "",
    "phase2g6_evidence_reference": "",
    "phase2g6_evidence_date": "",
    "phase2g6_reviewer": "",
    "phase2g6_review_date": "",
    "phase2g6_review_decision": "PENDING",
    "phase2g6_follow_up_required": "YES",
    "phase2g6_follow_up_action": "",
    "phase2g6_notes": "",
}


def stop(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        stop(f"Required input file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            stop(f"Input CSV has no header: {path}")
        columns = list(reader.fieldnames)
        rows = list(reader)

    return rows, columns


def write_csv(
    path: Path,
    columns: list[str],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="raise",
        )
        writer.writeheader()
        writer.writerows(rows)


def nonempty(row: dict[str, str], field: str) -> str:
    return (row.get(field) or "").strip()


def main() -> None:
    outputs = [WORKLIST, EVIDENCE, AUDIT]

    # Never overwrite an existing output from an earlier run.
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        stop(
            "Output file(s) already exist. No files were changed:\n  "
            + "\n  ".join(existing)
            + "\nReview or archive them before running again."
        )

    rows, source_columns = read_csv(SOURCE)

    missing = [c for c in REQUIRED_COLUMNS if c not in source_columns]
    if missing:
        stop(f"Required source columns are missing: {missing}")

    if len(rows) != EXPECTED_ROWS:
        stop(
            f"Expected {EXPECTED_ROWS} source rows, found {len(rows)}. "
            "No outputs were created."
        )

    ids = [nonempty(row, "candidate_record_id") for row in rows]
    if any(not candidate_id for candidate_id in ids):
        stop("One or more candidate_record_id values are blank.")

    if len(set(ids)) != len(ids):
        stop("Duplicate candidate_record_id values detected.")

    unknown_risk = sorted({
        nonempty(row, "phase2g5_access_risk_screen_v2")
        for row in rows
        if nonempty(row, "phase2g5_access_risk_screen_v2") not in RISK_ORDER
    })
    if unknown_risk:
        stop(f"Unrecognized risk screen labels: {unknown_risk}")

    unknown_priority = sorted({
        nonempty(row, "phase2g2_distance_priority")
        for row in rows
        if nonempty(row, "phase2g2_distance_priority")
        not in DISTANCE_PRIORITY_ORDER
    })
    if unknown_priority:
        stop(f"Unrecognized original distance priority labels: {unknown_priority}")

    for row in rows:
        try:
            distance = float(
                nonempty(row, "recalculated_nearest_road_distance_m")
            )
        except (TypeError, ValueError):
            stop(
                "Invalid nearest-road distance for candidate "
                f"{nonempty(row, 'candidate_record_id')}"
            )

        if distance < 0:
            stop(
                "Negative nearest-road distance for candidate "
                f"{nonempty(row, 'candidate_record_id')}"
            )

        for field in (
            "physical_vehicle_access_confirmed",
            "operational_facility_verified",
            "routing_eligible",
        ):
            if nonempty(row, field).upper() != "NO":
                stop(
                    f"Safety check failed: {field} is not NO for "
                    f"{nonempty(row, 'candidate_record_id')}. "
                    "No outputs were created."
                )

    # Sort using explicit, documented ranking categories.
    # Within each group, P1 precedes P2/P3/P4, then greater
    # mapped-road distance comes first.
    ordered = sorted(
        rows,
        key=lambda row: (
            RISK_ORDER[nonempty(row, "phase2g5_access_risk_screen_v2")],
            DISTANCE_PRIORITY_ORDER[
                nonempty(row, "phase2g2_distance_priority")
            ],
            -float(nonempty(row, "recalculated_nearest_road_distance_m")),
            nonempty(row, "candidate_record_id"),
        ),
    )

    # Avoid overwriting any source columns with the Phase 2G.6 fields.
    collisions = sorted(set(source_columns).intersection(FIELD_FIELDS))
    if collisions:
        stop(
            "Phase 2G.6 field names already exist in source: "
            f"{collisions}. No outputs were created."
        )

    worklist_columns = source_columns + list(FIELD_FIELDS.keys())
    worklist_rows: list[dict[str, str]] = []

    for sequence, source_row in enumerate(ordered, start=1):
        row = dict(source_row)
        for field, default in FIELD_FIELDS.items():
            row[field] = default

        row["phase2g6_review_sequence"] = str(sequence)
        worklist_rows.append(row)

    # Evidence register: one row per candidate, with identity and
    # risk context retained alongside empty evidence-entry fields.
    context_fields = [
        "candidate_record_id",
        "osm_id",
        "name",
        "fclass",
        "source_layer",
        "longitude",
        "latitude",
        "phase2g2_distance_priority",
        "phase2g5_access_risk_screen_v2",
        "recalculated_nearest_road_distance_m",
        "nearest_road_fclass",
        "physical_vehicle_access_confirmed",
        "operational_facility_verified",
        "routing_eligible",
    ]
    evidence_columns = context_fields + list(FIELD_FIELDS.keys())
    evidence_rows: list[dict[str, str]] = []

    for row in worklist_rows:
        evidence_rows.append({
            field: row.get(field, "")
            for field in evidence_columns
        })

    # Audit summary.
    risk_counts = Counter(
        nonempty(row, "phase2g5_access_risk_screen_v2")
        for row in worklist_rows
    )
    priority_counts = Counter(
        nonempty(row, "phase2g2_distance_priority")
        for row in worklist_rows
    )
    road_class_counts = Counter(
        nonempty(row, "nearest_road_fclass") or "(blank)"
        for row in worklist_rows
    )

    audit_lines = [
        "PHASE 2G.6 — FIELD-VERIFICATION WORKLIST AND EVIDENCE REGISTER",
        "=" * 72,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        "Status: completed",
        "",
        "INPUT",
        "-" * 72,
        str(SOURCE.relative_to(ROOT)),
        "",
        "METHOD",
        "-" * 72,
        "All candidates are retained; no candidate is approved automatically.",
        "Review order: HIGH_REVIEW, ELEVATED_REVIEW, STANDARD_REVIEW.",
        "Within each risk screen: original P1/P2/P3/P4 distance priority,",
        "then descending mapped-road distance.",
        "The sequence is a review-workload order, not a safety assessment.",
        "All Phase 2G.6 evidence fields begin pending or not reviewed.",
        "",
        "RESULTS",
        "-" * 72,
        f"Source rows: {len(rows)}",
        f"Worklist rows: {len(worklist_rows)}",
        f"Evidence register rows: {len(evidence_rows)}",
        f"Unique candidate IDs: {len(set(ids))}",
        "",
        "RISK SCREEN COUNTS",
        "-" * 72,
    ]

    for key in ("HIGH_REVIEW", "ELEVATED_REVIEW", "STANDARD_REVIEW"):
        audit_lines.append(f"{key}: {risk_counts.get(key, 0)}")

    audit_lines.extend([
        "",
        "ORIGINAL DISTANCE PRIORITY COUNTS",
        "-" * 72,
    ])
    for key in ("P1", "P2", "P3", "P4"):
        audit_lines.append(f"{key}: {priority_counts.get(key, 0)}")

    audit_lines.extend([
        "",
        "NEAREST ROAD CLASS COUNTS",
        "-" * 72,
    ])
    for key, count in sorted(road_class_counts.items()):
        audit_lines.append(f"{key}: {count}")

    audit_lines.extend([
        "",
        "SAFETY",
        "-" * 72,
        "Physical vehicle access confirmed: 0",
        "Operational facility verified: 0",
        "Routing eligible: 0",
        "Field verification: pending for all candidates",
        "",
        "OUTPUTS",
        "-" * 72,
        str(WORKLIST.relative_to(ROOT)),
        str(EVIDENCE.relative_to(ROOT)),
        str(AUDIT.relative_to(ROOT)),
        "",
        "VALIDATION",
        "-" * 72,
        "PASS: source row count is 255",
        "PASS: candidate IDs are nonblank and unique",
        "PASS: all risk screen labels are recognized",
        "PASS: all original distance priority labels are recognized",
        "PASS: all nearest-road distances are valid and nonnegative",
        "PASS: physical vehicle access remains unconfirmed",
        "PASS: operational facilities remain unverified",
        "PASS: all candidates remain routing-ineligible",
        "PASS: no existing output was overwritten",
        "",
        "LIMITATIONS",
        "-" * 72,
        "This worklist is not field evidence.",
        "Mapped-road proximity and road class do not establish an entrance,",
        "vehicle suitability, surface condition, seasonal passability,",
        "legal access, or facility operation.",
        "Do not change routing eligibility without documented verification",
        "and a separate reviewed decision.",
    ])

    # All validations happen before writing. Output paths were checked above.
    write_csv(WORKLIST, worklist_columns, worklist_rows)
    write_csv(EVIDENCE, evidence_columns, evidence_rows)
    AUDIT.write_text("\n".join(audit_lines) + "\n", encoding="utf-8")

    print("\n".join(audit_lines))
    print("\nPhase 2G.6 completed successfully.")


if __name__ == "__main__":
    main()
