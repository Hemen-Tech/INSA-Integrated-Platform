
from pathlib import Path
from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PDF_FOLDER = PROJECT_ROOT / "data" / "raw" / "real"
OUTPUT_FOLDER = PROJECT_ROOT / "data" / "processed"
OUTPUT_FILE = OUTPUT_FOLDER / "phase1_research_extracted.txt"

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

pdf_files = sorted(PDF_FOLDER.glob("*.pdf"))

if not pdf_files:
    raise FileNotFoundError(f"No PDF files found in {PDF_FOLDER}")

with OUTPUT_FILE.open("w", encoding="utf-8") as output:
    output.write("PNIS PHASE 1: RESEARCH EXTRACTION\n")
    output.write("=" * 80 + "\n")

    for pdf_path in pdf_files:
        print(f"Extracting: {pdf_path.name}")
        reader = PdfReader(str(pdf_path))

        output.write(f"\n\nSOURCE: {pdf_path.name}\n")
        output.write(f"PAGES: {len(reader.pages)}\n")
        output.write("=" * 80 + "\n")

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            output.write(f"\n--- PAGE {page_number} ---\n")
            output.write(text + "\n")

print(f"\nExtraction complete.")
print(f"PDFs processed: {len(pdf_files)}")
print(f"Report saved to: {OUTPUT_FILE}")
