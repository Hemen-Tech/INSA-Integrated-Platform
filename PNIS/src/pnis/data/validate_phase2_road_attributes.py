
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[3]
GPKG = ROOT / "data" / "processed" / "geographic" / "ethiopia.gpkg"
OUTPUT_DIR = ROOT / "data" / "processed"
ROAD_TABLE = "gis_osm_roads_free"
ADMIN_TABLE = "gis_osm_adminareas_a_free"


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def main() -> None:
    print("=" * 72)
    print("PNIS PHASE 2A — ROAD ATTRIBUTE VALIDATION")
    print("=" * 72)

    if not GPKG.exists():
        raise FileNotFoundError(f"GeoPackage not found: {GPKG}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "project": "Perishable Network Intelligence System",
        "phase": "Phase 2A — Road attribute validation",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": str(GPKG.relative_to(ROOT)),
        "source_size_bytes": GPKG.stat().st_size,
        "checks": {},
        "warnings": [],
    }

    # Open the source in read-only mode.
    connection = sqlite3.connect(
        GPKG.as_uri() + "?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row

    try:
        cursor = connection.cursor()

        tables = {
            row["name"]
            for row in cursor.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type IN ('table', 'view')
            """)
        }

        if ROAD_TABLE not in tables:
            raise RuntimeError(
                f"Required road layer missing: {ROAD_TABLE}"
            )

        if "gpkg_contents" not in tables:
            raise RuntimeError("Missing gpkg_contents metadata table.")

        # 1. Database and road-layer metadata.
        quick_check = cursor.execute(
            "PRAGMA quick_check"
        ).fetchone()[0]

        road_q = quote_identifier(ROAD_TABLE)
        columns = [
            row["name"]
            for row in cursor.execute(
                f"PRAGMA table_info({road_q})"
            )
        ]
        column_set = set(columns)

        total_roads = cursor.execute(
            f"SELECT COUNT(*) FROM {road_q}"
        ).fetchone()[0]

        report["checks"]["sqlite_quick_check"] = quick_check
        report["checks"]["road_layer"] = ROAD_TABLE
        report["checks"]["road_record_count"] = total_roads
        report["checks"]["road_columns"] = columns

        print(f"\nSource: {GPKG}")
        print(f"SQLite quick check: {quick_check}")
        print(f"Road records: {total_roads:,}")
        print(f"Fields: {', '.join(columns)}")

        # 2. Coordinate reference system and layer bounds.
        content = cursor.execute("""
            SELECT table_name, identifier, srs_id,
                   min_x, min_y, max_x, max_y
            FROM gpkg_contents
            WHERE table_name = ?
        """, (ROAD_TABLE,)).fetchone()

        if content:
            report["checks"]["road_layer_metadata"] = dict(content)

        geometry_meta = cursor.execute("""
            SELECT column_name, geometry_type_name, srs_id
            FROM gpkg_geometry_columns
            WHERE table_name = ?
        """, (ROAD_TABLE,)).fetchone()

        if geometry_meta:
            report["checks"]["road_geometry_metadata"] = dict(
                geometry_meta
            )

        # 3. Spatial-index table availability.
        index_tables = sorted(
            name for name in tables
            if name.lower().startswith(
                f"rtree_{ROAD_TABLE.lower()}_"
            )
        )

        report["checks"]["spatial_index_tables"] = index_tables
        report["checks"]["spatial_index_available"] = bool(
            index_tables
        )

        print("\n--- Spatial index ---")
        print(f"R-tree tables: {index_tables or 'None found'}")

        if not index_tables:
            report["warnings"].append(
                "No road R-tree spatial-index table was found. "
                "Spatial filtering may require a full scan."
            )

        # 4. Audit null and empty values in routing-related fields.
        field_results = {}

        for field in [
            "osm_id", "fclass", "oneway", "maxspeed",
            "bridge", "tunnel", "layer", "name", "ref",
        ]:
            if field not in column_set:
                field_results[field] = {
                    "available": False
                }
                continue

            field_q = quote_identifier(field)

            result = cursor.execute(f"""
                SELECT
                    SUM(CASE WHEN {field_q} IS NULL THEN 1 ELSE 0 END),
                    SUM(CASE
                        WHEN {field_q} IS NOT NULL
                         AND TRIM(CAST({field_q} AS TEXT)) = ''
                        THEN 1 ELSE 0
                    END)
                FROM {road_q}
            """).fetchone()

            null_count = result[0] or 0
            empty_count = result[1] or 0

            field_results[field] = {
                "available": True,
                "null_count": null_count,
                "empty_count": empty_count,
                "null_percent": round(
                    null_count / total_roads * 100, 4
                ) if total_roads else None,
                "empty_percent": round(
                    empty_count / total_roads * 100, 4
                ) if total_roads else None,
            }

        report["checks"]["field_completeness"] = field_results

        print("\n--- Field completeness ---")
        for field, values in field_results.items():
            if not values["available"]:
                print(f"{field}: FIELD MISSING")
            else:
                print(
                    f"{field}: null={values['null_count']:,}, "
                    f"empty={values['empty_count']:,}, "
                    f"null%={values['null_percent']}"
                )

        # 5. Categorical distributions.
        categorical_results = {}

        for field in ["fclass", "oneway", "bridge", "tunnel"]:
            if field not in column_set:
                continue

            field_q = quote_identifier(field)
            rows = cursor.execute(f"""
                SELECT COALESCE(
                    NULLIF(TRIM(CAST({field_q} AS TEXT)), ''),
                    '<NULL_OR_EMPTY>'
                ) AS category,
                COUNT(*) AS count
                FROM {road_q}
                GROUP BY category
                ORDER BY count DESC, category
            """).fetchall()

            categorical_results[field] = {
                row["category"]: row["count"]
                for row in rows
            }

            print(f"\n--- Distribution: {field} ---")
            for row in rows[:30]:
                print(f"{row['category']}: {row['count']:,}")

        report["checks"]["categorical_distributions"] = (
            categorical_results
        )

        # 6. Speed values. A value of zero is not a known speed limit.
        speed_results = {}

        if "maxspeed" in column_set:
            speed_q = quote_identifier("maxspeed")

            rows = cursor.execute(f"""
                SELECT CAST({speed_q} AS TEXT) AS speed_value,
                       COUNT(*) AS count
                FROM {road_q}
                GROUP BY CAST({speed_q} AS TEXT)
                ORDER BY count DESC
            """).fetchall()

            speed_results = {
                str(row["speed_value"]): row["count"]
                for row in rows
            }

            numeric_speed = cursor.execute(f"""
                SELECT
                    SUM(CASE
                        WHEN typeof({speed_q}) IN ('integer', 'real')
                         AND {speed_q} > 0
                        THEN 1 ELSE 0
                    END) AS positive_speed,
                    SUM(CASE
                        WHEN {speed_q} = 0 THEN 1 ELSE 0
                    END) AS zero_speed,
                    SUM(CASE
                        WHEN {speed_q} IS NULL THEN 1 ELSE 0
                    END) AS null_speed
                FROM {road_q}
            """).fetchone()

            report["checks"]["speed_summary"] = {
                "positive_numeric_speed_count": (
                    numeric_speed["positive_speed"] or 0
                ),
                "zero_speed_count": numeric_speed["zero_speed"] or 0,
                "null_speed_count": numeric_speed["null_speed"] or 0,
                "interpretation": (
                    "Zero or missing values must not be treated as "
                    "measured travel speeds."
                ),
            }

            print("\n--- Speed summary ---")
            for key, value in report["checks"]["speed_summary"].items():
                print(f"{key}: {value}")

        report["checks"]["speed_value_distribution"] = speed_results

        # 7. Duplicate OSM IDs.
        if "osm_id" in column_set:
            duplicate_summary = cursor.execute(f"""
                SELECT COUNT(*) AS duplicate_id_groups,
                       COALESCE(SUM(n - 1), 0) AS excess_records
                FROM (
                    SELECT COUNT(*) AS n
                    FROM {road_q}
                    WHERE osm_id IS NOT NULL AND TRIM(osm_id) <> ''
                    GROUP BY osm_id
                    HAVING COUNT(*) > 1
                )
            """).fetchone()

            duplicate_examples = cursor.execute(f"""
                SELECT osm_id, COUNT(*) AS count
                FROM {road_q}
                WHERE osm_id IS NOT NULL AND TRIM(osm_id) <> ''
                GROUP BY osm_id
                HAVING COUNT(*) > 1
                ORDER BY count DESC, osm_id
                LIMIT 20
            """).fetchall()

            report["checks"]["duplicate_osm_ids"] = {
                "duplicate_id_groups": (
                    duplicate_summary["duplicate_id_groups"]
                ),
                "excess_records": duplicate_summary["excess_records"],
                "examples": [dict(row) for row in duplicate_examples],
            }

            print("\n--- Duplicate OSM IDs ---")
            print(
                "Duplicate ID groups:",
                duplicate_summary["duplicate_id_groups"],
            )
            print(
                "Excess records:",
                duplicate_summary["excess_records"],
            )

        # 8. Sidama boundary attributes, if the expected layer exists.
        if ADMIN_TABLE in tables:
            admin_q = quote_identifier(ADMIN_TABLE)
            admin_columns = [
                row["name"]
                for row in cursor.execute(
                    f"PRAGMA table_info({admin_q})"
                )
            ]

            report["checks"]["admin_layer_columns"] = admin_columns

            print("\n--- Administrative layer fields ---")
            print(", ".join(admin_columns))

            likely_fields = [
                field for field in admin_columns
                if field.lower() in {
                    "osm_id", "name", "name_en", "admin_level",
                    "boundary", "type", "fid"
                }
            ]

            if likely_fields:
                selected_sql = ", ".join(
                    quote_identifier(field)
                    for field in likely_fields
                )
                sample_rows = cursor.execute(
                    f"SELECT {selected_sql} FROM {admin_q} "
                    "WHERE LOWER(CAST(name AS TEXT)) = 'sidama' "
                    "LIMIT 10"
                    if "name" in admin_columns
                    else f"SELECT {selected_sql} FROM {admin_q} LIMIT 0"
                ).fetchall()

                report["checks"]["sidama_admin_attribute_samples"] = [
                    dict(row) for row in sample_rows
                ]

                for row in sample_rows:
                    print(dict(row))

        # 9. Write a reproducible report.
        json_path = OUTPUT_DIR / "phase2_road_attribute_audit.json"
        text_path = OUTPUT_DIR / "phase2_road_attribute_audit.txt"

        json_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        lines = [
            "PNIS PHASE 2A — ROAD ATTRIBUTE VALIDATION",
            "=" * 55,
            f"Generated UTC: {report['generated_utc']}",
            f"Source: {report['source_file']}",
            f"SQLite quick check: {quick_check}",
            f"Road records: {total_roads:,}",
            "",
            "FIELD COMPLETENESS",
        ]

        for field, values in field_results.items():
            lines.append(f"{field}: {values}")

        lines.extend(["", "WARNINGS"])
        lines.extend(
            report["warnings"] or ["No preliminary warnings."]
        )
        lines.extend([
            "",
            "LIMITATION",
            "This audit checks metadata and attributes. It does not",
            "establish geometric validity, road connectivity, or",
            "accurate travel times.",
        ])

        text_path.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        print("\n--- Reports written ---")
        print(json_path.relative_to(ROOT))
        print(text_path.relative_to(ROOT))
        print("\nAudit completed.")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
