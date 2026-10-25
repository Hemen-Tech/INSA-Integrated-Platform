
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio


ROOT = Path.cwd()
SOURCE = ROOT / "data/processed/geographic/ethiopia.gpkg"
OUT = ROOT / "data/processed"

# Sidama boundary bounds in longitude/latitude, expanded by
# approximately 5 km. This is a discovery window, not a new boundary.
BBOX = (37.85, 6.09, 39.19, 7.22)

REPORT_TXT = OUT / "phase2f_facility_source_inventory.txt"
REPORT_JSON = OUT / "phase2f_facility_source_inventory.json"
CANDIDATES_CSV = OUT / "phase2f_osm_facility_candidates.csv"

LAYER_KEYWORDS = (
    "poi", "place", "transport", "pofw",
    "traffic", "building", "shop", "landuse",
)

SEARCH_TERMS = (
    "market", "farm", "warehouse", "collect",
    "cooperative", "agric", "storage", "wholesale",
    "food", "grain", "produce", "rural",
    "village", "town", "marketplace", "supermarket",
    "shop", "industrial", "depot", "distribution",
)


def safe_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    if not SOURCE.exists():
        raise FileNotFoundError(f"GeoPackage not found: {SOURCE}")

    print("=" * 76)
    print("PHASE 2F — FACILITY SOURCE INVENTORY")
    print("=" * 76)
    print(f"Source: {SOURCE}")
    print("Mode: read-only inspection")
    print(f"Discovery bounding box: {BBOX}")

    layer_table = pyogrio.list_layers(SOURCE)
    inventory = []
    report_lines = [
        "PHASE 2F — FACILITY SOURCE INVENTORY",
        "=" * 76,
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Source: {SOURCE}",
        f"Discovery bounding box: {BBOX}",
        "",
        "SOURCE LAYERS",
        "-" * 76,
    ]

    for layer_row in layer_table:
        layer_name = str(layer_row[0])
        geometry_type = str(layer_row[1]) if len(layer_row) > 1 else "unknown"

        try:
            info = pyogrio.read_info(SOURCE, layer=layer_name)
            fields = list(info.get("fields", []))
            feature_count = info.get("features")
            crs = str(info.get("crs"))
            error = None
        except Exception as exc:
            fields = []
            feature_count = None
            crs = None
            error = str(exc)

        inventory.append({
            "layer": layer_name,
            "geometry_type": geometry_type,
            "feature_count": feature_count,
            "crs": crs,
            "fields": fields,
            "metadata_error": error,
        })

        report_lines.append(
            f"{layer_name} | geometry={geometry_type} "
            f"| features={feature_count} | CRS={crs}"
        )

        if any(word in layer_name.lower() for word in LAYER_KEYWORDS):
            report_lines.append(f"  Fields: {', '.join(fields)}")

        if error:
            report_lines.append(f"  Metadata error: {error}")

    candidate_layers = [
        item for item in inventory
        if any(word in item["layer"].lower() for word in LAYER_KEYWORDS)
        and item["geometry_type"].lower() not in {"none", "unknown"}
    ]

    all_candidates = []
    layer_read_results = []

    report_lines += [
        "",
        "FACILITY-RELATED LAYER INSPECTION",
        "-" * 76,
    ]

    for item in candidate_layers:
        layer_name = item["layer"]
        print(f"\nInspecting: {layer_name}")

        try:
            # Read only the geographic discovery window.
            # This does not establish that a feature is a verified facility.
            gdf = gpd.read_file(
                SOURCE,
                layer=layer_name,
                engine="pyogrio",
                bbox=BBOX,
            )

            if gdf.empty:
                report_lines.append(f"{layer_name}: 0 features in discovery window")
                layer_read_results.append({
                    "layer": layer_name,
                    "features_in_bbox": 0,
                    "status": "completed",
                })
                continue

            report_lines.append(
                f"\n{layer_name}: {len(gdf):,} features in discovery window"
            )
            report_lines.append(
                "  Available fields: " + ", ".join(map(str, gdf.columns))
            )

            # Inspect category/name-like fields without assuming a fixed schema.
            text_columns = [
                col for col in gdf.columns
                if col != gdf.geometry.name
                and (
                    any(k in str(col).lower()
                        for k in ("name", "class", "type", "amenity",
                                  "shop", "office", "industrial",
                                  "fclass", "code", "operator"))
                )
            ]

            if text_columns:
                report_lines.append("  Category/name field summaries:")
                for col in text_columns:
                    values = (
                        gdf[col].fillna("").astype(str).str.strip()
                    )
                    top = values[values != ""].value_counts().head(12)
                    report_lines.append(f"    {col}:")
                    for value, count in top.items():
                        report_lines.append(f"      {value}: {count}")

            # Search across textual attributes for possible facility leads.
            # These are unverified candidates, not confirmed sites.
            searchable_columns = [
                col for col in gdf.columns
                if col != gdf.geometry.name
                and (
                    pd.api.types.is_object_dtype(gdf[col])
                    or pd.api.types.is_string_dtype(gdf[col])
                )
            ]

            if searchable_columns:
                combined = (
                    gdf[searchable_columns]
                    .fillna("")
                    .astype(str)
                    .agg(" ".join, axis=1)
                    .str.lower()
                )
                pattern = "|".join(SEARCH_TERMS)
                mask = combined.str.contains(pattern, regex=True, na=False)
                matches = gdf.loc[mask].copy()

                report_lines.append(
                    f"  Text-matched possible candidates: {len(matches):,}"
                )

                if not matches.empty:
                    matches["source_layer"] = layer_name
                    matches["candidate_match_text"] = combined.loc[matches.index]
                    matches["candidate_status"] = (
                        "unverified_osm_candidate_requires_review"
                    )

                    # Save geometry as WKT for a portable CSV review file.
                    matches["geometry_wkt"] = matches.geometry.to_wkt()
                    matches.drop(
                        columns=[matches.geometry.name],
                        errors="ignore",
                    ).to_csv(
                        CANDIDATES_CSV,
                        mode="a" if all_candidates else "w",
                        header=not all_candidates,
                        index=False,
                        encoding="utf-8",
                    )
                    all_candidates.extend(matches.drop(
                        columns=[matches.geometry.name],
                        errors="ignore",
                    ).to_dict("records"))

            layer_read_results.append({
                "layer": layer_name,
                "features_in_bbox": len(gdf),
                "status": "completed",
                "fields": list(map(str, gdf.columns)),
            })

        except Exception as exc:
            report_lines.append(f"{layer_name}: READ ERROR — {exc}")
            layer_read_results.append({
                "layer": layer_name,
                "status": "error",
                "error": str(exc),
            })

    report_lines += [
        "",
        "INTERPRETATION",
        "-" * 76,
        "OSM text matches are discovery leads only.",
        "They are not confirmed farms, collection points, markets, or warehouses.",
        "Names and tags must be reviewed, coordinates checked, and sources documented.",
        "No road graph or Phase 2C/2E output was modified.",
        "",
        f"Candidate CSV: {CANDIDATES_CSV}",
        f"Text report: {REPORT_TXT}",
        f"JSON report: {REPORT_JSON}",
    ]

    REPORT_TXT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(SOURCE),
        "bbox_wgs84": BBOX,
        "layers": inventory,
        "candidate_layers_inspected": layer_read_results,
        "candidate_csv": str(CANDIDATES_CSV),
        "candidate_rows": len(all_candidates),
        "interpretation": (
            "OSM matches are unverified discovery candidates, not verified facilities."
        ),
        "source_modified": False,
        "phase2c_phase2e_outputs_modified": False,
    }

    REPORT_JSON.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    print("\n" + "=" * 76)
    print("PHASE 2F SOURCE INVENTORY FINISHED")
    print("=" * 76)
    print(f"Layers in source: {len(inventory)}")
    print(f"Candidate layers inspected: {len(candidate_layers)}")
    print(f"Candidate rows: {len(all_candidates)}")
    print(f"Text report: {REPORT_TXT}")
    print(f"JSON report: {REPORT_JSON}")
    if all_candidates:
        print(f"Candidate CSV: {CANDIDATES_CSV}")
    print("\nReview candidate records before using them for operational routing.")


if __name__ == "__main__":
    main()
