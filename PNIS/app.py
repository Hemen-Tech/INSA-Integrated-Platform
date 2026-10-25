from __future__ import annotations

"""PNIS — Perishable Network Intelligence System
A data-grounded Streamlit dashboard for Sidama network intelligence and fieldwork.

The app deliberately never fabricates candidate records, network metrics, or routes.
Missing or unrecognized data is surfaced as a clear limitation instead.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import streamlit as st

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except Exception:
    px = None
    go = None
    PLOTLY_AVAILABLE = False

# -----------------------------------------------------------------------------
# App configuration and visual system
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="PNIS | Harvest & Route Intelligence",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_ROOT = Path(__file__).resolve().parent
PROBE_URL = os.environ.get("PROBE_URL", "http://localhost:3000/")
PROJECT_ROOT = Path(os.environ.get("PNIS_ROOT", str(APP_ROOT))).expanduser()
PROCESSED = PROJECT_ROOT / "data" / "processed"

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');
      :root { --bg:#07130f; --panel:#0d2119; --panel2:#132b20; --ink:#edf5e8; --muted:#9bad9b; --line:#263e2d; --teal:#a6d957; --blue:#73c6b6; --amber:#e7b85c; --red:#f17b68; }
      html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
      .stApp { background:#06131f; color:var(--ink); }
      [data-testid="stHeader"] { background:#06131f; }
      [data-testid="stAppViewContainer"] .main .block-container { max-width:1900px; padding:1rem 1.1rem 1.4rem; }
      [data-testid="stSidebar"] { background:linear-gradient(180deg,#071923 0%,#06131d 100%); border-right:1px solid #1b3541; min-width:218px; }
      [data-testid="stSidebar"] > div:first-child { padding-top:1rem; }
      [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color:#90a7b5; }
      [data-testid="stSidebar"] h2 { font-size:1.05rem!important; letter-spacing:-.03em; color:#e9f6f5; margin-bottom:0; }
      [data-testid="stSidebar"] [data-testid="stRadio"] > label { font-size:.65rem; letter-spacing:.14em; color:#668695; font-weight:800; }
      [data-testid="stSidebar"] [data-testid="stRadio"] > div { gap:.14rem; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label { border:1px solid transparent; border-radius:5px; padding:.26rem .48rem; margin:0; font-size:.78rem; transition:all .15s ease; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) { background:linear-gradient(90deg,rgba(44,202,143,.19),rgba(44,202,143,.055)); border-color:rgba(53,212,154,.22); box-shadow:inset 3px 0 #35d49a; color:#e9fff6; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background:rgba(53,212,154,.08); }
      h1,h2,h3 { font-family:'DM Sans',sans-serif!important; letter-spacing:-.035em; color:var(--ink); }
      h1 { font-weight:750!important; }
      p, label, .stCaption { color:var(--muted); }
      .hero { padding:1rem 1.25rem; border-radius:7px; background:#0b202d; border:1px solid #1d3a48; margin:.15rem 0 1rem; box-shadow:none; }
      .hero:after { display:none; }
      .hero-kicker,.section-eyebrow { color:#38d59a; text-transform:uppercase; letter-spacing:.14em; font-size:.64rem; font-weight:800; }
      .hero-title { font-size:1.8rem; font-weight:800; line-height:1.08; margin:.35rem 0; color:#f3f8fb; }
      .hero-copy { color:#9db5c2; font-size:.88rem; line-height:1.5; }
      .hero-pill { display:inline-block; margin-top:.6rem; padding:.25rem .5rem; border-radius:4px; background:#10372f; border:1px solid #1b604b; color:#72e5b8; font-size:.65rem; font-weight:700; }
      .metric-card { border:1px solid #1b3948; background:linear-gradient(145deg,#102737,#0b1c29); border-radius:7px; padding:.72rem .8rem; min-height:98px; box-shadow:0 5px 15px rgba(0,0,0,.14); }
      .metric-label { color:#9bb2bf; font-size:.68rem; font-weight:600; margin-bottom:.42rem; }
      .metric-value { color:#f1f7fa; font-size:1.55rem; font-weight:800; line-height:1.05; }
      .metric-foot { color:#6e8998; font-size:.65rem; margin-top:.4rem; }
      .panel { background:#0a1c29; border:1px solid #1a3544; border-radius:7px; padding:.8rem .9rem; }
      .panel:hover,.metric-card:hover { border-color:#2d6b5a; box-shadow:0 6px 18px rgba(0,0,0,.2); }
      .metric-card,.panel { transition:border-color .15s ease,box-shadow .15s ease; }
      .status { display:inline-block; border-radius:4px; padding:.2rem .42rem; font-size:.63rem; font-weight:800; }
      .status-green { color:#78e8b7; background:#10372f; }
      .status-amber { color:#ffd987; background:#40351e; }
      .status-red { color:#ff9ca7; background:#40232c; }
      .status-gray { color:#b4c4d5; background:#203443; }
      .note { border-left:3px solid var(--teal); padding:.7rem .85rem; background:#0e2b2a; border-radius:0 5px 5px 0; color:#c6f5ed; }
      .warning-note { border-left:3px solid var(--amber); padding:.7rem .85rem; background:#30291f; border-radius:0 5px 5px 0; color:#ffe0b5; }
      div[data-testid="stMetric"] { background:#0d2230; border:1px solid #1c3948; border-radius:7px; padding:.8rem; }
      div[data-testid="stMetricLabel"] { color:var(--muted); }
      .stButton > button,.stDownloadButton > button { border-radius:5px; font-weight:650; border:1px solid #2a4a5a; background:#102a39; color:#e7f3f7; transition:all .15s ease; }
      .stButton > button:hover,.stDownloadButton > button:hover { border-color:#35d49a; color:#8ff6c8; box-shadow:0 0 0 1px rgba(53,212,154,.1); }
      .stButton > button[kind="primary"],.stFormSubmitButton > button[kind="primary"] { background:#15996c; border-color:#25bd88; color:#fff; }
      .stTextInput input,.stTextArea textarea,.stDateInput input,[data-baseweb="select"] > div { background:#081a27!important; color:#e8f0fa!important; border-color:#254253!important; border-radius:5px!important; }
      [data-testid="stDataFrame"] { border:1px solid #1c3948; border-radius:6px; overflow:hidden; }
      [data-testid="stExpander"] { border-color:#1c3948; background:#0a1c29; border-radius:6px; }
      .stTabs [data-baseweb="tab"] { color:#90a7b5; }
      .stTabs [aria-selected="true"] { color:#42dfa5!important; border-bottom-color:#35d49a!important; }
      div[data-testid="stVerticalBlockBorderWrapper"] { border-color:#1c3948; }
      hr { border-color:#1b3544; }
      footer { visibility:hidden; }
      /* Home dashboard: compact regional GIS console inspired by the supplied reference */
      [data-testid="stSidebar"] { min-width:164px!important; max-width:164px!important; }
      [data-testid="stAppViewContainer"] .main .block-container { padding:.55rem .65rem 1rem!important; max-width:2200px!important; }
      .metric-card { border-radius:3px!important; background:linear-gradient(135deg,#102a3b,#0b1c2a)!important; box-shadow:inset 0 1px rgba(255,255,255,.025)!important; }
      .panel { border-radius:3px!important; background:#0a1b29!important; }
      .panel:hover,.metric-card:hover { border-color:#31566a!important; box-shadow:0 0 0 1px rgba(53,212,154,.06)!important; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label { border-radius:3px!important; padding:.32rem .42rem!important; font-size:.73rem!important; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) { background:#103a34!important; box-shadow:inset 3px 0 #35d49a!important; }
      .stPlotlyChart { border-radius:3px; }
      @media (max-width:900px) { [data-testid="stSidebar"] { min-width:unset!important; max-width:unset!important; } .hero { padding:1rem; } .hero-title { font-size:1.45rem; } .metric-value { font-size:1.2rem; } }

      /* PNIS field-to-market visual system: forest canopy, mineral soil, harvest-lime accents. */
      :root { --bg:#07130f; --panel:#0d2119; --panel2:#132b20; --ink:#edf5e8; --muted:#9bad9b; --line:#263e2d; --teal:#a6d957; --blue:#73c6b6; --amber:#e7b85c; --red:#f17b68; }
      html, body, [class*="css"] { font-family:'DM Sans',sans-serif!important; }
      h1,h2,h3,.hero-title { font-family:'Space Grotesk','DM Sans',sans-serif!important; letter-spacing:-.045em!important; }
      .stApp { background:radial-gradient(ellipse at 75% -18%,rgba(100,145,58,.13),transparent 40%),linear-gradient(145deg,#07130f 0%,#091711 48%,#07110d 100%)!important; }
      [data-testid="stHeader"] { background:rgba(7,19,15,.88)!important; }
      [data-testid="stAppViewContainer"] .main .block-container { max-width:1920px!important; padding:.75rem .9rem 1.5rem!important; }
      [data-testid="stSidebar"] { background:linear-gradient(180deg,#0b1d14 0%,#08150f 70%,#07110d 100%)!important; border-right:1px solid #2a422d!important; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label { border-radius:7px!important; padding:.42rem .55rem!important; font-weight:600!important; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) { background:linear-gradient(90deg,rgba(166,217,87,.17),rgba(115,198,182,.045))!important; border-color:rgba(166,217,87,.25)!important; box-shadow:inset 3px 0 #a6d957!important; color:#f1f8e8!important; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background:rgba(166,217,87,.075)!important; }
      .hero { position:relative; overflow:hidden; background:linear-gradient(115deg,rgba(20,48,31,.97),rgba(12,31,23,.94))!important; border:1px solid #2d4930!important; border-radius:10px!important; }
      .hero:before { content:""; position:absolute; right:-35px; top:-90px; width:300px; height:300px; border:1px solid rgba(166,217,87,.13); border-radius:48% 52% 63% 37%; transform:rotate(32deg); box-shadow:0 0 0 22px rgba(166,217,87,.025),0 0 0 45px rgba(166,217,87,.02); pointer-events:none; }
      .hero-kicker,.section-eyebrow { color:#b5e66b!important; letter-spacing:.16em!important; }
      .hero-pill { background:#1a3520!important; border-color:#426334!important; color:#c5ed8b!important; }
      .metric-card { background:linear-gradient(145deg,rgba(20,45,31,.98),rgba(11,28,20,.98))!important; border:1px solid #2a4430!important; border-radius:9px!important; box-shadow:0 8px 22px rgba(0,0,0,.12),inset 0 1px rgba(255,255,255,.025)!important; }
      .metric-card:hover { border-color:#7ca847!important; transform:translateY(-1px); box-shadow:0 10px 24px rgba(0,0,0,.18)!important; }
      .metric-label { color:#a8bca6!important; letter-spacing:.015em; }
      .metric-value { color:#f2f7e9!important; font-family:'Space Grotesk',sans-serif!important; }
      .metric-foot { color:#819883!important; }
      .panel { background:linear-gradient(145deg,rgba(14,34,24,.98),rgba(10,25,18,.98))!important; border:1px solid #273f2d!important; border-radius:9px!important; box-shadow:0 7px 20px rgba(0,0,0,.09)!important; }
      .panel:hover { border-color:#47683b!important; box-shadow:0 9px 24px rgba(0,0,0,.16)!important; }
      .status-green { color:#d1f49a!important; background:#203a20!important; }
      .status-amber { color:#f2d48e!important; background:#3b311b!important; }
      .status-red { color:#ffb3a7!important; background:#40251f!important; }
      .status-gray { color:#c1d0c1!important; background:#203329!important; }
      .note { background:#142d1c!important; border-left-color:#a6d957!important; }
      .warning-note { background:#342a18!important; border-left-color:#e7b85c!important; }
      .stButton > button,.stDownloadButton > button { border-radius:7px!important; background:#152b1d!important; border-color:#344d34!important; }
      .stButton > button:hover,.stDownloadButton > button:hover { border-color:#a6d957!important; color:#d9f6a8!important; box-shadow:0 0 0 1px rgba(166,217,87,.12)!important; }
      .stButton > button[kind="primary"],.stFormSubmitButton > button[kind="primary"] { background:#638e2d!important; border-color:#8ab744!important; color:#fff!important; }
      .stTextInput input,.stTextArea textarea,.stDateInput input,[data-baseweb="select"] > div { background:#0a1a12!important; color:#edf5e8!important; border-color:#344c36!important; }
      [data-testid="stDataFrame"] { border:1px solid #2a4430!important; border-radius:8px!important; }
      [data-testid="stExpander"] { border-color:#2a4430!important; background:#0d2119!important; border-radius:8px!important; }
      .stTabs [aria-selected="true"] { color:#c4eb81!important; border-bottom-color:#a6d957!important; }
      hr { border-color:#263e2d!important; }
      .stPlotlyChart { border-radius:8px; }
      /* Purpose-built PNIS interface: responsive rail, field-glass panels, restrained motion. */
      div[data-testid="stMetric"] { background:linear-gradient(145deg,#132b20,#0d2119)!important; border:1px solid #2a4430!important; border-radius:9px!important; }
      /* Keep the rail comfortably wide when open; Streamlit's native chevron collapses it. */
      [data-testid="stSidebar"] { min-width:258px!important; max-width:258px!important; width:258px!important; transition:width .22s ease, min-width .22s ease, max-width .22s ease; }
      [data-testid="stSidebar"] > div:first-child { padding:1.05rem .8rem 1rem!important; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label { min-height:39px; display:flex; align-items:center; gap:.55rem; border-radius:8px!important; padding:.55rem .72rem!important; font-size:.82rem!important; letter-spacing:.005em!important; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:hover { transform:translateX(2px); background:linear-gradient(90deg,rgba(166,217,87,.11),rgba(115,198,182,.025))!important; }
      [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) { box-shadow:inset 3px 0 #b7e779,0 0 22px rgba(166,217,87,.045)!important; }
      [data-testid="stSidebar"] button[kind="header"] { color:#b7e779!important; }
      .stApp { background:radial-gradient(ellipse at 78% 0%,rgba(91,133,47,.15),transparent 33%),radial-gradient(ellipse at 5% 55%,rgba(26,102,77,.08),transparent 28%),linear-gradient(150deg,#07130f 0%,#091811 48%,#07120d 100%)!important; }
      .hero { box-shadow:0 12px 42px rgba(0,0,0,.16),inset 0 1px rgba(255,255,255,.035)!important; }
      .hero:before { animation:canopy-drift 18s ease-in-out infinite alternate; }
      @keyframes canopy-drift { from { transform:translate3d(0,0,0) rotate(22deg); } to { transform:translate3d(-18px,12px,0) rotate(42deg); } }
      .metric-card { position:relative; overflow:hidden; isolation:isolate; }
      .metric-card:after { content:""; position:absolute; inset:0; z-index:-1; opacity:0; background:linear-gradient(115deg,transparent 20%,rgba(183,231,121,.08) 48%,transparent 72%); transform:translateX(-80%); transition:opacity .2s ease; }
      .metric-card:hover:after { opacity:1; animation:card-sheen 1.1s ease forwards; }
      @keyframes card-sheen { to { transform:translateX(80%); } }
      .panel { backdrop-filter:blur(8px); box-shadow:0 10px 28px rgba(0,0,0,.12),inset 0 1px rgba(255,255,255,.018)!important; }
      .panel:hover { transform:translateY(-1px); transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease; }
      .stPlotlyChart, [data-testid="stDataFrame"] { filter:drop-shadow(0 4px 10px rgba(0,0,0,.08)); }
      .stButton > button,.stDownloadButton > button { min-height:38px; }
      .stButton > button:active,.stDownloadButton > button:active { transform:translateY(1px) scale(.99); }
      [data-testid="stProgressBar"] > div > div { background:linear-gradient(90deg,#638e2d,#b7e779)!important; }
      @media (prefers-reduced-motion:reduce) { *,*:before,*:after { animation:none!important; transition:none!important; scroll-behavior:auto!important; } }
      @media (max-width:900px) { [data-testid="stAppViewContainer"] .main .block-container { padding:.55rem!important; } [data-testid="stSidebar"] { min-width:unset!important; max-width:unset!important; width:unset!important; } }

    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Helpers: robust file discovery, parsing, normalization, and safe rendering
# -----------------------------------------------------------------------------
def slug(value: Any) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[\s\-/]+", "_", text)
    text = re.sub(r"[^a-z0-9_]+", "", text)
    return re.sub(r"_+", "_", text).strip("_")


def nice_name(value: str) -> str:
    return str(value).replace("_", " ").replace("-", " ").strip().title()


def find_file(candidates: list[str]) -> Optional[Path]:
    for candidate in candidates:
        p = PROCESSED / candidate
        if p.exists() and p.is_file():
            return p
    return None


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        try:
            return pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(path, low_memory=False, encoding="latin-1")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return pd.json_normalize(raw)
        if isinstance(raw, dict):
            for key in ("records", "data", "candidates", "rows", "items"):
                if isinstance(raw.get(key), list):
                    return pd.json_normalize(raw[key])
            # Metrics/audit JSON isn't a row table; make a useful key/value table.
            return pd.json_normalize(raw, sep=".").T.reset_index(names="field").rename(columns={0: "value"})
    raise ValueError(f"Unsupported table format: {path.suffix}")


def normalized_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [slug(c) or f"column_{i+1}" for i, c in enumerate(out.columns)]
    # Keep a copy of original values but normalize common text fields for filters.
    for col in out.select_dtypes(include=["object", "string"]).columns:
        out[col] = out[col].map(lambda x: x.strip() if isinstance(x, str) else x)
    return out


def first_col(df: pd.DataFrame, names: list[str]) -> Optional[str]:
    for name in names:
        if name in df.columns:
            return name
    return None


def numeric_series(df: pd.DataFrame, names: list[str]) -> Optional[pd.Series]:
    col = first_col(df, names)
    if col is None:
        return None
    return pd.to_numeric(df[col], errors="coerce")


def fmt_int(value: Any) -> str:
    try:
        if pd.isna(value):
            return "—"
        return f"{int(value):,}"
    except (TypeError, ValueError, OverflowError):
        return "—"


def fmt_float(value: Any, digits: int = 1) -> str:
    try:
        if pd.isna(value):
            return "—"
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError, OverflowError):
        return "—"


def metric_card(label: str, value: str, foot: str = "") -> None:
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div><div class="metric-foot">{foot}</div></div>',
        unsafe_allow_html=True,
    )


def section(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="section-eyebrow">PNIS WORKSPACE</div><h2 style="margin-top:0">{title}</h2>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<p class="subtle" style="margin-top:-.45rem">{subtitle}</p>', unsafe_allow_html=True)


def show_missing(message: str, next_step: str = "") -> None:
    st.info(message)
    if next_step:
        st.caption(next_step)


def display_table(df: pd.DataFrame, height: int = 380) -> None:
    if df.empty:
        st.info("No records match the current filters.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True, height=height)


def discover_dataset() -> tuple[Optional[Path], Optional[pd.DataFrame]]:
    candidates = [
        "phase2g18_risk_prioritized_worklist.csv",
        "phase2g19_field_observation_template.csv",
        "phase2g19_fieldwork_execution_package.xlsx",
        "phase2g18_risk_prioritized_worklist.xlsx",
    ]
    path = find_file(candidates)
    if not path:
        return None, None
    try:
        df = normalized_frame(read_table(path))
        # For workbook, prefer the candidate sheet when the default first sheet is instructions.
        if path.suffix.lower() in {".xlsx", ".xls"}:
            xl = pd.ExcelFile(path)
            sheet = next((s for s in ["All Candidates", "High Risk First", "Field Observation Form"] if s in xl.sheet_names), None)
            if sheet:
                df = normalized_frame(pd.read_excel(path, sheet_name=sheet))
        return path, df
    except Exception as exc:
        st.warning(f"Found {path.name}, but could not read it: {exc}")
        return path, None


def load_audit_json() -> tuple[Optional[Path], Optional[dict[str, Any]]]:
    candidates = [
        "phase2e_vehicle_graph_audit.json",
        "phase2e1_route_validation_audit.json",
        "phase2e_route_validation_audit.json",
    ]
    path = find_file(candidates)
    if not path:
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return path, data if isinstance(data, dict) else {"data": data}
    except Exception:
        return path, None


def flatten_dict(value: Any, prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, dict):
                result.update(flatten_dict(item, name))
            elif isinstance(item, list):
                result[name] = f"[{len(item)} items]"
            else:
                result[name] = item
    else:
        result[prefix or "value"] = value
    return result


def classify_risk(value: Any) -> str:
    text = str(value).strip().upper()
    if "HIGH" in text:
        return "HIGH"
    if "ELEVATED" in text or "MEDIUM" in text or "MODERATE" in text:
        return "ELEVATED"
    if text in {"", "NAN", "NONE", "UNKNOWN"}:
        return "UNKNOWN"
    if "STANDARD" in text or "LOW" in text:
        return "STANDARD"
    return text


def route_graph_files() -> tuple[Optional[Path], Optional[Path]]:
    nodes = find_file(["phase2e_vehicle_graph_nodes.csv", "phase2e1_graph_nodes.csv", "phase2e_nodes.csv"])
    edges = find_file(["phase2e_vehicle_graph_edges.csv", "phase2e1_graph_edges.csv", "phase2e_edges.csv"])
    return nodes, edges

# -----------------------------------------------------------------------------
# Sidebar and data loading
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("<div style='display:flex;align-items:center;gap:9px;margin:.1rem 0 .15rem'><div style='width:30px;height:30px;border-radius:6px;background:linear-gradient(145deg,#1cb987,#08745d);display:flex;align-items:center;justify-content:center;color:#eafff6;font-size:17px;font-weight:800'>P</div><div><div style='font-size:1rem;font-weight:800;color:#eef8f8;letter-spacing:-.04em'>PNIS</div><div style='font-size:.58rem;color:#7e9aa8;letter-spacing:.12em'>HARVEST · ROUTE INTELLIGENCE</div></div></div>", unsafe_allow_html=True)
    st.link_button("← Back to PROBE", PROBE_URL, use_container_width=True)
    st.caption("Preview — In Development")
    st.caption("FIELD TO MARKET · SIDAMA")
    st.markdown("<div style='height:1px;background:#21364f;margin:.6rem 0 1rem 0'></div>", unsafe_allow_html=True)
    st.markdown("---")
    page_labels = {
        "◈  Command Center": "Overview",
        "◎  Geospatial Intelligence": "Geospatial Intelligence",
        "◉  Candidate Analytics": "Candidate Intelligence",
        "▤  Field Operations": "Fieldwork Register",
        "⌁  Road Network": "Road Network",
        "⇢  Routing Laboratory": "Routing Analysis",
        "▧  Data & Provenance": "Data & Provenance",
    }
    selected_label = st.radio("NAVIGATION", list(page_labels.keys()), label_visibility="visible")
    page = page_labels[selected_label]
    st.markdown("---")
    st.markdown("<div style='font-size:.66rem;color:#698796;letter-spacing:.1em;font-weight:800'>PROJECT DATA</div>", unsafe_allow_html=True)
    st.caption(str(PROJECT_ROOT))
    if not PROCESSED.exists():
        st.warning("Processed data folder was not found at this project root.")
    st.caption("Evidence-first mode · no synthetic records")

# Explicitly allow an in-session override without changing project files.
with st.sidebar.expander("Data location", expanded=False):
    custom_root = st.text_input("Project root path", value=str(PROJECT_ROOT), help="Folder containing data/processed.")
    if st.button("Use this path", use_container_width=True):
        st.session_state["custom_root"] = custom_root.strip()
        st.rerun()
if st.session_state.get("custom_root"):
    root_candidate = Path(st.session_state["custom_root"])
    if root_candidate.exists():
        PROJECT_ROOT = root_candidate
        PROCESSED = PROJECT_ROOT / "data" / "processed"

candidate_path, candidates = discover_dataset()
audit_path, audit_data = load_audit_json()
nodes_path, edges_path = route_graph_files()

# -----------------------------------------------------------------------------
# Header
# -----------------------------------------------------------------------------
if page != "Overview":
    st.markdown(
        """
        <div class="hero">
          <div class="hero-kicker">PNIS / SPATIAL OPERATIONS · SIDAMA, ETHIOPIA</div>
          <div class="hero-title">Perishable Network<br>Intelligence System</div>
          <div class="hero-copy">A field-to-market intelligence workspace for crop collection access, candidate review, field evidence, road-network quality, and vehicle routing. Explore each workspace from the left navigation; every metric is tied to a discovered project artifact.</div>
          <div class="hero-pill">● SOURCE-BACKED DATA &nbsp; · &nbsp; FIELD VALIDATION FIRST &nbsp; · &nbsp; ROUTING IS NOT APPROVAL</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# -----------------------------------------------------------------------------
