from pathlib import Path
import geopandas as gpd
import pyogrio

ROOT = Path.cwd()
GPKG = ROOT / "data" / "processed" / "geographic" / "ethiopia.gpkg"
OUT = ROOT / "data" / "processed" / "phase2f2_boundary_inventory.txt"

lines = []
def log(value=""):
    lines.append(str(value))
    print(value)

log("=" * 76)
log("PHASE 2F.2 — ADMINISTRATIVE BOUNDARY INVENTORY")
log("=" * 76)
log(f"GeoPackage: {GPKG}")
log(f"Exists: {GPKG.exists()}")

if not GPKG.exists():
    raise FileNotFoundError(GPKG)

layers = pyogrio.list_layers(GPKG)
log(f"\nTotal layers: {len(layers)}")
log("\nLAYERS MATCHING ADMINISTRATIVE / PLACE TERMS")

matches = []
for item in layers:
    layer_name = str(item[0])
    geom_type = str(item[1])
    if any(term in layer_name.lower() for term in
           ("admin", "boundary", "place", "region", "district")):
        matches.append(layer_name)
        log(f"\nLayer: {layer_name}")
        log(f"Geometry type: {geom_type}")
        try:
            info = pyogrio.read_info(GPKG, layer=layer_name)
            log(f"Feature count: {info.get('features')}")
            log(f"CRS: {info.get('crs')}")
            log(f"Fields: {info.get('fields')}")
            gdf = gpd.read_file(GPKG, layer=layer_name)
            log(f"Loaded rows: {len(gdf)}")
            log(f"Geometry types: {gdf.geom_type.value_counts().to_dict()}")
            log(f"Null/empty geometries: {int((gdf.geometry.isna() | gdf.geometry.is_empty).sum())}")
            for col in gdf.columns:
                if col != gdf.geometry.name and any(
                    term in col.lower()
                    for term in ("name", "admin", "region", "district", "type", "boundary")
                ):
                    vals = gdf[col].dropna().astype(str).drop_duplicates().head(30).tolist()
                    log(f"Values in {col}: {vals}")
            if gdf.crs is not None and len(gdf):
                log(f"Bounds: {gdf.total_bounds.tolist()}")
        except Exception as exc:
            log(f"INSPECTION ERROR: {type(exc).__name__}: {exc}")

if not matches:
    log("No layer names matched the administrative/place search terms.")

log("\n" + "=" * 76)
log("IMPORTANT: This inventory does not yet certify any layer as the Sidama boundary.")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
log(f"\nReport saved: {OUT}")
