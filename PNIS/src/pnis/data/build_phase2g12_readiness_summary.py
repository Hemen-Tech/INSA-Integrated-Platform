
import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("data/processed")

INPUTS = {
    "proximity": "phase2g1_candidate_road_proximity_register.csv",
    "access": "phase2g4_candidate_road_access_review_register_v2.csv",
    "risk": "phase2g5_candidate_access_risk_register_v2.csv",
    "evidence": "phase2g6_evidence_register.csv",
    "worklist": "phase2g6_field_verification_worklist.csv",
    "observations": "phase2g7_field_observation_register.csv",
    "plan": "phase2g10_fieldwork_priority_plan.csv",
    "form": "phase2g10_field_data_collection_form.csv",
}

OUTPUT_REGISTER = BASE / "phase2g12_facility_access_readiness_register.csv"
OUTPUT_SUMMARY = BASE / "phase2g12_readiness_summary.csv"
OUTPUT_AUDIT = BASE / "phase2g12_readiness_audit.txt"


def read_csv(filename):
    path = BASE / filename
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        rows = list(reader)
        return reader.fieldnames, rows


def value(row, key, default=""):
    item = row.get(key, default)
    return "" if item is None else str(item).strip()


def write_csv(path, rows, columns):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def id_map(rows, filename):
    result = {}
    for line_no, row in enumerate(rows, start=2):
        cid = value(row, "candidate_record_id")
        if not cid:
            raise ValueError(
                f"{filename}: blank candidate_record_id at CSV line {line_no}"
            )
        if cid in result:
            raise ValueError(
                f"{filename}: duplicate candidate_record_id {cid!r}"
            )
        result[cid] = row
    return result


def is_populated(row, fields):
    return any(value(row, field) for field in fields)


