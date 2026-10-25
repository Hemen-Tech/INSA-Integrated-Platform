import pandas as pd
from pathlib import Path

base = Path("data/processed")
files = [
    base / "phase2f_osm_facility_candidates.csv",
    base / "phase2f_candidate_review_register.csv",
]

for path in files:
    print("\n" + "=" * 76)
    print("FILE:", path.resolve())

    if not path.exists():
        print("NOT FOUND")
        continue

    df = pd.read_csv(path, dtype=str).fillna("")
    print("ROWS:", len(df))
    print("COLUMNS:", list(df.columns))

    if "fclass" in df.columns:
        market = df[df["fclass"].str.lower().eq("marketplace")]
        print("MARKETPLACE ROWS:", len(market))
        if not market.empty:
            print("FIRST MARKETPLACE RECORD:")
            print(market.iloc[0].to_dict())
    else:
        print("No fclass column available for marketplace filtering.")

print("\nDiagnostic complete. No files were changed.")
