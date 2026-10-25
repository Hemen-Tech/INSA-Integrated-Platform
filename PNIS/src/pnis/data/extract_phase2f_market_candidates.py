
from pathlib import Path
import pandas as pd

ROOT = Path.cwd()
SOURCE = ROOT / "data/processed/phase2f_candidate_review_register.csv"
OUTPUT = ROOT / "data/processed/phase2f_market_candidates_review.csv"
SUMMARY = ROOT / "data/processed/phase2f_market_candidates_summary.txt"

if not SOURCE.exists():
    raise FileNotFoundError(f"Missing input: {SOURCE}")

df = pd.read_csv(SOURCE, dtype=str, keep_default_na=False)

markets = df[
    df["review_group"].eq("MARKET_CANDIDATE")
].copy()

# Keep the original columns and append reviewer-controlled fields.
markets["market_identity_verified"] = "NO"
markets["currently_operating_verified"] = "NO"
markets["coordinate_verified"] = "NO"
markets["evidence_source"] = ""
markets["review_notes"] = ""

markets.to_csv(OUTPUT, index=False, encoding="utf-8-sig")

lines = [
    "PHASE 2F — MARKET CANDIDATE REVIEW",
    "=" * 60,
    f"Input register: {SOURCE}",
    f"Marketplace candidates: {len(markets)}",
    f"Output: {OUTPUT}",
    "",
    "CANDIDATE RECORDS",
    "-" * 60,
]

for _, row in markets.iterrows():
    lines.append(
        f"ID={row.get('candidate_record_id', '')} | "
        f"OSM={row.get('osm_id', '')} | "
        f"Name={row.get('name', '')} | "
        f"Layer={row.get('source_layer', '')} | "
        f"Class={row.get('fclass', '')}"
    )

lines += [
    "",
    "CONTROL",
    "-" * 60,
    "All candidates remain unverified.",
    "Do not use for operational routing until location and identity are checked.",
]

SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("Marketplace review list created.")
print(f"Records: {len(markets)}")
print(f"CSV: {OUTPUT}")
print(f"Summary: {SUMMARY}")
