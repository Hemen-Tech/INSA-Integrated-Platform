from pathlib import Path
import json
import pandas as pd
import geopandas as gpd
import pyogrio

ROOT = Path(".")
GPKG = ROOT / "data/processed/geographic/ethiopia.gpkg"
OLD_CSV = ROOT / "data/processed/phase2f_osm_facility_candidates.csv"
OUT_CSV = ROOT / "data/processed/phase2f1_osm_facility_candidates_corrected.csv"
OUT_REGISTER = ROOT / "data/processed/phase2f1_candidate_review_register_corrected.csv"
OUT_AUDIT = ROOT / "data/processed/phase2f1_candidate_rebuild_audit.txt"

if not GPKG.exists() or not OLD_CSV.exists():
    raise FileNotFoundError("Required GeoPackage or original candidate CSV is missing.")

old = pd.read_csv(OLD_CSV, dtype=str, keep_default_na=False)
required = {"osm_id", "name", "code", "fclass"}
missing = required - set(old.columns)
if missing:
    raise ValueError(f"Unexpected original CSV schema; missing columns: {sorted(missing)}")

# In the damaged CSV, 'name' contains the original source-layer name.
source_layers = sorted(set(old["name"].str.strip()) - {""})
available = {str(row[0]) for row in pyogrio.list_layers(GPKG)}
cache = {}
records = []
errors = []

def review_group(fclass, layer):
    fc = (fclass or "").lower()
    if fc == "marketplace":
        return "MARKET_CANDIDATE"
    if fc in {"supermarket", "convenience", "greengrocer", "food_court"}:
        return "RETAIL_OR_FOOD_MARKET_CANDIDATE"
    if layer in {"gis_osm_places_free", "gis_osm_places_a_free"}:
        return "SETTLEMENT_REFERENCE"
    if layer == "gis_osm_landuse_a_free":
        if fc in {"farmland", "farmyard", "orchard", "vineyard", "plant_nursery"}:
            return "AGRICULTURAL_LAND_ONLY"
        if fc in {"industrial", "commercial", "retail"}:
            return "INDUSTRIAL_SITE_CANDIDATE"
        return "OTHER_LANDUSE_REVIEW"
    if layer == "gis_osm_buildings_a_free":
        return "BUILDING_CANDIDATE"
    if fc in {"farm", "farmyard", "agricultural", "greenhouse", "plant_nursery"}:
        return "AGRICULTURAL_SITE_CANDIDATE"
    if fc in {"industrial", "warehouse", "works", "factory"}:
        return "INDUSTRIAL_SITE_CANDIDATE"
    return "OTHER_POI_REVIEW"

for layer in source_layers:
    if layer not in available:
        errors.append(f"Missing source layer: {layer}")
        continue

    subset = old[old["name"].str.strip() == layer].copy()
    ids = set(subset["osm_id"].astype(str).str.strip())

    if layer not in cache:
        # Candidates were originally discovered in this geographic search area.
        # This is only a retrieval filter, not the final Sidama boundary check.
        gdf = gpd.read_file(
            GPKG,
            layer=layer,
            bbox=(37.85, 6.09, 39.19, 7.22),
            engine="pyogrio",
        )
        if "osm_id" not in gdf.columns:
            errors.append(f"No osm_id field in {layer}")
            continue
        gdf["osm_id"] = gdf["osm_id"].astype(str)
        cache[layer] = gdf

    source = cache[layer]
    lookup = {}
    for _, src in source[source["osm_id"].isin(ids)].iterrows():
        lookup.setdefault(str(src["osm_id"]), []).append(src)

    for _, oldrow in subset.iterrows():
        osm_id = str(oldrow["osm_id"]).strip()
        matches = lookup.get(osm_id, [])

        if len(matches) != 1:
            errors.append(
                f"{layer} / {osm_id}: expected exactly 1 source match, got {len(matches)}"
            )
            continue

        src = matches[0]
        fclass = str(src.get("fclass", "") or "")
        name = str(src.get("name", "") or "")
        code = str(src.get("code", "") or "")
        population = str(src.get("population", "") or "") if "population" in source.columns else ""
        geom = src.geometry

        if geom is None or geom.is_empty:
            errors.append(f"{layer} / {osm_id}: missing or empty geometry")
            continue

        match_text = " ".join(x for x in [fclass, name] if x).lower()

        records.append({
            "osm_id": osm_id,
            "code": code,
            "fclass": fclass,
            "population": population,
            "name": name,
            "source_layer": layer,
            "candidate_match_text": match_text,
            "candidate_status": "UNVERIFIED_OSM_CANDIDATE_REQUIRES_REVIEW",
            "geometry_wkt": geom.wkt,
            "geometry_type": geom.geom_type,
            "longitude": (
                float(geom.x) if geom.geom_type == "Point"
                else float(geom.representative_point().x)
            ),
            "latitude": (
                float(geom.y) if geom.geom_type == "Point"
                else float(geom.representative_point().y)
            ),
            "review_group": review_group(fclass, layer),
            "verification_status": "UNVERIFIED",
            "operational_facility_confirmed": "NO",
            "routing_eligibility": "NOT_APPROVED_FOR_OPERATIONAL_ROUTING",
            "reviewer_notes": "",
        })

