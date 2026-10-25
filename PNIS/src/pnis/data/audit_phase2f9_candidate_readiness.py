from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "processed"

FILES = {
    "evidence": DATA / "phase2f5_verification_evidence_register.csv",
    "queue": DATA / "phase2f6_manual_verification_queue.csv",
    "nearby": DATA / "phase2f6_nearby_candidate_review.csv",
    "identity": DATA / "phase2f8_candidate_identity_reconciliation_register.csv",
    "spatial": DATA / "phase2f2_osm_facility_candidates_spatially_classified_v1.csv",
}

SUMMARY = DATA / "phase2f9_candidate_readiness_summary.csv"
AUDIT = DATA / "phase2f9_candidate_readiness_audit.txt"

def load_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    return pd.read_csv(path, dtype={"candidate_record_id": str})

def ids(df, column="candidate_record_id"):
    if column not in df.columns:
        raise KeyError(f"Required column '{column}' missing. Available columns: {df.columns.tolist()}")
    return set(df[column].dropna().astype(str).str.strip())

def truthy_no(series):
    return series.astype(str).str.strip().str.upper().isin(
        ["NO", "FALSE", "0", "NOT_APPROVED", "NOT APPROVED", "PENDING"]
    )

evidence = load_csv(FILES["evidence"])
queue = load_csv(FILES["queue"])
nearby = load_csv(FILES["nearby"])
identity = load_csv(FILES["identity"])
spatial = load_csv(FILES["spatial"])

required_spatial = {"candidate_record_id", "spatial_classification"}
missing = required_spatial - set(spatial.columns)
if missing:
    raise KeyError(f"Spatial file missing required columns: {sorted(missing)}")

evidence_ids = ids(evidence)
queue_ids = ids(queue)
spatial_ids = ids(spatial)

inside_mask = (
    spatial["spatial_classification"]
    .astype(str).str.strip().str.upper().eq("INSIDE_SIDAMA")
)
inside = spatial.loc[inside_mask].copy()
inside_ids = ids(inside)

