# PNIS Dashboard Starter

A Streamlit-first implementation of the PNIS home dashboard: a data-aware agricultural geospatial intelligence workspace for Sidama, Ethiopia.

> This starter uses `app.py` because that was the requested entry point. It is not a React/Next.js application. It provides an executable Python dashboard now; the data adapter and business rules can later be moved behind an API and consumed by a React + TypeScript frontend if that remains the desired production architecture.

## Included

- `app.py` — dashboard, data adapters, map, KPI panels, chart rail, filters and CSV export.
- `pnis_logo.png` — the supplied road emblem used in the sidebar.
- `pnis_background.png` — the dark PNIS banner used as the global page background.
- `requirements.txt` — Python dependencies.

## Run locally

Use the existing virtual environment at the PNIS project root. Python 3.13 is a reasonable choice for this geospatial stack; this starter does not require replacing any global Python installation.

```powershell
cd C:\Users\tadesse.yilma\INSA-Integrated-Platform\PNIS
.\.venv\Scripts\python.exe -m streamlit run .\pnis_dashboard\app.py --server.port 8503
```

Open `http://localhost:8503`. The sidebar marks this app as **Preview — In Development** and links to PROBE and Drought Intelligence. `PROBE_URL` and `DROUGHT_URL` can override their default destination URLs:

```powershell
$env:PROBE_URL = "http://localhost:3000/"
$env:DROUGHT_URL = "http://localhost:5501/"
.\.venv\Scripts\python.exe -m streamlit run .\pnis_dashboard\app.py --server.port 8503
```

The app uses the parent PNIS project's `data/processed/` files when that data directory exists. Its `requirements.txt` lists the dependencies; use the existing PNIS virtual environment rather than creating or replacing one for this integration.

## Connect existing PNIS data

The app supports being placed in `PNIS/pnis_dashboard/`. It detects the parent PNIS project root when that folder contains `data/`, then looks for the named files under `data/processed/`:

- `phase2g18_risk_prioritized_worklist.csv`
- `phase2g19_fieldwork_execution_package.xlsx`
- `phase2g19_field_observation_template.csv`
- `phase2e_vehicle_graph_nodes.csv`
- `phase2e_vehicle_graph_edges.csv`
- `phase2e1_route_validation_audit.json`
- `phase2e_vehicle_graph_audit.json`
- `phase2c_v2_sidama_buffered_roads.gpkg`

If a file is absent, the app leaves the associated metric unavailable rather than generating substitute operational records. You can also upload CSV, XLSX, JSON, or GeoPackage files in the app's **Connect project data** expander. Uploads are read into the current Streamlit session; original source files are not modified.

### Geospatial notes

- GeoPackages are read with GeoPandas and reprojected to EPSG:4326 for display.
- Road length is calculated after projecting to EPSG:32637. Confirm the source CRS and the appropriate local projected CRS before using the value in a report.
- Road geometry, graph connectivity, and road passability are different things. The dashboard does not claim that connected road segments are passable.
- Candidate review records are not automatically approved for routing.
- No candidate coordinates are invented. If valid geometry or latitude/longitude fields are missing, the map displays an empty-data message.
- The map uses CARTO's Dark Matter basemap style, which requires an internet connection. Uploaded project geometry is still local to the app session.

## What is implemented

- Overview dashboard with six data-aware KPIs.
- Persistent Streamlit sidebar navigation and collapse toggle.
- Source upload adapter for CSV, XLSX, JSON, and GeoPackage.
- Dark geospatial workspace, road/candidate/node layer toggles, and map extent based on loaded road geometry.
- Candidate text search and status/priority filter.
- Interactive Plotly summaries.
- Filtered CSV download.
- Data & Provenance inventory.
- Placeholder states for secondary navigation pages.

## Known limitations / next steps

- This is a functional starter, not a verified production deployment. It has not been tested against your private local files in this environment.
- Field names vary across source versions; the adapter uses conservative column-name matching. Review the detected columns and adjust `find_col()` if needed.
- Map feature selection/detail popups are limited by Streamlit's PyDeck wrapper. For richer feature click events, move the map to MapLibre GL JS in a React frontend or add a dedicated event-capable component.
- Date filtering, authentication, a backend API, live refresh, and persistent uploads are not implemented.
- The six KPI definitions are data-dependent. “High priority” is derived only when a recognizable priority/risk column exists; it is not a domain-validated risk score.
- The road graph and route audit are surfaced as source readiness signals, not a route-planning engine.
- For a production architecture, keep the current Python processing pipeline and expose stable read-only API endpoints; the React frontend should consume those endpoints rather than rewriting Phase 2 processing.

## Suggested production architecture

```text
Existing PNIS Python pipeline
       |
       +-- immutable source files + audit artifacts
       |
       +-- FastAPI read-only adapter / validation endpoints
                       |
                 React + TypeScript
                       |
       MapLibre GL JS + charts + typed data contracts
```

Keep source data, calculated metrics, provisional findings, and missing data explicitly distinguished in the UI.


## Background image

`pnis_background.png` is loaded from the same directory as `app.py` and applied as a global, fixed background on every page. A dark overlay preserves dashboard text contrast. If the image is missing, the app falls back to its dark gradient. The sidebar remains a solid dark surface for legibility.
