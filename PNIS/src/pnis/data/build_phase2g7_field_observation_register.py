from pathlib import Path
from datetime import datetime, timezone
import csv

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "processed"

SOURCE = DATA / "phase2g6_field_verification_worklist.csv"
OUTPUT = DATA / "phase2g7_field_observation_register.csv"
AUDIT = DATA / "phase2g7_field_observation_audit.txt"

REQUIRED_SOURCE_COLUMNS = [
    "candidate_record_id",
    "phase2g6_review_sequence",
    "phase2g5_access_risk_screen_v2",
    "phase2g2_distance_priority",
    "recalculated_nearest_road_distance_m",
    "nearest_road_fclass",
]

OBSERVATION_FIELDS = [
    "field_visit_date",
    "observer_name_or_id",
    "gps_latitude",
    "gps_longitude",
    "gps_accuracy_m",
    "candidate_location_confirmed",
    "facility_type_observed",
    "facility_operational_status",
    "physical_entrance_observed",
    "vehicle_access_observed",
    "vehicle_type_assessed",
    "road_surface_observed",
    "road_width_or_clearance_notes",
    "seasonal_passability_observed",
    "access_restrictions_observed",
    "photo_or_evidence_reference",
    "field_observation_notes",
    "verification_status",
    "reviewer_name_or_id",
    "review_date",
    "review_decision",
    "review_notes",
]

PENDING_DEFAULTS = {
    "candidate_location_confirmed": "PENDING",
    "facility_type_observed": "NOT_RECORDED",
    "facility_operational_status": "NOT_VERIFIED",
    "physical_entrance_observed": "NOT_VERIFIED",
    "vehicle_access_observed": "NOT_VERIFIED",
    "vehicle_type_assessed": "NOT_ASSESSED",
    "road_surface_observed": "NOT_RECORDED",
    "road_width_or_clearance_notes": "",
    "seasonal_passability_observed": "NOT_VERIFIED",
    "access_restrictions_observed": "NOT_VERIFIED",
    "photo_or_evidence_reference": "",
    "field_observation_notes": "",
    "verification_status": "PENDING_FIELD_VISIT",
    "reviewer_name_or_id": "",
    "review_date": "",
    "review_decision": "PENDING_REVIEW",
    "review_notes": "",
}

def stop(message):
    raise SystemExit("ERROR: " + message)

if not SOURCE.exists():
    stop(f"Required Phase 2G.6 input not found: {SOURCE}")

if OUTPUT.exists() or AUDIT.exists():
    stop(
        "At least one Phase 2G.7 output already exists. "
        "Nothing was overwritten. Inspect existing files before rerunning."
    )

with SOURCE.open("r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    source_columns = reader.fieldnames or []
    missing = [c for c in REQUIRED_SOURCE_COLUMNS if c not in source_columns]
    if missing:
        stop(f"Required source columns missing: {missing}")
    rows = list(reader)

if len(rows) != 255:
    stop(f"Expected 255 source rows, found {len(rows)}")

ids = [r["candidate_record_id"].strip() for r in rows]
if any(not value for value in ids):
    stop("A source candidate ID is blank")
if len(ids) != len(set(ids)):
    stop("Source candidate IDs are not unique")

fieldnames = list(source_columns)
for field in OBSERVATION_FIELDS:
    if field not in fieldnames:
        fieldnames.append(field)

for row in rows:
    for field, value in PENDING_DEFAULTS.items():
        row[field] = value

    # These fields must remain explicitly unapproved at this stage.
    row["field_visit_date"] = ""
    row["observer_name_or_id"] = ""
    row["gps_latitude"] = ""
    row["gps_longitude"] = ""
    row["gps_accuracy_m"] = ""
    row["reviewer_name_or_id"] = ""
    row["review_date"] = ""

with OUTPUT.open("x", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

with OUTPUT.open("r", encoding="utf-8-sig", newline="") as f:
    check_rows = list(csv.DictReader(f))

if len(check_rows) != 255:
    OUTPUT.unlink(missing_ok=True)
    stop("Output row-count validation failed; incomplete output removed")

check_ids = [r["candidate_record_id"].strip() for r in check_rows]
if check_ids != ids:
    OUTPUT.unlink(missing_ok=True)
    stop("Output candidate IDs/order do not match the source; output removed")

unsafe = [
    r for r in check_rows
    if r["verification_status"] != "PENDING_FIELD_VISIT"
    or r["review_decision"] != "PENDING_REVIEW"
    or r.get("routing_eligible", "NO") != "NO"
]
if unsafe:
    OUTPUT.unlink(missing_ok=True)
    stop(
        f"{len(unsafe)} rows failed pending/routing safeguard validation; "
        "output removed"
    )

now = datetime.now(timezone.utc).isoformat()
audit_lines = [
    "PHASE 2G.7 - FIELD OBSERVATION REGISTER AUDIT",
    "=" * 72,
    f"Generated UTC: {now}",
    "Status: completed",
    "",
    "INPUT",
    "-" * 72,
    str(SOURCE.relative_to(ROOT)),
    "",
    "METHOD",
    "-" * 72,
    "Retained every Phase 2G.6 candidate and source field.",
    "Added blank field-observation and independent-review fields.",
    "No field evidence was invented or inferred.",
    "No candidate was automatically approved for routing.",
    "",
    "RESULTS",
    "-" * 72,
    f"Source rows: {len(rows)}",
    f"Output rows: {len(check_rows)}",
    f"Unique candidate IDs: {len(set(check_ids))}",
    "Field visits recorded at generation: 0",
    "Review decisions completed at generation: 0",
    "Routing-eligible candidates: 0",
    "",
    "VALIDATION",
    "-" * 72,
    "PASS: all 255 candidate rows retained in source order",
    "PASS: candidate IDs are nonblank and unique",
    "PASS: all new observations start pending or unrecorded",
    "PASS: all review decisions start pending",
    "PASS: all candidates remain routing-ineligible",
    "PASS: no existing output was overwritten",
    "",
    "LIMITATIONS",
    "-" * 72,
    "This register is a blank recording template, not field evidence.",
    "Record only observations actually made and evidence actually collected.",
    "GPS, photographs, or notes alone do not establish vehicle suitability.",
    "Routing eligibility requires documented evidence and a separate review.",
    "",
    "OUTPUTS",
    "-" * 72,
    str(OUTPUT.relative_to(ROOT)),
    str(AUDIT.relative_to(ROOT)),
    "",
]

with AUDIT.open("x", encoding="utf-8", newline="") as f:
    f.write("\n".join(audit_lines))

print("=" * 72)
print("PHASE 2G.7 - FIELD OBSERVATION REGISTER")
print("=" * 72)
print("Status: completed")
print(f"Source candidates: {len(rows)}")
print(f"Output candidates: {len(check_rows)}")
print(f"Unique candidate IDs: {len(set(check_ids))}")
print("Field visits recorded: 0")
print("Review decisions completed: 0")
print("Routing-eligible candidates: 0")
print("")
print("OUTPUTS")
print(OUTPUT)
print(AUDIT)
print("")
print("VALIDATION: PASS")
