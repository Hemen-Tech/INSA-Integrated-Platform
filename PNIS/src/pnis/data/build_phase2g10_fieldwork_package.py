
import csv
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.cwd()
PROCESSED = ROOT / "data" / "processed"

SOURCE = PROCESSED / "phase2g6_field_verification_worklist.csv"

PLAN = PROCESSED / "phase2g10_fieldwork_priority_plan.csv"
FORM = PROCESSED / "phase2g10_field_data_collection_form.csv"
PROTOCOL = PROCESSED / "phase2g10_fieldwork_protocol.txt"
AUDIT = PROCESSED / "phase2g10_preparation_audit.txt"

EXPECTED_ROWS = 255

def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def int_or_large(value):
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 999999999

if not SOURCE.exists():
    raise FileNotFoundError(f"Required source file not found: {SOURCE}")

source_rows = read_csv(SOURCE)

if not source_rows:
    raise ValueError("The source worklist contains no data rows.")

required_columns = {
    "candidate_record_id",
    "longitude",
    "latitude",
    "review_priority",
    "phase2g5_risk_queue_order_v2",
    "phase2g6_review_sequence",
    "routing_eligibility",
    "routing_eligible",
    "operational_facility_confirmed",
    "physical_vehicle_access_confirmed",
}

available_columns = set(source_rows[0].keys())
missing_columns = sorted(required_columns - available_columns)

if missing_columns:
    raise ValueError(
        "Required columns are missing from the source: "
        + ", ".join(missing_columns)
    )

ids = [str(r.get("candidate_record_id", "")).strip() for r in source_rows]
blank_ids = sum(not value for value in ids)
unique_ids = set(value for value in ids if value)

if blank_ids:
    raise ValueError(f"Source contains {blank_ids} blank candidate IDs.")

if len(unique_ids) != len(ids):
    raise ValueError("Duplicate candidate IDs detected in the source worklist.")

# Sort by the existing risk queue, then Phase 2G.6 review sequence.
# This is a priority order, not a geographic route optimization.
ordered = sorted(
    source_rows,
    key=lambda r: (
        int_or_large(r.get("phase2g5_risk_queue_order_v2")),
        int_or_large(r.get("phase2g6_review_sequence")),
        str(r.get("candidate_record_id", "")).strip(),
    ),
)

plan_fields = [
    "phase2g10_visit_priority_order",
    "candidate_record_id",
    "osm_id",
    "candidate_match_text",
    "review_group",
    "longitude",
    "latitude",
    "review_priority",
    "phase2g2_distance_priority",
    "phase2g5_access_risk_screen_v2",
    "phase2g5_risk_queue_order_v2",
    "phase2g6_review_sequence",
    "recommended_review_action",
    "nearest_mapped_road_distance_m",
    "nearest_road_fclass",
    "phase2g3_vehicle_suitability_screen",
    "verification_status",
    "coordinate_review_status",
    "operating_status_review",
    "vehicle_access_review",
    "verification_decision",
    "follow_up_required",
    "routing_eligibility",
    "operational_facility_confirmed",
    "physical_vehicle_access_confirmed",
    "routing_eligible",
]

plan_rows = []

for index, row in enumerate(ordered, start=1):
    plan_row = {field: row.get(field, "") for field in plan_fields}
    plan_row["phase2g10_visit_priority_order"] = index
    plan_rows.append(plan_row)

write_csv(PLAN, plan_rows, plan_fields)

