from pathlib import Path
import geopandas as gpd

path = Path("data/processed/phase2c_v2_sidama_buffered_roads.gpkg")
layer = "sidama_buffered_roads_v2"

print("FILE EXISTS:", path.exists())
if not path.exists():
    raise SystemExit("ERROR: Phase 2C v2 GeoPackage not found.")

print("\nAVAILABLE LAYERS:")
import pyogrio
print(pyogrio.list_layers(path))

print("\nROAD LAYER SAMPLE:")
roads = gpd.read_file(path, layer=layer, rows=5)
print("CRS:", roads.crs)
print("COLUMNS:")
for col in roads.columns:
    print(" ", col)
print("\nSAMPLE:")
print(roads.drop(columns="geometry", errors="ignore").head(5).to_string(index=False))
print("\nGEOMETRY TYPES:")
print(roads.geometry.geom_type.value_counts(dropna=False).to_string())
