
from pathlib import Path
import csv
import math
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "processed"

SOURCE = DATA / "phase2g6_field_verification_worklist.csv"
PLAN = DATA / "phase2g10_fieldwork_priority_plan.csv"
FORM = DATA / "phase2g10_field_data_collection_form.csv"
PROTOCOL = DATA / "phase2g10_fieldwork_protocol.txt"
PREP_AUDIT = DATA / "phase2g10_preparation_audit.txt"

OUT_SUMMARY = DATA / "phase2g11_fieldwork_qa_summary.csv"
OUT_ISSUES = DATA / "phase2g11_fieldwork_qa_issues.csv"
OUT_AUDIT = DATA / "phase2g11_fieldwork_qa_audit.txt"

ID = "candidate_record_id"
REQUIRED_FORM_COLUMNS = [
    "field_visit_date", "observer_name_or_id",
    "actual_gps_longitude", "actual_gps_latitude", "gps_accuracy_m",
    "facility_identity_result", "verified_facility_name",
    "actual_facility_type", "operating_status",
    "facility_function_evidence", "facility_evidence_reference",
    "physical_entrance_found", "entrance_gps_longitude",
    "entrance_gps_latitude", "road_surface_observed",
    "road_condition_observed", "vehicle_types_tested_or_confirmed",
    "vehicle_access_result", "vehicle_restrictions", "seasonal_passability",
    "legal_or_permission_restrictions", "access_evidence_description",
    "photo_or_document_reference", "evidence_date", "visit_outcome",
    "follow_up_required", "follow_up_action", "field_notes",
    "reviewer_name_or_id", "review_date", "verification_decision",
    "decision_rationale", "routing_eligibility_review", "routing_eligible",
]
OBSERVATION_COLUMNS = [
    c for c in REQUIRED_FORM_COLUMNS
    if c not in ("routing_eligible",)
]

def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing input: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        rows = [
            {(k or "").strip(): (v or "").strip()
             for k, v in row.items()}
            for row in reader
        ]
    return rows, headers

def number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def first_column(headers, choices):
    return next((c for c in choices if c in headers), None)

