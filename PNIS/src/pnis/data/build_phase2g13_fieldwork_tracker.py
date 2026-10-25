
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "processed"

PLAN_FILE = DATA / "phase2g10_fieldwork_priority_plan.csv"
FORM_FILE = DATA / "phase2g10_field_data_collection_form.csv"
READINESS_FILE = DATA / "phase2g12_facility_access_readiness_register.csv"

TRACKER_FILE = DATA / "phase2g13_fieldwork_execution_tracker.csv"
SUMMARY_FILE = DATA / "phase2g13_fieldwork_execution_summary.csv"
AUDIT_FILE = DATA / "phase2g13_fieldwork_execution_audit.txt"

ID_FIELD = "candidate_record_id"

TRACKER_FIELDS = [
    "fieldwork_priority_order",
    ID_FIELD,
    "risk_queue_order",
    "review_sequence",
    "nearest_mapped_road_distance_m",
    "nearest_road_fclass",
    "vehicle_suitability_screen",
    "planned_longitude",
    "planned_latitude",
    "fieldwork_status",
    "field_visit_date",
    "observer_name_or_id",
    "actual_gps_longitude",
    "actual_gps_latitude",
    "facility_identity_result",
    "operating_status",
    "vehicle_access_result",
    "observed_road_condition",
    "vehicle_type_assessed",
    "photo_or_document_reference",
    "field_observation_notes",
    "review_decision",
    "reviewer_name_or_id",
    "review_date",
    "review_evidence_notes",
    "physical_vehicle_access_confirmed",
    "operational_facility_verified",
    "routing_eligible",
]

ALLOWED_FIELDWORK_STATUS = {
    "NOT_VISITED",
    "VISIT_SCHEDULED",
    "VISIT_COMPLETED",
    "FOLLOW_UP_REQUIRED",
}

def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        rows = list(reader)
    if ID_FIELD not in reader.fieldnames:
        raise ValueError(f"Missing {ID_FIELD!r} in {path.name}")
    return rows

def id_map(rows: list[dict[str, str]], label: str) -> dict[str, dict[str, str]]:
    result = {}
    for row_number, row in enumerate(rows, start=2):
        candidate_id = (row.get(ID_FIELD) or "").strip()
        if not candidate_id:
            raise ValueError(f"{label}: blank candidate ID on CSV row {row_number}")
        if candidate_id in result:
            raise ValueError(f"{label}: duplicate candidate ID {candidate_id}")
        result[candidate_id] = row
    return result

