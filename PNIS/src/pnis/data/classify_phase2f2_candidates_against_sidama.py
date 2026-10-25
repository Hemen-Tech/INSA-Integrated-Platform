
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

import pandas as pd
import geopandas as gpd
from shapely import wkt

ROOT = Path.cwd()
GPKG = ROOT / "data/processed/geographic/ethiopia.gpkg"
INPUT = ROOT / "data/processed/phase2f1_osm_facility_candidates_corrected_v2.csv"
OUT = ROOT / "data/processed/phase2f2_osm_facility_candidates_spatially_classified_v1.csv"
AUDIT = ROOT / "data/processed/phase2f2_spatial_classification_audit_v1.txt"

LAYER = "gis_osm_adminareas_a_free"
BOUNDARY_IDS = ("3306775", "13422229")
WORKING_BOUNDARY_ID = "3306775"


def main():
    if not GPKG.exists() or not INPUT.exists():
        raise FileNotFoundError("Required source GeoPackage or candidate CSV is missing.")

    candidates = pd.read_csv(INPUT, dtype={"osm_id": "Int64"})
    if len(candidates) != 497:
        raise ValueError(f"Expected 497 candidates; found {len(candidates)}.")

    required = {
        "candidate_record_id", "osm_id", "source_layer",
        "geometry_wkt", "longitude", "latitude",
        "verification_status", "operational_facility_confirmed",
        "routing_eligibility",
    }
    missing = required - set(candidates.columns)
    if missing:
        raise ValueError(f"Missing required candidate fields: {sorted(missing)}")

    admin = gpd.read_file(GPKG, layer=LAYER)
    matches = admin[admin["osm_id"].astype(str).isin(BOUNDARY_IDS)]

    found = set(matches["osm_id"].astype(str))
    if found != set(BOUNDARY_IDS):
        raise ValueError(f"Expected both Sidama boundary IDs; found {sorted(found)}.")

    boundary4 = matches.loc[
        matches["osm_id"].astype(str) == WORKING_BOUNDARY_ID, "geometry"
    ].iloc[0]
    boundary5 = matches.loc[
        matches["osm_id"].astype(str) == "13422229", "geometry"
    ].iloc[0]

    if boundary4 is None or boundary5 is None:
        raise ValueError("A Sidama boundary geometry is missing.")
    if boundary4.is_empty or boundary5.is_empty:
        raise ValueError("A Sidama boundary geometry is empty.")
    if not boundary4.is_valid or not boundary5.is_valid:
        raise ValueError("A Sidama boundary geometry is invalid.")
    if not boundary4.equals(boundary5):
        raise ValueError("Sidama boundary geometries no longer match.")

    boundary_edge = boundary4.boundary
    results = []

    for _, row in candidates.iterrows():
        raw = row.get("geometry_wkt")
        geom = None
        status = "GEOMETRY_REVIEW"

        try:
            if pd.notna(raw) and str(raw).strip():
                geom = wkt.loads(str(raw))
            if geom is None or geom.is_empty or not geom.is_valid:
                raise ValueError("Missing, empty, or invalid candidate geometry.")

            if boundary_edge.intersects(geom):
                status = "BOUNDARY_REVIEW"
            elif boundary4.covers(geom):
                status = "INSIDE_SIDAMA"
            elif boundary4.disjoint(geom):
                status = "OUTSIDE_SIDAMA"
            else:
                status = "BOUNDARY_REVIEW"

        except Exception:
            status = "GEOMETRY_REVIEW"

        results.append(status)

    candidates["spatial_classification"] = results
    candidates["boundary_osm_id"] = WORKING_BOUNDARY_ID
    candidates["boundary_admin_level"] = "admin_level4"
    candidates["boundary_name"] = "ሲዳማ ክልል Sidama سيداما"
    candidates["boundary_source"] = f"{GPKG} | {LAYER}"
    candidates["classification_method"] = (
        "Candidate WKT geometry compared with Sidama polygon; "
        "boundary contact flagged for review"
    )

    # Spatial classification must not promote candidates to operational status.
    candidates["verification_status"] = "UNVERIFIED"
    candidates["operational_facility_confirmed"] = "NO"
    candidates["routing_eligibility"] = "NOT_APPROVED_FOR_OPERATIONAL_ROUTING"

    if candidates["candidate_record_id"].duplicated().any():
        raise ValueError("Duplicate candidate_record_id values detected.")

    counts = Counter(results)
    candidates.to_csv(OUT, index=False, encoding="utf-8-sig")

    audit_lines = [
        "PNIS PHASE 2F.2 — SIDAMA CANDIDATE SPATIAL CLASSIFICATION",
        "=" * 72,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        "Status: completed",
        f"Input: {INPUT}",
        f"Output: {OUT}",
        f"Boundary GeoPackage: {GPKG}",
        f"Boundary layer: {LAYER}",
        f"Selected boundary OSM ID: {WORKING_BOUNDARY_ID}",
        "Selected boundary class: admin_level4",
        "Comparison boundary OSM ID: 13422229",
        f"Boundary geometries topologically equal: {boundary4.equals(boundary5)}",
        f"Boundary area km2 (EPSG:32637): "
        f"{boundary4 and gpd.GeoSeries([boundary4], crs=admin.crs).to_crs('EPSG:32637').area.iloc[0] / 1e6:.6f}",
        "",
        "CLASSIFICATION COUNTS",
        "-" * 72,
    ]
    for label in (
        "INSIDE_SIDAMA", "OUTSIDE_SIDAMA",
        "BOUNDARY_REVIEW", "GEOMETRY_REVIEW",
    ):
        audit_lines.append(f"{label}: {counts.get(label, 0)}")

    audit_lines += [
        "",
        "VALIDATION",
        "-" * 72,
        f"Input rows: {len(candidates)}",
        f"Output rows: {len(candidates)}",
        f"Unique candidate IDs: {candidates['candidate_record_id'].nunique()}",
        f"Missing candidate WKT: {candidates['geometry_wkt'].isna().sum()}",
        f"All verification_status UNVERIFIED: "
        f"{candidates['verification_status'].eq('UNVERIFIED').all()}",
        f"All operational_facility_confirmed NO: "
        f"{candidates['operational_facility_confirmed'].eq('NO').all()}",
        f"All routing ineligible: "
        f"{candidates['routing_eligibility'].eq('NOT_APPROVED_FOR_OPERATIONAL_ROUTING').all()}",
        "",
        "LIMITATIONS",
        "-" * 72,
        "Spatial inclusion does not confirm that a candidate is a real or operational facility.",
        "Outside candidates are retained for traceability and must not be silently deleted.",
        "Boundary and geometry review cases require manual investigation.",
        "The boundary is verified for consistency within the source GeoPackage, not independently",
        "certified as an authoritative government boundary.",
    ]

    AUDIT.write_text("\n".join(audit_lines) + "\n", encoding="utf-8")

    print("\n".join(audit_lines))
    print("\nFiles created:")
    print(OUT)
    print(AUDIT)


if __name__ == "__main__":
    main()
