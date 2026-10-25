from pathlib import Path
import json
import geopandas as gpd
import pyogrio

gpkg = Path("data/processed/geographic/ethiopia.gpkg")
out = Path("data/processed/phase2f1_source_schema_audit.txt")

if not gpkg.exists():
    raise FileNotFoundError(f"Source GeoPackage not found: {gpkg.resolve()}")

# Discovery extent only; exact Sidama-boundary validation comes later.
bbox = (37.85, 6.09, 39.19, 7.22)

target_layers = {
    "gis_osm_places_free",
    "gis_osm_traffic_free",
    "gis_osm_pois_free",
    "gis_osm_transport_free",
    "gis_osm_places_a_free",
    "gis_osm_pois_a_free",
    "gis_osm_buildings_a_free",
    "gis_osm_landuse_a_free",
}

lines = []

def log(value=""):
    lines.append(str(value))
    print(value)

layers = pyogrio.list_layers(gpkg)
layer_names = [str(row[0]) for row in layers]

log("=" * 78)
log("PHASE 2F.1 — ORIGINAL OSM SOURCE SCHEMA AUDIT")
log("=" * 78)
log(f"GeoPackage: {gpkg.resolve()}")
log(f"Discovery bbox (WGS84): {bbox}")
log("Read-only inspection; no source data changed.")

for layer in sorted(target_layers):
    if layer not in layer_names:
        log(f"\nLAYER NOT FOUND: {layer}")
        continue

    log("\n" + "-" * 78)
    log(f"LAYER: {layer}")

    try:
        info = pyogrio.read_info(gpkg, layer=layer)
        log(f"Geometry type: {info.get('geometry_type')}")
        log(f"CRS: {info.get('crs')}")
        log(f"Fields: {info.get('fields')}")
        log(f"Full-layer feature count: {info.get('features')}")

        gdf = gpd.read_file(
            gpkg,
            layer=layer,
            bbox=bbox,
            engine="pyogrio",
        )
        log(f"Features in discovery bbox: {len(gdf)}")
        log(f"Actual columns: {list(gdf.columns)}")

        if gdf.empty:
            continue

        # Show a few rows with short geometry summaries, not huge WKT strings.
        for idx, row in gdf.head(4).iterrows():
            record = {}
            for col in gdf.columns:
                if col == gdf.geometry.name:
                    geom = row.geometry
                    record["geometry_type"] = (
                        geom.geom_type if geom is not None else None
                    )
                    if geom is not None and not geom.is_empty:
                        point = (
                            geom if geom.geom_type == "Point"
                            else geom.representative_point()
                        )
                        record["representative_lon"] = round(point.x, 7)
                        record["representative_lat"] = round(point.y, 7)
                    else:
                        record["representative_lon"] = None
                        record["representative_lat"] = None
                else:
                    value = row[col]
                    if value is None:
                        record[col] = None
                    elif hasattr(value, "item"):
                        record[col] = value.item()
                    else:
                        record[col] = str(value)[:180]
            log(json.dumps(record, ensure_ascii=False, default=str))

    except Exception as exc:
        log(f"ERROR inspecting layer: {type(exc).__name__}: {exc}")

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"\nAudit saved to: {out.resolve()}")
