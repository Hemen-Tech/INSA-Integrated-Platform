from pathlib import Path
import pandas as pd
import geopandas as gpd
import pyogrio

gpkg = Path("data/processed/geographic/ethiopia.gpkg")
source_csv = Path("data/processed/phase2f_osm_facility_candidates.csv")
out_csv = Path("data/processed/phase2f1_osm_facility_candidates_corrected_v2.csv")
out_register = Path("data/processed/phase2f1_candidate_review_register_corrected_v2.csv")
out_audit = Path("data/processed/phase2f1_candidate_rebuild_audit_v2.txt")

old = pd.read_csv(source_csv, dtype=str, keep_default_na=False)
layers = {str(r[0]) for r in pyogrio.list_layers(gpkg)}
cache = {}
rebuilt, unresolved = [], []

def clean(value):
    return "" if value is None else str(value).strip()

def group_for(layer, fclass):
    fc = fclass.lower()
    if fc == "marketplace":
        return "MARKET_CANDIDATE"
    if fc in {"supermarket", "convenience", "greengrocer"}:
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

for idx, oldrow in old.iterrows():
    # The original CSV's layer name was written into different columns
    # depending on which source layer the candidate came from.
    name_value = clean(oldrow.get("name", ""))
    source_value = clean(oldrow.get("source_layer", ""))

    if source_value in layers:
        layer = source_value
    elif name_value in layers:
        layer = name_value
    else:
        unresolved.append({
            "original_row": idx + 2,
            "osm_id": clean(oldrow.get("osm_id")),
            "reason": "No recognized source layer in name or source_layer",
            "name_field": name_value,
            "source_layer_field": source_value,
        })
        continue

    if layer not in cache:
        try:
            cache[layer] = gpd.read_file(
                gpkg,
                layer=layer,
                bbox=(37.85, 6.09, 39.19, 7.22),
                engine="pyogrio",
            )
            cache[layer]["osm_id"] = cache[layer]["osm_id"].astype(str).str.strip()
            for col in ["code", "fclass", "name"]:
                if col in cache[layer].columns:
                    cache[layer][col] = cache[layer][col].map(clean)
        except Exception as exc:
            unresolved.append({
                "original_row": idx + 2,
                "osm_id": clean(oldrow.get("osm_id")),
                "reason": f"Layer read failed: {exc}",
                "name_field": name_value,
                "source_layer_field": source_value,
            })
            continue

    src = cache[layer]
    osm_id = clean(oldrow.get("osm_id"))
    code = clean(oldrow.get("code"))
    fclass = clean(oldrow.get("fclass"))

    matches = src[src["osm_id"] == osm_id]
    if "code" in src.columns and code:
        matches = matches[matches["code"] == code]
    if "fclass" in src.columns and fclass:
        matches = matches[matches["fclass"] == fclass]

    if len(matches) != 1:
        unresolved.append({
            "original_row": idx + 2,
            "osm_id": osm_id,
            "reason": f"Expected one match by layer+OSM ID+code+fclass; got {len(matches)}",
            "layer": layer,
            "code": code,
            "fclass": fclass,
            "name_field": name_value,
            "source_layer_field": source_value,
        })
        continue

    srcrow = matches.iloc[0]
    geom = srcrow.geometry
    if geom is None or geom.is_empty:
        unresolved.append({
            "original_row": idx + 2,
            "osm_id": osm_id,
            "reason": "Matched source geometry is empty",
            "layer": layer,
        })
        continue

    actual_name = clean(srcrow.get("name", ""))
    population = clean(srcrow.get("population", "")) if "population" in src.columns else ""
    representative = geom if geom.geom_type == "Point" else geom.representative_point()

    rebuilt.append({
        "original_row": idx + 2,
        "osm_id": osm_id,
        "code": clean(srcrow.get("code", "")),
        "fclass": clean(srcrow.get("fclass", "")),
        "population": population,
        "name": actual_name,
        "source_layer": layer,
        "candidate_match_text": " ".join(
            x for x in [osm_id, clean(srcrow.get("fclass", "")), actual_name] if x
        ).lower(),
        "candidate_status": "UNVERIFIED_OSM_CANDIDATE_REQUIRES_REVIEW",
        "geometry_wkt": geom.wkt,
        "geometry_type": geom.geom_type,
        "longitude": float(representative.x),
        "latitude": float(representative.y),
        "review_group": group_for(layer, clean(srcrow.get("fclass", ""))),
        "verification_status": "UNVERIFIED",
        "operational_facility_confirmed": "NO",
        "verification_source": "",
        "reviewer_notes": "",
        "coordinate_review_status": "NOT_REVIEWED",
        "routing_eligibility": "NOT_APPROVED_FOR_OPERATIONAL_ROUTING",
    })

result = pd.DataFrame(rebuilt)
if not result.empty:
    result.insert(0, "candidate_record_id", [
        f"PH2F1V2-{i:04d}" for i in range(1, len(result) + 1)
    ])

out_csv.parent.mkdir(parents=True, exist_ok=True)
result.to_csv(out_csv, index=False, encoding="utf-8-sig")
result.to_csv(out_register, index=False, encoding="utf-8-sig")

audit = [
    "=" * 76,
    "PHASE 2F.1 — CORRECTED CANDIDATE REGISTER V2 AUDIT",
    "=" * 76,
    f"Original CSV rows: {len(old)}",
    f"Rebuilt rows: {len(result)}",
    f"Unresolved rows: {len(unresolved)}",
    f"Corrected CSV: {out_csv.resolve()}",
    f"Corrected register: {out_register.resolve()}",
    "",
    "UNRESOLVED ROWS (first 150)",
]
for item in unresolved[:150]:
    audit.append(str(item))
if len(unresolved) > 150:
    audit.append(f"... {len(unresolved) - 150} more unresolved rows")

audit += ["", "VALIDATION"]
if not result.empty:
    audit += [
        f"Duplicate source-layer + OSM ID + code + fclass: "
        f"{int(result.duplicated(['source_layer','osm_id','code','fclass']).sum())}",
        f"Rows missing coordinates: "
        f"{int(result[['longitude','latitude']].isna().any(axis=1).sum())}",
        f"All unverified: {bool(result['verification_status'].eq('UNVERIFIED').all())}",
        f"All routing-ineligible: {bool(result['routing_eligibility'].eq('NOT_APPROVED_FOR_OPERATIONAL_ROUTING').all())}",
        "",
        "ROWS BY SOURCE LAYER",
        *[
            f"{k}: {v}" for k, v in
            result["source_layer"].value_counts().sort_index().items()
        ],
    ]
else:
    audit.append("No rows were reconstructed.")

out_audit.write_text("\n".join(audit) + "\n", encoding="utf-8")
print("\n".join(audit))
print(f"\nAudit saved to: {out_audit.resolve()}")
