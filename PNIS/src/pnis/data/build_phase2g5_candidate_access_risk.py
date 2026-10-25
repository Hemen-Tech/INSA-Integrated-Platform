from pathlib import Path
from datetime import datetime, timezone
import sys
import pandas as pd

ROOT = Path.cwd()
DATA = ROOT / "data" / "processed"

INPUT_G2 = DATA / "phase2g2_access_review_register.csv"
INPUT_G4 = DATA / "phase2g4_candidate_road_access_review_register_v2.csv"

OUTPUT_CSV = DATA / "phase2g5_candidate_access_risk_register.csv"
OUTPUT_AUDIT = DATA / "phase2g5_candidate_access_risk_audit.txt"

def stop(message):
    print(f"ERROR: {message}")
    sys.exit(1)

def find_column(df, candidates, description):
    for col in candidates:
        if col in df.columns:
            return col
    stop(
        f"Cannot identify {description}. "
        f"Expected one of {candidates}. "
        f"Available columns: {list(df.columns)}"
    )

def priority_rank(value):
    if pd.isna(value):
        return None
    value = str(value).strip().upper()
    if value.startswith("P1"):
        return 1
    if value.startswith("P2"):
        return 2
    if value.startswith("P3"):
        return 3
    if value.startswith("P4"):
        return 4
    return None

def priority_label(rank):
    return {1: "P1", 2: "P2", 3: "P3", 4: "P4"}.get(rank, "P4")

