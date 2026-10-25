
import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"

PRIORITY_FILE = PROCESSED / "phase2g10_fieldwork_priority_plan.csv"
RISK_FILE = PROCESSED / "phase2g5_candidate_access_risk_register_v2.csv"
PROGRESS_FILE = PROCESSED / "phase2g17_fieldwork_progress.csv"

OUT_CSV = PROCESSED / "phase2g18_risk_prioritized_worklist.csv"
OUT_SUMMARY = PROCESSED / "phase2g18_risk_prioritized_summary.csv"
OUT_AUDIT = PROCESSED / "phase2g18_risk_prioritized_audit.txt"

EXPECTED_ROWS = 255


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"Missing CSV headers: {path}")
        return reader.fieldnames, list(reader)


def require_columns(columns, required, filename):
    missing = [name for name in required if name not in columns]
    if missing:
        raise ValueError(
            f"{filename} is missing required columns: {missing}"
        )


def index_by_id(rows, id_column, filename):
    indexed = {}
    duplicates = []

    for row in rows:
        candidate_id = str(row.get(id_column, "")).strip()
        if not candidate_id:
            raise ValueError(
                f"{filename} contains a blank candidate_record_id."
            )
        if candidate_id in indexed:
            duplicates.append(candidate_id)
        else:
            indexed[candidate_id] = row

    if duplicates:
        raise ValueError(
            f"{filename} contains {len(duplicates)} duplicate candidate IDs. "
            "No outputs written."
        )

    return indexed


def clean(value):
    return str(value or "").strip()


def as_int(value, fallback=10**9):
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return fallback


def yes(value):
    return clean(value).upper() in {"YES", "Y", "TRUE", "1"}