# Overview — reference-inspired PNIS command center
# -----------------------------------------------------------------------------
if page == "Overview":
    candidate_count = len(candidates) if candidates is not None else None
    risk_col = first_col(candidates, ["risk_class", "risk_category", "risk_level", "risk", "priority_class"]) if candidates is not None else None
    status_col = first_col(candidates, ["fieldwork_status", "field_status", "status", "review_status"]) if candidates is not None else None
    high_count = int(candidates[risk_col].map(classify_risk).eq("HIGH").sum()) if candidates is not None and risk_col else None
    elevated_count = int(candidates[risk_col].map(classify_risk).eq("ELEVATED").sum()) if candidates is not None and risk_col else None
    pending_count = int(candidates[status_col].astype(str).str.contains("await|pending|not started|not_started", case=False, na=False).sum()) if candidates is not None and status_col else None
    graph_node_value = graph_edge_value = None
    if audit_data:
        flat = {slug(k.split(".")[-1]): v for k, v in flatten_dict(audit_data).items()}
        graph_node_value = next((v for k, v in flat.items() if "node" in k and ("count" in k or "rows" in k or k == "nodes")), None)
        graph_edge_value = next((v for k, v in flat.items() if "edge" in k and ("count" in k or "rows" in k or k == "edges")), None)

    # Compact title bar, matching the reference's GIS operations-console hierarchy.
    title_left, title_date, title_actions = st.columns([2.4, 1, 1.1])
    with title_left:
        st.markdown("<div class='section-eyebrow'>PERISHABLE NETWORK INTELLIGENCE SYSTEM</div><h1 style='font-size:1.65rem;margin:.05rem 0'>Harvest & Route Intelligence</h1><div class='subtle' style='font-size:.82rem'>SIDAMA, ETHIOPIA · Crop collection access, candidate review and vehicle-routing readiness</div>", unsafe_allow_html=True)
    with title_date:
        st.date_input("Dashboard date", value=pd.Timestamp.today().date(), label_visibility="collapsed", key="overview_date")
    with title_actions:
        ac1, ac2 = st.columns(2)
        with ac1:
            if st.button("↻ Refresh", use_container_width=True, key="overview_refresh"):
                st.cache_data.clear()
                st.rerun()
        with ac2:
            if candidates is not None:
                st.download_button("⇩ Export", candidates.to_csv(index=False).encode("utf-8-sig"), "pnis_candidate_worklist.csv", "text/csv", use_container_width=True, key="overview_export")
            else:
                st.button("⇩ Export", disabled=True, use_container_width=True, key="overview_export_disabled")

    st.markdown("<div style='height:1px;background:#203a4a;margin:.75rem 0 1rem'></div>", unsafe_allow_html=True)
    # Six compact KPIs echo the reference dashboard. Values only appear when source files support them.
    kpis = [
        ("◉", "Candidate records", fmt_int(candidate_count) if candidate_count is not None else "—", "Records in discovered worklist", "#4b9fff"),
        ("▣", "High-risk candidates", fmt_int(high_count) if high_count is not None else "—", "Requires priority review", "#ff667a"),
        ("◉", "Elevated review", fmt_int(elevated_count) if elevated_count is not None else "—", "Elevated risk tier", "#ffbd69"),
        ("⌖", "Awaiting fieldwork", fmt_int(pending_count) if pending_count is not None else "—", "Pending status in source", "#42d7b5"),
        ("⇢", "Routing graph", "Available" if nodes_path and edges_path else "Not detected", "Node and edge tables", "#a78bfa"),
        ("✓", "Field validation", "Pending" if candidates is not None else "Unknown", "Field evidence still required", "#39c8d2"),
    ]
    cols = st.columns(6, gap="small")
    for col, (symbol, label, value, foot, accent) in zip(cols, kpis):
        with col:
            st.markdown(f"<div class='metric-card' style='min-height:104px;padding:.78rem .82rem;border-top:2px solid {accent}'><div style='display:flex;justify-content:space-between;align-items:center'><span style='font-size:1.05rem;color:{accent}'>{symbol}</span><span style='font-size:.63rem;color:#7891a6'>PNIS</span></div><div class='metric-label' style='margin:.35rem 0 .32rem'>{label}</div><div class='metric-value' style='font-size:1.38rem'>{value}</div><div class='metric-foot'>{foot}</div></div>", unsafe_allow_html=True)

    # Main composition: operational map at left, source-grounded intelligence panels at right.
    map_col, intel_col = st.columns([2.15, 1], gap="small")
    with map_col:
        st.markdown("<div class='panel' style='padding:.75rem .85rem'>", unsafe_allow_html=True)
        st.markdown("<div style='display:flex;justify-content:space-between;align-items:center'><div><b>Field-to-Market Network</b><div class='subtle' style='font-size:.72rem'>Collection access · road corridors · candidate worklist</div></div><span class='status status-green'>LIVE PROJECT FILES</span></div>", unsafe_allow_html=True)
        m1, m2 = st.columns([1, 1])
        with m1:
            overview_show_roads = st.toggle("Road network", value=True, key="overview_roads")
        with m2:
            overview_show_candidates = st.toggle("Candidate locations", value=True, key="overview_candidates")
        road_path_overview = find_file(["phase2c_v2_sidama_buffered_roads.gpkg", "phase2c_sidama_buffered_roads.gpkg", "phase2b_sidama_intersecting_roads.gpkg"])
        overview_points = pd.DataFrame()
        lat_col = lon_col = overview_risk_col = overview_id_col = None
        if candidates is not None:
            lat_col = first_col(candidates, ["latitude", "lat", "y", "decimal_latitude", "lat_dd"])
            lon_col = first_col(candidates, ["longitude", "lon", "lng", "x", "decimal_longitude", "long_dd"])
            overview_risk_col = first_col(candidates, ["risk_class", "risk_category", "risk_level", "risk", "priority_class"])
            overview_id_col = first_col(candidates, ["candidate_record_id", "candidate_id", "record_id", "candidateid", "id"])
            if lat_col and lon_col:
                overview_points = candidates.copy()
                overview_points[lat_col] = pd.to_numeric(overview_points[lat_col], errors="coerce")
                overview_points[lon_col] = pd.to_numeric(overview_points[lon_col], errors="coerce")
                overview_points = overview_points.dropna(subset=[lat_col, lon_col])
                overview_points = overview_points[overview_points[lat_col].between(-90,90) & overview_points[lon_col].between(-180,180)]
        overview_roads = None
        overview_map_error = None
        if overview_show_roads and road_path_overview:
            try:
                import geopandas as gpd
                import pyogrio
                layer_names = [str(x[0]) for x in pyogrio.list_layers(road_path_overview) if len(x) and x[0]]
                layer_name = "sidama_buffered_roads_v2" if "sidama_buffered_roads_v2" in layer_names else (layer_names[0] if layer_names else None)
                overview_roads = gpd.read_file(road_path_overview, layer=layer_name) if layer_name else gpd.read_file(road_path_overview)
                if len(overview_roads) > 6500:
                    overview_roads = overview_roads.iloc[::max(1, len(overview_roads)//6500)].head(6500).copy()
                if overview_roads.crs is not None and str(overview_roads.crs).upper() not in {"EPSG:4326", "OGC:CRS84"}:
                    try: overview_roads[overview_roads.geometry.name] = overview_roads.geometry.simplify(25, preserve_topology=True)
                    except Exception: pass
                    overview_roads = overview_roads.to_crs("EPSG:4326")
                class_col = first_col(overview_roads, ["fclass", "road_class", "highway", "class"])
                name_col = first_col(overview_roads, ["name", "road_name", "ref"])
                keep_cols = [overview_roads.geometry.name] + [x for x in [class_col, name_col] if x and x != overview_roads.geometry.name]
                overview_roads = overview_roads[keep_cols]
                overview_roads = overview_roads[overview_roads.geometry.notna() & ~overview_roads.geometry.is_empty]
            except Exception as exc:
                overview_map_error = str(exc)
                overview_roads = None
        try:
            import folium
            from streamlit_folium import st_folium
            center = [float(overview_points[lat_col].median()), float(overview_points[lon_col].median())] if overview_show_candidates and not overview_points.empty else [6.8, 38.3]
            fmap = folium.Map(location=center, zoom_start=8, tiles=None, control_scale=True, prefer_canvas=True)
            folium.TileLayer("CartoDB dark_matter", name="Dark satellite-style basemap", control=True).add_to(fmap)
            folium.TileLayer("OpenStreetMap", name="Street map", control=True).add_to(fmap)
            if overview_show_roads and overview_roads is not None and not overview_roads.empty:
                rc = first_col(overview_roads, ["fclass", "road_class", "highway", "class"])
                folium.GeoJson(overview_roads, name="Sidama roads", style_function=lambda f: {"color":"#f4c84a" if str((f.get("properties") or {}).get(rc, "")).lower() in {"primary","trunk","motorway"} else "#43d6b5", "weight":1.35, "opacity":.8}, control=True).add_to(fmap)
            if overview_show_candidates and not overview_points.empty:
                layer = folium.FeatureGroup(name="Candidate worklist", show=True)
                for ix, row in overview_points.iterrows():
                    rsk = classify_risk(row[overview_risk_col]) if overview_risk_col else "UNKNOWN"
                    col = {"HIGH":"#ff667a", "ELEVATED":"#ffbd69", "STANDARD":"#3dd6b0"}.get(rsk, "#9aacc1")
                    label = str(row[overview_id_col]) if overview_id_col and pd.notna(row[overview_id_col]) else f"Worklist row {ix}"
                    folium.CircleMarker([float(row[lat_col]), float(row[lon_col])], radius=5, color="#07111f", weight=1, fill=True, fill_color=col, fill_opacity=.95, tooltip=f"{label} · {rsk}").add_to(layer)
                layer.add_to(fmap)
            folium.LayerControl(collapsed=False).add_to(fmap)
            st_folium(fmap, use_container_width=True, height=355, returned_objects=[], key="pnis_overview_map")
            st.caption(f"Road source: {road_path_overview.name if road_path_overview else 'not found'} · Candidate coordinates mapped: {len(overview_points) if overview_show_candidates else 0}. Road display may be sampled for performance; source files are not modified.")
        except ImportError:
            st.info("Install folium and streamlit-folium to enable the interactive map. The map workspace is available on the Geospatial Intelligence page once dependencies are installed.")
        except Exception as exc:
            st.warning(f"The interactive map could not be rendered: {exc}")
        if overview_map_error:
            st.caption(f"Road layer note: {overview_map_error}")
        st.markdown("</div>", unsafe_allow_html=True)

    with intel_col:
        st.markdown("<div class='panel' style='padding:.85rem'>", unsafe_allow_html=True)
        st.markdown("**Candidate Review Priorities**<div class='subtle' style='font-size:.72rem'>Risk classes from the active worklist</div>", unsafe_allow_html=True)
        if candidates is not None and risk_col:
            risk_counts = candidates[risk_col].map(classify_risk).value_counts().rename_axis("Risk tier").reset_index(name="Records")
            if PLOTLY_AVAILABLE:
                palette = {"HIGH":"#ff667a", "ELEVATED":"#ffbd69", "STANDARD":"#36d7b5", "UNKNOWN":"#61798e"}
                fig = px.pie(risk_counts, names="Risk tier", values="Records", hole=.62, color="Risk tier", color_discrete_map=palette, template="plotly_dark")
                fig.update_layout(height=205, margin=dict(l=0,r=0,t=5,b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=True, legend=dict(font=dict(size=10), orientation="h", y=-.1), font=dict(color="#dbe8f4"))
                fig.update_traces(textinfo="percent", textfont_size=10, marker_line_width=1, marker_line_color="#0a1725")
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False}, key="overview_risk_pie")
            else:
                st.dataframe(risk_counts, hide_index=True, use_container_width=True)
        else:
            st.caption("Risk distribution unavailable: a worklist or recognized risk field was not found.")
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)
        st.markdown("<div class='panel' style='padding:.85rem'>", unsafe_allow_html=True)
        st.markdown("**Field Evidence & Network Readiness**<div class='subtle' style='font-size:.72rem'>Evidence and routing checks</div>", unsafe_allow_html=True)
        readiness = [
            ("Candidate worklist", candidate_path is not None and candidates is not None),
            ("Road geometry source", road_path_overview is not None),
            ("Graph node table", nodes_path is not None),
            ("Graph edge table", edges_path is not None),
            ("Graph audit", audit_path is not None and audit_data is not None),
        ]
        ready_n = sum(ok for _, ok in readiness)
        st.markdown(f"<div style='display:flex;align-items:baseline;gap:.5rem'><span style='font-size:1.7rem;font-weight:800;color:#f1f7fc'>{ready_n}/{len(readiness)}</span><span class='subtle' style='font-size:.78rem'>project artifacts detected</span></div>", unsafe_allow_html=True)
        for label, ok in readiness:
            st.markdown(f"<div style='display:flex;justify-content:space-between;border-bottom:1px solid #203448;padding:.3rem 0;font-size:.75rem'><span>{label}</span><span style='color:{'#42d7b5' if ok else '#ffbd69'}'>{'● Ready' if ok else '○ Not found'}</span></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
    bottom_a, bottom_b, bottom_c = st.columns([1.15, 1.15, 1], gap="small")
    with bottom_a:
        st.markdown("<div class='panel' style='padding:.85rem'>", unsafe_allow_html=True)
        st.markdown("**Road Access Composition**<div class='subtle' style='font-size:.72rem'>Road classes in the existing spatial source</div>", unsafe_allow_html=True)
        road_path_for_chart = find_file(["phase2c_v2_sidama_buffered_roads.gpkg", "phase2c_sidama_buffered_roads.gpkg", "phase2b_sidama_intersecting_roads.gpkg"])
        try:
            import geopandas as gpd
            if road_path_for_chart:
                import pyogrio
                layers = [str(x[0]) for x in pyogrio.list_layers(road_path_for_chart) if len(x) and x[0]]
                lay = "sidama_buffered_roads_v2" if "sidama_buffered_roads_v2" in layers else (layers[0] if layers else None)
                class_df = gpd.read_file(road_path_for_chart, layer=lay, columns=None) if lay else gpd.read_file(road_path_for_chart)
                cls = first_col(class_df, ["fclass", "road_class", "highway", "class"])
                if cls:
                    class_counts = class_df[cls].fillna("Unknown").astype(str).value_counts().head(6).rename_axis("Road class").reset_index(name="Features")
                    if PLOTLY_AVAILABLE:
                        fig = px.bar(class_counts.sort_values("Features"), x="Features", y="Road class", orientation="h", template="plotly_dark", color="Features", color_continuous_scale=[[0,"#1c6574"],[1,"#43d6b5"]])
                        fig.update_layout(height=205, margin=dict(l=0,r=5,t=5,b=5), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", coloraxis_showscale=False, font=dict(color="#dbe8f4",size=10), xaxis_title="", yaxis_title="")
                        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False}, key="overview_road_classes")
                    else: st.dataframe(class_counts, hide_index=True, use_container_width=True)
                else: st.caption("Road-class field not found in source layer.")
            else: st.caption("Road GeoPackage not found.")
        except Exception as exc:
            st.caption(f"Road composition unavailable: {exc}")
        st.markdown("</div>", unsafe_allow_html=True)
    with bottom_b:
        st.markdown("<div class='panel' style='padding:.85rem'>", unsafe_allow_html=True)
        st.markdown("**Routing Validation**<div class='subtle' style='font-size:.72rem'>Graph artifacts and review status</div>", unsafe_allow_html=True)
        if nodes_path and edges_path:
            st.markdown("<span class='status status-green'>GRAPH TABLES FOUND</span>", unsafe_allow_html=True)
            try:
                node_rows = sum(1 for _ in open(nodes_path, encoding="utf-8-sig")) - 1
                edge_rows = sum(1 for _ in open(edges_path, encoding="utf-8-sig")) - 1
                st.markdown(f"<div style='display:flex;gap:1rem;margin:.55rem 0'><div><div class='subtle' style='font-size:.7rem'>Node rows</div><b>{fmt_int(node_rows)}</b></div><div><div class='subtle' style='font-size:.7rem'>Edge rows</div><b>{fmt_int(edge_rows)}</b></div></div>", unsafe_allow_html=True)
            except Exception:
                st.caption("Graph files detected; row counts could not be read.")
        else:
            st.markdown("<span class='status status-amber'>GRAPH NOT FULLY DETECTED</span>", unsafe_allow_html=True)
            st.caption("Routing remains unavailable until the expected graph node and edge tables are present.")
        st.caption("A computed shortest path is not a field-verified vehicle-access approval.")
        st.markdown("</div>", unsafe_allow_html=True)
    with bottom_c:
        st.markdown("<div class='panel' style='padding:.85rem'>", unsafe_allow_html=True)
        st.markdown("**Operations Watchlist**<div class='subtle' style='font-size:.72rem'>Actionable items from current project files</div>", unsafe_allow_html=True)
        alerts = []
        if candidates is None: alerts.append(("!", "Candidate worklist not found", "Load the Phase 2G.18 worklist."))
        elif high_count: alerts.append(("!", f"{fmt_int(high_count)} high-risk candidates", "Prioritize field review; do not auto-approve."))
        if not (nodes_path and edges_path): alerts.append(("⌁", "Routing graph incomplete", "Check graph node and edge CSVs."))
        if audit_data and audit_path: alerts.append(("✓", "Graph audit available", audit_path.name))
        if not alerts: alerts.append(("✓", "No additional alerts detected", "Review source provenance for details."))
        for symbol, heading, detail in alerts[:4]:
            st.markdown(f"<div style='display:flex;gap:.55rem;padding:.42rem 0;border-bottom:1px solid #203448'><span style='color:#ffbd69'>{symbol}</span><div><div style='font-size:.76rem;font-weight:700;color:#e6f0fa'>{heading}</div><div class='subtle' style='font-size:.68rem'>{detail}</div></div></div>", unsafe_allow_html=True)
        if st.button("Open Data & Provenance →", use_container_width=True, key="overview_provenance_button"):
            st.session_state["overview_nav_request"] = "▧  Data & Provenance"
            st.info("Choose Data & Provenance from the navigation menu to inspect source artifacts.")
        st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Geospatial Intelligence
