from pathlib import Path
from math import radians, sin, cos, asin, sqrt
from datetime import datetime, timezone
import pandas as pd

ROOT = Path.cwd()
INPUT = ROOT / "data" / "processed" / "phase2f5_verification_evidence_register.csv"
OUT = ROOT / "data" / "processed"

QUEUE = OUT / "phase2f6_manual_verification_queue.csv"
NEARBY = OUT / "phase2f6_nearby_candidate_review.csv"
PROTOCOL = OUT / "phase2f6_verification_protocol.txt"
AUDIT = OUT / "phase2f6_verification_protocol_audit.txt"

if not INPUT.exists():
    raise FileNotFoundError(f"Required input not found: {INPUT}")

df = pd.read_csv(INPUT, low_memory=False)

required = [
    "candidate_record_id", "longitude", "latitude",
    "review_group", "review_priority", "source_layer", "fclass",
    "verification_status", "verification_decision",
]
missing = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"Input is missing required columns: {missing}")

if df["candidate_record_id"].isna().any():
    raise ValueError("Candidate IDs contain missing values.")
if df["candidate_record_id"].duplicated().any():
    raise ValueError("Candidate IDs are not unique.")

lat = pd.to_numeric(df["latitude"], errors="coerce")
lon = pd.to_numeric(df["longitude"], errors="coerce")
valid = (
    lat.notna() & lon.notna()
    & lat.between(-90, 90) & lon.between(-180, 180)
)
if not valid.all():
    raise ValueError(f"Invalid coordinates detected: {(~valid).sum()}")

# These are proposed review-order rules, not verified facility classifications.
group_order = {
    "MARKET_CANDIDATE": 1,
    "RETAIL_OR_FOOD_MARKET_CANDIDATE": 1,
    "INDUSTRIAL_SITE_CANDIDATE": 2,
    "AGRICULTURAL_LAND_ONLY": 3,
    "OTHER_POI_REVIEW": 4,
    "BUILDING_CANDIDATE": 5,
    "SETTLEMENT_REFERENCE": 6,
    "OTHER_LANDUSE_REVIEW": 7,
}

queue = df.copy()
queue["review_batch_order"] = (
    queue["review_group"].map(group_order).fillna(8).astype(int)
)
queue["review_batch"] = queue["review_batch_order"].map({
    1: "BATCH_1_MARKETS_AND_RETAIL",
    2: "BATCH_2_INDUSTRIAL_SITES",
    3: "BATCH_3_AGRICULTURAL_CANDIDATES",
    4: "BATCH_4_OTHER_POIS",
    5: "BATCH_5_BUILDINGS",
    6: "BATCH_6_SETTLEMENT_REFERENCES",
    7: "BATCH_7_OTHER_LANDUSE",
}).fillna("BATCH_8_OTHER_REVIEW")

queue["verification_sequence"] = range(1, len(queue) + 1)
queue["proximity_review_required"] = "NO"
queue["proximity_review_note"] = "No nearby candidate flagged within 250 m"
queue["recommended_evidence"] = queue["review_group"].map({
    "MARKET_CANDIDATE":
        "Confirm site exists; market function; perishables handled; operating status; vehicle access",
    "RETAIL_OR_FOOD_MARKET_CANDIDATE":
        "Confirm business/site; food or perishable activity; operating status; loading and vehicle access",
    "INDUSTRIAL_SITE_CANDIDATE":
        "Confirm actual business and function; processing/storage relevance; operating status; vehicle access",
    "AGRICULTURAL_LAND_ONLY":
        "Confirm actual farm or farmyard; production activity; responsible contact; collection access",
    "OTHER_POI_REVIEW":
        "Confirm site identity and function; relevance to perishable logistics; operating status; access",
    "BUILDING_CANDIDATE":
        "Confirm building use and whether it is an operational logistics facility; verify access",
    "SETTLEMENT_REFERENCE":
        "Confirm settlement name/location; retain as geographic reference unless a specific facility is verified",
    "OTHER_LANDUSE_REVIEW":
        "Confirm land-use meaning and whether a distinct operational facility exists",
}).fillna("Confirm identity, actual function, operating status, and vehicle access")