def find_column(df, candidates):
    lookup = {c.strip().lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None

# Count unique candidate IDs participating in nearby pairs.
nearby_candidate_count = 0
nearby_id_columns = [
    c for c in nearby.columns
    if "candidate_record_id" in c.lower()
]
if nearby_id_columns:
    nearby_candidate_ids = set()
    for col in nearby_id_columns:
        nearby_candidate_ids.update(ids(nearby, col))
    nearby_candidate_count = len(nearby_candidate_ids)

same_osm_pairs = 0
osm_col = find_column(identity, ["same_osm_id", "osm_id_match", "same_osm_object"])
if osm_col:
    same_osm_pairs = int(
        identity[osm_col].astype(str).str.strip().str.upper().isin(
            ["TRUE", "YES", "1"]
        ).sum()
    )
else:
    # Derive same-OSM-ID pairs from explicit left/right OSM ID columns if present.
    left_osm = find_column(identity, ["osm_id_a", "osm_id_1", "left_osm_id", "osm_id_left"])
    right_osm = find_column(identity, ["osm_id_b", "osm_id_2", "right_osm_id", "osm_id_right"])
    if left_osm and right_osm:
        same_osm_pairs = int(
            (
                identity[left_osm].notna()
                & identity[right_osm].notna()
                & identity[left_osm].astype(str).eq(identity[right_osm].astype(str))
            ).sum()
        )

checks = []

def add_check(name, passed, detail):
    checks.append({
        "check": name,
        "status": "PASS" if passed else "FAIL",
        "detail": str(detail),
    })

add_check("evidence_rows_255", len(evidence) == 255, f"rows={len(evidence)}")
add_check("queue_rows_match_evidence", len(queue) == len(evidence), f"queue={len(queue)}, evidence={len(evidence)}")
add_check("evidence_ids_unique", len(evidence_ids) == len(evidence), f"unique={len(evidence_ids)}")
add_check("queue_ids_unique", len(queue_ids) == len(queue), f"unique={len(queue_ids)}")
add_check("evidence_queue_ids_match", evidence_ids == queue_ids,
          f"evidence-only={len(evidence_ids-queue_ids)}, queue-only={len(queue_ids-evidence_ids)}")

# Critical correction: compare evidence IDs to the inside-Sidama subset,
# not to all 497 spatial candidates.
add_check(
    "spatial_ids_match_evidence",
    inside_ids == evidence_ids,
    f"inside={len(inside_ids)}, evidence={len(evidence_ids)}, "
    f"evidence-missing-inside={len(evidence_ids-inside_ids)}, "
    f"inside-missing-evidence={len(inside_ids-evidence_ids)}, "
    f"outside_or_boundary_in_evidence={len(evidence_ids-inside_ids)}"
)

add_check("nearby_pair_count_53", len(nearby) == 53, f"pairs={len(nearby)}")
add_check("identity_pair_count_matches_nearby", len(identity) == len(nearby),
          f"identity_pairs={len(identity)}, nearby_pairs={len(nearby)}")

# Preserve the conservative decision rules by checking available decision fields.
verification_col = find_column(identity, ["identity_verified"])
if verification_col:
    identity_pending = truthy_no(identity[verification_col]).all()
    add_check("identity_pairs_not_auto_verified", identity_pending,
              f"column={verification_col}")
else:
    add_check("identity_pairs_not_auto_verified", False,
              "identity_verified column not found; inspect identity-register schema")

merge_col = find_column(identity, ["merge_authorized", "merge_or_delete_authorized"])
delete_col = find_column(identity, ["delete_authorized", "merge_or_delete_authorized"])
routing_col = find_column(identity, ["routing_approved", "routing_eligibility_approved"])

if merge_col:
    no_merge = truthy_no(identity[merge_col]).all()
    add_check("no_merge_authorized", no_merge, f"column={merge_col}")
else:
    add_check("no_merge_authorized", False, "No recognized merge-authorization column found")

if delete_col:
    no_delete = truthy_no(identity[delete_col]).all()
    add_check("no_delete_authorized", no_delete, f"column={delete_col}")
else:
    add_check("no_delete_authorized", False, "No recognized delete-authorization column found")

if routing_col:
    no_routing = truthy_no(identity[routing_col]).all()
    add_check("no_identity_pair_routing_approved", no_routing, f"column={routing_col}")
else:
    add_check("no_identity_pair_routing_approved", False,
              "No recognized routing-approval column found")

status_col = find_column(evidence, ["verification_status", "review_record_status"])
if status_col:
    pending = evidence[status_col].astype(str).str.strip().str.upper().isin(
        ["UNVERIFIED", "NOT_REVIEWED", "REVIEW_PENDING", "PENDING"]
    ).all()
    add_check("all_candidate_verification_pending", pending, f"column={status_col}")
else:
    add_check("all_candidate_verification_pending", False,
              "No recognized verification-status column found")

add_check("same_osm_id_pairs_detected", same_osm_pairs >= 1,
          f"same_osm_id_pairs={same_osm_pairs}")

summary_rows = [
    ("Phase 2F.5 evidence register rows", len(evidence)),
    ("Phase 2F.6 queue rows", len(queue)),
    ("Phase 2F.6 nearby pairs", len(nearby)),
    ("Phase 2F.7/2F.8 identity pairs", len(identity)),
    ("Spatial candidates total", len(spatial)),
    ("Spatial candidates inside Sidama", len(inside)),
    ("Spatial candidates outside Sidama", int(
        spatial["spatial_classification"].astype(str).str.strip().str.upper()
        .eq("OUTSIDE_SIDAMA").sum()
    )),
    ("Spatial candidates boundary review", int(
        spatial["spatial_classification"].astype(str).str.strip().str.upper()
        .eq("BOUNDARY_REVIEW").sum()
    )),
    ("Candidates flagged for proximity review", nearby_candidate_count),
    ("Candidates still unverified", len(evidence)),
    ("Same-OSM-ID pairs in identity register", same_osm_pairs),
]
pd.DataFrame(summary_rows, columns=["metric", "value"]).to_csv(SUMMARY, index=False)

passed = sum(c["status"] == "PASS" for c in checks)
failed = sum(c["status"] == "FAIL" for c in checks)
overall = "PASS" if failed == 0 else "FAIL"

lines = [
    "PNIS PHASE 2F.9 - CANDIDATE READINESS AUDIT",
    "=" * 68,
    f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
    "",
    "CORRECTED SPATIAL VALIDATION",
    "- Compare evidence-register IDs against only INSIDE_SIDAMA spatial IDs.",
    "- Do not compare the 255-row evidence register against all 497 spatial candidates.",
    "",
    "SUMMARY",
]
lines.extend(f"- {name}: {value}" for name, value in summary_rows)
lines.extend(["", "VALIDATION CHECKS"])
lines.extend(
    f"{c['status']} - {c['check']}: {c['detail']}" for c in checks
)
lines.extend([
    "",
    f"Checks passed: {passed}",
    f"Checks failed: {failed}",
    f"Overall status: {overall}",
    "",
    "SAFETY NOTES",
    "- Candidate records remain unverified pending evidence collection.",
    "- Nearby-pair review does not prove duplicate identity.",
    "- Matching OSM IDs do not verify operational facility function.",
    "- No candidate is approved for operational routing by this audit.",
    "",
])
AUDIT.write_text("\n".join(lines), encoding="utf-8")

print("\n".join(lines))
print(f"\nSummary CSV: {SUMMARY}")
print(f"Audit TXT:   {AUDIT}")
