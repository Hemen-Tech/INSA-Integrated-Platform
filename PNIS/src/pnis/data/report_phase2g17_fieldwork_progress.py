
import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"

VALIDATION_FILE = PROCESSED / "phase2g15_fieldwork_validation.csv"
READINESS_FILE = PROCESSED / "phase2g16_fieldwork_readiness.csv"

DETAIL_OUT = PROCESSED / "phase2g17_fieldwork_progress.csv"
SUMMARY_OUT = PROCESSED / "phase2g17_fieldwork_progress_summary.csv"
AUDIT_OUT = PROCESSED / "phase2g17_fieldwork_progress_audit.txt"

EXPECTED_CANDIDATES = 255

ID_NAMES = (
    "candidate_record_id",
    "candidate_id",
    "facility_candidate_id",
)

READINESS_NAMES = (
    "phase2g16_readiness_state",
    "readiness_state",
    "readiness_status",
    "fieldwork_readiness",
)

RISK_NAMES = (
    "risk_class",
    "risk_category",
    "access_risk_class",
    "screening_risk_class",
)

VISITED_VALUES = {
    "VISITED",
    "FIELDWORK_COMPLETED",
    "COMPLETED",
    "VISIT_COMPLETED",
    "DONE",
    "YES",
}

PENDING_VALUES = {
    "",
    "PENDING",
    "NOT_STARTED",
    "NOT VISITED",
    "AWAITING_FIELDWORK",
    "AWAITING FIELDWORK",
    "NO",
    "N/A",
    "NA",
}


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header row: {path}")
        rows = list(reader)
        return reader.fieldnames, rows


def find_column(columns, candidates):
    lookup = {column.strip().lower(): column for column in columns}
    for candidate in candidates:
        found = lookup.get(candidate.lower())
        if found:
            return found
    return None


def normalized(value):
    return str(value or "").strip().upper()


def is_true(value):
    return normalized(value) in {"TRUE", "YES", "Y", "1"}


def is_visited(row, status_column):
    if not status_column:
        return False
    return normalized(row.get(status_column)) in VISITED_VALUES


def add_metric(metrics, name, value):
    metrics.append({"metric": name, "value": str(value)})