# Haversine distance: flag all pairs at or below 250 m.
# Proximity does not establish duplication or shared identity.
def distance_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371008.8 * 2 * asin(sqrt(min(1.0, a)))

nearby_rows = []
coords = list(zip(lat.tolist(), lon.tolist()))
ids = df["candidate_record_id"].astype(str).tolist()

for i in range(len(df)):
    for j in range(i + 1, len(df)):
        d = distance_m(coords[i][0], coords[i][1], coords[j][0], coords[j][1])
        if d <= 250:
            nearby_rows.append({
                "candidate_record_id_a": ids[i],
                "candidate_record_id_b": ids[j],
                "distance_m": round(d, 2),
                "name_a": str(df.iloc[i].get("name", "")),
                "name_b": str(df.iloc[j].get("name", "")),
                "fclass_a": str(df.iloc[i]["fclass"]),
                "fclass_b": str(df.iloc[j]["fclass"]),
                "source_layer_a": str(df.iloc[i]["source_layer"]),
                "source_layer_b": str(df.iloc[j]["source_layer"]),
                "manual_review_required": "YES",
                "decision": "NOT_REVIEWED",
                "note": "Proximity only; do not automatically merge or delete",
            })

nearby = pd.DataFrame(nearby_rows)
if not nearby.empty:
    nearby["distance_m"] = pd.to_numeric(nearby["distance_m"])
    flagged_ids = set(nearby["candidate_record_id_a"]) | set(
        nearby["candidate_record_id_b"]
    )
    mask = queue["candidate_record_id"].astype(str).isin(flagged_ids)
    queue.loc[mask, "proximity_review_required"] = "YES"
    queue.loc[mask, "proximity_review_note"] = (
        "One or more candidate records are within 250 m; inspect identity and site distinction"
    )
else:
    nearby = pd.DataFrame(columns=[
        "candidate_record_id_a", "candidate_record_id_b", "distance_m",
        "name_a", "name_b", "fclass_a", "fclass_b",
        "source_layer_a", "source_layer_b",
        "manual_review_required", "decision", "note",
    ])

queue = queue.sort_values(
    ["review_batch_order", "review_priority", "candidate_record_id"],
    ascending=[True, True, True],
).reset_index(drop=True)
queue["verification_sequence"] = range(1, len(queue) + 1)

# Preserve all original columns and add only review-planning fields.
queue.to_csv(QUEUE, index=False, encoding="utf-8-sig")
nearby.to_csv(NEARBY, index=False, encoding="utf-8-sig")

protocol = f"""PNIS PHASE 2F.6 - MANUAL VERIFICATION PROTOCOL
Generated UTC: {datetime.now(timezone.utc).isoformat()}

PURPOSE
Create a review plan for candidate sites inside the working Sidama boundary.
This is a planning step, not a verified facility inventory.

REVIEW ORDER
1. Markets and retail/food-market candidates.
2. Industrial-site candidates.
3. Agricultural-land/farmyard candidates.
4. Other POIs.
5. Building candidates.
6. Settlement references.
7. Other land-use candidates.

EVIDENCE TO COLLECT FOR EACH RELEVANT CANDIDATE
- Candidate ID and OSM reference used to identify the mapped feature.
- Date checked and reviewer identity/initials.
- Evidence source and a reference to the evidence (field observation, authorized contact,
  official record, or dated source).
- Confirmation that the site exists and its actual function.
- Operating status, including unknown or temporarily closed where applicable.
- Coordinate/location check and any corrected coordinates with a recorded source.
- Vehicle access observations: approach road, access point, vehicle limitations, and
  unresolved access questions.
- Final review decision and reason.

DECISION SAFEGUARDS
- Do not mark a candidate verified without recorded supporting evidence.
- Do not infer a warehouse, collection point, farm, market, or processing function
  from an OSM class alone.
- A settlement reference is not an operational facility by default.
- Proximity within 250 m is a manual review flag only; it does not prove duplication.
- Do not automatically merge or delete nearby records.
- Do not approve vehicle routing from this phase alone.
- Unknown status must remain unknown; do not substitute assumptions for evidence.

CURRENT STATE
Candidates in input: {len(df)}
Nearby candidate pairs flagged within 250 m: {len(nearby)}
Candidates currently marked UNVERIFIED: {(df["verification_status"].astype(str) == "UNVERIFIED").sum()}
Candidates currently marked REVIEW_PENDING: {(df["verification_decision"].astype(str) == "REVIEW_PENDING").sum()}

OUTPUTS
- {QUEUE.name}: prioritized manual review queue.
- {NEARBY.name}: nearby candidate pairs for manual inspection.
- {PROTOCOL.name}: this protocol.
- {AUDIT.name}: validation results.
"""
PROTOCOL.write_text(protocol, encoding="utf-8")