# Create a field form with candidate IDs and coordinates prefilled.
# All observations remain blank until a real field visit occurs.
form_fields = [
    "candidate_record_id",
    "osm_id",
    "candidate_match_text",
    "planned_longitude",
    "planned_latitude",
    "field_visit_date",
    "field_visit_time_local",
    "observer_name_or_id",
    "actual_gps_longitude",
    "actual_gps_latitude",
    "gps_accuracy_m",
    "facility_identity_result",
    "verified_facility_name",
    "actual_facility_type",
    "operating_status",
    "facility_function_evidence",
    "facility_evidence_reference",
    "physical_entrance_found",
    "entrance_gps_longitude",
    "entrance_gps_latitude",
    "road_surface_observed",
    "road_condition_observed",
    "vehicle_types_tested_or_confirmed",
    "vehicle_access_result",
    "vehicle_restrictions",
    "seasonal_passability",
    "legal_or_permission_restrictions",
    "access_evidence_description",
    "photo_or_document_reference",
    "evidence_date",
    "visit_outcome",
    "follow_up_required",
    "follow_up_action",
    "field_notes",
    "reviewer_name_or_id",
    "review_date",
    "verification_decision",
    "decision_rationale",
    "routing_eligibility_review",
    "routing_eligible",
]

form_rows = []

for row in ordered:
    form_rows.append({
        "candidate_record_id": row.get("candidate_record_id", ""),
        "osm_id": row.get("osm_id", ""),
        "candidate_match_text": row.get("candidate_match_text", ""),
        "planned_longitude": row.get("longitude", ""),
        "planned_latitude": row.get("latitude", ""),
        "field_visit_date": "",
        "field_visit_time_local": "",
        "observer_name_or_id": "",
        "actual_gps_longitude": "",
        "actual_gps_latitude": "",
        "gps_accuracy_m": "",
        "facility_identity_result": "",
        "verified_facility_name": "",
        "actual_facility_type": "",
        "operating_status": "",
        "facility_function_evidence": "",
        "facility_evidence_reference": "",
        "physical_entrance_found": "",
        "entrance_gps_longitude": "",
        "entrance_gps_latitude": "",
        "road_surface_observed": "",
        "road_condition_observed": "",
        "vehicle_types_tested_or_confirmed": "",
        "vehicle_access_result": "",
        "vehicle_restrictions": "",
        "seasonal_passability": "",
        "legal_or_permission_restrictions": "",
        "access_evidence_description": "",
        "photo_or_document_reference": "",
        "evidence_date": "",
        "visit_outcome": "",
        "follow_up_required": "",
        "follow_up_action": "",
        "field_notes": "",
        "reviewer_name_or_id": "",
        "review_date": "",
        "verification_decision": "",
        "decision_rationale": "",
        "routing_eligibility_review": "",
        "routing_eligible": "NO",
    })

write_csv(FORM, form_rows, form_fields)

protocol_text = f"""PNIS PHASE 2G.10 - FIELDWORK PREPARATION PROTOCOL
Generated UTC: {datetime.now(timezone.utc).isoformat()}

1. PURPOSE
Prepare a controlled field verification process for the 255 candidate
records in the Phase 2G.6 worklist. This package is for planning and
recording future observations; it does not certify any candidate.

2. VISIT PRIORITY
The visit-priority plan follows the existing Phase 2G.5 risk queue,
then the Phase 2G.6 review sequence, then candidate ID.
This is NOT an optimized driving route. Grouping and route planning
require field-team starting points, transport, and access information.

3. BEFORE EACH VISIT
- Confirm the candidate_record_id and planned coordinates.
- Treat the mapped feature and its label as an unverified lead.
- Prepare a way to record GPS coordinates, date, observer, and evidence.
- Do not assume agricultural land is a verified farm or collection point.

4. REQUIRED FIELD CHECKS
- Establish the actual facility or farm identity and its function.
- Record whether it is operating and the basis for that conclusion.
- Record actual GPS coordinates and GPS accuracy where available.
- Locate and record the physical entrance separately when practical.
- Observe road surface and condition; record restrictions and seasonal
  passability.
- Record which vehicle types are supported and the evidence basis.
- Record access permissions or legal restrictions when relevant.
- Record evidence references, visit outcome, and required follow-up.

5. EVIDENCE QUALITY
Record only observations actually made and documents/photos actually
collected or inspected. Use stable evidence references and dates.
Distinguish direct observation, statements from a named source, and
unverified assumptions. Do not fabricate missing values or evidence.

6. FAILED OR INCOMPLETE VISITS
Use the visit outcome and follow-up fields to document not found,
inaccessible, closed, unsafe to approach, permission denied, or
insufficient evidence as applicable. Do not treat a failed visit as
proof that a facility does not exist. Schedule follow-up when needed.

7. REVIEW AND ROUTING SAFEGUARD
Field collection and approval are separate steps. A reviewer must
assess facility identity, operation, coordinates, physical entrance,
vehicle access, restrictions, and evidence quality before making a
decision. Keep routing_eligible = NO unless a separate authorized
review explicitly approves eligibility and updates the controlled
routing dataset. Never infer approval from road proximity alone.

8. CURRENT LIMITATION
The current register has no confirmed field visits. The generated form
contains blank observation fields and prefilled candidate identifiers
and planned coordinates only. No real-world access or facility status
is asserted by this package.

SOURCE
{SOURCE}
Existing source worklist was read only.
"""