def main():
    print("=" * 72)
    print("PNIS PHASE 2G.17 - FIELDWORK EXECUTION MONITORING")
    print("=" * 72)

    validation_columns, validation_rows = read_csv(VALIDATION_FILE)
    readiness_columns, readiness_rows = read_csv(READINESS_FILE)

    validation_id = find_column(validation_columns, ID_NAMES)
    readiness_id = find_column(readiness_columns, ID_NAMES)

    if not validation_id:
        raise ValueError(
            "Phase 2G.15 CSV is missing a candidate ID column. "
            f"Available columns: {validation_columns}"
        )

    if not readiness_id:
        raise ValueError(
            "Phase 2G.16 CSV is missing a candidate ID column. "
            f"Available columns: {readiness_columns}"
        )

    validation_status = find_column(
        validation_columns, ("fieldwork_status",)
    )
    validation_visited = find_column(
        validation_columns, ("field_visit_date",)
    )
    review_column = find_column(
        validation_columns, ("review_is_non_pending",)
    )
    reviewer_column = find_column(
        validation_columns, ("reviewer_present",)
    )
    review_date_column = find_column(
        validation_columns, ("review_date",)
    )
    evidence_columns = {
        "observed_road_condition_present": find_column(
            validation_columns, ("observed_road_condition_present",)
        ),
        "vehicle_type_assessed_present": find_column(
            validation_columns, ("vehicle_type_assessed_present",)
        ),
        "evidence_reference_present": find_column(
            validation_columns, ("evidence_reference_present",)
        ),
        "field_notes_present": find_column(
            validation_columns, ("field_notes_present",)
        ),
    }

    validation_by_id = {}
    duplicate_validation_ids = []

    for row in validation_rows:
        candidate_id = str(row.get(validation_id, "")).strip()
        if not candidate_id:
            continue
        if candidate_id in validation_by_id:
            duplicate_validation_ids.append(candidate_id)
        else:
            validation_by_id[candidate_id] = row

    readiness_by_id = {}
    duplicate_readiness_ids = []

    for row in readiness_rows:
        candidate_id = str(row.get(readiness_id, "")).strip()
        if not candidate_id:
            continue
        if candidate_id in readiness_by_id:
            duplicate_readiness_ids.append(candidate_id)
        else:
            readiness_by_id[candidate_id] = row

    if duplicate_validation_ids or duplicate_readiness_ids:
        raise ValueError(
            "Duplicate candidate IDs found in an input. "
            "No Phase 2G.17 outputs were written. "
            f"Phase 2G.15 duplicates: {len(duplicate_validation_ids)}; "
            f"Phase 2G.16 duplicates: {len(duplicate_readiness_ids)}."
        )

    validation_ids = set(validation_by_id)
    readiness_ids = set(readiness_by_id)

    missing_from_readiness = sorted(validation_ids - readiness_ids)
    missing_from_validation = sorted(readiness_ids - validation_ids)

    # Use the Phase 2G.16 rows as the main report population.
    detail_rows = []
    readiness_counts = Counter()
    risk_counts = Counter()
    visited_count = 0
    pending_count = 0
    manual_review_count = 0
    reviewer_missing_count = 0
    review_date_missing_count = 0
    incomplete_evidence_count = 0
    physical_access_yes_count = 0
    operational_verified_count = 0
    source_routing_yes_count = 0

    readiness_column = find_column(readiness_columns, READINESS_NAMES)
    risk_column = find_column(readiness_columns, RISK_NAMES)
    if not risk_column:
        risk_column = find_column(validation_columns, RISK_NAMES)

    for candidate_id in sorted(readiness_ids):
        readiness_row = readiness_by_id[candidate_id]
        validation_row = validation_by_id.get(candidate_id, {})

        readiness_value = (
            str(readiness_row.get(readiness_column, "")).strip()
            if readiness_column
            else "NOT_AVAILABLE_IN_SOURCE"
        )
        readiness_counts[readiness_value or "BLANK"] += 1

        status = (
            validation_row.get(validation_status, "")
            if validation_status
            else ""
        )
        visited = is_visited(validation_row, validation_status)

        # A dated visit also counts as visited if the status field is
        # absent or has not been updated consistently.
        visit_date = (
            str(validation_row.get(validation_visited, "")).strip()
            if validation_visited
            else ""
        )
        if visit_date and normalized(visit_date) not in PENDING_VALUES:
            visited = True

        if visited:
            visited_count += 1
        else:
            pending_count += 1

        review_recorded = (
            is_true(validation_row.get(review_column))
            if review_column
            else False
        )
        if review_recorded:
            manual_review_count += 1

        if review_recorded and reviewer_column:
            if not str(validation_row.get(reviewer_column, "")).strip():
                reviewer_missing_count += 1

        if review_recorded and review_date_column:
            if not str(validation_row.get(review_date_column, "")).strip():
                review_date_missing_count += 1

        evidence_complete = all(
            column is not None
            and is_true(validation_row.get(column))
            for column in evidence_columns.values()
        )

        if visited and not evidence_complete:
            incomplete_evidence_count += 1

        risk_value = ""
        if risk_column in readiness_columns if risk_column else False:
            risk_value = str(readiness_row.get(risk_column, "")).strip()
        elif risk_column and risk_column in validation_columns:
            risk_value = str(validation_row.get(risk_column, "")).strip()

        if risk_value:
            risk_counts[risk_value] += 1

        physical_access = normalized(
            validation_row.get("physical_vehicle_access_confirmed", "")
        )
        operational_verified = normalized(
            validation_row.get("operational_facility_verified", "")
        )
        source_routing = normalized(
            validation_row.get("source_routing_eligible", "")
        )

        # These columns may not be present in every Phase 2G.15 export.
        if physical_access == "YES":
            physical_access_yes_count += 1
        if operational_verified == "YES":
            operational_verified_count += 1
        if source_routing == "YES":
            source_routing_yes_count += 1

        combined = dict(readiness_row)
        combined["phase2g17_visit_status"] = (
            "VISITED" if visited else "AWAITING_FIELDWORK"
        )
        combined["phase2g17_manual_review_recorded"] = (
            "YES" if review_recorded else "NO"
        )
        combined["phase2g17_required_evidence_complete"] = (
            "YES" if evidence_complete else "NO"
        )
        combined["phase2g17_routing_approval_granted"] = "NO"
        combined["phase2g17_routing_note"] = (
            "No routing approval is granted by this report."
        )
        detail_rows.append(combined)

    metrics = []
    add_metric(metrics, "phase2g15_rows_read", len(validation_rows))
    add_metric(metrics, "phase2g16_rows_read", len(readiness_rows))
    add_metric(metrics, "expected_candidate_rows", EXPECTED_CANDIDATES)
    add_metric(metrics, "phase2g15_unique_candidate_ids", len(validation_ids))
    add_metric(metrics, "phase2g16_unique_candidate_ids", len(readiness_ids))
    add_metric(
        metrics,
        "phase2g15_count_matches_expected",
        len(validation_rows) == EXPECTED_CANDIDATES,
    )
    add_metric(
        metrics,
        "phase2g16_count_matches_expected",
        len(readiness_rows) == EXPECTED_CANDIDATES,
    )
    add_metric(metrics, "duplicate_phase2g15_ids", len(duplicate_validation_ids))
    add_metric(metrics, "duplicate_phase2g16_ids", len(duplicate_readiness_ids))
    add_metric(metrics, "validation_ids_missing_from_readiness", len(missing_from_readiness))
    add_metric(metrics, "readiness_ids_missing_from_validation", len(missing_from_validation))
    add_metric(metrics, "visited_candidates", visited_count)
    add_metric(metrics, "awaiting_fieldwork_candidates", pending_count)
    add_metric(metrics, "manual_reviews_recorded", manual_review_count)
    add_metric(metrics, "visited_candidates_with_incomplete_evidence", incomplete_evidence_count)
    add_metric(metrics, "reviewer_missing_on_recorded_reviews", reviewer_missing_count)
    add_metric(metrics, "review_date_missing_on_recorded_reviews", review_date_missing_count)
    add_metric(metrics, "physical_vehicle_access_confirmed_yes", physical_access_yes_count)
    add_metric(metrics, "operational_facility_verified_yes", operational_verified_count)
    add_metric(metrics, "source_routing_eligible_yes", source_routing_yes_count)
    add_metric(metrics, "routing_approval_granted_by_phase2g17", "NO")
    add_metric(metrics, "risk_column_available", risk_column is not None)
    add_metric(metrics, "readiness_column_available", readiness_column is not None)

    for state, count in sorted(readiness_counts.items()):
        add_metric(metrics, f"readiness_{state}", count)

    for risk, count in sorted(risk_counts.items()):
        safe_key = "_".join(risk.strip().split())
        add_metric(metrics, f"risk_group_{safe_key}", count)

    # Write outputs only after both inputs and their ID columns are validated.
    detail_fields = list(readiness_columns)
    for field in (
        "phase2g17_visit_status",
        "phase2g17_manual_review_recorded",
        "phase2g17_required_evidence_complete",
        "phase2g17_routing_approval_granted",
        "phase2g17_routing_note",
    ):
        if field not in detail_fields:
            detail_fields.append(field)

    with DETAIL_OUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=detail_fields, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(detail_rows)

    with SUMMARY_OUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerows(metrics)

    issue_lines = []
    if len(validation_rows) != EXPECTED_CANDIDATES:
        issue_lines.append("Phase 2G.15 row count differs from expected.")
    if len(readiness_rows) != EXPECTED_CANDIDATES:
        issue_lines.append("Phase 2G.16 row count differs from expected.")
    if missing_from_readiness:
        issue_lines.append("Some Phase 2G.15 candidate IDs are missing from Phase 2G.16.")
    if missing_from_validation:
        issue_lines.append("Some Phase 2G.16 candidate IDs are missing from Phase 2G.15.")
    if incomplete_evidence_count:
        issue_lines.append(
            "Visited candidates with incomplete required evidence need follow-up."
        )
    if reviewer_missing_count:
        issue_lines.append("Recorded reviews are missing reviewer information.")
    if review_date_missing_count:
        issue_lines.append("Recorded reviews are missing review dates.")

    with AUDIT_OUT.open("w", encoding="utf-8") as handle:
        handle.write(
            "PNIS PHASE 2G.17 - FIELDWORK EXECUTION MONITORING\n"
            + "=" * 72
            + "\n"
        )
        handle.write(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
        handle.write("Status: COMPLETED - READ-ONLY PROGRESS REPORT\n\n")
        handle.write("INPUTS\n")
        handle.write(f"{VALIDATION_FILE}\n{READINESS_FILE}\n\n")
        handle.write("RESULTS\n")
        handle.write(f"Phase 2G.15 rows: {len(validation_rows)}\n")
        handle.write(f"Phase 2G.16 rows: {len(readiness_rows)}\n")
        handle.write(f"Visited candidates: {visited_count}\n")
        handle.write(f"Awaiting fieldwork: {pending_count}\n")
        handle.write(f"Manual reviews recorded: {manual_review_count}\n")
        handle.write(
            "Visited candidates with incomplete required evidence: "
            f"{incomplete_evidence_count}\n"
        )
        handle.write(f"Source routing-eligible YES: {source_routing_yes_count}\n")
        handle.write("Routing approval granted by Phase 2G.17: NO\n\n")

        handle.write("READINESS COUNTS\n")
        if readiness_counts:
            for state, count in sorted(readiness_counts.items()):
                handle.write(f"{state}: {count}\n")
        else:
            handle.write("No readiness states available.\n")

        handle.write("\nRISK GROUP COUNTS\n")
        if risk_counts:
            for risk, count in sorted(risk_counts.items()):
                handle.write(f"{risk}: {count}\n")
        else:
            handle.write(
                "Risk category not available in these input CSV columns; "
                "no risk counts inferred.\n"
            )

        handle.write("\nDATA ALIGNMENT\n")
        handle.write(
            f"Phase 2G.15 IDs missing from Phase 2G.16: "
            f"{len(missing_from_readiness)}\n"
        )
        handle.write(
            f"Phase 2G.16 IDs missing from Phase 2G.15: "
            f"{len(missing_from_validation)}\n"
        )
        handle.write(
            f"Readiness column available: {'YES' if readiness_column else 'NO'}\n"
        )
        handle.write(
            f"Risk column available: {'YES' if risk_column else 'NO'}\n"
        )

        handle.write("\nISSUES / FOLLOW-UP\n")
        if issue_lines:
            for line in issue_lines:
                handle.write(f"- {line}\n")
        else:
            handle.write("No Phase 2G.17 data-alignment or evidence follow-up flags.\n")

        handle.write("\nGUARDRAILS\n")
        handle.write(
            "- Read-only report: does not edit the fieldwork workbook or earlier outputs.\n"
        )
        handle.write("- Does not edit Phase 2C road-network outputs or the Phase 2E graph.\n")
        handle.write("- Does not grant routing approval or change candidate eligibility.\n")
        handle.write(
            "- A recorded visit or manual review alone does not establish vehicle access.\n"
        )
        handle.write(
            "- Risk counts are reported only when a risk column exists in the input data.\n"
        )
        handle.write("\nOUTPUT FILES\n")
        handle.write(f"{DETAIL_OUT}\n{SUMMARY_OUT}\n{AUDIT_OUT}\n")

    print(f"Phase 2G.15 rows: {len(validation_rows)}")
    print(f"Phase 2G.16 rows: {len(readiness_rows)}")
    print(f"Visited candidates: {visited_count}")
    print(f"Awaiting fieldwork: {pending_count}")
    print(f"Manual reviews recorded: {manual_review_count}")
    print(f"Visited candidates with incomplete evidence: {incomplete_evidence_count}")
    print(f"Candidate IDs missing across inputs: {len(missing_from_readiness) + len(missing_from_validation)}")
    print("Routing approval granted: NO")
    print("\nOUTPUT FILES")
    print(DETAIL_OUT)
    print(SUMMARY_OUT)
    print(AUDIT_OUT)
    print("\nSTATUS: COMPLETED - READ-ONLY PROGRESS REPORT")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        print("No routing approval was granted.", file=sys.stderr)
        sys.exit(1)
