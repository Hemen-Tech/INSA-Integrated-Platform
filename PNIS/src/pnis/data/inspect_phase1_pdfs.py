
from pathlib import Path
from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PDF_FOLDER = PROJECT_ROOT / "data" / "raw" / "real"

pdf_files = sorted(PDF_FOLDER.glob("*.pdf"))

print("=" * 70)
print("PNIS PHASE 1: PDF INSPECTION")
print("=" * 70)
print(f"PDF folder: {PDF_FOLDER}")
print(f"PDF count: {len(pdf_files)}")

for pdf_path in pdf_files:
    print("\n" + "-" * 70)
    print(f"FILE: {pdf_path.name}")

    try:
        reader = PdfReader(str(pdf_path))
        print(f"Pages: {len(reader.pages)}")

        first_page_text = reader.pages[0].extract_text() or ""
        preview = " ".join(first_page_text.split())[:500]

        print("First-page text preview:")
        print(preview if preview else "[No extractable text found]")

    except Exception as error:
        print(f"Could not inspect PDF: {error}")

print("\nPDF inspection complete.")
