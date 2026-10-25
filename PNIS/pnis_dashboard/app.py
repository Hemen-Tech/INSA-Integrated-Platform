
from __future__ import annotations

import base64
import io
import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    import geopandas as gpd
except Exception:
    gpd = None


# ============================================================
# PNIS CONFIGURATION
# ============================================================

APP_TITLE = "PNIS | Perishable Network Intelligence System"
PROBE_URL = os.environ.get("PROBE_URL", "http://localhost:3000/")
DROUGHT_URL = os.environ.get("DROUGHT_URL", "http://localhost:5501/")

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent if (APP_DIR.parent / "data").is_dir() else APP_DIR
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
GEOGRAPHIC_DIR = PROCESSED_DIR / "geographic"

LOGO_PATH = APP_DIR / "pnis_logo.png"
BG_PATH = APP_DIR / "pnis_background.png"

ROAD_FILENAME = "phase2c_v2_sidama_buffered_roads.gpkg"
ROAD_LAYER = "sidama_buffered_roads_v2"

ETHIOPIA_GPKG = GEOGRAPHIC_DIR / "ethiopia.gpkg"
ADMIN_LAYER = "gis_osm_adminareas_a_free"

EXPECTED_FILES = {
    "risk worklist": "phase2g18_risk_prioritized_worklist.csv",
    "fieldwork package": "phase2g19_fieldwork_execution_package.xlsx",
    "observation template": "phase2g19_field_observation_template.csv",
    "graph nodes": "phase2e_vehicle_graph_nodes.csv",
    "graph edges": "phase2e_vehicle_graph_edges.csv",
    "route validation audit": "phase2e1_route_validation_audit.json",
    "graph audit": "phase2e_vehicle_graph_audit.json",
    "roads GeoPackage": ROAD_FILENAME,
}

# Verified Sidama bounds, longitude/latitude.
SIDAMA_BOUNDS = (37.906427, 6.1387516, 39.1327237, 7.1656743)
SIDAMA_CENTER = (38.519575, 6.652213)

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# VISUAL SYSTEM
# ============================================================

background_css = (
    "background-image: linear-gradient(rgba(5,12,10,.76), "
    "rgba(5,12,10,.84)), "
    f"url('data:image/png;base64,{base64.b64encode(BG_PATH.read_bytes()).decode()}'); "
    "background-size: cover; background-position: center; "
    "background-attachment: fixed; background-repeat: no-repeat;"
    if BG_PATH.is_file()
    else "background: linear-gradient(135deg,#07100f,#081310,#07100f);"
)

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');