def main():
    print("=" * 72)
    print("PNIS PHASE 2G.12 - FACILITY AND ACCESS READINESS")
    print("=" * 72)

    loaded = {}
    maps = {}
    headers = {}
    for key, filename in INPUTS.items():
        headers[key], loaded[key] = read_csv(filename)
        maps[key] = id_map(loaded[key], filename)
        print(f"{filename}: {len(loaded[key])} rows")

    source_ids = set(maps["proximity"])
    issues = []

    for key, filename in INPUTS.items():
        ids = set(maps[key])
        missing = sorted(source_ids - ids)
        unexpected = sorted(ids - source_ids)
        if missing or unexpected:
            issues.append(
                f"{key}: candidate ID mismatch; "
                f"missing={len(missing)}, unexpected={len(unexpected)}"
            )

    # Preserve Phase 2G.1 candidate order as the master order.
    register = []

    for source in loaded["proximity"]:
        cid = value(source, "candidate_record_id")
        access = maps["access"].get(cid, {})
        risk = maps["risk"].get(cid, {})
        evidence = maps["evidence"].get(cid, {})
        worklist = maps["worklist"].get(cid, {})
        observation = maps["observations"].get(cid, {})
        plan = maps["plan"].get(cid, {})
        form = maps["form"].get(cid, {})

        distance_text = value(
            risk, "recalculated_nearest_road_distance_m",
            value(source, "nearest_mapped_road_distance_m")
        )
        try:
            distance = float(distance_text) if distance_text else None
        except ValueError:
            distance = None

        risk_level = value(risk, "phase2g5_access_risk_screen_v2", "UNKNOWN")
        distance_band = value(
            risk, "phase2g5_distance_band_v2",
            value(source, "road_proximity_band", "UNKNOWN")
        )
        road_class = value(
            access, "nearest_road_fclass",
            value(source, "nearest_road_fclass", "UNKNOWN")
        )

        field_visit_recorded = is_populated(
            observation,
            ["field_visit_date", "observer_name_or_id"]
        )
        field_evidence_recorded = is_populated(
            observation,
            [
                "photo_or_evidence_reference",
                "field_observation_notes",
                "gps_latitude",
                "gps_longitude",
            ]
        )
        form_visit_recorded = is_populated(
            form,
            [
                "field_visit_date",
                "observer_name_or_id",
                "photo_or_document_reference",
                "actual_gps_longitude",
                "actual_gps_latitude",
            ]
        )
        evidence_recorded = is_populated(
            evidence,
            [
                "phase2g6_evidence_description",
                "phase2g6_evidence_reference",
                "phase2g6_evidence_date",
                "phase2g6_reviewer",
                "phase2g6_review_date",
            ]
        )

        if risk_level == "HIGH_REVIEW" or (
            distance is not None and distance > 500
        ):
            readiness = "PRIORITY_FIELD_VERIFICATION"
        elif risk_level == "ELEVATED_REVIEW" or (
            distance is not None and distance > 250
        ):
            readiness = "ELEVATED_FIELD_VERIFICATION"
        elif risk_level == "STANDARD_REVIEW":
            readiness = "STANDARD_FIELD_VERIFICATION"
        else:
            readiness = "RISK_CLASSIFICATION_REVIEW"

        register.append({
            "candidate_record_id": cid,
            "candidate_match_text": value(source, "candidate_match_text"),
            "review_group": value(source, "review_group"),
            "longitude": value(source, "longitude"),
            "latitude": value(source, "latitude"),
            "field_review_sequence": value(source, "field_review_sequence"),
            "phase2g10_visit_priority_order": value(
                plan, "phase2g10_visit_priority_order"
            ),
            "phase2g6_review_sequence": value(
                evidence, "phase2g6_review_sequence"
            ),
            "readiness_priority": readiness,
            "phase2g5_access_risk_screen_v2": risk_level,
            "phase2g5_access_risk_reason_v2": value(
                risk, "phase2g5_access_risk_reason_v2"
            ),
            "phase2g5_risk_queue_order_v2": value(
                risk, "phase2g5_risk_queue_order_v2"
            ),
            "distance_band": distance_band,
            "nearest_mapped_road_distance_m": (
                f"{distance:.3f}" if distance is not None else ""
            ),
            "nearest_road_fclass": road_class,
            "phase2g3_vehicle_suitability_screen": value(
                access, "phase2g3_vehicle_suitability_screen"
            ),
            "phase2g4_access_decision": value(
                access, "phase2g4_access_decision"
            ),
            "phase2g6_review_status": value(
                evidence, "phase2g6_review_status"
            ),
            "phase2g6_review_decision": value(
                evidence, "phase2g6_review_decision"
            ),
            "field_visit_recorded": "YES" if field_visit_recorded else "NO",
            "field_evidence_recorded": "YES" if field_evidence_recorded else "NO",
            "form_visit_recorded": "YES" if form_visit_recorded else "NO",
            "phase2g6_evidence_recorded": "YES" if evidence_recorded else "NO",
            "operational_facility_verified": "NO",
            "physical_vehicle_access_confirmed": "NO",
            "routing_eligible": "NO",
            "readiness_limitation": (
                "Candidate remains unverified. Mapped-road proximity and "
                "road-class screening do not establish physical access, "
                "facility operation, legal access, or vehicle passability."
            ),
        })

    # Final register must never grant operational routing eligibility.
    if any(row["routing_eligible"] != "NO" for row in register):
        issues.append("Routing safeguard failed: a candidate is not marked NO.")

    if len(register) != len(source_ids):
        issues.append(
            f"Register row count mismatch: rows={len(register)}, "
            f"unique source IDs={len(source_ids)}"
        )

    # Build overall summary.
    summary = []

    def add_summary(group_type, group_value, rows):
        summary.append({
            "summary_type": group_type,
            "summary_value": group_value,
            "candidate_count": len(rows),
            "field_visit_recorded_count": sum(
                r["field_visit_recorded"] == "YES" for r in rows
            ),
            "field_evidence_recorded_count": sum(
                r["field_evidence_recorded"] == "YES" for r in rows
            ),
            "operational_facility_verified_count": sum(
                r["operational_facility_verified"] == "YES" for r in rows
            ),
            "physical_vehicle_access_confirmed_count": sum(
                r["physical_vehicle_access_confirmed"] == "YES" for r in rows
            ),
            "routing_eligible_count": sum(
                r["routing_eligible"] == "YES" for r in rows
            ),
        })

    add_summary("OVERALL", "ALL_CANDIDATES", register)

    for field, group_type in [
        ("readiness_priority", "READINESS_PRIORITY"),
        ("phase2g5_access_risk_screen_v2", "ACCESS_RISK"),
        ("distance_band", "ROAD_PROXIMITY_BAND"),
        ("nearest_road_fclass", "NEAREST_ROAD_CLASS"),
    ]:
        groups = {}
        for row in register:
            label = row[field] or "UNKNOWN_OR_BLANK"
            groups.setdefault(label, []).append(row)
        for label in sorted(groups):
            add_summary(group_type, label, groups[label])

    register_columns = list(register[0].keys()) if register else [
        "candidate_record_id"
    ]
    summary_columns = [
        "summary_type",
        "summary_value",
        "candidate_count",
        "field_visit_recorded_count",
        "field_evidence_recorded_count",
        "operational_facility_verified_count",
        "physical_vehicle_access_confirmed_count",
        "routing_eligible_count",
    ]

    write_csv(OUTPUT_REGISTER, register, register_columns)
    write_csv(OUTPUT_SUMMARY, summary, summary_columns)

    total = len(register)
    high_risk = sum(
        row["phase2g5_access_risk_screen_v2"] == "HIGH_REVIEW"
        for row in register
    )
    elevated = sum(
        row["phase2g5_access_risk_screen_v2"] == "ELEVATED_REVIEW"
        for row in register
    )
    standard = sum(
        row["phase2g5_access_risk_screen_v2"] == "STANDARD_REVIEW"
        for row in register
    )
    over_500 = sum(
        row["nearest_mapped_road_distance_m"]
        and float(row["nearest_mapped_road_distance_m"]) > 500
        for row in register
    )
    visits = sum(row["field_visit_recorded"] == "YES" for row in register)
    evidence_count = sum(
        row["field_evidence_recorded"] == "YES" for row in register
    )

    checks = [
        ("All eight required inputs loaded", len(loaded) == 8),
        ("All source candidate IDs are unique and nonblank", True),
        ("Candidate ID sets match across all eight inputs", not any(
            "candidate ID mismatch" in issue for issue in issues
        )),
        ("Readiness register row count matches source", total == len(source_ids)),
        ("Routing eligibility remains NO for every candidate", all(
            row["routing_eligible"] == "NO" for row in register
        )),
        ("Operational facility verification remains NO", all(
            row["operational_facility_verified"] == "NO" for row in register
        )),
        ("Physical vehicle access confirmation remains NO", all(
            row["physical_vehicle_access_confirmed"] == "NO"
            for row in register
        )),
    ]

    passed = sum(ok for _, ok in checks)
    failed = len(checks) - passed
    status = "PASS" if failed == 0 and not issues else "REVIEW REQUIRED"

    lines = [
        "PNIS PHASE 2G.12 - FACILITY AND ACCESS READINESS AUDIT",
        "=" * 72,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Input files: {len(loaded)}",
        f"Readiness register rows: {total}",
        f"Summary rows: {len(summary)}",
        "",
        "CHECK RESULTS",
        "-" * 72,
    ]
    for label, ok in checks:
        lines.append(f"{'PASS' if ok else 'FAIL'}: {label}")
    lines += [
        "",
        "CANDIDATE SUMMARY",
        "-" * 72,
        f"High risk review: {high_risk}",
        f"Elevated review: {elevated}",
        f"Standard review: {standard}",
        f"Nearest mapped road >500 m: {over_500}",
        f"Observation register visit date/observer recorded: {visits}",
        f"Observation register evidence/GPS notes recorded: {evidence_count}",
        "Operational facility verified by this script: 0",
        "Physical vehicle access confirmed by this script: 0",
        "Routing-eligible candidates: 0",
        "",
        "INPUT FILES",
        "-" * 72,
    ]
    for key, filename in INPUTS.items():
        lines.append(f"{key}: {BASE / filename}")

    lines += [
        "",
        "OUTPUT FILES",
        "-" * 72,
        str(OUTPUT_REGISTER.resolve()),
        str(OUTPUT_SUMMARY.resolve()),
        str(OUTPUT_AUDIT.resolve()),
        "",
        "LIMITATIONS",
        "-" * 72,
        "This is a data consolidation and readiness screening, not field verification.",
        "The script does not establish facility identity, operation, legal access,",
        "physical entrance connectivity, road passability, or vehicle suitability.",
        "Blank field evidence is not interpreted as proof that a facility does not exist.",
        "All candidates remain routing-ineligible pending verified evidence and review.",
        "",
        f"Checks passed: {passed}/{len(checks)}",
        f"Checks failed: {failed}/{len(checks)}",
        f"Issues recorded: {len(issues)}",
    ]
    if issues:
        lines += ["", "ISSUES", "-" * 72]
        lines.extend(issues)
    lines += ["", f"Status: {status}"]

    OUTPUT_AUDIT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print(f"Readiness register: {OUTPUT_REGISTER.resolve()}")
    print(f"Summary:            {OUTPUT_SUMMARY.resolve()}")
    print(f"Audit:               {OUTPUT_AUDIT.resolve()}")
    print(f"Checks passed: {passed}/{len(checks)}")
    print(f"Checks failed: {failed}/{len(checks)}")
    print(f"Issues recorded: {len(issues)}")
    print(f"STATUS: {status}")

    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