def main():
    for path in (INPUT_G2, INPUT_G4):
        if not path.exists():
            stop(f"Required input file not found: {path}")

    g2 = pd.read_csv(INPUT_G2, low_memory=False)
    g4 = pd.read_csv(INPUT_G4, low_memory=False)

    key2 = find_column(
        g2,
        ["candidate_record_id", "candidate_id"],
        "Phase 2G.2 candidate ID"
    )
    key4 = find_column(
        g4,
        ["candidate_record_id", "candidate_id"],
        "Phase 2G.4 v2 candidate ID"
    )
    distance_col = find_column(
        g4,
        [
            "recalculated_nearest_road_distance_m",
            "nearest_mapped_road_distance_m"
        ],
        "nearest-road distance"
    )
    class_col = find_column(
        g4,
        ["nearest_road_fclass", "nearest_road_class"],
        "nearest-road class"
    )

    if g4[key4].isna().any() or g4[key4].duplicated().any():
        stop("Phase 2G.4 v2 candidate IDs are missing or duplicated.")
    if g2[key2].isna().any() or g2[key2].duplicated().any():
        stop("Phase 2G.2 candidate IDs are missing or duplicated.")

    g4["_join_id"] = g4[key4].astype(str).str.strip()
    g2["_join_id"] = g2[key2].astype(str).str.strip()

    if set(g4["_join_id"]) != set(g2["_join_id"]):
        missing_g2 = sorted(set(g4["_join_id"]) - set(g2["_join_id"]))
        missing_g4 = sorted(set(g2["_join_id"]) - set(g4["_join_id"]))
        stop(
            "Candidate ID sets differ between Phase 2G.2 and Phase 2G.4 v2. "
            f"Missing from G2: {missing_g2[:10]}; "
            f"missing from G4: {missing_g4[:10]}"
        )

    priority_candidates = [
        c for c in g2.columns
        if "priority" in c.lower()
        and c not in ("_join_id", key2)
    ]
    g2_priority_col = priority_candidates[0] if priority_candidates else None

    g2_keep = ["_join_id"]
    if g2_priority_col:
        g2_keep.append(g2_priority_col)

    merged = g4.merge(
        g2[g2_keep],
        on="_join_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_phase2g2")
    )

    if len(merged) != len(g4):
        stop("Merge changed the Phase 2G.4 v2 row count.")

    if g2_priority_col:
        merged = merged.rename(
            columns={g2_priority_col: "phase2g2_access_review_priority"}
        )
        # If a column of that name already existed in G4, pandas may have
        # retained a suffix; resolve it explicitly.
        if "phase2g2_access_review_priority" not in merged.columns:
            possible = [
                c for c in merged.columns
                if c.startswith("phase2g2_access_review_priority")
            ]
            if possible:
                merged = merged.rename(
                    columns={possible[0]: "phase2g2_access_review_priority"}
                )
    else:
        merged["phase2g2_access_review_priority"] = "NOT_AVAILABLE"

    distance = pd.to_numeric(merged[distance_col], errors="coerce")
    road_class = (
        merged[class_col].fillna("unknown").astype(str).str.strip().str.lower()
    )

    if distance.isna().any() or (distance < 0).any():
        stop("Nearest-road distances contain missing or negative values.")

    restrictive_classes = {
        "track", "path", "footway", "pedestrian", "steps", "cycleway"
    }
    uncertain_classes = {"unknown", "", "unclassified", "service"}

    merged["access_risk_screen"] = "STANDARD_REVIEW"
    merged["access_risk_reason"] = "Mapped-road proximity; physical access unverified"
    merged["phase2g5_distance_band"] = pd.cut(
        distance,
        bins=[-0.001, 25, 50, 100, 250, 500, float("inf")],
        labels=["0-25m", "25-50m", "50-100m", "100-250m", "250-500m", ">500m"],
        right=True
    ).astype(str)

    very_far = distance > 500
    far = (distance > 250) & ~very_far
    restrictive = road_class.isin(restrictive_classes)
    uncertain = road_class.isin(uncertain_classes)

    merged.loc[far, "access_risk_screen"] = "ELEVATED_REVIEW"
    merged.loc[far, "access_risk_reason"] = "Nearest mapped road is more than 250 m away"

    merged.loc[restrictive, "access_risk_screen"] = "HIGH_REVIEW"
    merged.loc[restrictive, "access_risk_reason"] = (
        "Nearest road class may be unsuitable for collection/delivery vehicles"
    )

    merged.loc[very_far, "access_risk_screen"] = "HIGH_REVIEW"
    merged.loc[very_far, "access_risk_reason"] = (
        "Nearest mapped road is more than 500 m away"
    )

    both = very_far & restrictive
    merged.loc[both, "access_risk_reason"] = (
        "More than 500 m from mapped road; nearest road class also requires scrutiny"
    )

    # Combine the new screen with the existing G2 priority.
    # Lower rank number means higher review urgency.
    screen_rank = merged["access_risk_screen"].map({
        "HIGH_REVIEW": 1,
        "ELEVATED_REVIEW": 2,
        "STANDARD_REVIEW": 4
    }).astype(int)

    if g2_priority_col:
        g2_rank = merged["phase2g2_access_review_priority"].map(priority_rank)
    else:
        g2_rank = pd.Series([None] * len(merged), index=merged.index)

    combined_rank = [
        min([x for x in (a, b) if x is not None])
        for a, b in zip(
            screen_rank.tolist(),
            g2_rank.tolist()
        )
    ]

    merged["phase2g5_review_priority"] = [priority_label(r) for r in combined_rank]
    merged["phase2g5_review_rank"] = combined_rank

    merged["recommended_verification_action"] = "Confirm facility location and physical vehicle access"
    merged.loc[restrictive, "recommended_verification_action"] = (
        "Inspect the final approach and confirm vehicle-appropriate road access"
    )
    merged.loc[very_far, "recommended_verification_action"] = (
        "Verify candidate coordinates and identify the actual access route on the ground"
    )
    merged.loc[both, "recommended_verification_action"] = (
        "Verify coordinates, inspect the final approach, and confirm vehicle access"
    )

    # These safety fields are intentionally conservative.
    merged["physical_vehicle_access_confirmed"] = "NO"
    merged["operational_facility_verified"] = "NO"
    merged["routing_eligible"] = "NO"
    merged["phase2g5_access_decision"] = "PENDING_FIELD_VERIFICATION"

    # Sort for fieldwork: highest priority first, then greatest road distance.
    merged = merged.sort_values(
        ["phase2g5_review_rank", distance_col],
        ascending=[True, False],
        kind="stable"
    ).reset_index(drop=True)

    merged["phase2g5_queue_order"] = range(1, len(merged) + 1)
    merged = merged.drop(columns=["_join_id"], errors="ignore")

    checks = {
        "Input candidate counts match": len(g2) == len(g4),
        "Output row count preserved": len(merged) == len(g4),
        "Output candidate IDs unique": merged[key4].is_unique,
        "All distances valid": pd.to_numeric(merged[distance_col], errors="coerce").notna().all(),
        "All candidates access-unconfirmed": (merged["physical_vehicle_access_confirmed"] == "NO").all(),
        "All candidates operationally unverified": (merged["operational_facility_verified"] == "NO").all(),
        "All candidates routing-ineligible": (merged["routing_eligible"] == "NO").all(),
        "All decisions pending field verification": (merged["phase2g5_access_decision"] == "PENDING_FIELD_VERIFICATION").all(),
        "All review priorities valid": merged["phase2g5_review_priority"].isin(["P1", "P2", "P3", "P4"]).all(),
        "Queue order unique": merged["phase2g5_queue_order"].is_unique
    }

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    generated = datetime.now(timezone.utc).isoformat()
    lines = [
        "PHASE 2G.5 — CANDIDATE ACCESS RISK PRIORITIZATION AUDIT",
        "=" * 72,
        f"Generated UTC: {generated}",
        "Status: " + ("completed" if all(checks.values()) else "failed"),
        "",
        "INPUTS",
        f"Phase 2G.2: {INPUT_G2.relative_to(ROOT)}",
        f"Phase 2G.4 v2: {INPUT_G4.relative_to(ROOT)}",
        f"Phase 2G.2 priority field used: {g2_priority_col or 'none found'}",
        "",
        "RESULTS",
        f"Candidate rows: {len(g4)}",
        f"Output rows: {len(merged)}",
        f"Distance field: {distance_col}",
        f"Road class field: {class_col}",
        f"Candidates over 250 m: {int((distance > 250).sum())}",
        f"Candidates over 500 m: {int(very_far.sum())}",
        f"Nearest road in potentially restrictive class: {int(restrictive.sum())}",
        "",
        "RISK SCREEN COUNTS",
        merged["access_risk_screen"].value_counts().to_string(),
        "",
        "FINAL REVIEW PRIORITY COUNTS",
        merged["phase2g5_review_priority"].value_counts().sort_index().to_string(),
        "",
        "NEAREST ROAD CLASS COUNTS",
        road_class.value_counts().to_string(),
        "",
        "SAFETY",
        f"Physical vehicle access confirmed: {(merged['physical_vehicle_access_confirmed'] == 'YES').sum()}",
        f"Operational facility verified: {(merged['operational_facility_verified'] == 'YES').sum()}",
        f"Routing eligible: {(merged['routing_eligible'] == 'YES').sum()}",
        "All candidates remain pending field verification.",
        "Road proximity and road class are screening evidence, not proof of physical access.",
        "",
        "OUTPUT",
        str(OUTPUT_CSV.relative_to(ROOT)),
        "",
        "VALIDATION"
    ]
    lines.extend(f"{'PASS' if passed else 'FAIL'}: {name}" for name, passed in checks.items())
    lines.append("")
    lines.append("Existing Phase 2 outputs were not modified.")

    OUTPUT_AUDIT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    if not all(checks.values()):
        stop("One or more validation checks failed.")
    print("\nPhase 2G.5 completed successfully.")

if __name__ == "__main__":
    main()
