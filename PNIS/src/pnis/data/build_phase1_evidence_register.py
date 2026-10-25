
from pathlib import Path
import csv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "phase1_evidence_register.csv"
)

EVIDENCE = [
    {
        "evidence_id": "EV001",
        "claim": "Ethiopia avocado production is available as an annual national time series for 2000–2024.",
        "source_file": "data/raw/public/faostat/avocado-production.csv",
        "evidence_type": "Public statistical data",
        "geographic_coverage": "Ethiopia, national",
        "pnis_use": "Provide historical national production context.",
        "limitations": "Does not establish production for a particular Sidama farm, district, or season.",
        "status": "Source identified; values require validation before analysis.",
    },
    {
        "evidence_id": "EV002",
        "claim": "Agriculture value added is available from the World Bank indicator dataset.",
        "source_file": "data/raw/public/world_bank/world_bank_agriculture_ethiopia.zip",
        "evidence_type": "Public macroeconomic data",
        "geographic_coverage": "Ethiopia, national",
        "pnis_use": "Optional national agriculture context.",
        "limitations": "Not avocado-specific and not a measure of supply-chain performance.",
        "status": "Source inspected; indicator metadata should accompany any reported value.",
    },
    {
        "evidence_id": "EV003",
        "claim": "An Ethiopia geographic data archive is available for potential road-network analysis.",
        "source_file": "data/raw/public/openstreetmap/ethiopia-latest-free.gpkg.zip",
        "evidence_type": "Public geographic data",
        "geographic_coverage": "Ethiopia",
        "pnis_use": "Potential input for mapping and transport-network preparation.",
        "limitations": "Road connectivity, coverage, access restrictions, and routing suitability have not yet been validated.",
        "status": "Archive identified; geographic content requires inspection.",
    },
    {
        "evidence_id": "EV004",
        "claim": "A 2026 study examines postharvest losses in Ethiopia's avocado value chain across multiple producing areas.",
        "source_file": "data/raw/real/ethiopia_avocado_postharvest_loss_multiregion_2026.pdf",
        "evidence_type": "Research publication",
        "geographic_coverage": "Multiple Ethiopian avocado-producing areas",
        "pnis_use": "Inform the research evidence base for loss mechanisms and possible scenarios.",
        "limitations": "Do not assume every reported percentage measures physical weight loss or applies to Sidama.",
        "status": "Text extracted; claims and measurement definitions must be checked against the paper.",
    },
    {
        "evidence_id": "EV005",
        "claim": "The Sidama–Gedeo study reports an average postharvest loss of 19.02% of total avocado harvest.",
        "source_file": "data/raw/real/sidama_gedeo_avocado_postharvest_loss_2026.pdf",
        "evidence_type": "Research finding",
        "geographic_coverage": "Sidama and Gedeo areas",
        "pnis_use": "Use as a published reference benchmark for clearly labeled sensitivity scenarios.",
        "limitations": "Not a measured loss rate for every farm or supply-chain stage. Avoid applying the percentage repeatedly and double-counting losses.",
        "status": "Reported in the extracted abstract; verify the definition and calculation in the original paper.",
    },
    {
        "evidence_id": "EV006",
        "claim": "The Sidama–Gedeo study reports a sample of 212 producers: 107 in Sidama and 105 in Gedeo.",
        "source_file": "data/raw/real/sidama_gedeo_avocado_postharvest_loss_2026.pdf",
        "evidence_type": "Research methodology",
        "geographic_coverage": "Sidama and Gedeo areas",
        "pnis_use": "Describe the study's producer sample and scope.",
        "limitations": "Study sample size is not the number of farms available to PNIS.",
        "status": "Reported in the extracted text; verify against the paper when citing.",
    },
    {
        "evidence_id": "EV007",
        "claim": "The Sidama–Gedeo study identifies harvest quantity, weather, disease, storage materials, and extension contact as factors associated with postharvest loss.",
        "source_file": "data/raw/real/sidama_gedeo_avocado_postharvest_loss_2026.pdf",
        "evidence_type": "Research finding",
        "geographic_coverage": "Sidama and Gedeo areas",
        "pnis_use": "Guide candidate variables for future data collection and scenario design.",
        "limitations": "Associations from the study are not proof of causation. Regression coding and coefficient interpretation require verification.",
        "status": "Reported in extracted regression text; detailed table verification remains necessary.",
    },
    {
        "evidence_id": "EV008",
        "claim": "The extracted text file consolidates text from both research PDFs.",
        "source_file": "data/processed/phase1_research_extracted.txt",
        "evidence_type": "Derived research artifact",
        "geographic_coverage": "Coverage of both source papers",
        "pnis_use": "Search and review research findings efficiently.",
        "limitations": "This is a derivative text extraction, not an independent source of evidence.",
        "status": "Extraction completed; consult original PDFs for important claims.",
    },
    {
        "evidence_id": "AS001",
        "claim": "A hypothetical 19.02% loss scenario may be included in the PNIS pilot.",
        "source_file": "EV005: Sidama–Gedeo study",
        "evidence_type": "Proposed scenario assumption",
        "geographic_coverage": "Pilot simulation only",
        "pnis_use": "Test a scenario using a published research benchmark.",
        "limitations": "Label as a scenario, not as a measured loss rate for a pilot farm.",
        "status": "Proposed; do not use as an observed operational value.",
    },
    {
        "evidence_id": "AS002",
        "claim": "Synthetic farms, vehicles, storage facilities, and buyer orders may be used to test the simulation before operational records are available.",
        "source_file": "PNIS pilot design",
        "evidence_type": "Synthetic pilot assumption",
        "geographic_coverage": "Explicitly simulated pilot",
        "pnis_use": "Test data flow, routing, simulation, and optimization logic.",
        "limitations": "Synthetic records must be visibly labeled and must not be presented as real farms or actual transactions.",
        "status": "Proposed; values and schema have not yet been finalized.",
    },
    {
        "evidence_id": "MD001",
        "claim": "Verified farm-level harvest quantities and harvest dates are not present in the six inventoried files.",
        "source_file": "Current Phase 1 inventory",
        "evidence_type": "Data gap assessment",
        "geographic_coverage": "PNIS pilot",
        "pnis_use": "Prioritize collection of farm-level harvest records.",
        "limitations": "This assessment covers only the files currently inventoried, not every possible external or future data source.",
        "status": "Gap identified in the current inventory.",
    },
    {
        "evidence_id": "MD002",
        "claim": "Verified operational records for vehicles, transport costs, cold storage capacity, buyer orders, and delivery outcomes are not present in the six inventoried files.",
        "source_file": "Current Phase 1 inventory",
        "evidence_type": "Data gap assessment",
        "geographic_coverage": "PNIS pilot",
        "pnis_use": "Define the operational data collection plan.",
        "limitations": "These gaps describe the current inventory; they do not prove that records are unavailable from stakeholders.",
        "status": "Gap identified in the current inventory.",
    },
]


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "evidence_id",
        "claim",
        "source_file",
        "evidence_type",
        "geographic_coverage",
        "pnis_use",
        "limitations",
        "status",
    ]

    with OUTPUT_PATH.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(EVIDENCE)

    print("=" * 72)
    print("PNIS PHASE 1 EVIDENCE REGISTER")
    print("=" * 72)
    print(f"Records written: {len(EVIDENCE)}")
    print(f"Output: {OUTPUT_PATH}")
    print()
    print("Record types:")

    counts = {}
    for record in EVIDENCE:
        category = record["evidence_type"]
        counts[category] = counts.get(category, 0) + 1

    for category, count in sorted(counts.items()):
        print(f"- {category}: {count}")

    print()
    print("Evidence register created.")
    print("Research findings, proposed assumptions, and data gaps")
    print("are recorded separately.")


if __name__ == "__main__":
    main()