def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def main() -> None:
    print("=" * 72)
    print("PNIS PHASE 2G.13 - FIELDWORK EXECUTION TRACKER")
    print("=" * 72)

    DATA.mkdir(parents=True, exist_ok=True)

    plan_rows = read_csv(PLAN_FILE)
    form_rows = read_csv(FORM_FILE)
    readiness_rows = read_csv(READINESS_FILE)

    plan = id_map(plan_rows, "Phase 2G.10 plan")
    form = id_map(form_rows, "Phase 2G.10 collection form")
    readiness = id_map(readiness_rows, "Phase 2G.12 readiness register")

    issues: list[str] = []
    plan_ids = set(plan)
    form_ids = set(form)
    readiness_ids = set(readiness)

    if plan_ids != form_ids:
        issues.append("Candidate IDs do not match between plan and collection form.")
    if plan_ids != readiness_ids:
        issues.append("Candidate IDs do not match between plan and readiness register.")

    # Keep the Phase 2G.10 priority order. Only create a new tracking file.
    tracker_rows: list[dict[str, str]] = []

    for index, plan_row in enumerate(plan_rows, start=1):
        candidate_id = (plan_row.get(ID_FIELD) or "").strip()
        form_row = form.get(candidate_id, {})
        readiness_row = readiness.get(candidate_id, {})

        tracker_rows.append({
            "fieldwork_priority_order": str(index),
            ID_FIELD: candidate_id,
            "risk_queue_order": plan_row.get("phase2g5_risk_queue_order_v2", ""),
            "review_sequence": plan_row.get("phase2g6_review_sequence", ""),
            "nearest_mapped_road_distance_m":
                plan_row.get("nearest_mapped_road_distance_m", ""),
            "nearest_road_fclass": plan_row.get("nearest_road_fclass", ""),
            "vehicle_suitability_screen":
                plan_row.get("phase2g3_vehicle_suitability_screen", ""),
            "planned_longitude": form_row.get("planned_longitude", ""),
            "planned_latitude": form_row.get("planned_latitude", ""),
            "fieldwork_status": "NOT_VISITED",
            "field_visit_date": "",
            "observer_name_or_id": "",
            "actual_gps_longitude": "",
            "actual_gps_latitude": "",
            "facility_identity_result": "",
            "operating_status": "",
            "vehicle_access_result": "",
            "observed_road_condition": "",
            "vehicle_type_assessed": "",
            "photo_or_document_reference": "",
            "field_observation_notes": "",
            "review_decision": "PENDING_REVIEW",
            "reviewer_name_or_id": "",
            "review_date": "",
            "review_evidence_notes": "",
            "physical_vehicle_access_confirmed": "NO",
            "operational_facility_verified": "NO",
            "routing_eligible": "NO",
        })

    # Guardrails: never initialize a candidate as visited or routing-eligible.
    checks: list[tuple[str, bool]] = [
        ("All three input files loaded", True),
        ("Candidate IDs are unique and nonblank in all inputs", True),
        ("Candidate ID sets match across all inputs", plan_ids == form_ids == readiness_ids),
        ("Tracker has one row per planned candidate", len(tracker_rows) == len(plan_rows)),
        ("Tracker candidate IDs are unique", len({r[ID_FIELD] for r in tracker_rows}) == len(tracker_rows)),
        ("All tracker statuses start as NOT_VISITED",
         all(r["fieldwork_status"] == "NOT_VISITED" for r in tracker_rows)),
        ("All candidates remain routing-ineligible",
         all(r["routing_eligible"] == "NO" for r in tracker_rows)),
        ("Access and operation are not pre-approved",
         all(
             r["physical_vehicle_access_confirmed"] == "NO"
             and r["operational_facility_verified"] == "NO"
             for r in tracker_rows
         )),
    ]

    write_csv(TRACKER_FILE, TRACKER_FIELDS, tracker_rows)

    status_counts = Counter(row["fieldwork_status"] for row in tracker_rows)
    risk_counts = Counter(
        (readiness.get(row[ID_FIELD], {}).get("phase2g5_access_risk_screen_v2", "")
         or "UNCLASSIFIED")
        for row in tracker_rows
    )

    summary_rows = [
        {
            "summary_type": "OVERALL",
            "summary_value": "ALL_CANDIDATES",
            "candidate_count": str(len(tracker_rows)),
        }
    ]
    for status, count in sorted(status_counts.items()):
        summary_rows.append({
            "summary_type": "FIELDWORK_STATUS",
            "summary_value": status,
            "candidate_count": str(count),
        })
    for risk, count in sorted(risk_counts.items()):
        summary_rows.append({
            "summary_type": "ACCESS_RISK",
            "summary_value": risk,
            "candidate_count": str(count),
        })

    write_csv(
        SUMMARY_FILE,
        ["summary_type", "summary_value", "candidate_count"],
        summary_rows,
    )

    failed = [name for name, passed in checks if not passed]
    lines = [
        "PNIS PHASE 2G.13 - FIELDWORK EXECUTION TRACKER AUDIT",
        "=" * 72,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Plan rows: {len(plan_rows)}",
        f"Collection form rows: {len(form_rows)}",
        f"Readiness register rows: {len(readiness_rows)}",
        f"Tracker rows: {len(tracker_rows)}",
        "",
        "CHECK RESULTS",
        "-" * 72,
    ]
    lines.extend(
        f'{"PASS" if passed else "FAIL"}: {name}'
        for name, passed in checks
    )
    lines.extend([
        "",
        "INITIAL FIELDWORK STATUS",
        "-" * 72,
        f"Not visited: {status_counts.get('NOT_VISITED', 0)}",
        f"Visit scheduled: {status_counts.get('VISIT_SCHEDULED', 0)}",
        f"Visit completed: {status_counts.get('VISIT_COMPLETED', 0)}",
        f"Follow-up required: {status_counts.get('FOLLOW_UP_REQUIRED', 0)}",
        f"Routing-eligible candidates: "
        f"{sum(r['routing_eligible'] == 'YES' for r in tracker_rows)}",
        "",
        "OUTPUT FILES",
        "-" * 72,
        str(TRACKER_FILE),
        str(SUMMARY_FILE),
        str(AUDIT_FILE),
        "",
        "IMPORTANT LIMITATIONS",
        "-" * 72,
        "This script creates a blank execution tracker; it does not record field visits.",
        "Only enter observations actually collected in the field.",
        "A mapped road or short road distance does not prove physical access.",
        "Do not mark a candidate routing-eligible until required evidence is reviewed "
        "and approval is explicitly documented.",
        "This script does not modify Phase 2C, Phase 2E, or Phase 2G source files.",
        "",
        f"Checks passed: {sum(p for _, p in checks)}/{len(checks)}",
        f"Checks failed: {len(failed)}/{len(checks)}",
        f"Issues recorded: {len(issues) + len(failed)}",
        f"Status: {'PASS' if not issues and not failed else 'REVIEW_REQUIRED'}",
    ])
    if issues:
        lines.extend(["", "ISSUES", "-" * 72, *issues])
    if failed:
        lines.extend(["", "FAILED CHECKS", "-" * 72, *failed])

    AUDIT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Tracker: {TRACKER_FILE}")
    print(f"Summary: {SUMMARY_FILE}")
    print(f"Audit:   {AUDIT_FILE}")
    print(f"Checks passed: {sum(p for _, p in checks)}/{len(checks)}")
    print(f"Checks failed: {len(failed)}/{len(checks)}")
    print(f"Issues recorded: {len(issues) + len(failed)}")
    print(f"STATUS: {'PASS' if not issues and not failed else 'REVIEW_REQUIRED'}")

    if issues or failed:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
