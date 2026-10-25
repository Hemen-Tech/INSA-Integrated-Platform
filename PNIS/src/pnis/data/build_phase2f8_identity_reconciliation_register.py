from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

out = Path("data/processed")
source = out / "phase2f7_detailed_identity_review_register.csv"
if not source.exists():
    raise FileNotFoundError(f"Missing input: {source}")

df = pd.read_csv(source, low_memory=False)

required = [
    "candidate_record_id_a", "candidate_record_id_b",
    "osm_id_a", "osm_id_b", "name_a", "name_b",
    "fclass_a", "fclass_b", "source_layer_a", "source_layer_b",
    "longitude_a", "latitude_a", "longitude_b", "latitude_b",
    "distance_m",
]
missing = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"Missing required fields: {missing}")

def text(value):
    return "" if pd.isna(value) else str(value).strip()

def same_osm_id(a, b):
    a, b = text(a), text(b)
    return bool(a and b and a.lower() != "nan" and a == b)

def same_coordinates(row):
    try:
        return (
            float(row["longitude_a"]) == float(row["longitude_b"])
            and float(row["latitude_a"]) == float(row["latitude_b"])
        )
    except (TypeError, ValueError):
        return False

def classify(row):
    same_id = same_osm_id(row["osm_id_a"], row["osm_id_b"])
    same_layer = text(row["source_layer_a"]) == text(row["source_layer_b"])
    same_class = text(row["fclass_a"]) == text(row["fclass_b"])
    exact_coords = same_coordinates(row)

    if same_id and exact_coords and same_layer and not same_class:
        return (
            "SAME_OSM_OBJECT_SAME_LAYER_CLASS_CONFLICT",
            "P1",
            "Review source attributes and class mapping; do not count as two independent sites without evidence."
        )
    if same_id and exact_coords and not same_layer:
        return (
            "SAME_OSM_OBJECT_CROSS_LAYER_REPRESENTATION",
            "P1",
            "Inspect layer semantics; likely one OSM object represented in multiple extracts, not two independent sites."
        )
    if same_id:
        return (
            "SAME_OSM_ID_REQUIRES_RECONCILIATION",
            "P1",
            "Inspect ID and geometry provenance before deciding whether records represent one object."
        )
    if exact_coords:
        return (
            "DIFFERENT_OSM_IDS_EXACT_COORDINATE_OVERLAP",
            "P2",
            "Check feature identity; exact coordinates alone do not prove duplication."
        )
    if text(row["fclass_a"]) == "farmland" and text(row["fclass_b"]) == "farmland":
        return (
            "NEARBY_AGRICULTURAL_FEATURES",
            "P3",
            "May be adjacent fields; do not merge without evidence."
        )
    if {"village", "town"}.intersection({text(row["fclass_a"]), text(row["fclass_b"])}):
        return (
            "SETTLEMENT_AND_NEARBY_FEATURE",
            "P3",
            "Likely requires geographic context; settlement is not automatically a facility."
        )
    return (
        "NEARBY_FEATURES_IDENTITY_UNRESOLVED",
        "P4",
        "Manual review required; proximity is not proof of duplication."
    )

classified = df.apply(classify, axis=1, result_type="expand")
classified.columns = [
    "relationship_class",
    "reconciliation_priority",
    "recommended_review_action",
]
result = pd.concat([df.reset_index(drop=True), classified], axis=1)

result["review_decision"] = "NOT_REVIEWED"
result["identity_verified"] = "NO"
result["merge_or_delete_authorized"] = "NO"
result["operational_facility_verified"] = "NO"
result["routing_approved"] = "NO"
result["reviewer_notes"] = ""

result = result.sort_values(
    ["reconciliation_priority", "distance_m"],
    ascending=[True, True],
).reset_index(drop=True)

output = out / "phase2f8_candidate_identity_reconciliation_register.csv"
audit = out / "phase2f8_identity_reconciliation_audit.txt"
result.to_csv(output, index=False, encoding="utf-8-sig")

checks = {
    "all_53_pairs_retained": len(result) == len(df) == 53,
    "same_osm_id_pairs_identified": bool(
        result["relationship_class"].str.startswith("SAME_OSM").any()
    ),
    "all_decisions_pending": (result["review_decision"] == "NOT_REVIEWED").all(),
    "no_identity_auto_verified": (result["identity_verified"] == "NO").all(),
    "no_merge_or_delete_authorized": (result["merge_or_delete_authorized"] == "NO").all(),
    "no_routing_approved": (result["routing_approved"] == "NO").all(),
}

lines = [
    "PNIS PHASE 2F.8 - CANDIDATE IDENTITY RECONCILIATION AUDIT",
    "=" * 68,
    f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
    f"Input pairs: {len(df)}",
    f"Output pairs: {len(result)}",
    "",
    "RELATIONSHIP CLASS COUNTS",
]
lines.extend(result["relationship_class"].value_counts().to_string().splitlines())
lines += ["", "VALIDATION CHECKS"]
lines.extend(f"{'PASS' if ok else 'FAIL'} - {name}" for name, ok in checks.items())
lines += [
    "",
    "LIMITATIONS",
    "- This register proposes review actions; it does not resolve identities automatically.",
    "- Matching OSM IDs and coordinates support a same-object hypothesis, not operational verification.",
    "- No candidate was deleted, merged, verified, or approved for routing.",
    "",
    f"Overall status: {'PASS' if all(checks.values()) else 'FAIL'}",
]
audit.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("=" * 68)
print("PHASE 2F.8 - CANDIDATE IDENTITY RECONCILIATION")
print("=" * 68)
print(f"Pairs: {len(result)}")
print("\nRelationship classes:")
print(result["relationship_class"].value_counts().to_string())
print("\nValidation:")
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} - {name}")
print("\nOutputs:")
print(output.resolve())
print(audit.resolve())

if not all(checks.values()):
    raise SystemExit("Phase 2F.8 validation failed.")
print("\nPhase 2F.8 completed successfully.")
