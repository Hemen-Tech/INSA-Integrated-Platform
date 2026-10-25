from pathlib import Path
import pandas as pd
import pyogrio

csv_path = Path("data/processed/phase2f_osm_facility_candidates.csv")
gpkg_path = Path("data/processed/geographic/ethiopia.gpkg")
out_path = Path("data/processed/phase2f1_mapping_diagnostic.txt")

df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
layers = {str(r[0]) for r in pyogrio.list_layers(gpkg_path)}

lines = []
def log(x=""):
    lines.append(str(x))
    print(x)

log("=" * 78)
log("PHASE 2F.1 — ORIGINAL CSV MAPPING DIAGNOSTIC")
log("=" * 78)
log(f"Rows: {len(df)}")
log(f"Columns: {list(df.columns)}")
log(f"Recognized GeoPackage layers: {len(layers)}")

# Count values in each column that exactly match real layer names.
log("\nEXACT LAYER-NAME MATCH COUNTS BY COLUMN")
for col in df.columns:
    matches = df[col].astype(str).str.strip().isin(layers)
    log(f"{col}: {int(matches.sum())}")

log("\nSAMPLE ROWS WITH PLACE NAMES IN THE 'name' COLUMN")
mask = ~df["name"].astype(str).str.strip().isin(layers)
cols = [c for c in df.columns if c != "geometry_wkt"]
log(f"Rows whose name value is not a GeoPackage layer: {int(mask.sum())}")
for _, row in df.loc[mask, cols].head(35).iterrows():
    log(" | ".join(f"{c}={row[c]}" for c in cols))

log("\nROWS WHERE 'source_layer' LOOKS LIKE AN ID/CLASS/NAME STRING")
s = df["source_layer"].astype(str).str.strip()
mask2 = ~s.isin(layers)
log(f"Rows with source_layer not matching a real layer: {int(mask2.sum())}")
for _, row in df.loc[mask2, cols].head(35).iterrows():
    log(" | ".join(f"{c}={row[c]}" for c in cols))

log("\nDUPLICATE OSM IDS IN ORIGINAL CSV")
dup = df[df["osm_id"].duplicated(keep=False)].sort_values("osm_id")
log(f"Rows participating in duplicate OSM IDs: {len(dup)}")
for _, row in dup[cols].head(30).iterrows():
    log(" | ".join(f"{c}={row[c]}" for c in cols))

out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"\nReport saved to: {out_path.resolve()}")