:root {{
  --bg:#07100f; --panel:#0c1916; --panel2:#10211c;
  --line:#20372e; --text:#edf5ed; --muted:#91a79a;
  --lime:#b7e45b; --green:#4fba77; --cyan:#61d6d1;
  --amber:#efbd61; --red:#f07878;
}}
html,body,[class*="css"] {{font-family:'Manrope',sans-serif;}}
.stApp {{ {background_css} color:var(--text); }}
[data-testid="stHeader"] {{background:rgba(7,16,15,.86);}}
[data-testid="stSidebar"] {{background:#091411;border-right:1px solid #20372e;}}
[data-testid="stSidebar"] > div {{padding-top:1rem;}}
.block-container {{padding:1.15rem 1.5rem 2.4rem;max-width:1800px;}}
h1,h2,h3,h4,p,span,label {{color:var(--text);}}
h1 {{font-size:1.48rem !important;letter-spacing:-.035em;font-weight:800 !important;}}
h2 {{font-size:1.05rem !important;letter-spacing:-.02em;}}
h3 {{font-size:.9rem !important;}}
small,.muted {{color:var(--muted) !important;}}
hr {{border-color:var(--line);}}
[data-testid="stMetricLabel"] {{color:#91a79a !important;font-size:.72rem;}}
[data-testid="stMetricValue"] {{color:#f0f6ed !important;font-size:1.5rem;font-weight:800;}}
.stButton button,.stDownloadButton button {{
  border-radius:6px;border:1px solid #345344;
  background:#12251d;color:#dff3df;font-weight:700;
}}
.stButton button:hover,.stDownloadButton button:hover {{
  border-color:var(--lime);color:var(--lime);
}}
.stSelectbox [data-baseweb="select"],.stTextInput input,.stDateInput input {{
  background:#0d1a16 !important;border-color:#294438 !important;color:#edf5ed !important;
}}
[data-testid="stFileUploader"] {{
  background:#0b1713;border:1px dashed #345344;border-radius:8px;padding:.4rem;
}}
.pnis-brand {{display:flex;align-items:center;gap:12px;padding:2px 0 18px;}}
.pnis-brand img {{width:60px;height:60px;object-fit:contain;border-radius:7px;background:#fff;}}
.pnis-word {{font-size:1.42rem;letter-spacing:.16em;font-weight:800;line-height:1.1;}}
.pnis-sub {{font-family:'DM Mono',monospace;font-size:.56rem;color:#91a79a;letter-spacing:.1em;margin-top:5px;}}
.eyebrow {{color:var(--lime);font-family:'DM Mono',monospace;font-size:.65rem;letter-spacing:.16em;text-transform:uppercase;}}
.page-head {{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:4px 0 14px;border-bottom:1px solid var(--line);margin-bottom:16px;}}
.page-context {{color:var(--muted);font-size:.78rem;margin-top:4px;}}
.panel {{background:linear-gradient(145deg,rgba(15,31,25,.96),rgba(10,22,18,.97));border:1px solid var(--line);border-radius:8px;padding:14px 15px;}}
.panel-title {{font-size:.76rem;text-transform:uppercase;letter-spacing:.1em;color:#c7d8cb;font-weight:800;margin-bottom:4px;}}
.panel-sub {{color:var(--muted);font-size:.68rem;margin-bottom:12px;}}
.status-pill {{display:inline-block;padding:4px 8px;border:1px solid #315440;background:#10261b;border-radius:4px;color:#b7e45b;font:.64rem 'DM Mono',monospace;}}
.kpi-label {{color:var(--muted);font-size:.69rem;letter-spacing:.03em;}}
.kpi-value {{color:#f0f6ed;font-size:1.45rem;font-weight:800;letter-spacing:-.04em;margin-top:5px;}}
.kpi-note {{color:#8ea598;font-size:.65rem;margin-top:4px;}}
.kpi-top {{display:flex;align-items:center;justify-content:space-between;}}
.kpi-dot {{width:7px;height:7px;border-radius:50%;background:var(--lime);}}
footer {{visibility:hidden;}}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# DATA ADAPTERS
# ============================================================

def read_csv_bytes(data: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(data), low_memory=False)


def load_uploaded(uploaded_file):
    name = uploaded_file.name.lower()
    raw = uploaded_file.getvalue()

    if name.endswith(".csv"):
        return read_csv_bytes(raw)

    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw))

    if name.endswith(".json"):
        obj = json.loads(raw.decode("utf-8"))
        if isinstance(obj, dict):
            return pd.DataFrame([
                {
                    "audit_key": key,
                    "audit_value": json.dumps(value)
                    if isinstance(value, (dict, list)) else value,
                }
                for key, value in obj.items()
            ])
        return pd.DataFrame(obj)

    if name.endswith((".gpkg", ".geojson", ".shp", ".zip")):
        if gpd is None:
            raise RuntimeError("GeoPandas is unavailable in this environment.")

        suffix = Path(name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            temp_path = tmp.name

        try:
            gdf = gpd.read_file(temp_path)
            if gdf.crs is not None:
                gdf = gdf.to_crs("EPSG:4326")
            return gdf
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    raise ValueError(f"Unsupported file type: {uploaded_file.name}")


def auto_load_local_files():
    result = {}

    if not PROCESSED_DIR.exists():
        result["data directory load error"] = (
            f"Processed directory not found: {PROCESSED_DIR}"
        )
        return result

    for label, filename in EXPECTED_FILES.items():
        path = PROCESSED_DIR / filename

        if not path.is_file():
            result[f"{label} load error"] = f"File not found: {path}"
            continue

        try:
            suffix = path.suffix.lower()

            if suffix == ".csv":
                result[label] = pd.read_csv(path, low_memory=False)

            elif suffix in (".xlsx", ".xls"):
                result[label] = pd.read_excel(path)

            elif suffix == ".json":
                result[label] = json.loads(path.read_text(encoding="utf-8"))

            elif suffix == ".gpkg":
                if gpd is None:
                    result[f"{label} load error"] = "GeoPandas is unavailable."
                    continue

                layer = ROAD_LAYER if filename == ROAD_FILENAME else None
                gdf = gpd.read_file(path, layer=layer)

                if gdf.empty:
                    result[f"{label} load error"] = f"Empty GeoPackage: {path.name}"
                    continue

                if gdf.crs is None:
                    result[f"{label} load error"] = f"Missing CRS: {path.name}"
                    continue

                result[label] = gdf.to_crs("EPSG:4326")

        except Exception as exc:
            result[f"{label} load error"] = f"{type(exc).__name__}: {exc}"

    # Load the administrative boundary independently of the Phase 2 outputs.
    if gpd is None:
        result["Sidama boundary load error"] = "GeoPandas is unavailable."
    elif not ETHIOPIA_GPKG.is_file():
        result["Sidama boundary load error"] = (
            f"Administrative GeoPackage not found: {ETHIOPIA_GPKG}"
        )
    else:
        try:
            admin = gpd.read_file(ETHIOPIA_GPKG, layer=ADMIN_LAYER)
            if admin.crs is None:
                raise ValueError("Administrative layer has no CRS.")

            name_col = next(
                (c for c in admin.columns if str(c).lower() == "name"), None
            )
            if name_col is None:
                raise ValueError("Administrative layer has no name field.")

            # Prefer the verified admin_level=4 Sidama regional boundary.
            # OSM IDs are retained as strings to avoid integer-format issues.
            mask = admin[name_col].fillna("").astype(str).str.contains(
                "Sidama|ሲዳማ", case=False, regex=True
            )
            matches = admin.loc[mask].copy()

            level_col = next(
                (c for c in matches.columns if str(c).lower() == "fclass"), None
            )
            if level_col:
                level4 = matches[
                    matches[level_col].astype(str).str.contains(
                        "admin_level4", case=False, regex=False
                    )
                ]
                if not level4.empty:
                    matches = level4

            if matches.empty:
                raise ValueError("No Sidama administrative boundary matched.")

            boundary = matches.to_crs("EPSG:4326")
            boundary = boundary[
                boundary.geometry.notna()
                & ~boundary.geometry.is_empty
                & boundary.geometry.is_valid
            ]

            if boundary.empty:
                raise ValueError("Sidama boundary geometry failed validation.")

            result["Sidama boundary"] = boundary

        except Exception as exc:
            result["Sidama boundary load error"] = (
                f"{type(exc).__name__}: {exc}"
            )

    return result


def find_col(df, patterns):
    if df is None or df.empty:
        return None

    normalized = {
        str(col).lower().replace(" ", "_"): col for col in df.columns
    }
    for pattern in patterns:
        for name, original in normalized.items():
            if pattern in name:
                return original
    return None


def display_count(value):
    return f"{value:,}" if value is not None else "—"


def dataframe_for_map(data):
    if not isinstance(data, pd.DataFrame) or data.empty:
        return None

    if hasattr(data, "geometry"):
        return data

    lat = find_col(data, ["latitude", "lat"])
    lon = find_col(data, ["longitude", "lon", "long"])

    if lat and lon:
        df = data.copy()
        df["_lat"] = pd.to_numeric(df[lat], errors="coerce")
        df["_lon"] = pd.to_numeric(df[lon], errors="coerce")
        df = df.dropna(subset=["_lat", "_lon"])
        return df[
            df["_lat"].between(-90, 90)
            & df["_lon"].between(-180, 180)
        ]

    return None


def style_plot(fig, height=220):
    fig.update_layout(
        height=height,
        margin=dict(l=4, r=4, t=20, b=4),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Manrope, sans-serif", color="#dce9df", size=10),
        legend=dict(font=dict(size=9), bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor="#1c3329", zerolinecolor="#1c3329"),
        yaxis=dict(gridcolor="#1c3329", zerolinecolor="#1c3329"),
    )
    return fig


def section_title(title, subtitle=None):
    st.markdown(
        f'<div class="panel-title">{title}</div>'
        + (f'<div class="panel-sub">{subtitle}</div>' if subtitle else ""),
        unsafe_allow_html=True,
    )


# ============================================================
# GEOGRAPHIC MAP — NO EXTERNAL BASEMAP REQUIRED
# ============================================================

def add_geometry_to_geo_figure(fig, gdf, color, width, max_features=None):
    """Add line and polygon outlines using Plotly's built-in geo projection."""
    if gdf is None or gdf.empty or not hasattr(gdf, "geometry"):
        return 0

    frame = gdf
    if max_features is not None and len(frame) > max_features:
        # Deterministic display subset only. Source data remains unchanged.
        frame = frame.iloc[
            list(range(0, len(frame), max(1, len(frame) // max_features)))
        ].head(max_features)

    count = 0
    for geom in frame.geometry:
        if geom is None or geom.is_empty:
            continue

        parts = []
        geom_type = geom.geom_type

        if geom_type == "LineString":
            parts = [geom]
        elif geom_type == "MultiLineString":
            parts = list(geom.geoms)
        elif geom_type == "Polygon":
            parts = [geom.exterior]
        elif geom_type == "MultiPolygon":
            parts = [poly.exterior for poly in geom.geoms]
        elif geom_type == "GeometryCollection":
            for sub in geom.geoms:
                if sub.geom_type == "LineString":
                    parts.append(sub)
                elif sub.geom_type == "MultiLineString":
                    parts.extend(list(sub.geoms))
                elif sub.geom_type == "Polygon":
                    parts.append(sub.exterior)
                elif sub.geom_type == "MultiPolygon":
                    parts.extend([poly.exterior for poly in sub.geoms])

        for part in parts:
            coords = list(part.coords)
            if len(coords) < 2:
                continue
            fig.add_trace(go.Scattergeo(
                lon=[xy[0] for xy in coords],
                lat=[xy[1] for xy in coords],
                mode="lines",
                line=dict(color=color, width=width),
                hoverinfo="skip",
                showlegend=False,
            ))
            count += 1

    return count


def build_sidama_map(boundary, roads, candidate_map=None, nodes=None,
                     show_roads=True, show_candidates=True, show_nodes=False):
    fig = go.Figure()
    boundary_parts = 0
    road_parts = 0

    if boundary is not None and not boundary.empty:
        boundary_parts = add_geometry_to_geo_figure(
            fig, boundary, color="#b7e45b", width=2.8
        )

    if show_roads and roads is not None and not roads.empty:
        # A display-only subset prevents the browser from being overwhelmed.
        # This does not change the stored GeoPackage or routing graph.
        road_parts = add_geometry_to_geo_figure(
            fig, roads, color="rgba(97,214,209,0.72)", width=0.65,
            max_features=6000,
        )

    if show_candidates and candidate_map is not None and not candidate_map.empty:
        if hasattr(candidate_map, "geometry"):
            point_frame = candidate_map[
                candidate_map.geometry.geom_type.isin(["Point", "MultiPoint"])
            ]
            if not point_frame.empty:
                if point_frame.geometry.geom_type.eq("Point").any():
                    points = point_frame[
                        point_frame.geometry.geom_type.eq("Point")
                    ]
                    fig.add_trace(go.Scattergeo(
                        lon=points.geometry.x,
                        lat=points.geometry.y,
                        mode="markers",
                        marker=dict(size=7, color="#efbd61", line=dict(width=1, color="#ffffff")),
                        name="Candidate locations",
                    ))
        elif {"_lon", "_lat"}.issubset(candidate_map.columns):
            fig.add_trace(go.Scattergeo(
                lon=candidate_map["_lon"],
                lat=candidate_map["_lat"],
                mode="markers",
                marker=dict(size=7, color="#efbd61", line=dict(width=1, color="#ffffff")),
                name="Candidate locations",
            ))

    if show_nodes and nodes is not None and not nodes.empty:
        lat_col = find_col(nodes, ["latitude", "lat"])
        lon_col = find_col(nodes, ["longitude", "lon", "long"])
        if lat_col and lon_col:
            nm = nodes.copy()
            nm["_lat"] = pd.to_numeric(nm[lat_col], errors="coerce")
            nm["_lon"] = pd.to_numeric(nm[lon_col], errors="coerce")
            nm = nm.dropna(subset=["_lat", "_lon"])
            nm = nm[
                nm["_lat"].between(6.0, 7.3)
                & nm["_lon"].between(37.7, 39.4)
            ]
            if not nm.empty:
                fig.add_trace(go.Scattergeo(
                    lon=nm["_lon"].head(5000),
                    lat=nm["_lat"].head(5000),
                    mode="markers",
                    marker=dict(size=3, color="#61d6d1"),
                    name="Graph nodes (display subset)",
                ))

    min_lon, min_lat, max_lon, max_lat = SIDAMA_BOUNDS
    fig.update_geos(
        projection_type="mercator",
        lonaxis_range=[min_lon - 0.08, max_lon + 0.08],
        lataxis_range=[min_lat - 0.08, max_lat + 0.08],
        showland=True,
        landcolor="#0d1a16",
        showocean=True,
        oceancolor="#07100f",
        showlakes=True,
        lakecolor="#10211c",
        showcountries=True,
        countrycolor="#345344",
        showcoastlines=False,
        showframe=False,
        bgcolor="rgba(0,0,0,0)",
        lonaxis=dict(showgrid=True, gridcolor="#1c3329", dtick=0.25),
        lataxis=dict(showgrid=True, gridcolor="#1c3329", dtick=0.25),
    )
    fig.update_layout(
        height=540,
        margin=dict(l=0, r=0, t=8, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Manrope, sans-serif", color="#dce9df", size=10),
        legend=dict(
            orientation="h", yanchor="bottom", y=0.01,
            xanchor="left", x=0.01, bgcolor="rgba(7,16,15,.7)"
        ),
    )
    return fig, boundary_parts, road_parts


# ============================================================
# SESSION STATE AND DATA LOADING
# ============================================================

if "collapsed" not in st.session_state:
    st.session_state.collapsed = False
if "page" not in st.session_state:
    st.session_state.page = "Overview"
if "refresh_count" not in st.session_state:
    st.session_state.refresh_count = 0

if (
    "datasets" not in st.session_state
    or st.session_state.get("loaded_refresh") != st.session_state.refresh_count
):
    st.session_state.datasets = auto_load_local_files()
    st.session_state.loaded_refresh = st.session_state.refresh_count


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    if LOGO_PATH.is_file():
        logo_base64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
        st.markdown(
            f"""
            <div class="pnis-brand">
              <img src="data:image/png;base64,{logo_base64}">
              <div><div class="pnis-word">PNIS</div>
              <div class="pnis-sub">NETWORK INTELLIGENCE</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="pnis-brand"><div><div class="pnis-word">PNIS</div>'
            '<div class="pnis-sub">NETWORK INTELLIGENCE</div></div></div>',
            unsafe_allow_html=True,
        )

    st.link_button("← Back to PROBE", PROBE_URL, use_container_width=True)
    st.link_button("Drought Intelligence", DROUGHT_URL, use_container_width=True)
    st.caption("Preview — In Development")

    if st.button("☰  Collapse sidebar", use_container_width=True):
        st.session_state.collapsed = not st.session_state.collapsed
        st.rerun()

    nav_items = [
        ("Overview", "◈"),
        ("Geospatial Intelligence", "⌖"),
        ("Candidate Intelligence", "◇"),
        ("Field Operations", "⊙"),
        ("Road Network", "⌁"),
        ("Routing Laboratory", "⇢"),
        ("Data & Provenance", "▤"),
    ]

    for label, icon in nav_items:
        shown = icon if st.session_state.collapsed else f"{icon}  {label}"
        if st.button(
            shown, key=f"nav_{label}", use_container_width=True,
            type="primary" if st.session_state.page == label else "secondary",
        ):
            st.session_state.page = label
            st.rerun()

    st.markdown("---")
    st.markdown('<div class="eyebrow">DATA PIPELINE</div>', unsafe_allow_html=True)
    st.markdown('<span class="status-pill">LOCAL / UPLOAD ADAPTER</span>',
                unsafe_allow_html=True)
    st.caption("v0.3.0 · Sidama workspace")
    st.caption("Connectivity does not establish road passability.")


# ============================================================
# HEADER AND UPLOAD
# ============================================================

datasets = st.session_state.datasets


def dataset_by_keyword(*keywords):
    for key, value in datasets.items():
        if (
            any(word in str(key).lower() for word in keywords)
            and isinstance(value, pd.DataFrame)
        ):
            return value
    return None


header_left, header_right = st.columns([4, 1.2])
page = st.session_state.page

with header_left:
    st.markdown(
        f"""
        <div class="page-head">
          <div>
            <div class="eyebrow">PNIS / SIDAMA, ETHIOPIA</div>
            <h1>{page}</h1>
            <div class="page-context">Perishable Network Intelligence System /
            Agricultural supply-chain operations</div>
          </div>
          <div class="status-pill">● &nbsp; DATA-AWARE WORKSPACE</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with header_right:
    if st.button("↻  Refresh data", use_container_width=True):
        st.session_state.refresh_count += 1
        st.rerun()

with st.expander("Connect project data · upload CSV, XLSX, JSON or GeoPackage"):
    st.markdown("Uploads are kept in this Streamlit session. Original files are unchanged.")
    uploaded = st.file_uploader(
        "Choose one or more files",
        type=["csv", "xlsx", "xls", "json", "gpkg", "geojson", "shp", "zip"],
        accept_multiple_files=True,
    )
    if uploaded:
        for file in uploaded:
            try:
                st.session_state.datasets[file.name] = load_uploaded(file)
                st.success(f"Loaded {file.name}")
            except Exception as exc:
                st.error(f"Could not load {file.name}: {exc}")

datasets = st.session_state.datasets
worklist = dataset_by_keyword("risk worklist", "phase2g18", "worklist")
field_package = dataset_by_keyword("fieldwork package", "phase2g19_fieldwork")
observations = dataset_by_keyword("observation template", "observation")
nodes = dataset_by_keyword("graph nodes", "vehicle_graph_nodes")
edges = dataset_by_keyword("graph edges", "vehicle_graph_edges")
roads = dataset_by_keyword("roads geopackage", ".gpkg", "buffered_roads")
boundary = dataset_by_keyword("sidama boundary")

audits = {
    key: value for key, value in datasets.items()
    if "audit" in str(key).lower() and "load error" not in str(key).lower()
}
load_errors = {
    key: value for key, value in datasets.items()
    if "load error" in str(key).lower()
}


# ============================================================
# FILTERS
# ============================================================

filtered_worklist = worklist.copy() if worklist is not None else pd.DataFrame()

if not filtered_worklist.empty:
    search_text = st.text_input(
        "⌕  Search candidate records",
        placeholder="Search IDs, names, locations or attributes…",
    )
    if search_text.strip():
        mask = filtered_worklist.astype(str).apply(
            lambda col: col.str.contains(search_text, case=False, na=False, regex=False)
        ).any(axis=1)
        filtered_worklist = filtered_worklist.loc[mask]

    status_col = find_col(
        filtered_worklist,
        ["review_status", "candidate_status", "status", "priority", "risk_level"],
    )
    if status_col:
        options = sorted(filtered_worklist[status_col].dropna().astype(str).unique())
        selected = st.multiselect(
            "Record status / priority filter", options, default=options,
            key="worklist_status_filter",
        )
        filtered_worklist = filtered_worklist[
            filtered_worklist[status_col].astype(str).isin(selected)
        ]


# ============================================================
# DATA & PROVENANCE PAGE
# ============================================================

if page == "Data & Provenance":
    st.subheader("Loaded data inventory")
    inventory = []
    for name, obj in datasets.items():
        if isinstance(obj, pd.DataFrame):
            inventory.append({
                "Source": name,
                "Type": "GeoDataFrame" if hasattr(obj, "geometry") else "Table",
                "Records": len(obj),
                "Columns": len(obj.columns),
                "CRS": str(getattr(obj, "crs", "n/a")),
            })
        elif isinstance(obj, dict):
            inventory.append({
                "Source": name, "Type": "JSON metadata",
                "Records": "n/a", "Columns": "n/a", "CRS": "n/a",
            })
        else:
            inventory.append({
                "Source": name, "Type": "Diagnostic",
                "Records": "n/a", "Columns": "n/a", "CRS": "n/a",
            })

    if inventory:
        st.dataframe(pd.DataFrame(inventory), use_container_width=True, hide_index=True)
    if load_errors:
        st.subheader("Data loading errors")
        st.json(load_errors)
    st.caption(f"Project root: {PROJECT_ROOT}")
    st.caption(f"Processed data directory: {PROCESSED_DIR}")
    st.stop()


# ============================================================
# OTHER WORKFLOW PAGES
# ============================================================

if page not in ("Overview", "Geospatial Intelligence"):
    st.markdown(
        f"""
        <div class="panel">
          <div class="panel-title">{page}</div>
          <p class="muted">This module is not yet implemented as an operational
          workflow. The application will not present unconnected actions as operational.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


# ============================================================
# KPI CALCULATIONS
# ============================================================

candidate_count = len(filtered_worklist) if worklist is not None else None
high_priority = None

if worklist is not None and not worklist.empty:
    priority_col = find_col(
        worklist, ["priority", "risk_level", "risk_category", "review_priority"]
    )
    if priority_col:
        high_priority = int(
            worklist[priority_col].astype(str).str.lower()
            .str.contains("high|critical|urgent|priority 1", regex=True).sum()
        )

road_length = None
if roads is not None and hasattr(roads, "geometry") and not roads.empty:
    try:
        road_length = roads.to_crs("EPSG:32637").geometry.length.sum() / 1000
    except Exception:
        pass

node_count = len(nodes) if nodes is not None else None
edge_count = len(edges) if edges is not None else None
validation_status = "Audit loaded" if audits else (
    "Unverified" if edges is not None else "Not available"
)

kpis = [
    ("CANDIDATE RECORDS", display_count(candidate_count),
     "Filtered worklist" if worklist is not None else "Source not connected", "#b7e45b"),
    ("HIGH-PRIORITY REVIEW", display_count(high_priority),
     "Derived from priority labels" if high_priority is not None else "Priority field unavailable", "#efbd61"),
    ("ROAD NETWORK", f"{road_length:,.1f} km" if road_length is not None else "—",
     "Projected geometry length" if road_length is not None else "GeoPackage unavailable", "#61d6d1"),
    ("GRAPH NODES / EDGES", f"{display_count(node_count)} / {display_count(edge_count)}",
     "Source graph tables" if nodes is not None and edges is not None else "Graph data unavailable", "#8fb5ff"),
    ("FIELD OBSERVATIONS", "Not verified",
     "Template availability is not field evidence", "#4fba77"),
    ("DATA VALIDATION", validation_status,
     "Audit presence only; not passability", "#efbd61"),
]

for col, (label, value, note, accent) in zip(st.columns(6), kpis):
    with col:
        st.markdown(
            f"""
            <div class="panel" style="min-height:112px;border-top:2px solid {accent};">
              <div class="kpi-top"><div class="kpi-label">{label}</div>
              <div class="kpi-dot" style="background:{accent};"></div></div>
              <div class="kpi-value" style="font-size:{'1.05rem' if len(value)>13 else '1.4rem'}">{value}</div>
              <div class="kpi-note">{note}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# MAP AND WORKLIST
# ============================================================

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
main_col, right_col = st.columns([1.85, 1], gap="medium")

with main_col:
    st.markdown(
        '<div class="panel-title">Sidama geospatial workspace</div>'
        '<div class="panel-sub">Verified administrative boundary and Phase 2C V2 road geometry</div>',
        unsafe_allow_html=True,
    )

    layer_a, layer_b, layer_c = st.columns(3)
    with layer_a:
        show_roads = st.toggle("Road network", value=True, key="show_roads")
    with layer_b:
        show_candidates = st.toggle("Candidates", value=True, key="show_candidates")
    with layer_c:
        show_nodes = st.toggle("Graph nodes", value=False, key="show_nodes")

    candidate_map = dataframe_for_map(filtered_worklist) if show_candidates else None

    fig, boundary_parts, road_parts = build_sidama_map(
        boundary=boundary,
        roads=roads,
        candidate_map=candidate_map,
        nodes=nodes,
        show_roads=show_roads,
        show_candidates=show_candidates,
        show_nodes=show_nodes,
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displayModeBar": True, "scrollZoom": True},
        key="pnis_sidama_map",
    )

    if boundary is None:
        st.error(
            "Sidama boundary could not be loaded. Check the boundary error "
            "in Map diagnostics below."
        )
    else:
        st.success(
            f"Sidama boundary loaded: {len(boundary):,} polygon feature(s). "
            f"Boundary outline parts rendered: {boundary_parts:,}."
        )

    if show_roads and roads is not None:
        st.info(
            f"Road source loaded: {len(roads):,} features. "
            f"Rendered line parts: {road_parts:,}. "
            "The display may use a deterministic subset for browser performance."
        )
    elif roads is None:
        st.warning("The Phase 2C V2 road GeoPackage is unavailable.")

    st.caption(
        "The geographic view is drawn from local geometry without an external "
        "basemap. Road geometry alone does not establish passability or routing approval."
    )

    with st.expander("Map diagnostics"):
        st.write("Application directory:", str(APP_DIR))
        st.write("Project root:", str(PROJECT_ROOT))
        st.write("Road GeoPackage:", str(PROCESSED_DIR / ROAD_FILENAME))
        st.write("Administrative GeoPackage:", str(ETHIOPIA_GPKG))
        st.write("Administrative layer:", ADMIN_LAYER)
        st.write("GeoPandas available:", gpd is not None)
        st.write("Boundary loaded:", boundary is not None)

        if boundary is not None:
            st.write("Boundary CRS:", str(boundary.crs))
            st.write("Boundary features:", len(boundary))
            st.write("Boundary bounds:", boundary.total_bounds.tolist())
            st.write("Boundary geometry types:", boundary.geometry.geom_type.value_counts().to_dict())

        st.write("Road dataset loaded:", roads is not None)
        if roads is not None:
            st.write("Road features:", f"{len(roads):,}")
            st.write("Road CRS:", str(roads.crs))
            st.write("Road bounds (longitude/latitude):", roads.total_bounds.tolist())
            st.write("Road geometry types:", roads.geometry.geom_type.value_counts().to_dict())

        if load_errors:
            st.error("One or more local sources failed to load.")
            st.json(load_errors)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="panel-title">Candidate worklist</div>'
        '<div class="panel-sub">Filtered records · review candidates are not automatically routing-approved</div>',
        unsafe_allow_html=True,
    )

    if not filtered_worklist.empty:
        exp_col, rows_col = st.columns([1, 2])
        with exp_col:
            st.download_button(
                "↓ Export filtered CSV",
                filtered_worklist.to_csv(index=False).encode("utf-8-sig"),
                file_name="pnis_filtered_worklist.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with rows_col:
            st.caption(f"{len(filtered_worklist):,} records in current view")

        st.dataframe(
            filtered_worklist, use_container_width=True,
            hide_index=True, height=230,
        )

        with st.expander("Inspect selected record"):
            row_idx = st.selectbox(
                "Choose record row",
                options=list(range(len(filtered_worklist))),
                format_func=lambda i: f"Row {i + 1} · {filtered_worklist.iloc[i, 0]}",
            )
            st.json(filtered_worklist.iloc[row_idx].to_dict(), expanded=True)
    else:
        st.info("Candidate worklist is unavailable or empty.")


# ============================================================
# INTELLIGENCE RAIL
# ============================================================

with right_col:
    st.markdown(
        '<div class="panel-title">Intelligence rail</div>'
        '<div class="panel-sub">Source-aware summaries</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        section_title("Candidate risk distribution", "Available risk / priority field")
        if worklist is not None and not worklist.empty:
            risk_col = find_col(
                worklist, ["risk_level", "risk_category", "priority", "review_priority", "candidate_status"]
            )
            if risk_col:
                counts = worklist[risk_col].fillna("Unspecified").astype(str).value_counts().reset_index()
                counts.columns = ["Category", "Records"]
                fig_risk = px.bar(
                    counts, x="Records", y="Category", orientation="h",
                    color="Category",
                    color_discrete_sequence=["#b7e45b", "#61d6d1", "#efbd61", "#4fba77", "#718b7e"],
                )
                fig_risk.update_layout(showlegend=False)
                style_plot(fig_risk, 210)
                st.plotly_chart(fig_risk, use_container_width=True, config={"displayModeBar": False})
            else:
                st.caption("No risk / priority column found.")
        else:
            st.caption("Candidate worklist unavailable.")

    with st.container(border=True):
        section_title("Fieldwork progress", "Actual observations must be provided separately")
        st.info(
            "The observation template is not evidence of completed fieldwork. "
            "Connect a real observation dataset to calculate progress."
        )

    with st.container(border=True):
        section_title("Routing readiness", "Connectivity does not establish road usability")
        if audits:
            for name, obj in audits.items():
                st.caption(f"{name}: {'audit JSON loaded' if isinstance(obj, dict) else 'data loaded'}")
            st.warning("Review the source audit before operational use.")
        elif nodes is not None and edges is not None:
            st.warning("Graph tables are loaded, but no validation audit is connected.")
        else:
            st.caption("Graph tables or validation audit are unavailable.")

    with st.container(border=True):
        section_title("Recent project alerts", "Data quality and workflow notices")
        alerts = []
        if worklist is None:
            alerts.append(("amber", "Candidate worklist not connected"))
        if roads is None:
            alerts.append(("amber", "Road GeoPackage not connected"))
        if boundary is None:
            alerts.append(("amber", "Sidama boundary not connected"))
        if not audits:
            alerts.append(("amber", "Validation audit not connected"))
        if load_errors:
            alerts.append(("amber", f"{len(load_errors)} data-loading issue(s) detected"))
        if not alerts:
            alerts.append(("green", "Expected sources detected; review audits before use"))

        for level, message in alerts:
            color = {"amber": "#efbd61", "green": "#b7e45b"}.get(level, "#61d6d1")
            st.markdown(
                f'<div style="display:flex;gap:9px;align-items:flex-start;margin:9px 0;font-size:.72rem">'
                f'<span style="color:{color}">●</span><span>{message}</span></div>',
                unsafe_allow_html=True,
            )


# ============================================================
# ANALYTICAL STRIP
# ============================================================

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
st.markdown(
    '<div class="panel-title">Analytical strip</div>'
    '<div class="panel-sub">Compact source-driven breakdowns</div>',
    unsafe_allow_html=True,
)
b1, b2, b3 = st.columns(3, gap="medium")

with b1:
    with st.container(border=True):
        section_title("Road composition", "Road class counts from loaded road geometry")
        road_class = find_col(roads, ["highway", "road_class", "road_type", "fclass", "class"]) if roads is not None else None
        if roads is not None and road_class:
            counts = roads[road_class].fillna("Unclassified").astype(str).value_counts().head(10).reset_index()
            counts.columns = ["Road class", "Features"]
            fig_class = px.bar(counts, x="Features", y="Road class", orientation="h",
                               color_discrete_sequence=["#4fba77"])
            style_plot(fig_class, 250)
            st.plotly_chart(fig_class, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("Road layer or road-class attribute unavailable.")

with b2:
    with st.container(border=True):
        section_title("Candidate review status", "Worklist classification")
        review_col = find_col(worklist, ["review_status", "candidate_status", "status"]) if worklist is not None else None
        if worklist is not None and review_col:
            counts = worklist[review_col].fillna("Unspecified").astype(str).value_counts().head(8).reset_index()
            counts.columns = ["Status", "Records"]
            fig_status = px.bar(counts, x="Status", y="Records", color_discrete_sequence=["#61d6d1"])
            fig_status.update_layout(xaxis_tickangle=-25)
            style_plot(fig_status, 250)
            st.plotly_chart(fig_status, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("Review-status field unavailable.")

with b3:
    with st.container(border=True):
        section_title("Network validation summary", "Source audit presence and graph coverage")
        summary = [
            ("Sidama boundary", "Loaded" if boundary is not None else "Unavailable"),
            ("Road geometry", "Loaded" if roads is not None else "Unavailable"),
            ("Graph nodes", display_count(node_count)),
            ("Graph edges", display_count(edge_count)),
            ("Audit sources", str(len(audits))),
            ("Passability", "Not inferred"),
            ("Routing approval", "Not inferred"),
        ]
        for label, value in summary:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;gap:8px;padding:9px 0;border-bottom:1px solid #1c3329;font-size:.72rem">'
                f'<span style="color:#91a79a">{label}</span><strong>{value}</strong></div>',
                unsafe_allow_html=True,
            )

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
st.caption(
    "PNIS · Data adapter v0.3.0 · Metrics are derived from connected sources "
    "where possible. Missing data is not replaced with invented operational records."
)
