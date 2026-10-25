
from pathlib import Path
import csv
import json
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = PROJECT_ROOT / "data"
OUTPUT_ROOT = DATA_ROOT / "processed"

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

SOURCE_NOTES = {
    "avocado-production.csv": {
        "source_type": "Public statistical data",
        "coverage": "Ethiopia, national annual production",
        "intended_use": "Historical national production context",
        "limitations": "Not farm-level or Sidama-specific harvest data.",
    },
    "world_bank_agriculture_ethiopia.zip": {
        "source_type": "Public statistical data",
        "coverage": "Ethiopia, agriculture value added indicator",
        "intended_use": "Macroeconomic agriculture context",
        "limitations": "Not avocado-specific or operational supply-chain data.",
    },
    "ethiopia-latest-free.gpkg.zip": {
        "source_type": "Public geographic data",
        "coverage": "Ethiopia geographic and transport features",
        "intended_use": "Potential road-network and geographic analysis",
        "limitations": "Road suitability, completeness, and routing usability require validation.",
    },
    "ethiopia_avocado_postharvest_loss_multiregion_2026.pdf": {
        "source_type": "Research publication",
        "coverage": "Multiple Ethiopian avocado-producing areas",
        "intended_use": "Evidence on postharvest loss and its drivers",
        "limitations": "Study-level results are not individual farm records.",
    },
    "sidama_gedeo_avocado_postharvest_loss_2026.pdf": {
        "source_type": "Research publication",
        "coverage": "Sidama and Gedeo areas",
        "intended_use": "Local evidence on avocado postharvest loss",
        "limitations": "Study findings should not be treated as measurements for every farm.",
    },
    "phase1_research_extracted.txt": {
        "source_type": "Processed research text",
        "coverage": "Text extracted from the two research PDFs",
        "intended_use": "Searchable research review and evidence extraction",
        "limitations": "Secondary extraction; verify important claims against the original PDF.",
    },
}


def inspect_csv(path):
    try:
        with path.open(
            "r", encoding="utf-8-sig", newline=""
        ) as file:
            reader = csv.reader(file)
            header = next(reader, [])
            sample_rows = []
            for row in reader:
                sample_rows.append(row)
                if len(sample_rows) >= 3:
                    break

        return {
            "readable": True,
            "columns": len(header),
            "column_names": header,
            "sample_rows_checked": len(sample_rows),
            "inspection_note": "Header and up to three data rows inspected.",
        }
    except Exception as exc:
        return {
            "readable": False,
            "inspection_note": str(exc),
        }


def inspect_zip(path):
    try:
        with zipfile.ZipFile(path, "r") as archive:
            members = archive.infolist()
            bad_member = archive.testzip()

        return {
            "readable": True,
            "archive_members": len(members),
            "archive_contents": [
                {
                    "name": item.filename,
                    "uncompressed_bytes": item.file_size,
                }
                for item in members[:30]
            ],
            "integrity_check": (
                "passed" if bad_member is None
                else f"failed at {bad_member}"
            ),
        }
    except Exception as exc:
        return {
            "readable": False,
            "inspection_note": str(exc),
        }


def main():
    inventory = []

    for path in sorted(DATA_ROOT.rglob("*")):
        if not path.is_file():
            continue

        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        record = {
            "file_name": path.name,
            "relative_path": relative_path,
            "file_size_bytes": path.stat().st_size,
            "source_type": "Unclassified",
            "coverage": "Not yet documented",
            "intended_use": "Needs review",
            "limitations": "Needs review",
            "inspection": {},
        }

        record.update(SOURCE_NOTES.get(path.name, {}))

        suffix = path.suffix.lower()

        if suffix == ".csv":
            record["inspection"] = inspect_csv(path)

        elif suffix == ".zip":
            record["inspection"] = inspect_zip(path)

        elif suffix == ".pdf":
            record["inspection"] = {
                "readable": path.stat().st_size > 0,
                "inspection_note": (
                    "File exists and is non-empty; PDF content "
                    "was inspected separately."
                ),
            }

        elif suffix == ".txt":
            record["inspection"] = {
                "readable": path.stat().st_size > 0,
                "inspection_note": (
                    "File exists and is non-empty; extracted text "
                    "was reviewed separately."
                ),
            }

        inventory.append(record)

    json_path = OUTPUT_ROOT / "phase1_data_inventory.json"
    csv_path = OUTPUT_ROOT / "phase1_data_inventory.csv"

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(inventory, file, indent=2, ensure_ascii=False)

    fieldnames = [
        "file_name",
        "relative_path",
        "file_size_bytes",
        "source_type",
        "coverage",
        "intended_use",
        "limitations",
    ]

    with csv_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for record in inventory:
            writer.writerow({
                key: record.get(key, "")
                for key in fieldnames
            })

    print("=" * 72)
    print("PNIS PHASE 1 DATA INVENTORY")
    print("=" * 72)
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Files inventoried: {len(inventory)}")
    print(f"CSV inventory: {csv_path}")
    print(f"Detailed JSON: {json_path}")
    print()
    print("Files found:")

    for record in inventory:
        print(
            f"- {record['relative_path']} "
            f"({record['file_size_bytes']:,} bytes)"
        )

    print()
    print("Inventory generation complete.")
    print("This inventory documents sources; it does not validate")
    print("the scientific accuracy of every source or claim.")


if __name__ == "__main__":
    main()