def write_csv(path, rows, headers):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def main():
    checks = []
    issues = []

    def check(name, passed, details):
        checks.append({
            "check": name,
            "status": "PASS" if passed else "FAIL",
            "details": details,
        })
        if not passed:
            issues.append({"check": name, "issue": details})

    try:
        source, sh = read_csv(SOURCE)
        plan, ph = read_csv(PLAN)
        form, fh = read_csv(FORM)
    except Exception as exc:
        check("Input files readable", False, str(exc))
        DATA.mkdir(parents=True, exist_ok=True)
        write_csv(OUT_SUMMARY, checks, ["check", "status", "details"])
        write_csv(OUT_ISSUES, issues, ["check", "issue"])
        OUT_AUDIT.write_text(
            f"PHASE 2G.11 QA\nStatus: REVIEW REQUIRED\n{exc}\n",
            encoding="utf-8"
        )
        print(f"QA could not proceed: {exc}")
        return 1

    check("Candidate ID column exists in all files",
          all(ID in h for h in (sh, ph, fh)),
          f"Required column: {ID}")

    if not all(ID in h for h in (sh, ph, fh)):
        source_ids, plan_ids, form_ids = [], [], []
        check("Candidate ID comparisons", False,
              "Cannot compare IDs because a file lacks candidate_id.")
    else:
        source_ids = [r.get(ID, "") for r in source]
        plan_ids = [r.get(ID, "") for r in plan]
        form_ids = [r.get(ID, "") for r in form]

        def valid_ids(ids):
            return all(ids) and len(ids) == len(set(ids))

        check("Source row count and IDs",
              len(source) == 255 and valid_ids(source_ids),
              f"Rows={len(source)}; nonblank unique IDs={valid_ids(source_ids)}.")
        check("Plan row count and IDs",
              len(plan) == len(source) and valid_ids(plan_ids),
              f"Rows={len(plan)}; source rows={len(source)}; "
              f"nonblank unique IDs={valid_ids(plan_ids)}.")
        check("Form row count and IDs",
              len(form) == len(source) and valid_ids(form_ids),
              f"Rows={len(form)}; source rows={len(source)}; "
              f"nonblank unique IDs={valid_ids(form_ids)}.")
        check("Plan ID set matches source",
              set(plan_ids) == set(source_ids),
              f"Missing={len(set(source_ids)-set(plan_ids))}; "
              f"unexpected={len(set(plan_ids)-set(source_ids))}.")
        check("Form ID set matches source",
              set(form_ids) == set(source_ids),
              f"Missing={len(set(source_ids)-set(form_ids))}; "
              f"unexpected={len(set(form_ids)-set(source_ids))}.")
        check("Plan and form candidate order matches",
              plan_ids == form_ids,
              "IDs appear in the same order." if plan_ids == form_ids
              else "Plan and form candidate order differs.")

    # Check planned coordinates against source coordinates by candidate ID.
    lon_src = first_column(sh, ["longitude", "candidate_longitude"])
    lat_src = first_column(sh, ["latitude", "candidate_latitude"])
    lon_plan = first_column(ph, [
        "longitude", "planned_longitude", "candidate_longitude",
        "planned_lon", "candidate_lon"
    ])
    lat_plan = first_column(ph, [
        "latitude", "planned_latitude", "candidate_latitude",
        "planned_lat", "candidate_lat"
    ])

    if all(ID in h for h in (sh, ph)) and all(
        [lon_src, lat_src, lon_plan, lat_plan]
    ):
        source_by_id = {r[ID]: r for r in source}
        missing = 0
        mismatches = []
        for r in plan:
            original = source_by_id.get(r.get(ID, ""))
            if original is None:
                continue
            values = [
                number(original.get(lon_src, "")),
                number(original.get(lat_src, "")),
                number(r.get(lon_plan, "")),
                number(r.get(lat_plan, "")),
            ]
            if any(v is None for v in values):
                missing += 1
            elif (abs(values[0] - values[2]) > 1e-9
                  or abs(values[1] - values[3]) > 1e-9):
                mismatches.append(r.get(ID, ""))
        check("Planned coordinates match source",
              missing == 0 and not mismatches,
              f"Missing/unparseable={missing}; mismatches={len(mismatches)}; "
              f"columns={lon_plan}/{lat_plan}.")
    else:
        check("Coordinate columns available", False,
              f"Source columns={lon_src}/{lat_src}; "
              f"plan columns={lon_plan}/{lat_plan}.")

    missing_columns = [c for c in REQUIRED_FORM_COLUMNS if c not in fh]
    check("Required field evidence columns present",
          not missing_columns,
          "Missing columns: " + (
              ", ".join(missing_columns) if missing_columns else "none"
          ))

    # Routing must remain blocked. This audit never approves candidates.
    routing = [r.get("routing_eligible", "").strip().upper() for r in form]
    check("All form candidates remain routing-ineligible",
          len(routing) == len(form) and all(v == "NO" for v in routing),
          f"NO={sum(v == 'NO' for v in routing)} of {len(form)} form rows.")

    for col in [
        "routing_eligibility",
        "operational_facility_confirmed",
        "physical_vehicle_access_confirmed",
    ]:
        if col in ph:
            allowed = {
                "NO", "NOT_APPROVED_FOR_OPERATIONAL_ROUTING",
                "FALSE", "0", "PENDING", "UNVERIFIED"
            }
            bad = sum(r.get(col, "").strip().upper() not in allowed for r in plan)
            check(f"Plan safeguard: {col}", bad == 0,
                  f"Unexpected or blank values={bad} of {len(plan)}.")
        else:
            check(f"Plan safeguard column exists: {col}", False,
                  f"Expected column '{col}' is absent from the plan.")

    # Before visits, field-observation/evidence fields should remain blank.
    populated = []
    for col in OBSERVATION_COLUMNS:
        if col in fh:
            count = sum(bool(r.get(col, "").strip()) for r in form)
            if count:
                populated.append(f"{col}={count}")
    check("No fabricated field observations detected",
          not populated,
          "Populated fields: " + (
              ", ".join(populated) if populated else "none"
          ))

    # Check the declared priority keys and whether the rows are ordered by them.
    priority_keys = [
        c for c in [
            "phase2g5_risk_queue_order_v2",
            "phase2g6_review_sequence",
        ] if c in ph
    ]
    if priority_keys and ID in ph:
        def priority_key(row):
            result = []
            for key in priority_keys:
                value = row.get(key, "")
                n = number(value)
                result.append((0, n) if n is not None else (1, value.casefold()))
            result.append((2, row.get(ID, "")))
            return tuple(result)

        expected = sorted(plan, key=priority_key)
        ordered = [r.get(ID, "") for r in plan] == [
            r.get(ID, "") for r in expected
        ]
        check("Plan follows Phase 2G.5/2G.6 priority keys",
              ordered,
              f"Checked keys: {', '.join(priority_keys)}; "
              "candidate ID used as final tie-breaker.")
    else:
        check("Priority fields available", False,
              "Could not find phase2g5_risk_queue_order_v2 and/or "
              "phase2g6_review_sequence in the plan.")

    protocol_ok = PROTOCOL.exists()
    protocol_text = (
        PROTOCOL.read_text(encoding="utf-8-sig", errors="replace")
        if protocol_ok else ""
    )
    check("Fieldwork protocol exists", protocol_ok, str(PROTOCOL))
    terms = ["routing", "vehicle", "evidence"]
    missing_terms = [t for t in terms if t not in protocol_text.lower()]
    check("Protocol describes key safeguards",
          protocol_ok and not missing_terms,
          "Missing terms: " + (
              ", ".join(missing_terms) if missing_terms else "none"
          ))

    prep_ok = PREP_AUDIT.exists()
    check("Phase 2G.10 preparation audit exists", prep_ok, str(PREP_AUDIT))
    if prep_ok:
        prep_text = PREP_AUDIT.read_text(
            encoding="utf-8-sig", errors="replace"
        )
        check("Preparation audit reports zero issues",
              "Issues found: 0" in prep_text,
              "Exact zero-issues marker found."
              if "Issues found: 0" in prep_text
              else "Expected 'Issues found: 0' marker not found.")

    status = (
        "PASS" if all(c["status"] == "PASS" for c in checks)
        else "REVIEW REQUIRED"
    )
    write_csv(OUT_SUMMARY, checks, ["check", "status", "details"])
    write_csv(OUT_ISSUES, issues, ["check", "issue"])

    lines = [
        "PNIS PHASE 2G.11 - INDEPENDENT FIELDWORK PACKAGE QA",
        "=" * 68,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Source rows: {len(source)}",
        f"Plan rows: {len(plan)}",
        f"Form rows: {len(form)}",
        f"Checks passed: {sum(c['status']=='PASS' for c in checks)} / {len(checks)}",
        f"Checks failed: {sum(c['status']=='FAIL' for c in checks)} / {len(checks)}",
        f"Issues recorded: {len(issues)}",
        "",
        "CHECK RESULTS",
        "-" * 68,
    ]
    lines += [
        f"{c['status']}: {c['check']} — {c['details']}" for c in checks
    ]
    lines += [
        "",
        "OUTPUT FILES",
        str(OUT_SUMMARY),
        str(OUT_ISSUES),
        str(OUT_AUDIT),
        "",
        "LIMITATION",
        "This audit checks file consistency and safeguards only. It does not",
        "verify facility identity, operation, physical access, road passability,",
        "or field evidence.",
        "",
        f"Status: {status}",
    ]
    OUT_AUDIT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 68)
    print("PHASE 2G.11 - INDEPENDENT FIELDWORK PACKAGE QA")
    print("=" * 68)
    print(f"Source rows: {len(source)}")
    print(f"Plan rows: {len(plan)}")
    print(f"Form rows: {len(form)}")
    print(f"Checks passed: {sum(c['status']=='PASS' for c in checks)} / {len(checks)}")
    print(f"Checks failed: {sum(c['status']=='FAIL' for c in checks)} / {len(checks)}")
    print(f"Issues recorded: {len(issues)}")
    print(f"Summary: {OUT_SUMMARY}")
    print(f"Issues:  {OUT_ISSUES}")
    print(f"Audit:   {OUT_AUDIT}")
    print(f"STATUS: {status}")
    return 0 if status == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
