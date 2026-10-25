
from pathlib import Path
import csv
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[3]

SOURCE_FOLDERS = [
    PROJECT_ROOT / "data" / "raw" / "public" / "faostat",
    PROJECT_ROOT / "data" / "raw" / "public" / "world_bank",
    PROJECT_ROOT / "data" / "raw" / "public" / "openstreetmap",
    PROJECT_ROOT / "data" / "raw" / "real",
]

MAX_SAMPLE_ROWS = 3


def inspect_csv(path: Path) -> None:
    print("\n" + "=" * 80)
    print(f"CSV FILE: {path.relative_to(PROJECT_ROOT)}")
    print(f"Size: {path.stat().st_size / 1_000_000:.2f} MB")

    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]

    for encoding in encodings:
        try:
            with path.open(
                "r", encoding=encoding, newline=""
            ) as file:
                reader = csv.reader(file)
                header = next(reader, None)

                if not header:
                    print("WARNING: File is empty.")
                    return

                print(f"Encoding: {encoding}")
                print(f"Column count: {len(header)}")
                print("\nColumns:")

                for number, column in enumerate(header, start=1):
                    print(f"  {number:>3}. {column}")

                print(f"\nFirst {MAX_SAMPLE_ROWS} data rows:")

                for row_number, row in enumerate(
                    reader, start=1
                ):
                    if row_number > MAX_SAMPLE_ROWS:
                        break

                    print(f"  Row {row_number}: {row[:8]}")

            return

        except UnicodeDecodeError:
            continue

    print("ERROR: Could not read this CSV with the tested encodings.")


def inspect_zip(path: Path) -> None:
    print("\n" + "=" * 80)
    print(f"ZIP FILE: {path.relative_to(PROJECT_ROOT)}")
    print(f"Size: {path.stat().st_size / 1_000_000:.2f} MB")

    try:
        with zipfile.ZipFile(path, "r") as archive:
            members = archive.infolist()
            print(f"Files inside ZIP: {len(members)}")

            for member in members[:30]:
                print(
                    f"  {member.filename} "
                    f"({member.file_size / 1_000_000:.2f} MB)"
                )

            if len(members) > 30:
                print("  ... additional entries omitted")

            bad_member = archive.testzip()

            if bad_member:
                print(f"WARNING: ZIP integrity issue: {bad_member}")
            else:
                print("ZIP integrity check: PASSED")

    except zipfile.BadZipFile:
        print("ERROR: This file is not a valid ZIP archive.")


def inspect_pdf(path: Path) -> None:
    print("\n" + "=" * 80)
    print(f"PDF FILE: {path.relative_to(PROJECT_ROOT)}")
    print(f"Size: {path.stat().st_size / 1_000_000:.2f} MB")

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        print(f"Pages: {len(reader.pages)}")
        print(f"Encrypted: {reader.is_encrypted}")

        if reader.is_encrypted:
            print("Text preview skipped: PDF is encrypted.")
            return

        text = "\n".join(
            (page.extract_text() or "")
            for page in reader.pages[:2]
        )

        if text.strip():
            print("\nText preview from first two pages:")
            print(text[:1800])
        else:
            print(
                "No extractable text found. "
                "The PDF may contain scanned page images."
            )

    except ImportError:
        print(
            "PDF inspection skipped: pypdf is not installed. "
            "Run: python -m pip install pypdf"
        )
    except Exception as error:
        print(f"PDF inspection error: {error}")


def main() -> None:
    print("=" * 80)
    print("PNIS PHASE 1 — SOURCE FILE INSPECTION")
    print("=" * 80)
    print(f"Project root: {PROJECT_ROOT}")

    if not PROJECT_ROOT.exists():
        print("ERROR: Project root does not exist.")
        return

    files_found = 0

    for folder in SOURCE_FOLDERS:
        print(f"\n\nFOLDER: {folder.relative_to(PROJECT_ROOT)}")

        if not folder.exists():
            print("WARNING: Folder does not exist.")
            continue

        files = sorted(
            item for item in folder.rglob("*")
            if item.is_file()
        )

        if not files:
            print("No files found.")
            continue

        for path in files:
            files_found += 1
            suffix = path.suffix.lower()

            if suffix == ".csv":
                inspect_csv(path)
            elif suffix == ".zip":
                inspect_zip(path)
            elif suffix == ".pdf":
                inspect_pdf(path)
            else:
                print(
                    f"\nOTHER FILE: "
                    f"{path.relative_to(PROJECT_ROOT)}"
                )

    print("\n" + "=" * 80)
    print(f"Total files inspected: {files_found}")
    print("Inspection finished. No source files were modified.")
    print("=" * 80)


if __name__ == "__main__":
    main()
