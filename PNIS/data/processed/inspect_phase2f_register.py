import pandas as pd
from pathlib import Path

p = Path("data/processed/phase2f_candidate_review_register.csv")
df = pd.read_csv(p, dtype=str).fillna("")

print("FILE:", p.resolve())
print("ROWS:", len(df))
print("\nACTUAL CSV COLUMNS:")
for c in df.columns:
    print(f"  {c!r}")

print("\nFIRST 5 RECORDS (actual column/value pairs):")
for i, row in df.head(5).iterrows():
    print(f"\nROW {i + 1}")
    for c in df.columns:
        value = row[c]
        print(f"  {c}: {value[:180]}")

print("\nMARKETPLACE FILTER CHECK:")
for c in df.columns:
    matches = df[c].str.lower().eq("marketplace").sum()
    if matches:
        print(f"  {c}: {matches} exact marketplace matches")
