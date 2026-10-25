from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import geopandas as gpd
import numpy as np

ROOT = Path("data/processed")
CANDIDATE_FILE = ROOT / "phase2g1_candidate_road_proximity_register.csv"
ROAD_REVIEW_FILE = ROOT / "phase2g3_road_suitability_review_register.csv"
ROAD_GPKG = ROOT / "phase2c_v2_sidama_buffered_roads.gpkg"
ROAD_LAYER = "sidama_buffered_roads_v2"

OUT_CSV = ROOT / "phase2g4_candidate_road_access_review_register_v2.csv"
OUT_AUDIT = ROOT / "phase2g4_candidate_road_access_review_audit_v2.txt"

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def main():
    for path in [CANDIDATE_FILE, ROAD_REVIEW_FILE, ROAD_GPKG]:
        require(path.exists(), f"Required input missing: {path}")

    candidates = pd.read_csv(CANDIDATE_FILE, encoding="utf-8-sig")
    road_review = pd.read_csv(ROAD_REVIEW_FILE, encoding="utf-8-sig")
    roads = gpd.read_file(ROAD_GPKG, layer=ROAD_LAYER)

    require(len(candidates) > 0, "Candidate register is empty.")
    require(len(roads) > 0, "Road layer is empty.")
    require("candidate_record_id" in candidates, "Candidate ID column missing.")
    require({"longitude", "latitude"}.issubset(candidates.columns),
            "Candidate coordinates missing.")
    require("osm_id" in roads.columns, "Road layer has no osm_id.")
    require("osm_id" in road_review.columns, "Phase 2G.3 has no osm_id.")
    require(roads.crs is not None, "Road layer CRS is undefined.")
    require(roads.crs.to_epsg() == 32637,
            f"Expected road CRS EPSG:32637; found {roads.crs}.")

    candidates["longitude"] = pd.to_numeric(candidates["longitude"], errors="coerce")
    candidates["latitude"] = pd.to_numeric(candidates["latitude"], errors="coerce")
    valid_coords = (
        candidates["longitude"].notna()
        & candidates["latitude"].notna()
        & candidates["longitude"].between(-180, 180)
        & candidates["latitude"].between(-90, 90)
    )
    require(valid_coords.all(),
            f"{int((~valid_coords).sum())} candidates have invalid coordinates.")

    # Project candidate coordinates into the road layer's metric CRS.
    points = gpd.GeoDataFrame(
        candidates[["candidate_record_id", "longitude", "latitude"]].copy(),
        geometry=gpd.points_from_xy(
            candidates["longitude"], candidates["latitude"]
        ),
        crs="EPSG:4326",
    ).to_crs(roads.crs)

    roads = roads.loc[
        roads.geometry.notna()
        & ~roads.geometry.is_empty
    ].copy()
    roads = roads.reset_index(drop=True)
    roads["_road_row"] = np.arange(len(roads), dtype=int)

    # Spatial nearest join. Keep distance in metres and the matched road row.
    nearest = gpd.sjoin_nearest(
        points,
        roads[["_road_row", "osm_id", "code", "fclass", "name",
               "ref", "oneway", "maxspeed", "geometry"]],
        how="left",
        distance_col="recalculated_nearest_road_distance_m",
    )

    # A point can have multiple equally near roads. Keep all ties for auditing.
    tie_counts = nearest.groupby("candidate_record_id").size()
    nearest = nearest.sort_values(
        ["candidate_record_id", "recalculated_nearest_road_distance_m",
         "_road_row" if "_road_row" in nearest.columns else "index_right"],
        kind="stable",
    )
    chosen = nearest.drop_duplicates("candidate_record_id", keep="first").copy()
    chosen["nearest_road_tie_count"] = (
        chosen["candidate_record_id"].map(tie_counts).fillna(0).astype(int)
    )

    # Build a conservative OSM ID linkage to Phase 2G.3.
    review = road_review.copy()
    review["_osm_key"] = review["osm_id"].astype("string").str.strip()
    review["_osm_key"] = review["_osm_key"].replace("", pd.NA)
    review_counts = review["_osm_key"].value_counts(dropna=True)
    review["_phase2g3_id_count"] = review["_osm_key"].map(review_counts).fillna(0)

    # Select review columns with distinct names to avoid overwriting nearest-road data.
    review_cols = [
        "osm_id", "road_review_id", "review_road_class",
        "vehicle_suitability_screen", "review_priority",
        "field_verification_status", "vehicle_suitability_decision",
        "vehicle_suitability_verified", "routing_eligible",
        "eligibility_reason", "_phase2g3_id_count",
    ]
    review_cols = [c for c in review_cols if c in review.columns]
    review_unique = review.loc[
        review["_phase2g3_id_count"].eq(1), review_cols
    ].copy()
    review_unique = review_unique.rename(columns={
        "osm_id": "phase2g3_osm_id",
        "road_review_id": "phase2g3_road_review_id",
        "review_road_class": "phase2g3_review_road_class",
        "vehicle_suitability_screen": "phase2g3_vehicle_suitability_screen",
        "review_priority": "phase2g3_review_priority",
        "field_verification_status": "phase2g3_field_verification_status",
        "vehicle_suitability_decision": "phase2g3_vehicle_suitability_decision",
        "vehicle_suitability_verified": "phase2g3_vehicle_suitability_verified",
        "routing_eligible": "phase2g3_routing_eligible",
        "eligibility_reason": "phase2g3_eligibility_reason",
        "_phase2g3_id_count": "phase2g3_osm_id_count",
    })
    chosen["_osm_key"] = chosen["osm_id"].astype("string").str.strip()
    chosen["_osm_key"] = chosen["_osm_key"].replace("", pd.NA)
    chosen = chosen.merge(
        review_unique,
        left_on="_osm_key",
        right_on=review_unique["phase2g3_osm_id"].astype("string").str.strip(),
        how="left",
        validate="many_to_one",
    )

    # Restore original candidate register fields and attach nearest-road findings.
    chosen = chosen.drop(columns=["geometry"], errors="ignore")
    attach_cols = [
        "candidate_record_id", "osm_id", "code", "fclass", "name",
        "ref", "oneway", "maxspeed", "recalculated_nearest_road_distance_m",
        "nearest_road_tie_count", "phase2g3_road_review_id",
        "phase2g3_review_road_class",
        "phase2g3_vehicle_suitability_screen",
        "phase2g3_review_priority",
        "phase2g3_field_verification_status",
        "phase2g3_vehicle_suitability_decision",
        "phase2g3_vehicle_suitability_verified",
        "phase2g3_routing_eligible", "phase2g3_eligibility_reason",
    ]
    attach_cols = [c for c in attach_cols if c in chosen.columns]
    nearest_info = chosen[attach_cols].copy()
    nearest_info = nearest_info.rename(columns={
        "osm_id": "nearest_road_osm_id",
        "code": "nearest_road_code",
        "fclass": "nearest_road_fclass",
        "name": "nearest_road_name",
        "ref": "nearest_road_ref",
        "oneway": "nearest_road_oneway",
        "maxspeed": "nearest_road_maxspeed",
    })

    # Avoid collisions with candidate columns.
    candidate_out = candidates.copy()
    merged = candidate_out.merge(
        nearest_info,
        on="candidate_record_id",
        how="left",
        validate="one_to_one",
    )

    original_distance = pd.to_numeric(
        merged.get("nearest_mapped_road_distance_m"), errors="coerce"
    )
    recalculated = pd.to_numeric(
        merged["recalculated_nearest_road_distance_m"], errors="coerce"
    )
    merged["phase2g1_vs_recalculated_distance_difference_m"] = (
        recalculated - original_distance
    ).abs()

    def join_status(row):
        if pd.isna(row.get("nearest_road_osm_id")):
            return "NO_NEAREST_ROAD_MATCH"
        key = str(row["nearest_road_osm_id"]).strip()
        count = review_counts.get(key, 0)
        if count == 1 and pd.notna(row.get("phase2g3_road_review_id")):
            return "MATCHED_UNIQUE_OSM_ID"
        if count > 1:
            return "AMBIGUOUS_DUPLICATE_OSM_ID_IN_PHASE2G3"
        return "ROAD_FOUND_BUT_NO_PHASE2G3_OSM_ID_MATCH"

    merged["phase2g4_linkage_status"] = merged.apply(join_status, axis=1)
    merged["phase2g4_review_action"] = np.where(
        merged["phase2g4_linkage_status"].eq("MATCHED_UNIQUE_OSM_ID"),
        "REVIEW_NEAREST_ROAD_AND_FIELD_VERIFY_ACCESS",
        "RESOLVE_ROAD_IDENTITY_OR_LINKAGE",
    )

    # Safety guardrails: this is proximity evidence, never proof of access.
    merged["physical_vehicle_access_confirmed"] = "NO"
    merged["operational_facility_verified"] = "NO"
    merged["routing_eligible"] = "NO"
    merged["phase2g4_access_decision"] = "PENDING_FIELD_VERIFICATION"
    merged["phase2g4_evidence_scope"] = (
        "Nearest mapped road only; physical access, legal access, "
        "vehicle suitability, and facility operation are unverified."
    )

    # Stable candidate IDs must remain unique and complete.
    require(merged["candidate_record_id"].is_unique,
            "Output has duplicate candidate IDs.")
    require(len(merged) == len(candidates),
            "Output row count differs from candidate register.")
    require(merged["routing_eligible"].eq("NO").all(),
            "Safety check failed: a candidate became routing eligible.")
    require(merged["physical_vehicle_access_confirmed"].eq("NO").all(),
            "Safety check failed: access was marked confirmed.")
    require(merged["operational_facility_verified"].eq("NO").all(),
            "Safety check failed: facility was marked verified.")

    merged.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    distances_ok = recalculated.notna().all()
    max_difference = (
        merged["phase2g1_vs_recalculated_distance_difference_m"].max()
        if merged["phase2g1_vs_recalculated_distance_difference_m"].notna().any()
        else float("nan")
    )
    status_counts = merged["phase2g4_linkage_status"].value_counts(dropna=False)
    unique_matches = int(
        merged["phase2g4_linkage_status"].eq("MATCHED_UNIQUE_OSM_ID").sum()
    )
    audit_lines = [
        "PHASE 2G.4 V2 — CANDIDATE TO NEAREST-ROAD LINKAGE AUDIT",
        "=" * 72,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        "Status: " + ("completed" if distances_ok else "review_required"),
        "",
        "INPUTS",
        f"Candidates: {CANDIDATE_FILE}",
        f"Road network: {ROAD_GPKG} | layer={ROAD_LAYER}",
        f"Road suitability review: {ROAD_REVIEW_FILE}",
        "",
        "RESULTS",
        f"Candidate rows: {len(candidates)}",
        f"Output rows: {len(merged)}",
        f"Road features considered: {len(roads)}",
        f"Candidate coordinates valid: {int(valid_coords.sum())}/{len(candidates)}",
        f"Candidates with recalculated distance: {int(recalculated.notna().sum())}",
        f"Unique Phase 2G.3 OSM ID linkages: {unique_matches}",
        f"Max absolute distance difference vs Phase 2G.1 (m): {max_difference}",
        "",
        "LINKAGE STATUS COUNTS",
    ]
    audit_lines.extend(f"{key}: {value}" for key, value in status_counts.items())
    audit_lines += [
        "",
        "SAFETY",
        "Physical vehicle access confirmed: 0",
        "Operational facility verified: 0",
        "Routing eligible: 0",
        "Nearest-road proximity is not proof of physical access.",
        "",
        "OUTPUT",
        str(OUT_CSV),
        "",
        "VALIDATION",
        f"Unique candidate IDs: {merged['candidate_record_id'].is_unique}",
        f"Row count preserved: {len(merged) == len(candidates)}",
        f"All recalculated distances present: {distances_ok}",
        f"All candidates routing-ineligible: {merged['routing_eligible'].eq('NO').all()}",
        f"All candidates access-unconfirmed: {merged['physical_vehicle_access_confirmed'].eq('NO').all()}",
    ]
    OUT_AUDIT.write_text("\n".join(audit_lines) + "\n", encoding="utf-8")

    print("\n" + "\n".join(audit_lines))
    print("\nPhase 2G.4 v2 completed. Original Phase 2G.4 outputs were not modified.")

if __name__ == "__main__":
    main()