checks = {
    "input_rows_255": len(df) == 255,
    "candidate_ids_unique": df["candidate_record_id"].is_unique,
    "coordinates_valid": bool(valid.all()),
    "queue_rows_match_input": len(queue) == len(df),
    "queue_ids_match_input": set(queue["candidate_record_id"]) == set(df["candidate_record_id"]),
    "queue_ids_unique": queue["candidate_record_id"].is_unique,
    "nearby_pairs_have_distances": bool(
        nearby.empty or (pd.to_numeric(nearby["distance_m"], errors="coerce").notna().all()
                         and (pd.to_numeric(nearby["distance_m"]) <= 250).all())
    ),
    "no_candidate_auto_verified": bool(
        (queue["verification_status"].astype(str) == "UNVERIFIED").all()
    ),
    "all_decisions_still_pending": bool(
        (queue["verification_decision"].astype(str) == "REVIEW_PENDING").all()
    ),
}

audit_lines = [
    "PNIS PHASE 2F.6 - VERIFICATION PROTOCOL AUDIT",
    "=" * 68,
    f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
    f"Input: {INPUT}",
    f"Queue: {QUEUE}",
    f"Nearby review register: {NEARBY}",
    f"Protocol: {PROTOCOL}",
    "",
    f"Input rows: {len(df)}",
    f"Queue rows: {len(queue)}",
    f"Nearby pairs within 250 m: {len(nearby)}",
    f"Candidates flagged for proximity review: {(queue['proximity_review_required'] == 'YES').sum()}",
    "",
    "REVIEW BATCH COUNTS",
]
audit_lines.extend(queue["review_batch"].value_counts().sort_index().to_string().splitlines())
audit_lines += ["", "VALIDATION CHECKS"]
audit_lines.extend(f"{'PASS' if passed else 'FAIL'} - {name}" for name, passed in checks.items())
audit_lines += [
    "",
    "LIMITATIONS",
    "- Proximity flags do not establish duplicate identity.",
    "- Candidate function, operation, and vehicle access remain unverified.",
    "- No routing eligibility is granted by this script.",
    "",
    f"Overall status: {'PASS' if all(checks.values()) else 'FAIL'}",
]
AUDIT.write_text("\n".join(audit_lines) + "\n", encoding="utf-8")

print("=" * 68)
print("PHASE 2F.6 - VERIFICATION PROTOCOL BUILD")
print("=" * 68)
print(f"Input candidates: {len(df)}")
print(f"Queue rows: {len(queue)}")
print(f"Nearby pairs within 250 m: {len(nearby)}")
print(f"Candidates flagged for proximity review: {(queue['proximity_review_required'] == 'YES').sum()}")
print("\nReview batches:")
print(queue["review_batch"].value_counts().sort_index().to_string())
print("\nValidation:")
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} - {name}")
print("\nOutputs:")
for p in [QUEUE, NEARBY, PROTOCOL, AUDIT]:
    print(f"{p} [{p.stat().st_size:,} bytes]")
if not all(checks.values()):
    raise SystemExit("PHASE 2F.6 FAILED: inspect audit and correct before proceeding.")
print("\nPHASE 2F.6 completed successfully.")
