
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

PROXIMITY_CSV = PROCESSED_DIR / "phase2g1_candidate_road_proximity_register.csv"
ROAD_REVIEW_CSV = PROCESSED_DIR / "phase2g3_road_suitability_review_register.csv"

OUTPUT_CSV = PROCESSED_DIR / "phase2g4_candidate_road_access_review_register.csv"
OUTPUT_AUDIT = PROCESSED_DIR / "phase2g4_candidate_road_access_review_audit.txt"


CANDIDATE_ID_ALIASES = [
    "candidate_record_id", "candidate_id", "record_id", "candidate_uid", "review_id"
]

# Prefer a feature/source FID when the proximity register contains one.
NEAREST_FID_ALIASES = [
    "nearest_road_source_fid",
    "nearest_road_fid",
    "nearest_fid",
    "nearest_road_feature_id",
    "nearest_road_id",
    "road_fid",
    "nearest_source_fid",
]

NEAREST_OSM_ALIASES = [
    "nearest_road_source_osm_id",
    "nearest_road_osm_id",
    "nearest_osm_id",
    "nearest_osm",
    "road_osm_id",
]

NEAREST_CLASS_ALIASES = [
    "nearest_road_fclass",
    "nearest_road_class",
    "nearest_fclass",
    "nearest_class",
    "road_fclass",
]


def normalized_key(value: object) -> str:
    """Normalize CSV identifier values without turning missing values into IDs."""
    if pd.isna(value):
        return ""
    value = str(value).strip()
    if not value or value.lower() in {"nan", "none", "null", "<na>"}:
        return ""
    # CSV exports can represent integer identifiers as e.g. "123.0".
    if value.endswith(".0") and value[:-2].isdigit():
        value = value[:-2]
    return value


def find_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    by_lower = {str(col).strip().lower(): col for col in df.columns}
    for alias in aliases:
        if alias.lower() in by_lower:
            return by_lower[alias.lower()]
    return None


