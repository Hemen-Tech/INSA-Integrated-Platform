
from __future__ import annotations

import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"

INPUT_CSV = PROCESSED / "phase2g15_fieldwork_validation.csv"
INPUT_SUMMARY = PROCESSED / "phase2g15_fieldwork_validation_summary.csv"

OUTPUT_CSV = PROCESSED / "phase2g16_fieldwork_readiness.csv"
OUTPUT_SUMMARY = PROCESSED / "phase2g16_fieldwork_readiness_summary.csv"
OUTPUT_AUDIT = PROCESSED / "phase2g16_fieldwork_readiness_audit.txt"

EXPECTED_CANDIDATES = 255


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def truth(value: str) -> bool:
    return value.strip().upper() in {"YES", "TRUE", "1", "Y"}


def main() -> int:
    validation_rows = read_csv(INPUT_CSV)
    summary_rows = read_csv(INPUT_SUMMARY)
    summary = {r.get("metric", ""): r.get("value", "") for r in summary_rows}

    if not validation_rows:
        raise ValueError("Phase 2G.15 validation CSV contains no candidate rows.")

    required_columns = {
        "excel_row",
        "candidate_record_id",
        "fieldwork_status",
        "field_visit_date",
        "observer_name_or_id",
        "actual_gps_longitude",
        "actual_gps_latitude",
        "actual_gps_valid",
        "facility_identity_result",
        "operating_status",
        "vehicle_access_result",
        "observed_road_condition_present",
        "vehicle_type_assessed_present",
        "evidence_reference_present",
        "field_notes_present",
        "review_decision",
        "review_is_non_pending",
        "reviewer_present",
        "review_date",
        "physical_vehicle_access_confirmed",
        "operational_facility_verified",
        "source_routing_eligible",
        "validation_issue_count",
        "validation_issues",
        "validation_disposition",
        "routing_approval_granted_by_script",
    }

    missing_columns = sorted(required_columns - set(validation_rows[0].keys()))
    if missing_columns:
        raise ValueError(
            "Phase 2G.15 CSV is missing expected columns: "
            + ", ".join(missing_columns)
        )

    output_rows = []
    issue_counts: Counter[str] = Counter()

    visited_statuses = {
        "VISITED",
        "FIELDWORK_COMPLETED",
        "COMPLETED",
        "VISIT_COMPLETED",
    }
    pending_decisions = {"", "PENDING_REVIEW", "NOT_REVIEWED", "PENDING"}

    for row in validation_rows:
        get = lambda key: (row.get(key) or "").strip()
        candidate_id = get("candidate_record_id")
        status = get("fieldwork_status").upper()
        decision = get("review_decision").upper()
        visited = status in visited_statuses

        observation_checks = {
            "visit_date": bool(get("field_visit_date")),
            "observer": bool(get("observer_name_or_id")),
            "actual_gps_valid": truth(get("actual_gps_valid")),
            "facility_identity_result": bool(get("facility_identity_result")),
            "operating_status": bool(get("operating_status")),
            "vehicle_access_result": bool(get("vehicle_access_result")),
            "observed_road_condition": truth(get("observed_road_condition_present")),
            "vehicle_type_assessed": truth(get("vehicle_type_assessed_present")),
            "evidence_reference": truth(get("evidence_reference_present")),
            "field_notes": truth(get("field_notes_present")),
        }

        missing_observation_fields = [
            name for name, present in observation_checks.items() if not present
        ]

        issues = []
        if not candidate_id:
            issues.append("MISSING_CANDIDATE_ID")
            issue_counts["MISSING_CANDIDATE_ID"] += 1

        if visited and missing_observation_fields:
            issues.append("INCOMPLETE_FIELD_OBSERVATION")
            issue_counts["INCOMPLETE_FIELD_OBSERVATION"] += 1

        reviewed = (
            truth(get("review_is_non_pending"))
            or decision not in pending_decisions
        )

        missing_review_fields = []
        if reviewed:
            if not truth(get("reviewer_present")):
                missing_review_fields.append("reviewer")
            if not get("review_date"):
                missing_review_fields.append("review_date")

            if missing_review_fields:
                issues.append("INCOMPLETE_REVIEW_RECORD")
                issue_counts["INCOMPLETE_REVIEW_RECORD"] += 1

        if not visited:
            readiness = "AWAITING_FIELDWORK"
        elif missing_observation_fields:
            readiness = "FIELDWORK_EVIDENCE_INCOMPLETE"
        elif not reviewed:
            readiness = "AWAITING_MANUAL_REVIEW"
        elif missing_review_fields:
            readiness = "REVIEW_EVIDENCE_INCOMPLETE"
        else:
            readiness = "MANUAL_REVIEW_RECORDED"

        source_routing = get("source_routing_eligible").upper() or "BLANK"
        physical_access = get("physical_vehicle_access_confirmed").upper()
        operational_verified = get("operational_facility_verified").upper()

        guardrail_ok = not (
            physical_access == "YES" and operational_verified != "YES"
        )

        if source_routing == "YES":
            issues.append("SOURCE_ALREADY_MARKS_ROUTING_ELIGIBLE")
            issue_counts["SOURCE_ALREADY_MARKS_ROUTING_ELIGIBLE"] += 1

        if not guardrail_ok:
            issues.append("ACCESS_GUARDRAIL_REQUIRES_REVIEW")
            issue_counts["ACCESS_GUARDRAIL_REQUIRES_REVIEW"] += 1

        # Phase 2G.16 reports readiness only; it never approves routing.
        output_rows.append({
            "excel_row": get("excel_row"),
            "candidate_record_id": candidate_id,
            "fieldwork_status": status,
            "fieldwork_readiness": readiness,
            "missing_observation_fields": ";".join(missing_observation_fields),
            "review_decision": decision or "BLANK",
            "review_fields_missing": ";".join(missing_review_fields),
            "physical_vehicle_access_confirmed": physical_access,
            "operational_facility_verified": operational_verified,
            "source_routing_eligible": source_routing,
            "routing_approval_granted_by_phase2g16": "NO",
            "guardrail_check": "PASS" if guardrail_ok else "REVIEW_REQUIRED",
            "source_validation_issue_count": get("validation_issue_count"),
            "source_validation_issues": get("validation_issues"),
            "phase2g16_issue_count": str(len(issues)),
            "phase2g16_issues": ";".join(issues),
        })

    id_counts = Counter(
        row["candidate_record_id"] for row in output_rows
        if row["candidate_record_id"]
    )
    unique_ids = len(id_counts)
    duplicate_ids = sum(1 for count in id_counts.values() if count > 1)

    readiness_counts = Counter(row["fieldwork_readiness"] for row in output_rows)
    visited_count = sum(1 for row in output_rows if row["fieldwork_status"] in visited_statuses)
    total_issues = sum(int(row["phase2g16_issue_count"]) for row in output_rows)
    routing_yes = sum(1 for row in output_rows if row["source_routing_eligible"] == "YES")

    summary_output = [
        {"metric": "candidate_rows_read", "value": str(len(output_rows))},
        {"metric": "expected_candidate_rows", "value": str(EXPECTED_CANDIDATES)},
        {"metric": "candidate_row_count_matches_expected", "value": str(len(output_rows) == EXPECTED_CANDIDATES)},
        {"metric": "unique_candidate_ids", "value": str(unique_ids)},
        {"metric": "duplicate_candidate_id_values", "value": str(duplicate_ids)},
        {"metric": "visited_rows", "value": str(visited_count)},
        {"metric": "awaiting_fieldwork_rows", "value": str(readiness_counts["AWAITING_FIELDWORK"])},
        {"metric": "fieldwork_evidence_incomplete_rows", "value": str(readiness_counts["FIELDWORK_EVIDENCE_INCOMPLETE"])},
        {"metric": "awaiting_manual_review_rows", "value": str(readiness_counts["AWAITING_MANUAL_REVIEW"])},
        {"metric": "review_evidence_incomplete_rows", "value": str(readiness_counts["REVIEW_EVIDENCE_INCOMPLETE"])},
        {"metric": "manual_review_recorded_rows", "value": str(readiness_counts["MANUAL_REVIEW_RECORDED"])},
        {"metric": "total_phase2g16_issues", "value": str(total_issues)},
        {"metric": "source_routing_eligible_yes_rows", "value": str(routing_yes)},
        {"metric": "routing_approval_granted_by_phase2g16", "value": "NO"},
        {"metric": "phase2g15_candidate_count_matches_expected", "value": summary.get("candidate_row_count_matches_expected", "UNKNOWN")},
    ]

    for label, count in sorted(readiness_counts.items()):
        summary_output.append({"metric": f"readiness_{label}", "value": str(count)})

    for label, count in sorted(issue_counts.items()):
        summary_output.append({"metric": f"issue_{label}", "value": str(count)})

    audit = [
        "PNIS PHASE 2G.16 - FIELDWORK COMPLETION AND READINESS GATE",
        "=" * 72,
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "Status: COMPLETED - READ-ONLY READINESS AUDIT",
        "",
        "INPUTS",
        str(INPUT_CSV),
        str(INPUT_SUMMARY),
        "",
        "RESULTS",
        f"Candidate rows read: {len(output_rows)}",
        f"Expected candidate rows: {EXPECTED_CANDIDATES}",
        f"Unique candidate IDs: {unique_ids}",
        f"Duplicate candidate ID values: {duplicate_ids}",
        f"Visited rows: {visited_count}",
        f"Awaiting fieldwork rows: {readiness_counts['AWAITING_FIELDWORK']}",
        f"Fieldwork evidence incomplete rows: {readiness_counts['FIELDWORK_EVIDENCE_INCOMPLETE']}",
        f"Awaiting manual review rows: {readiness_counts['AWAITING_MANUAL_REVIEW']}",
        f"Review evidence incomplete rows: {readiness_counts['REVIEW_EVIDENCE_INCOMPLETE']}",
        f"Manual review recorded rows: {readiness_counts['MANUAL_REVIEW_RECORDED']}",
        f"Phase 2G.16 issues: {total_issues}",
        f"Source routing-eligible YES rows: {routing_yes}",
        "Routing approval granted by this script: NO",
        "",
        "READINESS COUNTS",
    ]

    for label, count in sorted(readiness_counts.items()):
        audit.append(f"{label}: {count}")

    audit += ["", "ISSUE COUNTS"]
    audit.extend(
        [f"{label}: {count}" for label, count in sorted(issue_counts.items())]
        if issue_counts else ["None"]
    )

    audit += [
        "",
        "GUARDRAILS",
        "- Read-only audit: does not edit the workbook, Phase 2G.15 outputs, or routing graph.",
        "- This script never grants routing approval.",
        "- Blank observations for unvisited candidates are not failed inspections.",
        "- Road proximity alone does not prove physical vehicle access.",
        "- Manual review recorded does not itself establish routing eligibility.",
        "",
        "OUTPUTS",
        str(OUTPUT_CSV),
        str(OUTPUT_SUMMARY),
        str(OUTPUT_AUDIT),
    ]

    write_csv(OUTPUT_CSV, output_rows)
    write_csv(OUTPUT_SUMMARY, summary_output)
    OUTPUT_AUDIT.write_text("\n".join(audit) + "\n", encoding="utf-8")

    print("=" * 72)
    print("PNIS PHASE 2G.16 - FIELDWORK COMPLETION AND READINESS GATE")
    print("=" * 72)
    print(f"Candidate rows read: {len(output_rows)}")
    print(f"Unique candidate IDs: {unique_ids}")
    print(f"Duplicate candidate IDs: {duplicate_ids}")
    print(f"Visited rows: {visited_count}")
    print(f"Awaiting fieldwork: {readiness_counts['AWAITING_FIELDWORK']}")
    print(f"Rows with Phase 2G.16 issues: {sum(1 for row in output_rows if int(row['phase2g16_issue_count']) > 0)}")
    print(f"Total Phase 2G.16 issues: {total_issues}")
    print("Routing approval granted: NO")
    print("\nOUTPUT FILES")
    print(OUTPUT_CSV)
    print(OUTPUT_SUMMARY)
    print(OUTPUT_AUDIT)
    print("\nSTATUS: COMPLETED - READ-ONLY READINESS AUDIT")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