PROTOCOL.write_text(protocol_text, encoding="utf-8")

# Validate generated artifacts.
plan_check = read_csv(PLAN)
form_check = read_csv(FORM)

issues = []

if len(source_rows) != EXPECTED_ROWS:
    issues.append(f"Source row count is {len(source_rows)}, expected {EXPECTED_ROWS}.")

if len(plan_check) != len(source_rows):
    issues.append("Plan row count does not match source row count.")

if len(form_check) != len(source_rows):
    issues.append("Form row count does not match source row count.")

if len({r["candidate_record_id"] for r in plan_check}) != len(plan_check):
    issues.append("Duplicate candidate IDs found in generated plan.")

if len({r["candidate_record_id"] for r in form_check}) != len(form_check):
    issues.append("Duplicate candidate IDs found in generated form.")

if [r["candidate_record_id"] for r in plan_check] != [
    r["candidate_record_id"] for r in form_check
]:
    issues.append("Plan and form candidate order differs.")

routing_not_no = sum(
    str(r.get("routing_eligible", "")).strip().upper() != "NO"
    for r in form_check
)

if routing_not_no:
    issues.append(
        f"{routing_not_no} form rows do not have routing_eligible=NO."
    )

audit_lines = [
    "PNIS PHASE 2G.10 - FIELDWORK PREPARATION AUDIT",
    f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
    f"Source rows: {len(source_rows)}",
    f"Unique source candidate IDs: {len(unique_ids)}",
    f"Plan rows: {len(plan_check)}",
    f"Field form rows: {len(form_check)}",
    f"Form rows with routing_eligible=NO: {len(form_check) - routing_not_no}",
    f"Issues found: {len(issues)}",
    "",
    "OUTPUT FILES",
    str(PLAN),
    str(FORM),
    str(PROTOCOL),
    "",
    "LIMITATION",
    "This package prepares fieldwork; it does not verify facility identity,",
    "operational status, physical vehicle access, or routing eligibility.",
    "",
]

if issues:
    audit_lines.append("Status: REVIEW REQUIRED")
    audit_lines.extend(f"ISSUE: {issue}" for issue in issues)
else:
    audit_lines.append(
        "Status: PASS - generated row counts, IDs, order, and routing safeguard validated."
    )

AUDIT.write_text("\n".join(audit_lines) + "\n", encoding="utf-8")

print("=" * 68)
print("PHASE 2G.10 - FIELDWORK PACKAGE")
print("=" * 68)
print(f"Source records: {len(source_rows)}")
print(f"Plan rows: {len(plan_check)}")
print(f"Field form rows: {len(form_check)}")
print(f"Routing eligible in form: {routing_not_no} rows not marked NO")
print(f"Issues found: {len(issues)}")
print(f"Audit: {AUDIT}")

for issue in issues:
    print("ISSUE:", issue)

if issues:
    raise SystemExit("Phase 2G.10 validation failed; inspect the audit.")