def main():
    print("=" * 72)
    print("PNIS PHASE 2G.18 - RISK-PRIORITIZED FIELDWORK WORKLIST")
    print("=" * 72)

    priority_columns, priority_rows = read_csv(PRIORITY_FILE)
    risk_columns, risk_rows = read_csv(RISK_FILE)
    progress_columns, progress_rows = read_csv(PROGRESS_FILE)

    require_columns(
        priority_columns,
        [
            "candidate_record_id",
            "phase2g10_visit_priority_order",
            "phase2g5_access_risk_screen_v2",
            "phase2g5_risk_queue_order_v2",
            "longitude",
            "latitude",
            "recommended_review_action",
            "routing_eligible",
        ],
        PRIORITY_FILE.name,
    )
    require_columns(
        risk_columns,
        [
            "candidate_record_id",
            "phase2g5_access_risk_screen_v2",
            "phase2g5_access_risk_reason_v2",
            "phase2g5_risk_queue_order_v2",
            "phase2g5_recommended_action_v2",
            "routing_eligible",
        ],
        RISK_FILE.name,
    )
    require_columns(
        progress_columns,
        [
            "candidate_record_id",
            "phase2g17_visit_status",
            "fieldwork_readiness",
            "phase2g17_routing_approval_granted",
        ],
        PROGRESS_FILE.name,
    )

    priority_by_id = index_by_id(
        priority_rows, "candidate_record_id", PRIORITY_FILE.name
    )
    risk_by_id = index_by_id(
        risk_rows, "candidate_record_id", RISK_FILE.name
    )
    progress_by_id = index_by_id(
        progress_rows, "candidate_record_id", PROGRESS_FILE.name
    )

    priority_ids = set(priority_by_id)
    risk_ids = set(risk_by_id)
    progress_ids = set(progress_by_id)

    if (
        len(priority_rows) != EXPECTED_ROWS
        or len(risk_rows) != EXPECTED_ROWS
        or len(progress_rows) != EXPECTED_ROWS
    ):
        raise ValueError(
            "Input row counts do not all equal 255. "
            "No outputs written. Inspect the source files first."
        )

    if priority_ids != risk_ids or priority_ids != progress_ids:
        raise ValueError(
            "Candidate IDs do not match exactly across the three inputs. "
            "No outputs written. Investigate the unmatched IDs first."
        )

    # Compare the risk classification in the priority plan with the
    # corresponding authoritative Phase 2G.5 risk-register value.
    risk_mismatches = []
    for candidate_id in sorted(priority_ids):
        priority_risk = clean(
            priority_by_id[candidate_id].get(
                "phase2g5_access_risk_screen_v2"
            )
        ).upper()
        register_risk = clean(
            risk_by_id[candidate_id].get(
                "phase2g5_access_risk_screen_v2"
            )
        ).upper()

        if priority_risk != register_risk:
            risk_mismatches.append(
                (candidate_id, priority_risk, register_risk)
            )

    if risk_mismatches:
        preview = risk_mismatches[:10]
        raise ValueError(
            f"{len(risk_mismatches)} risk classifications differ between "
            "Phase 2G.10 and Phase 2G.5. No outputs written. "
            f"First mismatches: {preview}"
        )

    output_rows = []
    risk_counts = Counter()
    visit_counts = Counter()
    readiness_counts = Counter()
    routing_yes_count = 0
    approval_yes_count = 0

    for candidate_id, priority in priority_by_id.items():
        risk = risk_by_id[candidate_id]
        progress = progress_by_id[candidate_id]

        risk_class = clean(priority.get("phase2g5_access_risk_screen_v2"))
        visit_status = clean(progress.get("phase2g17_visit_status"))
        readiness = clean(progress.get("fieldwork_readiness"))

        risk_counts[risk_class or "BLANK"] += 1
        visit_counts[visit_status or "BLANK"] += 1
        readiness_counts[readiness or "BLANK"] += 1

        if yes(priority.get("routing_eligible")):
            routing_yes_count += 1
        if yes(progress.get("phase2g17_routing_approval_granted")):
            approval_yes_count += 1

        output_rows.append({
            "fieldwork_priority_order":
                priority.get("phase2g10_visit_priority_order", ""),
            "candidate_record_id": candidate_id,
            "osm_id": priority.get("osm_id", ""),
            "candidate_match_text": priority.get("candidate_match_text", ""),
            "review_group": priority.get("review_group", ""),
            "longitude": priority.get("longitude", ""),
            "latitude": priority.get("latitude", ""),
            "risk_class": risk_class,
            "risk_queue_order":
                priority.get("phase2g5_risk_queue_order_v2", ""),
            "risk_reason":
                risk.get("phase2g5_access_risk_reason_v2", ""),
            "nearest_mapped_road_distance_m":
                priority.get("nearest_mapped_road_distance_m", ""),
            "nearest_road_fclass": priority.get("nearest_road_fclass", ""),
            "review_priority": priority.get("review_priority", ""),
            "recommended_review_action":
                priority.get("recommended_review_action", ""),
            "phase2g5_recommended_action":
                risk.get("phase2g5_recommended_action_v2", ""),
            "fieldwork_visit_status": visit_status,
            "fieldwork_readiness": readiness,
            "manual_review_recorded":
                progress.get("phase2g17_manual_review_recorded", ""),
            "required_evidence_complete":
                progress.get("phase2g17_required_evidence_complete", ""),
            "source_routing_eligible":
                progress.get("source_routing_eligible", ""),
            "routing_eligible_in_priority_plan":
                priority.get("routing_eligible", ""),
            "routing_approval_granted": "NO",
            "worklist_note":
                "Priority order is for field verification; not routing approval.",
        })

    # Keep the existing Phase 2G.10 operational order.
    output_rows.sort(
        key=lambda row: (
            as_int(row["fieldwork_priority_order"]),
            as_int(row["risk_queue_order"]),
            row["candidate_record_id"],
        )
    )

    fields = list(output_rows[0].keys()) if output_rows else []

    # Prepare summary metrics.
    metrics = []

    def metric(name, value):
        metrics.append({"metric": name, "value": str(value)})

    metric("priority_plan_rows", len(priority_rows))
    metric("risk_register_rows", len(risk_rows))
    metric("progress_report_rows", len(progress_rows))
    metric("expected_candidate_rows", EXPECTED_ROWS)
    metric("unique_candidate_ids_in_each_source", len(priority_ids))
    metric("candidate_id_sets_match", priority_ids == risk_ids == progress_ids)
    metric("risk_classification_mismatches", len(risk_mismatches))
    metric("routing_eligible_in_priority_plan_yes", routing_yes_count)
    metric("routing_approval_granted_by_phase2g18", "NO")
    metric("output_candidate_rows", len(output_rows))

    for risk_class, count in sorted(risk_counts.items()):
        metric(f"risk_class_{risk_class}", count)

    for status, count in sorted(visit_counts.items()):
        metric(f"visit_status_{status}", count)

    for state, count in sorted(readiness_counts.items()):
        metric(f"readiness_{state or 'BLANK'}", count)

    # Outputs are written only after row counts, IDs, schemas, and risk
    # classifications have passed validation.
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows)

    with OUT_SUMMARY.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerows(metrics)

    with OUT_AUDIT.open("w", encoding="utf-8") as handle:
        handle.write(
            "PNIS PHASE 2G.18 - RISK-PRIORITIZED FIELDWORK WORKLIST\n"
            + "=" * 72 + "\n"
        )
        handle.write(
            f"Generated: {datetime.now().isoformat(timespec='seconds')}\n"
        )
        handle.write("Status: COMPLETED - INPUT VALIDATION PASSED\n\n")
        handle.write("INPUTS\n")
        handle.write(f"{PRIORITY_FILE}\n{RISK_FILE}\n{PROGRESS_FILE}\n\n")
        handle.write("VALIDATION\n")
        handle.write(f"Priority-plan rows: {len(priority_rows)}\n")
        handle.write(f"Risk-register rows: {len(risk_rows)}\n")
        handle.write(f"Progress-report rows: {len(progress_rows)}\n")
        handle.write(f"Unique candidate IDs: {len(priority_ids)}\n")
        handle.write("Candidate ID sets match: YES\n")
        handle.write("Risk classification mismatches: 0\n\n")
        handle.write("FIELDWORK STATUS\n")
        handle.write(f"Visited candidates: {visit_counts.get('VISITED', 0)}\n")
        handle.write(
            "Awaiting fieldwork: "
            f"{visit_counts.get('AWAITING_FIELDWORK', 0)}\n"
        )
        handle.write("\nRISK COUNTS\n")
        for risk_class, count in sorted(risk_counts.items()):
            handle.write(f"{risk_class}: {count}\n")
        handle.write("\nGUARDRAILS\n")
        handle.write("- Existing inputs were read only.\n")
        handle.write("- Existing workbook, audits, and routing graph were not edited.\n")
        handle.write("- Phase 2G.10 visit priority order was preserved.\n")
        handle.write("- Risk classes were cross-checked against Phase 2G.5.\n")
        handle.write("- This worklist does not certify facility identity or access.\n")
        handle.write("- Routing approval granted by Phase 2G.18: NO.\n\n")
        handle.write("OUTPUT FILES\n")
        handle.write(f"{OUT_CSV}\n{OUT_SUMMARY}\n{OUT_AUDIT}\n")

    print(f"Priority-plan rows: {len(priority_rows)}")
    print(f"Risk-register rows: {len(risk_rows)}")
    print(f"Progress-report rows: {len(progress_rows)}")
    print(f"Candidate IDs matched: {len(priority_ids)}")
    print(f"Risk classification mismatches: {len(risk_mismatches)}")
    print(f"Visited candidates: {visit_counts.get('VISITED', 0)}")
    print(
        "Awaiting fieldwork: "
        f"{visit_counts.get('AWAITING_FIELDWORK', 0)}"
    )
    print("\nRISK COUNTS")
    for risk_class, count in sorted(risk_counts.items()):
        print(f"{risk_class}: {count}")

    print("\nRouting approval granted: NO")
    print("\nOUTPUT FILES")
    print(OUT_CSV)
    print(OUT_SUMMARY)
    print(OUT_AUDIT)
    print("\nSTATUS: COMPLETED - INPUT VALIDATION PASSED")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        print("No routing approval was granted.", file=sys.stderr)
        sys.exit(1)
