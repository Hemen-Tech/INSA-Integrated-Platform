from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

out = Path("data/processed")
pairs_path = out / "phase2f6_nearby_candidate_review.csv"
queue_path = out / "phase2f6_manual_verification_queue.csv"

if not pairs_path.exists() or not queue_path.exists():
    raise FileNotFoundError("Required Phase 2F.6 output is missing.")

pairs = pd.read_csv(pairs_path, low_memory=False)
queue = pd.read_csv(queue_path, low_memory=False)

key = "candidate_record_id"
required = [key, "osm_id", "name", "fclass", "source_layer", "longitude", "latitude"]
missing = [c for c in required if c not in queue.columns]
if missing:
    raise ValueError(f"Queue is missing required fields: {missing}")

if queue[key].duplicated().any():
    raise ValueError("Candidate IDs in queue are not unique.")

lookup = queue.set_index(key, drop=False)

def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()

def detail(candidate_id, suffix):
    candidate_id = str(candidate_id)
    if candidate_id not in lookup.index:
        raise ValueError(f"Pair references unknown candidate ID: {candidate_id}")
    row = lookup.loc[candidate_id]
    return {
        f"candidate_record_id_{suffix}": candidate_id,
        f"osm_id_{suffix}": clean(row.get("osm_id")),
        f"name_{suffix}": clean(row.get("name")),
        f"fclass_{suffix}": clean(row.get("fclass")),
        f"source_layer_{suffix}": clean(row.get("source_layer")),
        f"longitude_{suffix}": row.get("longitude"),
        f"latitude_{suffix}": row.get("latitude"),
        f"review_group_{suffix}": clean(row.get("review_group")),
    }

records = []
for _, pair in pairs.iterrows():
    a = detail(pair["candidate_record_id_a"], "a")
    b = detail(pair["candidate_record_id_b"], "b")
    distance = float(pair["distance_m"])

    same_layer = a["source_layer_a"] == b["source_layer_b"]
    same_class = a["fclass_a"] == b["fclass_b"]
    exact = distance < 0.01

    if exact:
        priority = "P1_EXACT_COORDINATE_OVERLAP"
    elif distance < 25 and not same_layer:
        priority = "P1_VERY_CLOSE_CROSS_LAYER"
    elif distance < 50:
        priority = "P2_CLOSE_PAIR"
    elif not same_layer:
        priority = "P3_CROSS_LAYER_WITHIN_250M"
    else:
        priority = "P4_NEARBY_PAIR"

    records.append({
        **a,
        **b,
        "distance_m": round(distance, 2),
        "same_source_layer": "YES" if same_layer else "NO",
        "same_feature_class": "YES" if same_class else "NO",
        "review_priority": priority,
        "manual_identity_check": "REQUIRED",
        "review_decision": "NOT_REVIEWED",
        "merge_or_delete_authorized": "NO",
        "routing_approval": "NOT_APPROVED",
        "reviewer_notes": "",
    })

report = pd.DataFrame(records)
report["_priority_order"] = report["review_priority"].map({
    "P1_EXACT_COORDINATE_OVERLAP": 1,
    "P1_VERY_CLOSE_CROSS_LAYER": 2,
    "P2_CLOSE_PAIR": 3,
    "P3_CROSS_LAYER_WITHIN_250M": 4,
    "P4_NEARBY_PAIR": 5,
}).fillna(9)

report = report.sort_values(
    ["_priority_order", "distance_m", "candidate_record_id_a", "candidate_record_id_b"]
).drop(columns="_priority_order")

report_path = out / "phase2f7_detailed_identity_review_register.csv"
audit_path = out / "phase2f7_identity_review_audit.txt"
report.to_csv(report_path, index=False, encoding="utf-8-sig")

checks = {
    "pair_count_matches_phase2f6": len(report) == len(pairs),
    "pair_records_enriched_from_candidate_queue": (
        set(report["candidate_record_id_a"]).union(
            set(report["candidate_record_id_b"])
        ).issubset(set(queue[key]))
    ),
    "no_pair_auto_merged_or_deleted": (
        report["merge_or_delete_authorized"] == "NO"
    ).all(),
    "no_pair_routing_approved": (
        report["routing_approval"] == "NOT_APPROVED"
    ).all(),
    "all_pairs_pending_manual_review": (
        report["review_decision"] == "NOT_REVIEWED"
    ).all(),
}

lines = [
    "PNIS PHASE 2F.7 - DETAILED IDENTITY REVIEW AUDIT",
    "=" * 66,
    f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
    f"Phase 2F.6 pairs: {len(pairs)}",
    f"Detailed review rows: {len(report)}",
    "",
    "PRIORITY COUNTS",
]
lines.extend(report["review_priority"].value_counts().sort_index().to_string().splitlines())
lines += [
    "",
    "IMPORTANT LIMITATIONS",
    "- Exact or nearby coordinates do not prove duplicate identity.",
    "- Close records may represent distinct adjacent facilities.",
    "- No records were merged, deleted, or approved for routing.",
    "",
    "VALIDATION CHECKS",
]
lines.extend(f"{'PASS' if ok else 'FAIL'} - {name}" for name, ok in checks.items())
lines += [
    "",
    f"Overall status: {'PASS' if all(checks.values()) else 'FAIL'}",
]
audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("=" * 66)
print("PHASE 2F.7 - DETAILED IDENTITY REVIEW REGISTER")
print("=" * 66)
print(f"Nearby pairs: {len(report)}")
print("\nPriority counts:")
print(report["review_priority"].value_counts().sort_index().to_string())
print("\nValidation:")
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} - {name}")
print("\nOutputs:")
print(report_path.resolve())
print(audit_path.resolve())

if not all(checks.values()):
    raise SystemExit("Phase 2F.7 validation failed.")