result = pd.DataFrame(records)

if not result.empty:
    result = result.sort_values(
        ["source_layer", "osm_id"], kind="stable"
    ).reset_index(drop=True)
    result.insert(0, "candidate_record_id", [
        f"PH2F1-{i:04d}" for i in range(1, len(result) + 1)
    ])

OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
result.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
result.to_csv(OUT_REGISTER, index=False, encoding="utf-8-sig")

summary = [
    "=" * 76,
    "PHASE 2F.1 — CANDIDATE SOURCE REBUILD AUDIT",
    "=" * 76,
    f"Original candidate rows: {len(old)}",
    f"Reconstructed rows: {len(result)}",
    f"Source layers referenced: {len(source_layers)}",
    f"Unresolved source records: {len(errors)}",
    f"Corrected candidate CSV: {OUT_CSV.resolve()}",
    f"Corrected review register: {OUT_REGISTER.resolve()}",
    "",
    "RECONSTRUCTED RECORDS BY SOURCE LAYER",
]
if not result.empty:
    summary.extend(
        f"{k}: {v}" for k, v in
        result.groupby("source_layer").size().sort_values(ascending=False).items()
    )
    summary += ["", "REVIEW GROUP COUNTS"]
    summary.extend(
        f"{k}: {v}" for k, v in
        result["review_group"].value_counts().sort_index().items()
    )
    summary += [
        "",
        "GEOMETRY TYPES",
        *[
            f"{k}: {v}" for k, v in
            result["geometry_type"].value_counts().sort_index().items()
        ],
        "",
        "SAFETY CHECKS",
        f"Duplicate source-layer + OSM ID rows: "
        f"{int(result.duplicated(['source_layer', 'osm_id']).sum())}",
        f"Missing names: {int(result['name'].fillna('').eq('').sum())}",
        f"Missing coordinates: {int(result[['longitude','latitude']].isna().any(axis=1).sum())}",
        f"All remain unverified: {bool(result['verification_status'].eq('UNVERIFIED').all())}",
        f"All remain routing-ineligible: {bool(result['routing_eligibility'].eq('NOT_APPROVED_FOR_OPERATIONAL_ROUTING').all())}",
    ]

summary += ["", "UNRESOLVED RECORDS"]
summary.extend(errors[:100] if errors else ["None"])
if len(errors) > 100:
    summary.append(f"... {len(errors) - 100} additional errors omitted")

OUT_AUDIT.write_text("\n".join(summary) + "\n", encoding="utf-8")
print("\n".join(summary))
print(f"\nAudit saved: {OUT_AUDIT.resolve()}")

if len(result) != len(old) or errors:
    print("\nWARNING: Not every original record was reconstructed. Review the audit before proceeding.")
