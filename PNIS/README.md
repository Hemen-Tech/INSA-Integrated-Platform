# PNIS — Harvest & Route Intelligence

> Phase 1 integration status: **Preview — In Development**

A dark agritech operations dashboard for the Perishable Network Intelligence System. The UI uses a wider responsive navigation rail, native Streamlit sidebar collapse/expand control, subtle canopy animation, interactive cards, live project-file discovery, map layer toggles, Plotly charts, and downloadable source-backed records.

## Install

Place `app.py` and `requirements.txt` in the PNIS project root (the folder that contains `data/processed`). Keep all existing Phase 2 outputs unchanged.

```powershell
python -m pip install -r .\requirements.txt
python -m py_compile .\app.py
python -m streamlit run .\app.py
```

Open `http://localhost:8501`. If that port is already in use, choose another port with `--server.port`. Use the sidebar's native collapse control to slide the navigation out of view and reopen it. Data values are read from existing project artifacts; missing fields are shown as unavailable instead of being fabricated.

## Notes

The script was syntax-checked in the packaging environment. Confirm the dashboard against your local project files and browser; the live app has not been exercised against your Windows data in this environment.

## Separate root dashboard and platform destination

This README describes the separate root `app.py` implementation. The INSA platform's PNIS destination is `pnis_dashboard/app.py`, launched from the PNIS project root on port 8503:

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\pnis_dashboard\app.py --server.port 8503
```

The nested dashboard README documents its configurable **Back to PROBE** link. The root dashboard remains a separate implementation and is not the integrated destination. Cross-app navigation does not provide shared authentication or data.