# -----------------------------------------------------------------------------
elif page == "Geospatial Intelligence":
    section("Geospatial intelligence", "Interactive spatial workspace · source-backed candidate and road layers")
    road_path = find_file(["phase2c_v2_sidama_buffered_roads.gpkg", "phase2c_sidama_buffered_roads.gpkg", "phase2b_sidama_intersecting_roads.gpkg"])

    # Map controls: only toggle layers that exist in source data.
    c1, c2, c3 = st.columns([1, 1, 1.3])
    with c1:
        show_candidates = st.toggle("Candidate locations", value=True, key="geo_show_candidates")
    with c2:
        show_roads = st.toggle("Road network", value=True, key="geo_show_roads")
    with c3:
        road_limit = st.selectbox("Road detail level", ["Balanced (up to 6,000 features)", "Detailed (up to 12,000 features)"], index=0, key="geo_road_detail")
    max_roads = 6000 if road_limit.startswith("Balanced") else 12000

    candidate_points = pd.DataFrame()
    candidate_lat = candidate_lon = candidate_risk = candidate_id = candidate_status = None
    if candidates is not None:
        candidate_lat = first_col(candidates, ["latitude", "lat", "y", "decimal_latitude", "lat_dd"])
        candidate_lon = first_col(candidates, ["longitude", "lon", "lng", "x", "decimal_longitude", "long_dd"])
        candidate_risk = first_col(candidates, ["risk_class", "risk_category", "risk_level", "risk", "priority_class"])
        candidate_id = first_col(candidates, ["candidate_record_id", "candidate_id", "record_id", "candidateid", "id"])
        candidate_status = first_col(candidates, ["fieldwork_status", "field_status", "status", "review_status"])
        if candidate_lat and candidate_lon:
            candidate_points = candidates.copy()
            candidate_points[candidate_lat] = pd.to_numeric(candidate_points[candidate_lat], errors="coerce")
            candidate_points[candidate_lon] = pd.to_numeric(candidate_points[candidate_lon], errors="coerce")
            candidate_points = candidate_points.dropna(subset=[candidate_lat, candidate_lon])
            candidate_points = candidate_points[candidate_points[candidate_lat].between(-90, 90) & candidate_points[candidate_lon].between(-180, 180)]

    # Read and prepare real road geometry for an interactive Folium map.
    roads = None
    road_error = None
    road_source_count = None
    if show_roads and road_path:
        try:
            import geopandas as gpd
            import pyogrio
            layer_names = []
            try:
                listed = pyogrio.list_layers(road_path)
                layer_names = [str(x[0]) for x in listed if len(x) and x[0]]
            except Exception:
                pass
            requested_layer = "sidama_buffered_roads_v2"
            layer_to_read = requested_layer if requested_layer in layer_names else (layer_names[0] if layer_names else None)
            roads = gpd.read_file(road_path, layer=layer_to_read) if layer_to_read else gpd.read_file(road_path)
            road_source_count = len(roads)
            if roads.crs is not None and str(roads.crs).upper() not in {"EPSG:4326", "OGC:CRS84"}:
                # Simplify in the projected source CRS before transforming for web mapping.
                try:
                    roads[roads.geometry.name] = roads.geometry.simplify(25, preserve_topology=True)
                except Exception:
                    pass
                roads = roads.to_crs("EPSG:4326")
            if len(roads) > max_roads:
                # Deterministic visualization subset; all calculations remain based on original source data.
                roads = roads.iloc[::max(1, len(roads) // max_roads)].head(max_roads).copy()
            roads = roads[roads.geometry.notna() & ~roads.geometry.is_empty].copy()
            road_class_col = first_col(roads, ["fclass", "road_class", "highway", "class"])
            name_col = first_col(roads, ["name", "road_name", "ref"])
            keep = [roads.geometry.name]
            for col in [road_class_col, name_col]:
                if col and col not in keep:
                    keep.append(col)
            roads = roads[keep].copy()
            roads = roads[roads.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
            roads = roads.to_crs("EPSG:4326")
        except Exception as exc:
            roads = None
            road_error = str(exc)

    # Establish map center from real coordinates only.
    map_center = [7.0, 38.3]
    if show_candidates and not candidate_points.empty:
        map_center = [float(candidate_points[candidate_lat].median()), float(candidate_points[candidate_lon].median())]
    elif roads is not None and not roads.empty:
        bounds = roads.total_bounds
        map_center = [(float(bounds[1]) + float(bounds[3])) / 2, (float(bounds[0]) + float(bounds[2])) / 2]

    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown("**Spatial operations map**  ·  <span style='color:#38d6c0'>●</span> candidate layer  ·  <span style='color:#5b9cff'>━</span> road layer", unsafe_allow_html=True)
    try:
        import folium
        from streamlit_folium import st_folium
        fmap = folium.Map(location=map_center, zoom_start=8, tiles=None, control_scale=True, prefer_canvas=True)
        folium.TileLayer("CartoDB dark_matter", name="Dark basemap", control=True).add_to(fmap)
        folium.TileLayer("OpenStreetMap", name="Street basemap", control=True).add_to(fmap)
        if show_roads and roads is not None and not roads.empty:
            road_class_col = first_col(roads, ["fclass", "road_class", "highway", "class"])
            def road_style(feature):
                props = feature.get("properties", {})
                rc = str(props.get(road_class_col, "")).lower() if road_class_col else ""
                color = "#38d6c0" if rc in {"primary", "trunk", "motorway"} else ("#4b9cff" if rc in {"secondary", "tertiary"} else "#617b96")
                return {"color": color, "weight": 2.1 if color == "#38d6c0" else 1.25, "opacity": 0.78}
            tooltip_fields = [c for c in [road_class_col, first_col(roads, ["name", "road_name", "ref"])] if c]
            folium.GeoJson(roads, name="Road network", style_function=road_style,
                tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, aliases=[nice_name(c) for c in tooltip_fields]) if tooltip_fields else None,
                smooth_factor=1.5, control=True).add_to(fmap)
        if show_candidates and not candidate_points.empty:
            fg = folium.FeatureGroup(name="Candidate locations", show=True)
            for _, row in candidate_points.iterrows():
                risk = classify_risk(row[candidate_risk]) if candidate_risk else "UNKNOWN"
                color = {"HIGH":"#ff667a", "ELEVATED":"#ffbd69", "STANDARD":"#38d6c0"}.get(risk, "#91a5bb")
                cid = str(row[candidate_id]) if candidate_id and pd.notna(row[candidate_id]) else f"Candidate row {row.name}"
                tooltip = [cid, f"Risk: {risk}"]
                if candidate_status and pd.notna(row[candidate_status]):
                    tooltip.append(f"Status: {row[candidate_status]}")
                folium.CircleMarker(location=[float(row[candidate_lat]), float(row[candidate_lon])], radius=6,
                    color="#07111f", weight=1.5, fill=True, fill_color=color, fill_opacity=.95,
                    tooltip=" · ".join(tooltip)).add_to(fg)
            fg.add_to(fmap)
        folium.LayerControl(collapsed=False).add_to(fmap)
        st_folium(fmap, use_container_width=True, height=610, returned_objects=[], key="pnis_interactive_geo_map")
    except ImportError:
        st.warning("Interactive map dependencies are missing. Install `folium` and `streamlit-folium` to enable map layers.")
        if show_candidates and not candidate_points.empty and PLOTLY_AVAILABLE:
            fig = px.scatter_mapbox(candidate_points, lat=candidate_lat, lon=candidate_lon,
                color=candidate_points[candidate_risk].map(classify_risk) if candidate_risk else None,
                hover_name=candidate_id if candidate_id else None, zoom=7, height=560, mapbox_style="carto-darkmatter",
                color_discrete_map={"HIGH":"#ff667a","ELEVATED":"#ffbd69","STANDARD":"#38d6c0","UNKNOWN":"#91a5bb"})
            fig.update_layout(margin=dict(l=0,r=0,t=0,b=0), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:
        st.error(f"Map rendering failed safely: {exc}")
    st.markdown('</div>', unsafe_allow_html=True)

    # Spatial layer status / diagnostics in compact cards.
    m1, m2, m3 = st.columns(3)
    with m1:
        metric_card("Candidate points", fmt_int(len(candidate_points)) if candidate_lat and candidate_lon else "Unavailable", "Valid coordinate pairs" if candidate_lat and candidate_lon else "No recognized coordinate columns")
    with m2:
        metric_card("Road features", fmt_int(road_source_count) if road_source_count is not None else "Unavailable", f"Displaying up to {max_roads:,} features" if road_source_count is not None else (road_error or "Road GeoPackage not found"))
    with m3:
        metric_card("Coordinate reference", "WGS84 map", "Roads transformed for web display when CRS is available")
    if road_error:
        st.caption(f"Road layer could not be loaded: {road_error}")
    if road_source_count is not None and road_source_count > max_roads:
        st.caption(f"Map rendering uses a deterministic display subset of {max_roads:,} road features out of {road_source_count:,} source features for browser performance. Source data is not modified; the subset is for visualization only.")
    if candidate_points.empty and (not show_roads or roads is None or roads.empty):
        show_missing("No geographic layers are currently available to display.", "Check the candidate coordinate fields and the Phase 2C road GeoPackage under data/processed.")
    with st.expander("Layer metadata and provenance"):
        st.write({
            "Project root": str(PROJECT_ROOT),
            "Candidate source": str(candidate_path) if candidate_path else "Not found",
            "Latitude field": candidate_lat or "Not detected",
            "Longitude field": candidate_lon or "Not detected",
            "Risk field": candidate_risk or "Not detected",
            "Road source": str(road_path) if road_path else "Not found",
            "Road source feature count": road_source_count,
            "Map layer controls": "Basemap and source layers",
        })

# -----------------------------------------------------------------------------
# Candidate Intelligence
# -----------------------------------------------------------------------------
elif page == "Candidate Intelligence":
    section("Candidate intelligence", "Filter and inspect the actual candidate worklist. No demo rows are generated when source files are absent.")
    if candidates is None:
        show_missing("No readable candidate dataset was found.", "Place phase2g18_risk_prioritized_worklist.csv in data/processed, or choose a different project root in the sidebar.")
    else:
        df = candidates.copy()
        risk_col = first_col(df, ["risk_class", "risk_category", "risk_level", "risk", "priority_class"])
        id_col = first_col(df, ["candidate_record_id", "candidate_id", "record_id", "candidateid", "id"])
        status_col = first_col(df, ["fieldwork_status", "field_status", "status", "review_status"])
        commodity_col = first_col(df, ["commodity", "crop", "product", "commodity_type"])
        risk_filter_col = "_pnis_risk_filter"
        if risk_col:
            df[risk_filter_col] = df[risk_col].map(classify_risk)
        with st.container(border=True):
            f1, f2, f3 = st.columns([1, 1, 1.25])
            with f1:
                risk_options = sorted(df[risk_filter_col].dropna().astype(str).unique().tolist()) if risk_col else []
                selected_risks = st.multiselect("Risk tier", risk_options, default=risk_options)
            with f2:
                status_options = sorted(df[status_col].dropna().astype(str).unique().tolist()) if status_col else []
                selected_status = st.multiselect("Fieldwork status", status_options, default=status_options)
            with f3:
                search = st.text_input("Search candidate / location / commodity", placeholder="Type an ID, place, or keyword")
        if risk_col:
            df = df[df[risk_filter_col].isin(selected_risks)]
        if status_col and selected_status:
            df = df[df[status_col].astype(str).isin(selected_status)]
        elif status_col and not selected_status:
            df = df.iloc[0:0]
        if search.strip():
            mask = df.astype(str).apply(lambda col: col.str.contains(search.strip(), case=False, na=False)).any(axis=1)
            df = df[mask]
        st.caption(f"Showing {len(df):,} of {len(candidates):,} records · Source: {candidate_path.name if candidate_path else 'unknown'}")
        if risk_col and PLOTLY_AVAILABLE and not df.empty:
            risk_summary = df[risk_filter_col].value_counts().rename_axis("Risk tier").reset_index(name="Records")
            chart = px.pie(risk_summary, names="Risk tier", values="Records", hole=.68,
                           color="Risk tier", color_discrete_map={"HIGH":"#ff6f7d","ELEVATED":"#ffbd69","STANDARD":"#38d6c0","UNKNOWN":"#71869c"},
                           template="plotly_dark")
            chart.update_layout(height=280, margin=dict(l=8,r=8,t=8,b=8), paper_bgcolor="rgba(0,0,0,0)",
                                plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#d9e7f5"), legend_title_text="Risk tier")
            st.plotly_chart(chart, use_container_width=True, config={"displayModeBar": False})
        show_cols = [c for c in [id_col, risk_col, status_col, commodity_col] if c]
        # Put the identifying fields first while preserving all fields for the downloadable extract.
        show_cols += [c for c in df.columns if c not in show_cols and c != risk_filter_col]
        display_table(df[show_cols].drop(columns=[risk_filter_col], errors="ignore"))
        st.download_button("Download filtered candidates (CSV)", df.drop(columns=[risk_filter_col], errors="ignore").to_csv(index=False).encode("utf-8-sig"), file_name="pnis_filtered_candidates.csv", mime="text/csv")

        lat_col = first_col(df, ["latitude", "lat", "y", "decimal_latitude", "lat_dd"])
        lon_col = first_col(df, ["longitude", "lon", "lng", "x", "decimal_longitude", "long_dd"])
        if lat_col and lon_col:
            map_df = df[[lat_col, lon_col]].copy()
            map_df[lat_col] = pd.to_numeric(map_df[lat_col], errors="coerce")
            map_df[lon_col] = pd.to_numeric(map_df[lon_col], errors="coerce")
            map_df = map_df.dropna()
            map_df = map_df[map_df[lat_col].between(-90, 90) & map_df[lon_col].between(-180, 180)]
            if not map_df.empty:
                st.markdown("### Candidate locations")
                st.map(map_df.rename(columns={lat_col: "latitude", lon_col: "longitude"}), latitude="latitude", longitude="longitude", size=12)
            else:
                st.caption("Coordinate columns were found, but no valid latitude/longitude pairs remain after filtering.")
        else:
            st.caption("Map hidden: the worklist does not contain recognizable latitude and longitude columns.")

# -----------------------------------------------------------------------------
# Fieldwork Register
# -----------------------------------------------------------------------------
elif page == "Fieldwork Register":
    section("Fieldwork register", "A careful capture workflow for field observations. Recording an observation does not approve a road or route.")
    st.markdown('<div class="warning-note"><b>Governance:</b> Field observations are evidence, not routing authorization. Keep routing approval at <b>NO</b> until the project’s formal review process confirms the decision.</div>', unsafe_allow_html=True)
    if candidates is None:
        show_missing("Candidate worklist is not available, so the register cannot prefill candidate IDs.", "Add the Phase 2G.18 worklist to data/processed or use the Data & Provenance page to confirm the active project root.")
    else:
        df = candidates.copy()
        id_col = first_col(df, ["candidate_record_id", "candidate_id", "record_id", "candidateid", "id"])
        risk_col = first_col(df, ["risk_class", "risk_category", "risk_level", "risk"])
        location_col = first_col(df, ["location_name", "candidate_name", "site_name", "name", "locality", "woreda", "kebele"])
        if not id_col:
            show_missing("The dataset is readable, but no recognizable candidate ID column was found.", "Expected one of: candidate_record_id, candidate_id, record_id, id.")
        else:
            records = df[id_col].dropna().astype(str).drop_duplicates().tolist()
            with st.form("field_observation_form", clear_on_submit=False):
                candidate_id = st.selectbox("Candidate ID", records, index=None, placeholder="Choose a candidate")
                selected = df[df[id_col].astype(str).eq(str(candidate_id))] if candidate_id else pd.DataFrame()
                if not selected.empty:
                    row = selected.iloc[0]
                    details = []
                    if risk_col: details.append(f"Risk tier: {row.get(risk_col, '—')}")
                    if location_col: details.append(f"Location: {row.get(location_col, '—')}")
                    st.caption(" · ".join(details))
                f1, f2 = st.columns(2)
                with f1:
                    observed_on = st.date_input("Observation date", value=None)
                    observer = st.text_input("Observer / team", placeholder="Enter the actual observer")
                    access_status = st.selectbox("Vehicle access observed", ["Not assessed", "Accessible at visit", "Restricted / difficult", "Not accessible", "Seasonal / uncertain"])
                    surface = st.selectbox("Observed road surface", ["Not assessed", "Paved", "Gravel", "Earth / dirt", "Track / path", "Mixed", "Other"])
                with f2:
                    seasonality = st.selectbox("Seasonal access", ["Not assessed", "All-season observed", "Wet-season concern", "Dry-season only / likely", "Unknown"])
                    vehicle_type = st.selectbox("Vehicle suitability", ["Not assessed", "Motorcycle / small vehicle", "Pickup / light truck", "Medium truck", "Heavy truck", "Unknown"])
                    barrier = st.selectbox("Access barrier", ["Not assessed", "None observed at visit", "Bridge / culvert", "Slope / erosion", "Width / turning", "Security / permission", "Other"])
                    approval = st.selectbox("Routing approval", ["NO — field evidence only"], disabled=True)
                notes = st.text_area("Observed facts and limitations", placeholder="Record what was directly observed. Separate observation from assumption.", height=110)
                evidence_ref = st.text_input("Evidence reference", placeholder="Photo filename, GPS track, form ID, or document reference")
                submitted = st.form_submit_button("Prepare observation record", type="primary", use_container_width=True)
            if submitted:
                if not candidate_id:
                    st.error("Choose a candidate ID before preparing a record.")
                elif not observer.strip():
                    st.error("Enter the actual observer or field team.")
                elif not notes.strip() and not evidence_ref.strip():
                    st.error("Add observed facts or an evidence reference so the record is traceable.")
                else:
                    record = {
                        "candidate_record_id": candidate_id,
                        "observation_date": observed_on.isoformat() if observed_on else "",
                        "observer": observer.strip(),
                        "vehicle_access_observed": access_status,
                        "road_surface_observed": surface,
                        "seasonal_access_observed": seasonality,
                        "vehicle_suitability_observed": vehicle_type,
                        "access_barrier_observed": barrier,
                        "observation_notes": notes.strip(),
                        "evidence_reference": evidence_ref.strip(),
                        "routing_approval_granted": "NO",
                        "record_type": "field_observation_not_route_approval",
                    }
                    st.success("Observation record prepared. It has not been written to disk and does not grant routing approval.")
                    st.download_button("Download observation record (CSV)", pd.DataFrame([record]).to_csv(index=False).encode("utf-8-sig"), file_name=f"pnis_field_observation_{slug(candidate_id)}.csv", mime="text/csv")
                    st.download_button("Download observation record (JSON)", json.dumps(record, indent=2, ensure_ascii=False).encode("utf-8"), file_name=f"pnis_field_observation_{slug(candidate_id)}.json", mime="application/json")

# -----------------------------------------------------------------------------
# Road Network
# -----------------------------------------------------------------------------
elif page == "Road Network":
    section("Road network readiness", "Inspect real audit outputs and graph tables without implying that mapped roads are all passable.")
    if audit_data:
        st.markdown(f"**Audit source:** `{audit_path.name}`")
        flat = flatten_dict(audit_data)
        audit_df = pd.DataFrame([{"Field": k, "Value": v} for k, v in flat.items()])
        display_table(audit_df, height=340)
        st.download_button("Download flattened audit (CSV)", audit_df.to_csv(index=False).encode("utf-8-sig"), file_name="pnis_graph_audit_fields.csv", mime="text/csv")
    else:
        show_missing("No recognized Phase 2E graph audit JSON was found. Graph readiness metrics are not displayed as estimates.", "Expected: phase2e_vehicle_graph_audit.json or phase2e1_route_validation_audit.json in data/processed.")

    st.markdown("### Graph files")
    file_rows = []
    for label, path in [("Nodes", nodes_path), ("Edges", edges_path)]:
        if path:
            try:
                size_mb = path.stat().st_size / (1024 * 1024)
                file_rows.append({"Artifact": label, "File": path.name, "Size (MB)": round(size_mb, 2), "Status": "Found"})
            except OSError:
                file_rows.append({"Artifact": label, "File": path.name, "Size (MB)": None, "Status": "Found; size unavailable"})
        else:
            file_rows.append({"Artifact": label, "File": "—", "Size (MB)": None, "Status": "Not found"})
    display_table(pd.DataFrame(file_rows), height=150)

    if edges_path:
        st.markdown("### Edge table sample")
        try:
            edges = normalized_frame(pd.read_csv(edges_path, nrows=5000, low_memory=False))
            st.caption("Preview is limited to the first 5,000 rows to keep the dashboard responsive. Full file is unchanged.")
            display_table(edges.head(100), height=330)
            st.download_button("Download edge preview (CSV)", edges.head(5000).to_csv(index=False).encode("utf-8-sig"), file_name="pnis_edge_preview_5000.csv", mime="text/csv")
        except Exception as exc:
            st.error(f"Could not preview edge file: {exc}")
    else:
        st.caption("Edge preview unavailable because no recognized graph edge CSV was found.")

# -----------------------------------------------------------------------------
# Routing Analysis — real graph only, no arithmetic placeholders
# -----------------------------------------------------------------------------
elif page == "Routing Analysis":
    section("Routing analysis", "Shortest paths are calculated only from a usable node/edge table with recognized endpoint and distance fields.")
    st.markdown('<div class="warning-note"><b>Operational caution:</b> A graph path is not proof of legal access, current passability, vehicle clearance, bridge capacity, or seasonal reliability. Validate the route with field evidence before dispatch.</div>', unsafe_allow_html=True)
    if not nodes_path or not edges_path:
        show_missing("Routing is disabled because the expected graph node and edge CSV files were not both found.", "Expected names include phase2e_vehicle_graph_nodes.csv and phase2e_vehicle_graph_edges.csv. No route distance or travel time is fabricated.")
    else:
        try:
            nodes = normalized_frame(pd.read_csv(nodes_path, low_memory=False))
            edges = normalized_frame(pd.read_csv(edges_path, low_memory=False))
            node_id_col = first_col(nodes, ["node_id", "nodeid", "id", "osmid", "node"])
            from_col = first_col(edges, ["source", "from_node", "u", "origin_node", "start_node", "from"])
            to_col = first_col(edges, ["target", "to_node", "v", "destination_node", "end_node", "to"])
            weight_col = first_col(edges, ["length_m", "length_meters", "distance_m", "distance_meters", "length", "weight", "cost_m", "edge_length_m"])
            if not all([node_id_col, from_col, to_col, weight_col]):
                st.error("Graph files were found, but the required fields could not be identified safely.")
                st.write({"Node ID field": node_id_col, "From field": from_col, "To field": to_col, "Distance/cost field": weight_col})
                st.caption("Rename columns only after confirming their meaning. A generic 'weight' field is treated as distance only if no explicit distance column exists.")
                st.markdown("**Detected node columns:** " + ", ".join(nodes.columns))
                st.markdown("**Detected edge columns:** " + ", ".join(edges.columns))
            else:
                import networkx as nx
                nodes[node_id_col] = nodes[node_id_col].astype(str)
                edges[from_col] = edges[from_col].astype(str)
                edges[to_col] = edges[to_col].astype(str)
                edges[weight_col] = pd.to_numeric(edges[weight_col], errors="coerce")
                valid_edges = edges.dropna(subset=[from_col, to_col, weight_col]).copy()
                valid_edges = valid_edges[valid_edges[weight_col] >= 0]
                node_ids = set(nodes[node_id_col].dropna().astype(str))
                valid_edges = valid_edges[valid_edges[from_col].isin(node_ids) & valid_edges[to_col].isin(node_ids)]
                if valid_edges.empty:
                    st.error("No valid edges remain after checking endpoint IDs and non-negative costs. Routing is unavailable.")
                else:
                    graph = nx.DiGraph()
                    graph.add_nodes_from(node_ids)
                    graph.add_weighted_edges_from(valid_edges[[from_col, to_col, weight_col]].itertuples(index=False, name=None), weight="_pnis_cost")
                    st.caption(f"Loaded {len(node_ids):,} node IDs and {len(valid_edges):,} valid directed edge rows from project files. Parallel edges are collapsed by DiGraph; use a MultiDiGraph if preserving parallel-road alternatives is required.")
                    with st.form("route_query_form"):
                        q1, q2 = st.columns(2)
                        with q1: origin = st.text_input("Origin node ID", placeholder="Paste an exact node ID from the graph")
                        with q2: destination = st.text_input("Destination node ID", placeholder="Paste an exact node ID from the graph")
                        calculate = st.form_submit_button("Calculate shortest path", type="primary", use_container_width=True)
                    if calculate:
                        if origin not in node_ids or destination not in node_ids:
                            st.error("Both node IDs must match the graph's node ID column exactly.")
                        else:
                            try:
                                path_nodes = nx.shortest_path(graph, source=origin, target=destination, weight="_pnis_cost", method="dijkstra")
                                cost = nx.shortest_path_length(graph, source=origin, target=destination, weight="_pnis_cost", method="dijkstra")
                                route_edges = []
                                for u, v in zip(path_nodes[:-1], path_nodes[1:]):
                                    route_edges.append({"from_node": u, "to_node": v, "edge_cost": graph[u][v]["_pnis_cost"]})
                                st.success("A shortest path was found in the supplied graph.")
                                r1, r2, r3 = st.columns(3)
                                with r1: metric_card("Graph cost", fmt_float(cost, 2), f"Source field: {weight_col}")
                                with r2: metric_card("Path nodes", fmt_int(len(path_nodes)), "Includes origin and destination")
                                with r3: metric_card("Path edges", fmt_int(max(0, len(path_nodes)-1)), "Directed transitions")
                                st.markdown("**Node sequence**")
                                st.code(" → ".join(path_nodes), language=None)
                                route_df = pd.DataFrame(route_edges)
                                display_table(route_df, height=280)
                                st.download_button("Download calculated path (CSV)", route_df.to_csv(index=False).encode("utf-8-sig"), file_name="pnis_calculated_path.csv", mime="text/csv")
                                st.caption("The displayed graph cost is in the units of the source field. It is labeled as kilometres only when the source field itself explicitly defines kilometres; no travel time is estimated.")
                            except nx.NetworkXNoPath:
                                st.error("No directed path exists between these nodes in the loaded graph.")
                            except nx.NodeNotFound:
                                st.error("Origin or destination is not present in the loaded graph.")
        except Exception as exc:
            st.error(f"Could not load graph tables safely: {exc}")

# -----------------------------------------------------------------------------
# Data & Provenance
# -----------------------------------------------------------------------------
elif page == "Data & Provenance":
    section("Data & provenance", "See which files this dashboard found and which formats it supports.")
    st.markdown("### Active project paths")
    st.code(f"Project root: {PROJECT_ROOT}\nProcessed data: {PROCESSED}", language=None)
    artifact_names = [
        "phase2g18_risk_prioritized_worklist.csv",
        "phase2g19_fieldwork_execution_package.xlsx",
        "phase2g19_field_observation_template.csv",
        "phase2e_vehicle_graph_audit.json",
        "phase2e1_route_validation_audit.json",
        "phase2e_vehicle_graph_nodes.csv",
        "phase2e_vehicle_graph_edges.csv",
        "phase2c_v2_sidama_buffered_roads.gpkg",
        "phase2c_v2_road_connectivity_audit.txt",
        "phase2d_road_attribute_audit.txt",
    ]
    rows = []
    for name in artifact_names:
        path = PROCESSED / name
        exists = path.exists()
        rows.append({"Expected artifact": name, "Status": "Found" if exists else "Not found", "Size (MB)": round(path.stat().st_size / 1048576, 2) if exists and path.is_file() else None})
    display_table(pd.DataFrame(rows), height=380)

    st.markdown("### Current dataset schema")
    if candidate_path and candidates is not None:
        schema = pd.DataFrame({
            "Column": candidates.columns,
            "Detected type": [str(candidates[c].dtype) for c in candidates.columns],
            "Non-empty rows": [int(candidates[c].notna().sum()) for c in candidates.columns],
            "Unique values": [int(candidates[c].nunique(dropna=True)) for c in candidates.columns],
        })
        st.caption(f"Candidate source: {candidate_path.name} · {len(candidates):,} rows · {len(candidates.columns):,} columns")
        display_table(schema, height=400)
        st.download_button("Download dataset schema (CSV)", schema.to_csv(index=False).encode("utf-8-sig"), file_name="pnis_dataset_schema.csv", mime="text/csv")
    else:
        show_missing("No candidate table is currently loaded, so no candidate schema is available.")

    st.markdown("### Data integrity principles")
    st.markdown("""
    - **No synthetic candidate records:** absent source files produce an explicit unavailable state.
    - **No invented route metrics:** route calculations require real graph files and recognized fields.
    - **No automatic approvals:** a field observation is not a routing approval.
    - **Visible provenance:** data sources and schema are shown so reviewers can trace dashboard content.
    - **Non-destructive:** this app reads project files and only offers downloads for user-requested exports; it does not overwrite Phase 2 outputs.
    """)

# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.markdown("---")
footer_left, footer_right = st.columns([2, 1])
with footer_left:
    st.caption("PNIS · Evidence-led planning support · Validate all operational decisions against current field conditions.")
with footer_right:
    st.caption("Dashboard status: read-only source data")