def safe_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def main() -> int:
    generated_utc = datetime.now(timezone.utc).isoformat()

    for path in [PROXIMITY_CSV, ROAD_REVIEW_CSV]:
        if not path.exists():
            print(f"ERROR: Required input file not found:\n{path}")
            return 1

    try:
        candidates = pd.read_csv(PROXIMITY_CSV, dtype="string", keep_default_na=False)
        roads = pd.read_csv(ROAD_REVIEW_CSV, dtype="string", keep_default_na=False)
    except Exception as exc:
        print(f"ERROR: Failed to read input CSV: {exc}")
        return 1

    if candidates.empty:
        print("ERROR: Phase 2G.1 candidate proximity register is empty.")
        return 1
    if roads.empty:
        print("ERROR: Phase 2G.3 road review register is empty.")
        return 1

    candidate_id_col = find_column(candidates, CANDIDATE_ID_ALIASES)
    distance_col = find_column(
        candidates,
        ["nearest_mapped_road_distance_m", "nearest_road_distance_m", "distance_to_nearest_road_m"],
    )
    band_col = find_column(candidates, ["road_proximity_band", "proximity_band"])

    if candidate_id_col is None:
        print("ERROR: Could not identify the candidate ID column.")
        print("Available candidate columns:")
        print(", ".join(candidates.columns))
        return 1

    if distance_col is None:
        print("ERROR: Could not identify the nearest-road distance column.")
        print("Available candidate columns:")
        print(", ".join(candidates.columns))
        return 1

    candidate_fid_col = find_column(candidates, NEAREST_FID_ALIASES)
    candidate_osm_col = find_column(candidates, NEAREST_OSM_ALIASES)
    candidate_class_col = find_column(candidates, NEAREST_CLASS_ALIASES)

    # Road register fields include original source columns and normalized copies.
    road_fid_col = find_column(roads, ["source_fid", "fid"])
    road_osm_col = find_column(roads, ["source_osm_id", "osm_id"])
    road_class_col = find_column(roads, ["review_road_class", "fclass"])

    # Prefer FID only if both registers contain a usable FID key; otherwise OSM ID.
    join_kind = ""
    candidate_key_col = None
    road_key_col = None

    if candidate_fid_col and road_fid_col:
        candidate_fid_values = candidates[candidate_fid_col].map(normalized_key)
        road_fid_values = roads[road_fid_col].map(normalized_key)
        if candidate_fid_values.ne("").any() and road_fid_values.ne("").any():
            join_kind = "FID"
            candidate_key_col = candidate_fid_col
            road_key_col = road_fid_col

    if not join_kind and candidate_osm_col and road_osm_col:
        candidate_osm_values = candidates[candidate_osm_col].map(normalized_key)
        road_osm_values = roads[road_osm_col].map(normalized_key)
        if candidate_osm_values.ne("").any() and road_osm_values.ne("").any():
            join_kind = "OSM_ID"
            candidate_key_col = candidate_osm_col
            road_key_col = road_osm_col

    # Build a lookup only from unique road keys. Duplicate keys are treated as
    # ambiguous, never resolved arbitrarily.
    lookup: dict[str, int] = {}
    ambiguous_keys: set[str] = set()
    road_key_to_use: pd.Series | None = None

    if join_kind and candidate_key_col and road_key_col:
        road_key_to_use = roads[road_key_col].map(normalized_key)
        counts = road_key_to_use[road_key_to_use.ne("")].value_counts()
        ambiguous_keys = set(counts[counts > 1].index)
        for idx, key in road_key_to_use.items():
            if key and key not in ambiguous_keys:
                lookup[key] = idx

    output = candidates.copy()
    output["phase2g4_road_join_method"] = join_kind if join_kind else "NO_STABLE_ID_AVAILABLE"
    output["phase2g4_road_match_status"] = ""
    output["phase2g4_matched_road_review_id"] = ""
    output["phase2g4_matched_source_fid"] = ""
    output["phase2g4_matched_source_osm_id"] = ""
    output["phase2g4_matched_road_class"] = ""
    output["phase2g4_vehicle_suitability_screen"] = ""
    output["phase2g4_road_review_priority"] = ""
    output["phase2g4_road_review_reason"] = ""

    if join_kind and candidate_key_col:
        for idx, value in candidates[candidate_key_col].items():
            key = normalized_key(value)
            if not key:
                output.at[idx, "phase2g4_road_match_status"] = "MISSING_NEAREST_ROAD_ID"
            elif key in ambiguous_keys:
                output.at[idx, "phase2g4_road_match_status"] = "AMBIGUOUS_ROAD_ID_NOT_JOINED"
            elif key not in lookup:
                output.at[idx, "phase2g4_road_match_status"] = "ROAD_ID_NOT_FOUND"
            else:
                road_idx = lookup[key]
                output.at[idx, "phase2g4_road_match_status"] = "MATCHED_BY_" + join_kind
                output.at[idx, "phase2g4_matched_road_review_id"] = safe_text(
                    roads.at[road_idx, "road_review_id"]
                    if "road_review_id" in roads.columns else ""
                )
                output.at[idx, "phase2g4_matched_source_fid"] = safe_text(
                    roads.at[road_idx, "source_fid"]
                    if "source_fid" in roads.columns else ""
                )
                output.at[idx, "phase2g4_matched_source_osm_id"] = safe_text(
                    roads.at[road_idx, "source_osm_id"]
                    if "source_osm_id" in roads.columns else ""
                )
                output.at[idx, "phase2g4_matched_road_class"] = safe_text(
                    roads.at[road_idx, road_class_col] if road_class_col else ""
                )
                for source_col, output_col in [
                    ("vehicle_suitability_screen", "phase2g4_vehicle_suitability_screen"),
                    ("review_priority", "phase2g4_road_review_priority"),
                    ("review_reason", "phase2g4_road_review_reason"),
                ]:
                    if source_col in roads.columns:
                        output.at[idx, output_col] = safe_text(roads.at[road_idx, source_col])
    else:
        # Do not fabricate a road join. If Phase 2G.1 already stores the nearest
        # road class, retain it as a provisional attribute only.
        for idx in candidates.index:
            output.at[idx, "phase2g4_road_match_status"] = "NO_STABLE_ROAD_ID_AVAILABLE"
            if candidate_class_col:
                output.at[idx, "phase2g4_matched_road_class"] = safe_text(
                    candidates.at[idx, candidate_class_col]
                )

    # A fallback class is descriptive only. It does not imply a verified join.
    if candidate_class_col:
        for idx in output.index:
            if not output.at[idx, "phase2g4_matched_road_class"]:
                output.at[idx, "phase2g4_matched_road_class"] = safe_text(
                    candidates.at[idx, candidate_class_col]
                )
                if output.at[idx, "phase2g4_road_match_status"] == "NO_STABLE_ROAD_ID_AVAILABLE":
                    output.at[idx, "phase2g4_road_match_status"] = (
                        "CLASS_FROM_PROXIMITY_REGISTER_ID_UNJOINED"
                    )

    # Conservative access-review conclusions. No automatic approvals.
    def access_priority(status: str, road_class: str, distance: float) -> tuple[str, str]:
        status = status.strip()
        road_class = road_class.strip().lower()

        if status.startswith("AMBIGUOUS") or status in {
            "ROAD_ID_NOT_FOUND", "MISSING_NEAREST_ROAD_ID",
            "NO_STABLE_ROAD_ID_AVAILABLE",
        }:
            return (
                "P1_JOIN_OR_IDENTITY_REVIEW",
                "Nearest-road identity could not be safely confirmed.",
            )

        if road_class in {"path", "footway", "steps", "pedestrian", "cycleway", "bridleway"}:
            return (
                "P1_POTENTIALLY_RESTRICTIVE_NEAREST_ROAD",
                "Nearest mapped road class may restrict vehicle access; field verification required.",
            )

        if road_class in {"track", "track_grade1", "track_grade2", "track_grade3",
                          "track_grade4", "track_grade5", "service", "unclassified"}:
            return (
                "P2_SURFACE_AND_VEHICLE_ACCESS_REVIEW",
                "Verify surface, width, seasonality, and vehicle access.",
            )

        if pd.notna(distance) and distance > 500:
            return (
                "P1_FAR_FROM_MAPPED_ROAD",
                "Candidate is more than 500 m from the mapped nearest road; inspect access route.",
            )

        if pd.notna(distance) and distance > 100:
            return (
                "P2_ACCESS_PATH_REVIEW",
                "Candidate is more than 100 m from the mapped nearest road; verify the connecting access path.",
            )

        return (
            "P3_FIELD_ACCESS_CONFIRMATION",
            "Road proximity does not confirm a usable entrance or vehicle access.",
        )

    distances = pd.to_numeric(output[distance_col], errors="coerce")
    priority_results = [
        access_priority(
            safe_text(output.at[idx, "phase2g4_road_match_status"]),
            safe_text(output.at[idx, "phase2g4_matched_road_class"]),
            float(distances.at[idx]) if pd.notna(distances.at[idx]) else float("nan"),
        )
        for idx in output.index
    ]
    output["phase2g4_access_review_priority"] = [x[0] for x in priority_results]
    output["phase2g4_access_review_reason"] = [x[1] for x in priority_results]

    # Manual review fields and conservative safety flags.
    output["physical_entrance_confirmed"] = "NO"
    output["physical_vehicle_access_confirmed"] = "NO"
    output["access_path_field_result"] = ""
    output["seasonal_passability_field_result"] = ""
    output["vehicle_restriction_field_result"] = ""
    output["field_verification_status"] = "PENDING"
    output["access_decision"] = "REVIEW_PENDING"
    output["review_evidence_reference"] = ""
    output["reviewer"] = ""
    output["review_date"] = ""
    output["review_notes"] = ""
    output["operational_facility_verified"] = "NO"
    output["routing_eligible"] = "NO"

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    checks: list[tuple[str, bool, str]] = []

    def add_check(name: str, passed: bool, detail: str) -> None:
        checks.append((name, bool(passed), detail))

    id_values = output[candidate_id_col].map(normalized_key)
    valid_distances = distances.notna() & distances.ge(0)
    match_counts = output["phase2g4_road_match_status"].value_counts().to_dict()

    add_check("input_candidates_present", len(output) > 0, f"rows={len(output)}")
    add_check(
        "candidate_ids_complete_and_unique",
        id_values.ne("").all() and id_values.is_unique,
        f"nonblank={int(id_values.ne('').sum())}; unique={id_values.nunique()}",
    )
    add_check(
        "nearest_road_distances_valid",
        valid_distances.all(),
        f"valid={int(valid_distances.sum())}; total={len(output)}",
    )
    add_check(
        "access_priorities_assigned",
        output["phase2g4_access_review_priority"].ne("").all(),
        f"assigned={int(output['phase2g4_access_review_priority'].ne('').sum())}",
    )
    add_check(
        "field_verification_pending",
        output["field_verification_status"].eq("PENDING").all(),
        f"non_pending={int((~output['field_verification_status'].eq('PENDING')).sum())}",
    )
    add_check(
        "access_decisions_pending",
        output["access_decision"].eq("REVIEW_PENDING").all(),
        f"non_pending={int((~output['access_decision'].eq('REVIEW_PENDING')).sum())}",
    )
    add_check(
        "no_physical_vehicle_access_confirmed",
        output["physical_vehicle_access_confirmed"].eq("NO").all(),
        f"confirmed_yes={int(output['physical_vehicle_access_confirmed'].eq('YES').sum())}",
    )
    add_check(
        "no_operational_facilities_verified",
        output["operational_facility_verified"].eq("NO").all(),
        f"verified_yes={int(output['operational_facility_verified'].eq('YES').sum())}",
    )
    add_check(
        "no_candidates_routing_eligible",
        output["routing_eligible"].eq("NO").all(),
        f"eligible_yes={int(output['routing_eligible'].eq('YES').sum())}",
    )
    add_check(
        "road_join_status_recorded",
        output["phase2g4_road_match_status"].ne("").all(),
        f"statuses={len(match_counts)}",
    )
    add_check(
        "output_paths_are_phase2g4",
        OUTPUT_CSV.name.startswith("phase2g4_")
        and OUTPUT_AUDIT.name.startswith("phase2g4_"),
        f"csv={OUTPUT_CSV.name}",
    )

    passed = sum(1 for _, ok, _ in checks if ok)
    failed = len(checks) - passed

    priority_counts = output["phase2g4_access_review_priority"].value_counts().sort_index()
    match_lines = [f"  {name}: {count}" for name, count in sorted(match_counts.items())]
    priority_lines = [f"  {name}: {count}" for name, count in priority_counts.items()]

    audit_lines = [
        "PNIS PHASE 2G.4 - CANDIDATE-TO-ROAD ACCESS REVIEW",
        "=" * 72,
        f"Generated UTC: {generated_utc}",
        f"Project root: {PROJECT_ROOT}",
        "",
        "INPUTS",
        "-" * 72,
        f"Candidate proximity register: {PROXIMITY_CSV}",
        f"Road suitability register: {ROAD_REVIEW_CSV}",
        f"Candidate ID column: {candidate_id_col}",
        f"Nearest-road distance column: {distance_col}",
        f"Proximity band column: {band_col or '(not found)'}",
        f"Candidate nearest-road FID column: {candidate_fid_col or '(not found)'}",
        f"Candidate nearest-road OSM ID column: {candidate_osm_col or '(not found)'}",
        f"Candidate nearest-road class column: {candidate_class_col or '(not found)'}",
        f"Road FID column: {road_fid_col or '(not found)'}",
        f"Road OSM ID column: {road_osm_col or '(not found)'}",
        f"Selected join method: {join_kind or 'none'}",
        "",
        "METHOD AND SAFETY LIMITS",
        "-" * 72,
        "The register links candidate proximity evidence to road review attributes",
        "only when a usable identifier is available. Ambiguous identifiers are",
        "not joined arbitrarily. A road class copied from the proximity register",
        "without an identifier match is explicitly marked as unjoined.",
        "Nearest-road distance does not prove a physical entrance, access path,",
        "legal access, vehicle passability, or operational facility status.",
        "All candidates remain unverified and routing-ineligible.",
        "",
        "SUMMARY",
        "-" * 72,
        f"Candidate records: {len(output)}",
        f"Unique candidate IDs: {id_values.nunique()}",
        f"Matched by stable ID: {int(output['phase2g4_road_match_status'].str.startswith('MATCHED_BY_').sum())}",
        f"Unresolved/ambiguous joins: {int((~output['phase2g4_road_match_status'].str.startswith('MATCHED_BY_')).sum())}",
        f"Median nearest mapped-road distance (m): {distances.median():.3f}",
        f"Maximum nearest mapped-road distance (m): {distances.max():.3f}",
        "",
        "ROAD JOIN STATUS COUNTS",
        "-" * 72,
        *match_lines,
        "",
        "ACCESS REVIEW PRIORITY COUNTS",
        "-" * 72,
        *priority_lines,
        "",
        "VALIDATION CHECKS",
        "-" * 72,
    ]
    audit_lines.extend(
        f"{'PASS' if ok else 'FAIL'} - {name}: {detail}"
        for name, ok, detail in checks
    )
    audit_lines.extend(
        [
            "",
            f"Checks passed: {passed}",
            f"Checks failed: {failed}",
            f"Overall status: {'PASS' if failed == 0 else 'FAIL'}",
            "",
            "OUTPUTS",
            "-" * 72,
            f"Access review register CSV: {OUTPUT_CSV}",
            f"Audit TXT: {OUTPUT_AUDIT}",
        ]
    )

    OUTPUT_AUDIT.write_text("\n".join(audit_lines) + "\n", encoding="utf-8")
    print("\n".join(audit_lines))

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
