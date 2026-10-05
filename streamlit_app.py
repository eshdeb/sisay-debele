from __future__ import annotations

_APP_NOTES = """
REACH Climate–Health Early Warning Data Portal · FINAL V15 · DECISION-CENTRED + SPACE-TIME + BRAZIL FACILITY QA

V5.0 restores/preserves the V4.4 + V4.5 functionality and adds:
- Zambia + Brazil country selector.
- Zambia: all 116 districts from the bundled user shapefile.
- Brazil: official IBGE 2024 municipalities loaded state-by-state; Pernambuco is
  the operational default for Recife and Palmares.
- Heatwave, rainfall-driven flood, GloFAS river flood, drought/dry anomaly,
  and compound-hazard screening.
- Physical magnitude, probabilistic/risk-class spatial maps.
- Focus-location time series with ensemble uncertainty.
- GloFAS discharge as a selectable flood hazard, not only a lower-page panel.
- Compound flood+heat, drought+heat, and sequential drought->flood screening.
- Exact valid start/end windows and focus-event timing.
- ENSO/RONI, IOD/DMI for Zambia, and Tropical Atlantic SST-gradient context for Brazil.
- ENSO phase-probability bars with 3-month outlook values and dominant phase.
- Linked temporal + spatial seasonal anomaly visualisation with filled/bar temporal views and contextual basemaps.
- Official NOAA CPC ENSO phase, strength and RONI anomaly outlook visualisations.
- Source portal with direct hyperlinks.
- Transparent decision-maker summary plus optional local Ollama rewrite.
- Pilot-site two-model historical verification: ECMWF IFS vs NOAA GFS against ERA5.
- Facility-level spatial temperature gradients and point forecasts nested under pilot districts/municipalities.
- Point-level ECMWF vs NOAA GFS comparison with ERA5 historical climatology and forecast anomalies.
- High-contrast filled navigation tabs and forecast controls for modern accessible use.
- Labelled facility contour surfaces for temperature and rainfall where spatial variation exists.
- Facility comparison bar charts, parent-area/facility summary statistics and clearer district/facility interpretation.
- Expanded documentation for national geography and REACH pilot facility coverage.
- V13 adds a decision-centred landing page, a clear forecast-to-action journey, stronger visual hierarchy, compact source architecture, cascading selection context, and GitHub architecture/design documentation while preserving all V12 forecast, facility, verification and export functionality.
- V14 adds explicit forecast-valid space-time context and cascading day/week/month facility views.
- V15 adds Brazil-specific label de-cluttering and municipality-boundary coordinate quality control so invalid offshore/out-of-boundary facility points do not drive maps or interpolation.

Scientific boundary:
Compound scores are screening indices unless explicitly described as a forecast
probability. The app never multiplies component probabilities to imply independence.
"""

from pathlib import Path
from datetime import datetime, timezone
from io import StringIO, BytesIO
import hashlib
import json
import re
import time
import unicodedata
import zipfile

import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.colors import Normalize, TwoSlopeNorm, ListedColormap, BoundaryNorm
from matplotlib.cm import ScalarMappable
from scipy.stats import genextreme


ROOT = Path(__file__).resolve().parent
ZAMBIA_GEOJSON = ROOT / "zambia_116_districts.geojson"
ZAMBIA_POINTS = ROOT / "zambia_116_district_forecast_points.csv"
BRAZIL_GEOJSON = ROOT / "brazil_5572_municipalities_simplified.geojson"
BRAZIL_POINTS = ROOT / "brazil_5572_municipality_points.csv"
CACHE_DIR = ROOT / ".reach_cache"
CACHE_DIR.mkdir(exist_ok=True)

# Facility drill-down sources. Facility locations are used for point-specific hazard
# forecasts; operational risk is only claimed when readiness/access inputs are present.
ZAMBIA_FACILITY_QUERY_URL = "https://www.map.gov.zm/arcgis/rest/services/Health/NSDI_Health/MapServer/0/query"
ZAMBIA_FACILITY_SOURCE_URL = "https://www.map.gov.zm/arcgis/rest/services/Health/NSDI_Health/MapServer/0"
BRAZIL_CNES_ENDPOINT = "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos"
BRAZIL_CNES_SOURCE_URL = "https://dadosabertos.saude.gov.br/dataset/cnes-cadastro-nacional-de-estabelecimentos-de-saude"
ZAMBIA_PILOT_FACILITY_XLS = ROOT / "zambia_pilot_facility_details.xls"
ZAMBIA_PILOT_HMIS_CSV = ROOT / "zambia_pilot_hmis_context.csv"
FACILITY_OVERVIEW_OPTION = "District / municipality overview"
FACILITY_SCREEN_SOFT_LIMIT = 180

st.set_page_config(
    page_title="REACH Climate–Health EWS",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.main .block-container{padding-top:.30rem;padding-bottom:2rem;max-width:1780px}
.hero{background:linear-gradient(108deg,#082F49,#075985 55%,#0F766E);
padding:18px 24px;border-radius:18px;color:white;margin-bottom:8px;
box-shadow:0 8px 22px rgba(15,23,42,.12)}
.hero h1{color:white;margin:0;font-size:1.90rem}
.hero p{color:#DDEAF3;margin:.3rem 0 0;font-size:.98rem}
.brandline{display:flex;align-items:center;gap:12px;margin-bottom:7px}
.brandmark{display:inline-flex;align-items:center;justify-content:center;background:#F59E0B;color:#082F49;
font-weight:900;letter-spacing:.08em;padding:7px 12px;border-radius:9px}
.brandtag{font-size:.84rem;color:#CCFBF1;font-weight:650;letter-spacing:.03em}
.footerbrand{margin-top:22px;padding:13px 16px;border-top:1px solid #CBD5E1;color:#475569;font-size:.84rem}
.hoverhint{background:#F8FAFC;border:1px solid #CBD5E1;border-radius:10px;padding:8px 11px;color:#475569;font-size:.86rem}
.panel{background:#fff;border:1px solid #D9E2EC;border-radius:15px;padding:14px;
box-shadow:0 2px 8px rgba(15,23,42,.04)}
.section{font-size:1.18rem;font-weight:760;color:#0F172A;margin:.55rem 0 .3rem}
.summary{background:#EFF6FF;border:1px solid #93C5FD;border-left:6px solid #2563EB;
border-radius:14px;padding:14px 16px;margin:9px 0}
.good{background:#F0FDF4;border-left:5px solid #16A34A;border-radius:8px;padding:10px 13px;margin:8px 0}
.warn{background:#FFF7ED;border-left:5px solid #F97316;border-radius:8px;padding:10px 13px;margin:8px 0}
.source-card{background:white;border:1px solid #D9E2EC;border-radius:12px;padding:10px 12px;min-height:86px}
.source-title{font-weight:800;color:#075985}
.source-note{font-size:.82rem;color:#475569}
div[data-testid="stMetric"]{background:white;border:1px solid #E2E8F0;padding:8px 10px;border-radius:12px}
div.stButton > button{background:#0F766E;color:white;border:0;border-radius:9px;font-weight:800}
div.stButton > button:hover{background:#115E59;color:white;border:0}
a[data-testid="stLinkButton"]{background:#0B5A7A;color:white !important;border-radius:10px;border:0;font-weight:800;box-shadow:0 4px 12px rgba(11,90,122,.15)}

/* ------------------------------------------------------------------
   Accessible scholarly navigation and forecast controls.
   V10 deliberately uses light controls with dark text and a large,
   high-contrast chevron zone so the full selector reads as clickable.
   ------------------------------------------------------------------ */
[data-testid="stTabs"] [role="tablist"],
div[data-baseweb="tab-list"]{
  gap:.48rem !important; display:flex !important; flex-wrap:wrap !important;
  overflow:visible !important; background:#F3F6F8 !important;
  border:1px solid #CDD8DE !important; border-radius:15px !important;
  padding:.50rem !important; margin:.25rem 0 .85rem !important;
  box-shadow:0 2px 8px rgba(15,23,42,.05) !important;
}
[data-testid="stTabs"] [role="tab"],
[data-testid="stTabs"] button[data-baseweb="tab"],
button[data-baseweb="tab"]{
  min-height:48px !important; height:auto !important; white-space:normal !important;
  border-radius:10px !important; padding:.64rem .92rem !important;
  color:#243746 !important; font-weight:820 !important; letter-spacing:.003em !important;
  border:1px solid #C9D5DA !important;
  background:#E7EEF1 !important;
  box-shadow:0 2px 6px rgba(15,23,42,.05) !important;
  opacity:1 !important; cursor:pointer !important;
}
[data-testid="stTabs"] [role="tab"] *,
button[data-baseweb="tab"] *{
  color:#243746 !important; font-weight:820 !important; opacity:1 !important;
}
[data-testid="stTabs"] [role="tab"]:hover,
button[data-baseweb="tab"]:hover{
  background:#DCE8EB !important; border-color:#8FA7AF !important;
  transform:translateY(-1px) !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"],
button[data-baseweb="tab"][aria-selected="true"]{
  background:#496D73 !important;
  color:#FFFFFF !important; border:1px solid #496D73 !important;
  box-shadow:0 3px 9px rgba(42,73,79,.16) !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] *,
button[data-baseweb="tab"][aria-selected="true"] *{color:#FFFFFF !important;}
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-baseweb="tab-border"]{display:none !important;}

/* Forecast setup controls: readable light field + obvious large dropdown button. */
[data-testid="stSelectbox"] label p,
[data-testid="stNumberInput"] label p,
[data-testid="stSlider"] label p,
[data-testid="stRadio"] label p{
  color:#0F172A !important; font-weight:820 !important; font-size:1.12rem !important;
  line-height:1.28 !important; margin-bottom:.20rem !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"]{
  min-height:54px !important; border-radius:12px !important; overflow:hidden !important;
  border:1px solid #AEBFC7 !important;
  background:#EAF0F2 !important;
  box-shadow:0 2px 7px rgba(15,23,42,.06) !important;
  cursor:pointer !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div{
  min-height:54px !important; background:transparent !important;
  border:0 !important; border-radius:0 !important; box-shadow:none !important;
  cursor:pointer !important;
}
[data-testid="stSelectbox"] [role="combobox"],
[data-testid="stSelectbox"] div[aria-haspopup="listbox"]{
  min-height:54px !important; background:transparent !important;
  border:0 !important; border-radius:0 !important; box-shadow:none !important;
  color:#17313D !important; cursor:pointer !important;
}
[data-testid="stSelectbox"] [role="combobox"] *,
[data-testid="stSelectbox"] div[aria-haspopup="listbox"] *{
  color:#17313D !important; font-weight:780 !important; font-size:1.09rem !important;
}
/* Make Streamlit/BaseWeb's chevron area a real visual button rather than a pale sliver. */
[data-testid="stSelectbox"] [data-baseweb="select"] > div > div:last-child{
  min-width:56px !important; width:56px !important; height:54px !important;
  display:flex !important; align-items:center !important; justify-content:center !important;
  background:#3F6872 !important; border-left:1px solid #345761 !important;
  border-radius:0 11px 11px 0 !important; cursor:pointer !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div > div:last-child:hover{
  background:#315761 !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div > div:last-child svg{
  width:22px !important; height:22px !important; fill:#FFFFFF !important; color:#FFFFFF !important;
  stroke:#FFFFFF !important; opacity:1 !important;
}
/* Fallback for Streamlit versions that expose the chevron outside the last inner div. */
[data-testid="stSelectbox"] svg{
  width:22px !important; height:22px !important; fill:#3F6872 !important; color:#3F6872 !important;
  opacity:1 !important; pointer-events:none !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div > div:last-child svg{
  fill:#FFFFFF !important; color:#FFFFFF !important; stroke:#FFFFFF !important;
}
[data-baseweb="popover"] [role="listbox"]{
  background:#FFFFFF !important; border:1px solid #B8C8CF !important;
  box-shadow:0 10px 24px rgba(15,23,42,.12) !important;
}
[data-baseweb="popover"] [role="option"],
[role="listbox"] [role="option"]{
  color:#152A35 !important; background:#FFFFFF !important;
  font-weight:700 !important; font-size:1.02rem !important; min-height:44px !important;
}
[data-baseweb="popover"] [role="option"]:hover,
[role="listbox"] [role="option"]:hover{background:#E7F0F2 !important;color:#17313D !important}
[data-testid="stNumberInput"] input,[data-testid="stTextInput"] input{
  border-radius:10px !important;border:1px solid #94A3B8 !important;background:#F8FAFC !important;font-weight:750 !important
}
[data-testid="stRadio"] div[role="radiogroup"]{gap:.35rem}
[data-testid="stRadio"] div[role="radiogroup"] label{
  background:#EEF2F1 !important;border:1px solid #BCC9C8 !important;border-radius:9px !important;padding:.30rem .52rem !important;font-weight:800 !important
}
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"]{background:#0F766E !important;border-color:#0F766E !important}
div.stDownloadButton > button{
  background:linear-gradient(135deg,#607A88,#617F78) !important;color:#FFFFFF !important;
  border:0 !important;border-radius:10px !important;font-weight:850 !important;
  box-shadow:0 3px 10px rgba(55,78,84,.14) !important
}
div.stDownloadButton > button:hover{filter:brightness(1.07)}

.facility-focus{background:linear-gradient(110deg,#ECFDF5,#EFF6FF);border:1px solid #86EFAC;border-left:6px solid #0F766E;border-radius:14px;padding:12px 15px;margin:9px 0}
.facility-focus b{color:#064E3B}

/* V13 · decision-centred landing page and calmer scientific design system. */
:root{
  --reach-ink:#102A36; --reach-muted:#58707B; --reach-line:#D8E2E6;
  --reach-canvas:#F7FAFB; --reach-card:#FFFFFF; --reach-navy:#123B4A;
  --reach-teal:#2F6F73; --reach-teal-2:#6F9696; --reach-gold:#C99B3D;
  --reach-green:#4E7B68; --reach-clay:#A86F5B;
}
[data-testid="stAppViewContainer"]{background:linear-gradient(180deg,#F9FBFC 0%,#FFFFFF 38%,#FFFFFF 100%)}
.main .block-container{max-width:1680px !important;padding-top:.65rem !important}
.hero-v13{background:linear-gradient(120deg,#102F3B 0%,#164D5C 48%,#2E6E6D 100%);border-radius:22px;padding:1.35rem 1.55rem 1.25rem;color:#fff;box-shadow:0 14px 34px rgba(16,42,54,.15);position:relative;overflow:hidden;margin-bottom:.8rem}
.hero-v13:after{content:"";position:absolute;right:-90px;top:-115px;width:310px;height:310px;border-radius:50%;border:46px solid rgba(255,255,255,.055)}
.hero-v13 .eyebrow{font-size:.77rem;font-weight:850;letter-spacing:.13em;text-transform:uppercase;color:#D5ECE8;margin-bottom:.48rem}
.hero-v13 h1{font-size:2.22rem;line-height:1.08;margin:0 0 .46rem;color:#fff;letter-spacing:-.018em}
.hero-v13 .sub{max-width:980px;color:#E9F3F4;font-size:1.02rem;line-height:1.52;margin:0}
.hero-v13 .trust{display:inline-flex;gap:.45rem;align-items:center;margin-top:.78rem;padding:.34rem .62rem;border-radius:999px;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.18);font-size:.80rem;color:#F5FAFA;font-weight:720}
.journey-wrap{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem;margin:.35rem 0 1rem}
.journey-step{background:#fff;border:1px solid var(--reach-line);border-radius:14px;padding:.78rem .88rem;box-shadow:0 3px 10px rgba(16,42,54,.045)}
.journey-step .n{display:inline-flex;width:26px;height:26px;align-items:center;justify-content:center;border-radius:8px;background:#E5F0EF;color:#255C61;font-weight:900;font-size:.78rem;margin-right:.4rem}
.journey-step b{color:var(--reach-ink);font-size:.91rem}.journey-step span{display:block;color:var(--reach-muted);font-size:.78rem;line-height:1.35;margin-top:.32rem}
.landing-card{background:#FFFFFF;border:1px solid var(--reach-line);border-radius:16px;padding:1rem 1.05rem;box-shadow:0 4px 14px rgba(16,42,54,.05)}
.landing-kicker{font-size:.76rem;letter-spacing:.08em;text-transform:uppercase;color:#66808A;font-weight:850;margin-bottom:.18rem}
.landing-title{font-size:1.08rem;font-weight:850;color:var(--reach-ink);margin-bottom:.2rem}
.landing-copy{color:var(--reach-muted);font-size:.86rem;line-height:1.45}
.source-compact{background:#fff;border:1px solid #D9E3E7;border-radius:12px;padding:.68rem .72rem;min-height:72px}
.source-compact .source-title{font-size:.88rem}.source-compact .source-note{font-size:.75rem;line-height:1.28}
.selection-context{background:#F4F8F8;border:1px solid #CDDCDD;border-left:5px solid #4E7B68;border-radius:12px;padding:.68rem .82rem;margin:.35rem 0 .72rem;color:#29464F;font-size:.86rem;font-weight:690}
.selection-context b{color:#17343D}
.section{letter-spacing:-.006em}
@media(max-width:900px){.journey-wrap{grid-template-columns:1fr 1fr}.hero-v13 h1{font-size:1.72rem}}
@media(max-width:600px){.journey-wrap{grid-template-columns:1fr}.hero-v13{padding:1.05rem}.hero-v13 h1{font-size:1.48rem}}
.facility-note{background:#F8FAFC;border:1px solid #CBD5E1;border-radius:12px;padding:10px 12px;color:#334155}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Configuration / source URLs
# ---------------------------------------------------------------------------
ECMWF_URL = "https://api.open-meteo.com/v1/ecmwf"
GFS_URL = "https://api.open-meteo.com/v1/gfs"
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
SEASONAL_URL = "https://seasonal-api.open-meteo.com/v1/seasonal"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
SINGLE_RUNS_URL = "https://single-runs-api.open-meteo.com/v1/forecast"
FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"

CPC_ENSO_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/probabilities/"
CPC_ENSO_STRENGTH_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/strengths.php"
CPC_ENSO_OUTLOOK_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/outlook/"
DMI_CSV = "https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.csv"
DMI_WEB = "https://psl.noaa.gov/data/timeseries/month/DMI/"
TNA_CSV = "https://psl.noaa.gov/data/correlation/tna.csv"
TSA_CSV = "https://psl.noaa.gov/data/correlation/tsa.csv"
NMME_URL = "https://www.cpc.ncep.noaa.gov/products/NMME/probindex.shtml"
NOAA_PSL_INDICES = "https://psl.noaa.gov/data/climateindices/list/"
NOAA_NAO_URL = "https://psl.noaa.gov/data/20thC_Rean/timeseries/monthly/NAO/"
GLOFAS_SUMMARY_URL = "https://confluence.ecmwf.int/spaces/CEMS/pages/265028883/GloFAS+Flood+Summary"
FBF_PAPER_URL = "https://nhess.copernicus.org/articles/15/895/2015/"
EWEA_PAPER_URL = "https://www.sciencedirect.com/science/article/pii/S2212420918314274"
YE2025_URL = "https://www.sciencedirect.com/science/article/pii/S0959652625012028"
LIU2020_URL = "https://pmc.ncbi.nlm.nih.gov/articles/PMC7518989/"
FEOFILOVS2024_URL = "https://doi.org/10.3390/risks12030043"

ZMD_PRODUCTS = "https://zmd.gov.zm/products/"
ZMD_ENSO = "https://zmd.gov.zm/zambia-enso-explorer/"
IBGE_MALHAS = "https://www.ibge.gov.br/geociencias/organizacao-do-territorio/estrutura-territorial/15774-malhas"
CEMADEN_URL = "https://www.gov.br/cemaden/"
APAC_URL = "https://www.apac.pe.gov.br/"

BRAZIL_UFS = {
    "Acre":"AC","Alagoas":"AL","Amapá":"AP","Amazonas":"AM","Bahia":"BA","Ceará":"CE",
    "Distrito Federal":"DF","Espírito Santo":"ES","Goiás":"GO","Maranhão":"MA",
    "Mato Grosso":"MT","Mato Grosso do Sul":"MS","Minas Gerais":"MG","Pará":"PA",
    "Paraíba":"PB","Paraná":"PR","Pernambuco":"PE","Piauí":"PI","Rio de Janeiro":"RJ",
    "Rio Grande do Norte":"RN","Rio Grande do Sul":"RS","Rondônia":"RO","Roraima":"RR",
    "Santa Catarina":"SC","São Paulo":"SP","Sergipe":"SE","Tocantins":"TO",
}

PILOT = {
    ("Zambia","Senanga"): {
        "flood_type":"Slow-onset seasonal riverine / floodplain flooding",
        "logic":"Upper Zambezi discharge/stage → Barotse floodplain inundation",
        "primary":"GloFAS river discharge",
        "river_seed_lat":-16.116667,"river_seed_lon":23.266667,
    },
    ("Zambia","Sinazongwe"): {
        "flood_type":"Rapid rainfall-driven local fluvial / flash-flood setting",
        "logic":"Heavy rainfall + antecedent wetness/runoff → local streams, crossings and road disruption",
        "primary":"ECMWF/GFS rainfall; local runoff/stream observations should be added",
        "river_seed_lat":-17.2614,"river_seed_lon":27.4618,
    },
    ("Brazil","Recife"): {
        "flood_type":"Multi-source urban flooding: pluvial/flash + river overflow + tidal/backwater effects",
        "logic":"Extreme rainfall + drainage/river/tidal state → urban inundation and access disruption",
        "primary":"Rainfall ensemble + APAC/CEMADEN/local hydrological context",
        "river_seed_lat":-8.0476,"river_seed_lon":-34.8770,
    },
    ("Brazil","Palmares"): {
        "flood_type":"Primarily riverine flooding in the Una River basin",
        "logic":"Una-basin rainfall → river discharge/stage → inundation",
        "primary":"GloFAS discharge + basin rainfall; validate against APAC/CEMADEN gauges",
        "river_seed_lat":-8.6842,"river_seed_lon":-35.5910,
    },
}

HORIZONS = {
    "Short range":{"window":"0–3 days","action":"Immediate readiness: communicate warning, protect critical stock, confirm staff, transport/referrals and outreach changes."},
    "Medium range":{"window":"4–15 days","action":"Pre-positioning: commodities, generator/fuel checks, route checks, surge staffing and referral transport."},
    "Sub-seasonal":{"window":"2–6 weeks","action":"Readiness planning: buffer stocks, outreach rescheduling, maintenance, staffing and logistics planning."},
    "Seasonal":{"window":"1–7 months","action":"Strategic preparedness: budget/procurement, infrastructure maintenance, contingency planning and seasonal coordination."},
}

RISK = [
    (0,10,"No / minimal","#2E7D32"),
    (10,30,"Low","#7CB342"),
    (30,50,"Moderate","#F9A825"),
    (50,70,"High","#EF6C00"),
    (70,85,"Very high","#C62828"),
    (85,101,"Extreme","#6A1B9A"),
]


# ---------------------------------------------------------------------------
# Cache / HTTP
# ---------------------------------------------------------------------------
def _cache_path(url, params):
    blob = json.dumps([url, params], sort_keys=True, default=str).encode()
    return CACHE_DIR / (hashlib.sha256(blob).hexdigest() + ".json")


def cached_json(url, params, max_age=10800, timeout=90):
    p = _cache_path(url, params)
    if p.exists() and time.time() - p.stat().st_mtime <= max_age:
        return json.loads(p.read_text(encoding="utf-8")), "cache"
    err = None
    for delay in (0,3,8):
        if delay:
            time.sleep(delay)
        try:
            r = requests.get(url, params=params, timeout=timeout, headers={"User-Agent":"REACH-EWS/FINAL-V5"})
            if r.status_code == 429:
                err = RuntimeError("429 Too Many Requests")
                continue
            r.raise_for_status()
            x = r.json()
            if isinstance(x,dict) and x.get("error"):
                raise RuntimeError(x.get("reason","API error"))
            p.write_text(json.dumps(x),encoding="utf-8")
            return x,"live"
        except Exception as e:
            err=e
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")),"stale cache"
    raise err if err else RuntimeError("Online request failed")


def clear_cache():
    for p in CACHE_DIR.glob("*.json"):
        try: p.unlink()
        except Exception: pass


# ---------------------------------------------------------------------------
# Static geography: Zambia + Brazil state-by-state
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_zambia():
    geo = json.loads(ZAMBIA_GEOJSON.read_text(encoding="utf-8"))
    pts = pd.read_csv(ZAMBIA_POINTS, dtype={"DIST_CODE":str})
    df = pts.rename(columns={
        "DIST_CODE":"REGION_CODE","DISTRICT":"REGION_NAME","PROVINCE":"ADMIN1",
        "rep_lat":"rep_lat","rep_lon":"rep_lon",
    }).copy()
    # GeoJSON uses DIST_CODE; make a generic property too.
    for f in geo["features"]:
        f["properties"]["REGION_CODE"] = str(f["properties"]["DIST_CODE"])
        f["properties"]["REGION_NAME"] = f["properties"]["DISTRICT"]
    return geo, df



@st.cache_data(show_spinner=False)
def load_brazil_state(state_name):
    """
    Municipality geometry is packaged from the user's uploaded BR_Municipios_2023
    shapefile. Forecasts are still requested state-by-state for API stability.
    """
    full_geo = json.loads(BRAZIL_GEOJSON.read_text(encoding="utf-8"))
    pts = pd.read_csv(BRAZIL_POINTS, dtype={"REGION_CODE": str, "ADMIN1_CODE": str})
    df = pts[pts["ADMIN1"] == state_name].copy()
    wanted = set(df["REGION_CODE"].astype(str))
    features = [
        f for f in full_geo["features"]
        if str(f["properties"].get("REGION_CODE")) in wanted
    ]
    return {"type": "FeatureCollection", "features": features}, df


def geography(country, brazil_state_name):
    if country == "Zambia":
        return load_zambia()
    return load_brazil_state(brazil_state_name)


# ---------------------------------------------------------------------------
# Health-facility registry and facility-level forecast drill-down
# ---------------------------------------------------------------------------
def _text_key(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _find_column(df, exact=(), contains=()):
    if df is None or df.empty:
        return None
    keyed = {_text_key(c): c for c in df.columns}
    for candidate in exact:
        k = _text_key(candidate)
        if k in keyed:
            return keyed[k]
    for c in df.columns:
        k = _text_key(c)
        if any(_text_key(token) in k for token in contains):
            return c
    return None


def _valid_lat_lon(df):
    out = df.copy()
    out["rep_lat"] = pd.to_numeric(out.get("rep_lat"), errors="coerce")
    out["rep_lon"] = pd.to_numeric(out.get("rep_lon"), errors="coerce")
    out = out[out["rep_lat"].between(-90, 90) & out["rep_lon"].between(-180, 180)].copy()
    return out


def _extract_combined_coordinates(series):
    lat, lon = [], []
    for value in series.astype(str):
        nums = re.findall(r"[-+]?\d+(?:\.\d+)?", value)
        if len(nums) >= 2:
            a, b = float(nums[0]), float(nums[1])
            # Zambia and Brazil are both in the Southern Hemisphere; use this only as a fallback parser.
            if -90 <= a <= 90 and -180 <= b <= 180:
                lat.append(a); lon.append(b); continue
        lat.append(np.nan); lon.append(np.nan)
    return pd.Series(lat, index=series.index), pd.Series(lon, index=series.index)


def _standardise_project_facilities(raw, district_hint=""):
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    name_col = _find_column(df,
        exact=("facility name","health facility name","health facility","facility","dhis2 name","facility_name"),
        contains=("facilityname","healthfacility","dhis2name"))
    lat_col = _find_column(df, exact=("latitude","lat","y"), contains=("latitude",))
    lon_col = _find_column(df, exact=("longitude","lon","long","x"), contains=("longitude",))
    coord_col = _find_column(df, contains=("coordinate","gps"))
    district_col = _find_column(df, exact=("district",), contains=("district",))
    type_col = _find_column(df, exact=("facility type","type","level"), contains=("facilitytype","facilitylevel"))
    id_col = _find_column(df, exact=("facility id","dhis2 id","orgunit uid","uid","id"), contains=("orgunit","facilityid","dhis2id"))
    if name_col is None:
        return pd.DataFrame()
    out = pd.DataFrame(index=df.index)
    out["FacilityName"] = df[name_col].astype(str).str.strip()
    if lat_col is not None and lon_col is not None:
        out["rep_lat"] = pd.to_numeric(df[lat_col], errors="coerce")
        out["rep_lon"] = pd.to_numeric(df[lon_col], errors="coerce")
    elif coord_col is not None:
        out["rep_lat"], out["rep_lon"] = _extract_combined_coordinates(df[coord_col])
    else:
        return pd.DataFrame()
    out["ParentArea"] = df[district_col].astype(str).str.strip() if district_col is not None else district_hint
    out["FacilityType"] = df[type_col].astype(str).str.strip() if type_col is not None else "Health facility"
    out["FacilityID"] = df[id_col].astype(str).str.strip() if id_col is not None else [f"REACH-{i+1}" for i in range(len(out))]
    out["Country"] = "Zambia"
    out["Source"] = "REACH project facility file"
    out["SourceURL"] = ""
    out["MCHPriority"] = True
    out["MCHServices"] = "Project facility registry; service profile not inferred from location alone"
    out = _valid_lat_lon(out)
    out = out[out["FacilityName"].ne("") & out["FacilityName"].str.lower().ne("nan")].copy()
    out["REGION_CODE"] = "FAC-ZM-PROJ-" + out["FacilityID"].astype(str).map(_text_key)
    out["REGION_NAME"] = out["FacilityName"]
    out["ADMIN1"] = out["ParentArea"]
    return out.reset_index(drop=True)


@st.cache_data(ttl=86400, show_spinner=False)
def zambia_facilities_online(district):
    district_names = [district]
    if _text_key(district) == "sinazongwe":
        district_names.append("Senazongwe")
    frames, statuses = [], []
    for dname in district_names:
        safe = str(dname).replace("'", "''")
        params = {
            "where": f"District='{safe}'",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "f": "json",
        }
        try:
            payload, status = cached_json(ZAMBIA_FACILITY_QUERY_URL, params, 86400, 45)
            statuses.append(status)
            rows = []
            for feat in payload.get("features", []) if isinstance(payload, dict) else []:
                a = feat.get("attributes", {}) or {}
                g = feat.get("geometry", {}) or {}
                name = a.get("Fac_Label") or a.get("DHIS2_Name") or a.get("Facility") or ""
                lat = a.get("Latitude", g.get("y"))
                lon = a.get("Longitude", g.get("x"))
                rows.append({
                    "FacilityID": f"ZM-NSDI-{a.get('OBJECTID','')}",
                    "FacilityName": str(name).strip(),
                    "FacilityType": str(a.get("Fac_Type") or "Health facility").strip(),
                    "ParentArea": str(a.get("District") or dname).strip(),
                    "Province": str(a.get("Province") or "").strip(),
                    "Country": "Zambia",
                    "rep_lat": lat,
                    "rep_lon": lon,
                    "Source": "Zambia NSDI health-facility layer",
                    "SourceURL": ZAMBIA_FACILITY_SOURCE_URL,
                    "MCHPriority": True,
                    "MCHServices": "Facility type from the national spatial registry; specific MCH services require HMIS/project data",
                })
            if rows:
                frames.append(pd.DataFrame(rows))
        except Exception:
            continue
    if not frames:
        return pd.DataFrame(), "online registry unavailable"
    out = pd.concat(frames, ignore_index=True, sort=False)
    out = _valid_lat_lon(out)
    out = out[out["FacilityName"].ne("")].copy()
    out["REGION_CODE"] = out["FacilityID"].astype(str)
    out["REGION_NAME"] = out["FacilityName"]
    out["ADMIN1"] = out["ParentArea"]
    out = out.drop_duplicates(subset=["FacilityName","rep_lat","rep_lon"]).reset_index(drop=True)
    return out, "/".join(sorted(set(statuses))) if statuses else "online"


@st.cache_data(show_spinner=False)
def zambia_facilities_project(district):
    if not ZAMBIA_PILOT_FACILITY_XLS.exists():
        return pd.DataFrame()
    frames = []
    try:
        xls = pd.ExcelFile(ZAMBIA_PILOT_FACILITY_XLS)
    except Exception:
        return pd.DataFrame()
    for sheet in xls.sheet_names:
        parsed = pd.DataFrame()
        for header in range(0, 8):
            try:
                candidate = pd.read_excel(ZAMBIA_PILOT_FACILITY_XLS, sheet_name=sheet, header=header)
                parsed = _standardise_project_facilities(candidate, district_hint=sheet)
                if not parsed.empty:
                    break
            except Exception:
                continue
        if not parsed.empty:
            frames.append(parsed)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True, sort=False)
    target = _text_key(district)
    aliases = {target}
    if target == "sinazongwe": aliases.add("senazongwe")
    keep = out["ParentArea"].map(_text_key).isin(aliases)
    if keep.any():
        out = out.loc[keep].copy()
    out = out.drop_duplicates(subset=["FacilityName","rep_lat","rep_lon"]).reset_index(drop=True)
    return out


def _record_list(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("estabelecimentos","data","Data","results","items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _one_flag(value):
    try:
        return int(float(value)) == 1
    except Exception:
        return str(value).strip().casefold() in {"sim","yes","true","1"}


@st.cache_data(show_spinner=False)
def _brazil_municipality_geometry(region_code):
    """Return the bundled municipality geometry for coordinate QA."""
    code = re.sub(r"\D", "", str(region_code))
    try:
        gj = json.loads(BRAZIL_GEOJSON.read_text(encoding="utf-8"))
    except Exception:
        return None
    for feat in gj.get("features", []):
        props = feat.get("properties", {}) or {}
        if re.sub(r"\D", "", str(props.get("REGION_CODE", ""))) == code:
            return feat.get("geometry")
    return None

def _point_in_ring(lon, lat, ring):
    if not ring or len(ring) < 3:
        return False
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        # Ray casting; tiny epsilon prevents division instability on horizontal edges.
        intersects = ((yi > lat) != (yj > lat)) and (lon < (xj-xi)*(lat-yi)/((yj-yi) or 1e-15) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside

def _point_in_polygon_coords(lon, lat, poly_coords):
    if not poly_coords:
        return False
    if not _point_in_ring(lon, lat, poly_coords[0]):
        return False
    # Holes are excluded.
    for hole in poly_coords[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True

def _point_in_geometry(lon, lat, geometry):
    if not geometry:
        return True  # fail open if the bundled boundary cannot be read
    gtype = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if gtype == "Polygon":
        return _point_in_polygon_coords(lon, lat, coords)
    if gtype == "MultiPolygon":
        return any(_point_in_polygon_coords(lon, lat, poly) for poly in coords)
    return True

def _qc_brazil_facility_coordinates(df, region_code, municipality_name):
    """Remove implausible CNES coordinates outside the selected municipality.

    Coordinates are never guessed or silently moved. Records outside the official bundled
    municipality geometry are flagged and excluded from spatial forecasting/interpolation.
    This prevents offshore or wrong-municipality points from distorting the facility surface.
    """
    if df is None or df.empty:
        return df, 0
    geom = _brazil_municipality_geometry(region_code)
    if geom is None:
        out = df.copy()
        out["CoordinateQC"] = "Boundary QA unavailable"
        return out, 0
    out = df.copy()
    inside=[]
    for r in out.itertuples():
        try:
            ok = _point_in_geometry(float(r.rep_lon), float(r.rep_lat), geom)
        except Exception:
            ok = False
        inside.append(bool(ok))
    out["CoordinateQC"] = ["Inside municipality boundary" if x else "Excluded: outside municipality boundary" for x in inside]
    removed = int((~pd.Series(inside, index=out.index)).sum())
    out = out.loc[pd.Series(inside, index=out.index)].copy()
    return out.reset_index(drop=True), removed

@st.cache_data(ttl=86400, show_spinner=False)
def brazil_facilities_online(region_code, municipality_name):
    code = re.sub(r"\D", "", str(region_code))
    candidates = []
    if len(code) >= 6:
        candidates.append(code[:6])
    if code and code not in candidates:
        candidates.append(code)
    all_rows, statuses = [], []
    for mun_code in candidates:
        seen_page_signature = set()
        rows_for_code = []
        for page in range(0, 100):
            params = {"codigo_municipio": mun_code, "status": 1, "limit": 20, "offset": page}
            try:
                payload, status = cached_json(BRAZIL_CNES_ENDPOINT, params, 86400, 45)
                statuses.append(status)
            except Exception:
                break
            rows = _record_list(payload)
            if not rows:
                break
            sig = tuple(str(r.get("codigo_cnes") or r.get("codigo_estabelecimento_saude") or "") for r in rows[:3])
            if sig and sig in seen_page_signature:
                break
            seen_page_signature.add(sig)
            rows_for_code.extend(rows)
            if len(rows) < 20:
                break
        if rows_for_code:
            all_rows = rows_for_code
            break
    if not all_rows:
        return pd.DataFrame(), "CNES registry unavailable"
    rows = []
    for r in all_rows:
        name = r.get("nome_fantasia") or r.get("nome_razao_social") or ""
        lat = r.get("latitude_estabelecimento_decimo_grau") or r.get("latitude")
        lon = r.get("longitude_estabelecimento_decimo_grau") or r.get("longitude")
        code_type = r.get("codigo_tipo_unidade")
        ftype = r.get("descricao_tipo_unidade") or r.get("descricao_nivel_hierarquia") or "Health facility"
        obst = _one_flag(r.get("estabelecimento_possui_centro_obstetrico"))
        neo = _one_flag(r.get("estabelecimento_possui_centro_neonatal"))
        hosp = _one_flag(r.get("estabelecimento_possui_atendimento_hospitalar"))
        name_key = _text_key(name)
        mch_name = any(token in name_key for token in ("matern","obstetr","neonat","pediatr","crianca","mulher"))
        services = []
        if obst: services.append("obstetric centre")
        if neo: services.append("neonatal centre")
        if hosp: services.append("hospital care")
        rows.append({
            "FacilityID": str(r.get("codigo_cnes") or r.get("codigo_estabelecimento_saude") or ""),
            "FacilityName": str(name).strip(),
            "FacilityType": str(ftype).strip(),
            "ParentArea": municipality_name,
            "Country": "Brazil",
            "rep_lat": lat,
            "rep_lon": lon,
            "Source": "CNES / DATASUS OpenDataSUS",
            "SourceURL": BRAZIL_CNES_SOURCE_URL,
            "MCHPriority": bool(obst or neo or hosp or mch_name),
            "MCHServices": ", ".join(services) if services else "CNES facility profile; specific MCH service availability should be checked before operational use",
            "RegistryUpdated": str(r.get("data_atualizacao") or ""),
        })
    out = pd.DataFrame(rows)
    out = _valid_lat_lon(out)
    out = out[out["FacilityName"].ne("")].copy()
    out["REGION_CODE"] = "FAC-BR-CNES-" + out["FacilityID"].astype(str)
    out["REGION_NAME"] = out["FacilityName"]
    out["ADMIN1"] = out["ParentArea"]
    out = out.drop_duplicates(subset=["FacilityID"]).reset_index(drop=True)
    out, excluded_qc = _qc_brazil_facility_coordinates(out, region_code, municipality_name)
    registry_status = "/".join(sorted(set(statuses))) if statuses else "online"
    if excluded_qc:
        registry_status += f" · coordinate QA: {excluded_qc} out-of-boundary record(s) excluded"
    else:
        registry_status += " · coordinate QA: all mapped records inside municipality boundary"
    return out, registry_status


@st.cache_data(ttl=86400, show_spinner=False)
def facilities_for_area(country, focus, region_code):
    if (country, focus) not in PILOT:
        return pd.DataFrame(), "Facility drill-down is currently configured for the four REACH pilot areas."
    if country == "Zambia":
        project = zambia_facilities_project(focus)
        online, online_status = zambia_facilities_online(focus)
        frames = []
        if not project.empty:
            frames.append(project)
        if not online.empty:
            frames.append(online)
        if not frames:
            return pd.DataFrame(), online_status
        out = pd.concat(frames, ignore_index=True, sort=False)
        out["_name_key"] = out["FacilityName"].map(_text_key)
        # Prefer project records when the same named facility appears in both sources.
        out["_priority"] = out["Source"].eq("REACH project facility file").astype(int)
        out = out.sort_values(["_name_key","_priority"], ascending=[True,False]).drop_duplicates("_name_key", keep="first")
        out = out.drop(columns=["_name_key","_priority"]).reset_index(drop=True)
        return out, f"REACH project file + Zambia NSDI ({online_status})" if not online.empty and not project.empty else ("REACH project facility file" if not project.empty else f"Zambia NSDI ({online_status})")
    return brazil_facilities_online(region_code, focus)


@st.cache_data(ttl=86400, show_spinner=False)
def zambia_national_facility_count():
    """Return live count from the national Zambia NSDI facility layer when available."""
    try:
        payload,status=cached_json(
            ZAMBIA_FACILITY_QUERY_URL,
            {"where":"1=1","returnCountOnly":"true","f":"json"},
            86400,45
        )
        count=int(payload.get("count")) if isinstance(payload,dict) and payload.get("count") is not None else None
        return count,status
    except Exception as exc:
        return None,f"unavailable: {exc}"


@st.cache_data(show_spinner=False)
def zambia_project_facility_counts():
    """Counts in the bundled REACH facility-detail workbook, independent of coordinate availability."""
    counts={"Senanga":None,"Sinazongwe":None}
    if not ZAMBIA_PILOT_FACILITY_XLS.exists():
        return counts
    try:
        xls=pd.ExcelFile(ZAMBIA_PILOT_FACILITY_XLS)
        frames=[]
        for sheet in xls.sheet_names:
            for header in range(0,4):
                try:
                    d=pd.read_excel(ZAMBIA_PILOT_FACILITY_XLS,sheet_name=sheet,header=header)
                    district_col=_find_column(d,exact=("district",),contains=("district",))
                    facility_col=_find_column(d,exact=("facility", "facility name", "health facility"),contains=("facility",))
                    if district_col is not None and facility_col is not None:
                        frames.append(d[[district_col,facility_col]].rename(columns={district_col:"District",facility_col:"Facility"}))
                        break
                except Exception:
                    continue
        if frames:
            allf=pd.concat(frames,ignore_index=True)
            allf=allf.dropna(subset=["District","Facility"])
            for name in counts:
                g=allf[allf["District"].map(_text_key)==_text_key(name)]
                counts[name]=int(g["Facility"].astype(str).str.strip().replace("",np.nan).dropna().nunique())
    except Exception:
        pass
    return counts


@st.cache_data(ttl=86400, show_spinner=False)
def all_pilot_live_facility_counts():
    """Live mapped facility counts for the four REACH pilots plus Zambia national registry count."""
    rows=[]
    for name in ("Senanga","Sinazongwe"):
        d,status=zambia_facilities_online(name)
        rows.append({"Country":"Zambia","Pilot area":name,"Live mapped facilities":len(d),"Registry":"Zambia NSDI","Status":status})
    for name,code in (("Recife","2611606"),("Palmares","2610004")):
        d,status=brazil_facilities_online(code,name)
        rows.append({"Country":"Brazil","Pilot area":name,"Live mapped facilities":len(d),"Registry":"CNES / DATASUS","Status":status})
    national_count,national_status=zambia_national_facility_count()
    return pd.DataFrame(rows),national_count,national_status


@st.cache_data(show_spinner=False)
def load_pilot_hmis_context():
    if not ZAMBIA_PILOT_HMIS_CSV.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(ZAMBIA_PILOT_HMIS_CSV)
    except Exception:
        return pd.DataFrame()


def safe_file_part(value):
    x = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    x = re.sub(r"[^A-Za-z0-9._-]+", "_", x).strip("_")
    return x[:90] or "area"



def _meaningful_facility_type(value):
    """Return a readable facility type; hide raw numeric / 'CNES type 39' style codes."""
    x = str(value or "").strip()
    if not x or x.casefold() in {"nan","none","health facility"}:
        return ""
    if re.fullmatch(r"(?:cnes\s*type\s*)?\d+(?:\.0)?", x, flags=re.I):
        return ""
    return x


def facility_dropdown_labels(df):
    """Prefer the actual facility name. Only add an identifier when names are duplicated."""
    if df is None or df.empty:
        return {}
    counts = df["FacilityName"].astype(str).value_counts()
    labels = {}
    for r in df.itertuples():
        name = str(r.FacilityName).strip() or "Unnamed health facility"
        if counts.get(name, 0) > 1:
            fid = str(getattr(r, "FacilityID", "")).strip()
            suffix = f" · ID {fid}" if fid else ""
            labels[str(r.REGION_CODE)] = name + suffix
        else:
            labels[str(r.REGION_CODE)] = name
    return labels


def _idw_grid(df, value_col, grid_size=70, power=2.0):
    """Inverse-distance interpolation for visualising facility point forecasts.
    This is a display surface from sampled facility points, not the native NWP grid.
    """
    d = df[["rep_lat","rep_lon",value_col]].copy()
    d["rep_lat"] = pd.to_numeric(d["rep_lat"], errors="coerce")
    d["rep_lon"] = pd.to_numeric(d["rep_lon"], errors="coerce")
    d[value_col] = pd.to_numeric(d[value_col], errors="coerce")
    d = d.dropna()
    if len(d) < 3:
        return None
    x=d["rep_lon"].to_numpy(float); y=d["rep_lat"].to_numpy(float); z=d[value_col].to_numpy(float)
    padx=max((x.max()-x.min())*.08, .015); pady=max((y.max()-y.min())*.08, .015)
    gx=np.linspace(x.min()-padx,x.max()+padx,grid_size)
    gy=np.linspace(y.min()-pady,y.max()+pady,grid_size)
    xx,yy=np.meshgrid(gx,gy)
    dx=xx[...,None]-x[None,None,:]; dy=yy[...,None]-y[None,None,:]
    dist2=dx*dx+dy*dy
    w=1.0/np.maximum(dist2,1e-10)**(power/2.0)
    zz=np.sum(w*z[None,None,:],axis=2)/np.sum(w,axis=2)
    return gx,gy,zz


def facility_contour_gradient_figure(df, value_col, title, unit, selected_code=None, colorscale=None, diverging=False):
    """Labelled IDW contour surface from facility point forecasts.

    V11 keeps the gradient surface fully visible while preserving strong scientific labels.
    Contour values, facility names, point markers, the selected-facility star and axes stay
    fully opaque and dark. The surface is a visual interpolation of values sampled
    at facility coordinates; it is not the native NWP grid. When all point values
    are effectively identical, no artificial gradient is drawn.
    """
    grid=_idw_grid(df,value_col)
    vals=pd.to_numeric(df[value_col],errors="coerce")
    finite=vals.dropna()
    if grid is None or finite.empty or finite.nunique() < 2:
        return None
    gx,gy,zz=grid
    zmin=float(finite.min()); zmax=float(finite.max())
    if diverging:
        lim=max(abs(zmin),abs(zmax),0.1)
        zmin,zmax=-lim,lim
    span=max(zmax-zmin,1e-6)
    n_levels=7
    contour_step=span/n_levels

    # Keep scientifically intuitive, muted colours. The gradient surface is fully
    # opaque so the spatial pattern remains easy to see; labels are rendered on top.
    if colorscale is not None:
        scale=colorscale
    elif diverging and unit=="°C":
        scale=[[0.00,"#3F6F9F"],[0.20,"#78A9C2"],[0.40,"#C1D9DF"],[0.50,"#F7F5EF"],
               [0.60,"#E7C7AF"],[0.80,"#D18A69"],[1.00,"#B65C4A"]]
    elif diverging:
        scale=[[0.00,"#B65C4A"],[0.20,"#D29173"],[0.40,"#E8D2C4"],[0.50,"#F7F5EF"],
               [0.60,"#C9DDE2"],[0.80,"#7AA9BC"],[1.00,"#3F6F9F"]]
    elif unit=="°C":
        scale=[[0.00,"#355F8D"],[0.18,"#4A86A8"],[0.36,"#78B7B2"],[0.54,"#C7D6A5"],
               [0.72,"#E4C46A"],[0.88,"#D98B5F"],[1.00,"#B55B5A"]]
    else:
        scale=[[0.00,"#F3F6F4"],[0.20,"#D9E8E0"],[0.42,"#A8CCBE"],[0.64,"#74AD9E"],
               [0.82,"#4C8D82"],[1.00,"#214E55"]]

    decimals=1 if unit in ("°C","mm","%") else 0
    fig=go.Figure()

    # 1) Fully visible colour field. Do not fade the scientific gradient surface.
    fig.add_trace(go.Contour(
        x=gx,y=gy,z=zz,colorscale=scale,zmin=zmin,zmax=zmax,
        contours=dict(start=zmin,end=zmax,size=contour_step,coloring="heatmap",showlines=False,showlabels=False),
        line=dict(width=0),opacity=1.0,
        colorbar=dict(title=dict(text=unit,font=dict(color="#111827",size=12)),
                      thickness=13,len=.70,tickformat=f".{decimals}f",outlinewidth=0,
                      tickfont=dict(color="#1F2937",size=11)),
        hovertemplate=f"Longitude %{{x:.3f}}<br>Latitude %{{y:.3f}}<br>Interpolated value %{{z:.{decimals}f}} {unit}<extra></extra>",
        name="Interpolated facility-point forecast"
    ))

    # 2) Fully opaque dark contour lines + numeric labels, drawn above the surface.
    fig.add_trace(go.Contour(
        x=gx,y=gy,z=zz,zmin=zmin,zmax=zmax,showscale=False,
        contours=dict(start=zmin,end=zmax,size=contour_step,coloring="lines",showlines=True,showlabels=True,
                      labelfont=dict(size=12,color="#111827",family="Arial Black")),
        line=dict(width=1.05,color="#263238"),opacity=1.0,
        hoverinfo="skip",name="Labelled contours",showlegend=False
    ))

    point_custom=np.stack([
        df["FacilityName"].astype(str),
        vals.map(lambda v:"—" if pd.isna(v) else f"{v:.{decimals}f} {unit}")
    ],axis=1)
    # Dense Brazil pilot registries become unreadable when every facility name is printed.
    # Keep all names on hover and show only the selected facility label in Brazil. Zambia
    # retains direct labels because the pilot facility sets are small enough to read.
    is_brazil = "Country" in df.columns and df["Country"].astype(str).str.casefold().eq("brazil").any()
    positions=["top center","bottom center","middle right","middle left"]
    text_positions=[positions[i % len(positions)] for i in range(len(df))]
    label_size=10 if len(df)<=35 else (9 if len(df)<=70 else 8)
    base_text = ["" for _ in range(len(df))] if is_brazil else df["FacilityName"].astype(str).tolist()
    fig.add_trace(go.Scatter(
        x=df["rep_lon"],y=df["rep_lat"],mode="markers+text",
        text=base_text,textposition=text_positions,
        textfont=dict(size=label_size,color="#111827",family="Arial"),
        marker=dict(size=8,color=vals,colorscale=scale,cmin=zmin,cmax=zmax,opacity=.96,
                    line=dict(width=1.0,color="#FFFFFF"),showscale=False),
        customdata=point_custom,hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
        name="Health facilities",cliponaxis=False
    ))
    if selected_code:
        sel=df[df["REGION_CODE"].astype(str)==str(selected_code)]
        if not sel.empty:
            r=sel.iloc[0]
            fig.add_trace(go.Scatter(
                x=[r.rep_lon],y=[r.rep_lat],mode="markers+text",text=[f"★ {r.FacilityName}"],textposition="top center",
                textfont=dict(size=11,color="#111827",family="Arial Black"),
                marker=dict(size=16,symbol="star",color="#C28A16",opacity=1.0,line=dict(width=1.5,color="#FFFFFF")),
                name="Selected facility",cliponaxis=False
            ))
    fig.update_layout(
        title=dict(text=title,x=.01,xanchor="left",font=dict(size=15,color="#111827")),height=540,
        xaxis_title="Longitude",yaxis_title="Latitude",margin=dict(l=40,r=20,t=58,b=44),
        legend=dict(orientation="h",y=-.15,font=dict(size=10,color="#1F2937")),
        plot_bgcolor="#FBFCFD",paper_bgcolor="white",font=dict(color="#1F2937",family="Arial")
    )
    fig.update_xaxes(gridcolor="rgba(148,163,184,.16)",zeroline=False,tickfont=dict(color="#374151"),title_font=dict(color="#374151"))
    fig.update_yaxes(scaleanchor="x",scaleratio=1,gridcolor="rgba(148,163,184,.16)",zeroline=False,tickfont=dict(color="#374151"),title_font=dict(color="#374151"))
    return fig

def facility_temperature_gradient_figure(df, value_col, title, selected_code=None, diverging=False):
    """Temperature wrapper retained for compatibility/preflight checks."""
    return facility_contour_gradient_figure(df,value_col,title,"°C",selected_code,diverging=diverging)


def facility_precipitation_gradient_figure(df, value_col, title, selected_code=None, diverging=False):
    """Rainfall contour surface with labelled mm isolines where variation exists."""
    return facility_contour_gradient_figure(df,value_col,title,"mm",selected_code,diverging=diverging)


def facility_signal_bar_figure(df, value_col, title, unit, selected_code=None, max_bars=35):
    """Horizontal facility-ranking bar chart for the active forecast signal."""
    d=df.copy()
    d["_v"]=pd.to_numeric(d[value_col],errors="coerce")
    d=d.dropna(subset=["_v"])
    if d.empty:
        return None
    selected=pd.DataFrame()
    if selected_code:
        selected=d[d["REGION_CODE"].astype(str)==str(selected_code)]
    d=d.sort_values("_v",ascending=False).head(max_bars)
    if not selected.empty and str(selected.iloc[0]["REGION_CODE"]) not in set(d["REGION_CODE"].astype(str)):
        d=pd.concat([d,selected],ignore_index=True).drop_duplicates("REGION_CODE",keep="last")
    d=d.sort_values("_v",ascending=True)
    colors=["#C28A16" if selected_code and str(c)==str(selected_code) else "#6F8FA0" for c in d["REGION_CODE"]]
    labels=[("★ " if selected_code and str(c)==str(selected_code) else "")+str(n) for c,n in zip(d["REGION_CODE"],d["FacilityName"])]
    fig=go.Figure(go.Bar(
        x=d["_v"],y=labels,orientation="h",marker=dict(color=colors,opacity=.68,line=dict(width=.45,color="rgba(52,67,75,.30)")),
        text=[f"{v:.1f} {unit}" for v in d["_v"]],textposition="outside",
        hovertemplate="<b>%{y}</b><br>%{x:.1f} "+unit+"<extra></extra>"
    ))
    fig.update_layout(
        title=dict(text=title,x=.01,xanchor="left",font=dict(size=15)),height=max(430,26*len(d)+120),
        xaxis_title=unit,yaxis_title="",margin=dict(l=20,r=55,t=55,b=35),
        plot_bgcolor="#F7F8F8",paper_bgcolor="white",showlegend=False,font=dict(color="#34434B",family="Arial")
    )
    return fig


def facility_two_model_bar_figure(df, col_a, col_b, title, unit, selected_code=None, max_bars=30):
    """Grouped ECMWF/GFS bars across facilities; selected facility is marked with a star."""
    d=df.copy()
    d["_a"]=pd.to_numeric(d[col_a],errors="coerce")
    d["_b"]=pd.to_numeric(d[col_b],errors="coerce")
    d["_mean"]=d[["_a","_b"]].mean(axis=1)
    d=d.dropna(subset=["_mean"])
    if d.empty:
        return None
    selected=pd.DataFrame()
    if selected_code:
        selected=d[d["REGION_CODE"].astype(str)==str(selected_code)]
    d=d.sort_values("_mean",ascending=False).head(max_bars)
    if not selected.empty and str(selected.iloc[0]["REGION_CODE"]) not in set(d["REGION_CODE"].astype(str)):
        d=pd.concat([d,selected],ignore_index=True).drop_duplicates("REGION_CODE",keep="last")
    d=d.sort_values("_mean",ascending=True)
    labels=[("★ " if selected_code and str(c)==str(selected_code) else "")+str(n) for c,n in zip(d["REGION_CODE"],d["FacilityName"])]
    fig=go.Figure()
    fig.add_trace(go.Bar(x=d["_a"],y=labels,orientation="h",name="ECMWF IFS HRES",marker=dict(color="#66889A",opacity=.68,line=dict(width=.40,color="rgba(52,67,75,.26)")),text=[f"{v:.1f}" if pd.notna(v) else "" for v in d["_a"]],textposition="outside"))
    fig.add_trace(go.Bar(x=d["_b"],y=labels,orientation="h",name="NOAA GFS",marker=dict(color="#8B7F98",opacity=.64,line=dict(width=.40,color="rgba(72,61,84,.24)")),text=[f"{v:.1f}" if pd.notna(v) else "" for v in d["_b"]],textposition="outside"))
    fig.update_layout(
        barmode="group",title=dict(text=title,x=.01,xanchor="left",font=dict(size=15)),
        height=max(460,30*len(d)+140),xaxis_title=unit,yaxis_title="",
        margin=dict(l=20,r=55,t=55,b=40),plot_bgcolor="#F7F8F8",paper_bgcolor="white",
        legend=dict(orientation="h",y=1.04,x=0),font=dict(color="#34434B",family="Arial")
    )
    return fig


def facility_point_spatial_figure(df, value_col, title, unit, selected_code=None, basemap_name="Streets / places", diverging=False):
    d=df.copy(); vals=pd.to_numeric(d[value_col],errors="coerce")
    finite=vals.dropna()
    if diverging:
        lim=max(.1,float(np.nanquantile(np.abs(finite),.98))) if len(finite) else 1.0
        cmin,cmax=-lim,lim; scale=[[0.0,"#4E6B82"],[0.25,"#93A8B7"],[0.5,"#F2F0EA"],[0.75,"#C89587"],[1.0,"#84514B"]]
    else:
        cmin=float(finite.quantile(.02)) if len(finite) else 0.0
        cmax=float(finite.quantile(.98)) if len(finite) else 1.0
        if cmax<=cmin:cmax=cmin+1
        scale=[[0.0,"#536F86"],[0.35,"#AFC2CC"],[0.6,"#DDD8C8"],[0.82,"#C58E76"],[1.0,"#87524B"]] if unit=="°C" else [[0.0,"#EFF3F4"],[0.35,"#BED1D9"],[0.65,"#7FA1AF"],[1.0,"#476979"]]
    fig=go.Figure(go.Scattermap(
        lon=d["rep_lon"],lat=d["rep_lat"],mode="markers",
        marker=dict(size=11,color=vals,colorscale=scale,cmin=cmin,cmax=cmax,opacity=.76,colorbar=dict(title=unit,thickness=13,len=.64,outlinewidth=0)),
        customdata=np.stack([d["FacilityName"].astype(str),vals.map(lambda v:"—" if pd.isna(v) else f"{v:.1f} {unit}")],axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",name="Facilities"
    ))
    if selected_code:
        sel=d[d["REGION_CODE"].astype(str)==str(selected_code)]
        if not sel.empty:
            r=sel.iloc[0]
            fig.add_trace(go.Scattermap(lon=[r.rep_lon],lat=[r.rep_lat],mode="markers+text",text=[r.FacilityName],textposition="top center",
                                        marker=dict(size=17,color="#B38B45",opacity=.88),name="Selected facility"))
    centre,zoom=map_view_from_df(d)
    fig.update_layout(map=dict(style=BASEMAP_STYLES.get(basemap_name,"carto-voyager"),center=centre,zoom=max(zoom,7.8)),
                      title=dict(text=title,x=.01,xanchor="left",font=dict(size=15)),height=500,margin=dict(l=0,r=0,t=55,b=25),legend=dict(orientation="h",y=-.04))
    return fig


def facility_two_model_comparison(regions,horizon,period):
    """Sample ECMWF IFS HRES and NOAA GFS at every facility coordinate."""
    if regions is None or regions.empty:
        return pd.DataFrame(), ""
    records=regions.to_dict("records")
    ec,ec_status=regional_deterministic(records,"ECMWF IFS HRES")
    gf,gf_status=regional_deterministic(records,"NOAA GFS")
    s,e=daily_slice(horizon,period)
    rows=[]
    for r in regions.itertuples():
        code=str(r.REGION_CODE); a=ec.get(code,{}); b=gf.get(code,{})
        et=a.get("tmax",pd.Series(dtype=float)).iloc[s:e]; gt=b.get("tmax",pd.Series(dtype=float)).iloc[s:e]
        ep=a.get("precip",pd.Series(dtype=float)); gp=b.get("precip",pd.Series(dtype=float))
        er=ep.rolling(3,min_periods=3).sum().iloc[max(0,s-2):e]
        gr=gp.rolling(3,min_periods=3).sum().iloc[max(0,s-2):e]
        rows.append({
            **r._asdict(),
            "ECMWF_Tmax_C":float(et.max()) if len(et.dropna()) else np.nan,
            "GFS_Tmax_C":float(gt.max()) if len(gt.dropna()) else np.nan,
            "ECMWF_Rain3_mm":float(er.max()) if len(er.dropna()) else np.nan,
            "GFS_Rain3_mm":float(gr.max()) if len(gr.dropna()) else np.nan,
        })
    out=pd.DataFrame(rows)
    out["Tmax_ModelMean_C"]=out[["ECMWF_Tmax_C","GFS_Tmax_C"]].mean(axis=1)
    out["Tmax_ECMWF_minus_GFS_C"]=out["ECMWF_Tmax_C"]-out["GFS_Tmax_C"]
    out["Rain3_ModelMean_mm"]=out[["ECMWF_Rain3_mm","GFS_Rain3_mm"]].mean(axis=1)
    out["Rain3_ECMWF_minus_GFS_mm"]=out["ECMWF_Rain3_mm"]-out["GFS_Rain3_mm"]
    return out, f"ECMWF {ec_status} · NOAA GFS {gf_status}"


def facility_longrange_component_values(regions, long_payload, period):
    """Build facility-level long-range temperature/precipitation anomaly components.

    `long_payload` is the ECMWF EC46/SEAS5 response already retrieved by
    build_map_values(), so this adds no extra API request. Values are means over the
    selected week/month window and remain physical anomalies (°C / mm).
    """
    if regions is None or regions.empty or not isinstance(long_payload, dict):
        return pd.DataFrame()
    section,sl=long_slice(period)
    rows=[]
    for r in regions.itertuples():
        code=str(r.REGION_CODE)
        x=long_payload.get(code,{})
        ts=x.get(f"{section}_temp",pd.Series(dtype=float)).iloc[sl]
        ps=x.get(f"{section}_precip",pd.Series(dtype=float)).iloc[sl]
        rows.append({
            **r._asdict(),
            "TempAnomaly_C":float(ts.mean()) if len(ts.dropna()) else np.nan,
            "PrecipAnomaly_mm":float(ps.mean()) if len(ps.dropna()) else np.nan,
        })
    return pd.DataFrame(rows)

def facility_screen_subset(facilities, selected_code=None):
    if facilities is None or facilities.empty:
        return pd.DataFrame(), False
    f = facilities.copy()
    limited = False
    if len(f) > FACILITY_SCREEN_SOFT_LIMIT:
        priority = f[f.get("MCHPriority", False).fillna(False).astype(bool)].copy() if "MCHPriority" in f else pd.DataFrame()
        if not priority.empty:
            f = priority
        if len(f) > FACILITY_SCREEN_SOFT_LIMIT:
            f = f.sort_values(["FacilityName","FacilityID"]).head(FACILITY_SCREEN_SOFT_LIMIT).copy()
            limited = True
    if selected_code is not None and selected_code not in set(f["REGION_CODE"].astype(str)):
        selected = facilities[facilities["REGION_CODE"].astype(str) == str(selected_code)]
        if not selected.empty:
            f = pd.concat([f, selected], ignore_index=True, sort=False).drop_duplicates("REGION_CODE")
    return f.reset_index(drop=True), limited


def facility_forecast_figure(parent_geo, parent_code, facility_values, selected_code, hazard, horizon, map_mode, period, source_label, basemap_name):
    df = facility_values.copy()
    unit = unit_for(hazard, horizon, map_mode)
    risk_mode = ("risk" in map_mode.lower()) or ("Probabilistic" in map_mode) or hazard.startswith("Compound")
    vals = pd.to_numeric(df["value"], errors="coerce")
    if risk_mode:
        colorscale = [[0.00,"#2E7D32"],[0.10,"#7CB342"],[0.30,"#F9A825"],[0.50,"#EF6C00"],[0.70,"#C62828"],[0.85,"#6A1B9A"],[1.00,"#6A1B9A"]]
        cmin, cmax = 0, 100
    else:
        finite = vals.dropna()
        if horizon in ("Sub-seasonal","Seasonal"):
            lim = max(.1, float(np.nanquantile(np.abs(finite), .98))) if len(finite) else 1.0
            cmin, cmax = -lim, lim
            colorscale = "RdBu_r" if hazard == "Heatwave" else "RdBu"
        else:
            cmin = float(finite.quantile(.02)) if len(finite) else 0.0
            cmax = float(finite.quantile(.98)) if len(finite) else 1.0
            if cmax <= cmin: cmax = cmin + 1.0
            colorscale = "YlOrRd" if hazard == "Heatwave" else "Blues"
    df["VALUE_DISPLAY"] = [fmt(v, unit) for v in vals]
    df["TYPE_DISPLAY"] = df.get("FacilityType", "Health facility").fillna("Health facility").astype(str)
    df["SOURCE_DISPLAY"] = df.get("Source", "Facility registry").fillna("Facility registry").astype(str)
    custom = np.stack([df["FacilityName"].astype(str),df["TYPE_DISPLAY"],df["VALUE_DISPLAY"],df["SOURCE_DISPLAY"]],axis=1)
    fig = go.Figure()
    features = [x for x in parent_geo.get("features",[]) if str(x.get("properties",{}).get("REGION_CODE")) == str(parent_code)]
    if features:
        fig.add_trace(go.Choroplethmap(
            geojson={"type":"FeatureCollection","features":features},locations=[str(parent_code)],z=[1],featureidkey="properties.REGION_CODE",
            colorscale=[[0,"#E2E8F0"],[1,"#E2E8F0"]],showscale=False,marker=dict(opacity=.18,line=dict(width=2,color="#334155")),hoverinfo="skip"
        ))
    fig.add_trace(go.Scattermap(
        lon=df["rep_lon"],lat=df["rep_lat"],mode="markers",
        marker=dict(size=11,color=vals,colorscale=colorscale,cmin=cmin,cmax=cmax,opacity=.92,
                    colorbar=dict(title=unit,thickness=13,len=.62)),
        customdata=custom,name="Health facilities",
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>Forecast: <b>%{customdata[2]}</b><br>Registry: %{customdata[3]}<extra></extra>"
    ))
    selected = df[df["REGION_CODE"].astype(str)==str(selected_code)] if selected_code else pd.DataFrame()
    if not selected.empty:
        r = selected.iloc[0]
        fig.add_trace(go.Scattermap(lon=[r.rep_lon],lat=[r.rep_lat],mode="markers+text",text=[r.FacilityName],textposition="top center",
                                    marker=dict(size=19,color="#F59E0B"),name="Selected facility",hovertemplate=f"<b>{r.FacilityName}</b><extra></extra>"))
    centre, zoom = map_view_from_df(df)
    fig.update_layout(
        map=dict(style=BASEMAP_STYLES.get(basemap_name,"carto-voyager"),center=centre,zoom=max(zoom,7.8)),
        height=540,margin=dict(l=0,r=0,t=50,b=28),
        title=dict(text=f"Health-facility forecast screen · {hazard} · {period_display_label(horizon,period)}",x=.01,xanchor="left",font=dict(size=16)),
        hoverlabel=dict(bgcolor="white",font_size=13,font_family="Arial"),legend=dict(orientation="h",y=-.04),
    )
    return fig


def render_pilot_hmis_context(district):
    h = load_pilot_hmis_context()
    if h.empty or "district" not in h:
        return
    d = h[h["district"].map(_text_key) == _text_key(district)].copy()
    if d.empty:
        return
    for c in ("year","anc1","anc4","idelv","pnc48h","penta3","rr_anc","rr_idelv","rr_vacc","total_facilities","total_beds"):
        if c in d: d[c] = pd.to_numeric(d[c], errors="coerce")
    latest_year = int(d["year"].dropna().max()) if "year" in d and d["year"].notna().any() else None
    st.markdown("#### District HMIS context")
    st.caption("District-level HMIS context from the uploaded REACH dataset. These values are not attributed to an individual facility and are not used to manufacture a facility readiness score.")
    if latest_year is not None:
        y = d[d["year"]==latest_year]
        metrics = [("ANC1", "anc1"),("ANC4", "anc4"),("Institutional deliveries", "idelv"),("PNC within 48 h", "pnc48h"),("Penta3", "penta3")]
        cols = st.columns(len(metrics))
        for col,(label,key) in zip(cols,metrics):
            val = y[key].sum(min_count=1) if key in y else np.nan
            col.metric(f"{label} · {latest_year}", "—" if pd.isna(val) else f"{val:,.0f}")
        annual = d.groupby("year",as_index=False)[[k for _,k in metrics if k in d]].sum(min_count=1)
        if len(annual):
            st.line_chart(annual.set_index("year"),use_container_width=True)
        reporting = []
        for label,key in (("ANC reporting","rr_anc"),("Delivery reporting","rr_idelv"),("Vaccination reporting","rr_vacc")):
            if key in y and y[key].notna().any(): reporting.append(f"{label}: {y[key].mean():.1f}%")
        if reporting: st.caption(" · ".join(reporting))


# ---------------------------------------------------------------------------
# Parsers / formatting
# ---------------------------------------------------------------------------
def value_series(payload, section, key):
    d=payload.get(section,{}) or {}
    t=pd.to_datetime(d.get("time",[]),errors="coerce")
    v=pd.to_numeric(pd.Series(d.get(key,[])),errors="coerce")
    if len(t)!=len(v): return pd.Series(dtype=float)
    return pd.Series(v.to_numpy(),index=t,name=key)


def member_frame(payload, section, base):
    d=payload.get(section,{}) or {}
    times=d.get("time",[])
    if not times: return pd.DataFrame()
    cols={}
    for k,v in d.items():
        if k!="time" and isinstance(v,list) and len(v)==len(times) and (k==base or k.startswith(base+"_")):
            cols[k]=pd.to_numeric(pd.Series(v),errors="coerce").to_numpy()
    return pd.DataFrame(cols,index=pd.to_datetime(times,errors="coerce"))


def stat_summary(values):
    s=pd.to_numeric(pd.Series(values),errors="coerce").dropna()
    if s.empty: return {"min":np.nan,"mean":np.nan,"median":np.nan,"max":np.nan}
    return {"min":float(s.min()),"mean":float(s.mean()),"median":float(s.median()),"max":float(s.max())}


def fmt(v,unit="",dec=1):
    return "—" if not np.isfinite(v) else f"{v:,.{dec}f} {unit}".strip()


def fmt_dt(x,hour=True):
    if x is None or pd.isna(x): return "—"
    x=pd.Timestamp(x)
    return x.strftime("%d %b %Y %H:%M UTC") if hour else x.strftime("%d %b %Y")


def risk_label(v):
    if not np.isfinite(v): return "Data unavailable"
    for lo,hi,label,_ in RISK:
        if lo <= v < hi: return label
    return "Extreme"


def risk_color(label):
    for _,_,lab,col in RISK:
        if lab==label:return col
    return "#64748B"




def health_impact_outlook(hazard,horizon,mode,selected_value,map_values,facility_values=None):
    """Transparent forecast-to-health screening layer.

    This deliberately does not predict disease cases or service counts. It converts the
    selected climate/hydrological signal into an operational screening class using the
    selected area's position within the current mapped forecast distribution (or a
    probability value when the dashboard is already in probability mode).
    """
    mv=pd.to_numeric(pd.Series(map_values),errors="coerce").dropna()
    fv=pd.to_numeric(pd.Series(facility_values if facility_values is not None else []),errors="coerce").dropna()
    if not np.isfinite(selected_value):
        score=np.nan
    elif str(mode).lower().find("prob")>=0 or str(mode).lower().find("risk")>=0:
        score=float(np.clip(selected_value,0,100))
    elif len(mv)>=4:
        # Higher heat/rain/discharge/compound values imply greater hazard. For dry anomaly,
        # more-negative values imply a stronger dry signal, so reverse the percentile.
        if hazard=="Drought / dry anomaly":
            score=float(100.0*(mv>=selected_value).mean())
        else:
            score=float(100.0*(mv<=selected_value).mean())
    else:
        score=np.nan
    if not np.isfinite(score):
        level="Data unavailable"; action="Check the forecast data connection before interpreting health implications."
    elif score < 50:
        level="Routine"; action="No elevated climate-linked operational signal is identified from this forecast. Continue routine services and normal surveillance."
    elif score < 75:
        level="Watch"; action="Review local access, staffing, power/WASH and referral conditions; keep routine services running while watching for deterioration."
    elif score < 90:
        level="Prepare"; action="Prepare continuity measures: check routes and referrals, critical stocks, power/WASH, staffing and outreach schedules."
    else:
        level="High concern"; action="Prioritise continuity planning for exposed facilities and populations and verify local warnings, access constraints and readiness before action."

    pathways={
      "Heatwave": {
        "population":"Heat exposure can increase heat illness, dehydration and cardiorespiratory stress, especially among older people, infants, pregnant people, outdoor workers and people with chronic illness.",
        "system":"High heat can increase care demand and can affect staff comfort, medicine/cold-chain conditions, power demand and service continuity.",
        "mch":"For maternal and child health, check safe access, waiting conditions, hydration, outreach schedules, referral transport and continuity of ANC/PNC, delivery and immunisation services.",
        "wash":"No specific WASH-disease outbreak is inferred from temperature alone. Continue routine surveillance and use local epidemiological data before making a disease claim."},
      "Flood – rainfall": {
        "population":"Heavy rainfall can increase injury, displacement and exposure to contaminated water where flooding occurs. Rainfall itself is a precursor; it is not flood depth.",
        "system":"The main health-system pathway is access disruption: roads/crossings, ambulance or boat referral, outreach, supply delivery, power/WASH and facility functionality.",
        "mch":"Check continuity of ANC/PNC, institutional delivery, immunisation and emergency referral where travel or facility access could be disrupted.",
        "wash":"Flooding can elevate diarrhoeal/WASH risk when water or sanitation systems are affected, but the dashboard does not predict disease cases without surveillance and exposure data."},
      "Flood – river discharge (GloFAS)": {
        "population":"High river flow can signal riverine flooding, displacement, injury and isolation of communities when local thresholds are exceeded.",
        "system":"Check river crossings, road passability, referral routes, outreach, supply chains and facility access.",
        "mch":"Prioritise referral continuity and access to delivery, ANC/PNC and child health services in potentially isolated areas.",
        "wash":"River flooding may increase WASH-related exposure, but case occurrence requires epidemiological/surveillance evidence."},
      "Drought / dry anomaly": {
        "population":"Persistent dry conditions can affect water availability, food security, heat exposure and population movement.",
        "system":"Check facility water security, WASH, supply logistics, outreach burden and service demand pressures.",
        "mch":"Monitor continuity of maternal/child services where water scarcity, transport costs or household constraints may affect care seeking.",
        "wash":"Dry conditions can alter water quantity and hygiene practices; the dashboard does not infer a disease outbreak from a climate anomaly alone."},
      "Compound – Flood + Heatwave": {
        "population":"Concurrent heat and heavy rainfall/flood conditions can combine heat stress with access, displacement and WASH pressures.",
        "system":"Plan for simultaneous demand pressure and disruption to access, logistics, power/WASH and referral pathways.",
        "mch":"Protect continuity of time-sensitive maternal and child services and referral transport under combined access and heat pressure.",
        "wash":"WASH-related risk can rise if flooding compromises water/sanitation; disease cases are not predicted without surveillance data."},
      "Compound – Drought + Heatwave": {
        "population":"Combined warm and dry conditions can intensify heat stress, water scarcity and livelihood pressures.",
        "system":"Check water availability, power/cooling, staffing, outreach and supply resilience.",
        "mch":"Monitor access and continuity for pregnant people, newborns and children, especially where household water or transport constraints worsen.",
        "wash":"This is a climate-pressure signal, not a prediction of infection or outbreak."},
      "Compound – Drought → Flood": {
        "population":"A dry-to-wet transition can create rapid changes in runoff, access and WASH conditions.",
        "system":"Prepare for changing logistics and access conditions rather than treating the whole period as one constant hazard state.",
        "mch":"Review outreach and referral plans across the transition window so time-sensitive services remain available.",
        "wash":"Disease risk depends on realised flooding, water quality and surveillance; the sequence alone does not predict cases."}
    }
    p=pathways.get(hazard,{
        "population":"Use the selected hazard signal as an exposure screen, not as a direct prediction of illness.",
        "system":"Check local access and facility readiness before translating the hazard signal into service-disruption risk.",
        "mch":"Maintain continuity of time-sensitive maternal and child health services.",
        "wash":"Disease outcomes require epidemiological and surveillance data in addition to the climate forecast."})
    exposed_facilities=0
    if len(fv)>=4:
        q=float(fv.quantile(.8))
        exposed_facilities=int((fv<=q).sum()) if hazard=="Drought / dry anomaly" else int((fv>=q).sum())
    return {"score":score,"level":level,"action":action,"pathways":p,"exposed_facilities":exposed_facilities,"facility_n":int(len(fv))}

def period_options(horizon):
    if horizon=="Short range": return ["Next 3 days"]
    if horizon=="Medium range": return ["Days 4–7","Days 8–15","Full days 4–15"]
    if horizon=="Sub-seasonal": return ["Week 2","Week 3","Week 4","Week 5","Week 6","Weeks 2–6"]
    return ["Month 1","Month 2","Month 3","Month 4","Month 5","Month 6","Month 7","Months 1–3","Months 4–7"]


def period_display_label(horizon, period):
    """User-facing calendar label; the internal period key remains unchanged."""
    if horizon != "Seasonal":
        return period
    base_month = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize().replace(day=1)
    if period.startswith("Month "):
        n = int(period.split()[-1])
        d = base_month + pd.DateOffset(months=n-1)
        return f"{period} · {d.strftime('%B %Y')}"
    if period == "Months 1–3":
        d1 = base_month
        d2 = base_month + pd.DateOffset(months=2)
        return f"{period} · {d1.strftime('%b')}–{d2.strftime('%b %Y')}"
    if period == "Months 4–7":
        d1 = base_month + pd.DateOffset(months=3)
        d2 = base_month + pd.DateOffset(months=6)
        return f"{period} · {d1.strftime('%b')}–{d2.strftime('%b %Y')}"
    return period


def daily_slice(horizon,period):
    if horizon=="Short range": return 0,3
    return {"Days 4–7":(3,7),"Days 8–15":(7,15),"Full days 4–15":(3,15)}[period]


def long_slice(period):
    if period.startswith("Week "):
        i=int(period.split()[-1])-1; return "weekly",slice(i,i+1)
    if period=="Weeks 2–6": return "weekly",slice(1,6)
    if period.startswith("Month "):
        i=int(period.split()[-1])-1; return "monthly",slice(i,i+1)
    if period=="Months 1–3": return "monthly",slice(0,3)
    return "monthly",slice(3,7)


def discharge_slice(horizon,period):
    if horizon in ("Short range","Medium range"): return daily_slice(horizon,period)
    if horizon=="Sub-seasonal":
        if period=="Weeks 2–6": return 7,42
        w=int(period.split()[-1]); return (w-1)*7,w*7
    if period=="Months 1–3": return 0,90
    if period=="Months 4–7": return 90,210
    m=int(period.split()[-1]); return (m-1)*30,min(m*30,210)


# ---------------------------------------------------------------------------
# Hazard / map-mode controls
# ---------------------------------------------------------------------------
def hazards_for_horizon(h):
    base=["Heatwave","Flood – rainfall","Flood – river discharge (GloFAS)","Compound – Flood + Heatwave"]
    if h in ("Sub-seasonal","Seasonal"):
        base += ["Drought / dry anomaly","Compound – Drought + Heatwave","Compound – Drought → Flood"]
    return base


def map_modes(hazard,horizon):
    if hazard.startswith("Compound"):
        return ["Risk-class screening"]
    if hazard=="Flood – river discharge (GloFAS)":
        return ["Physical magnitude","Relative risk-class screening"]
    if horizon in ("Short range","Medium range"):
        return ["Physical magnitude","Probabilistic risk classes"]
    return ["Physical anomaly","Risk-class screening"]


BASEMAP_STYLES = {
    "Streets / places": "carto-voyager",
    "OpenStreetMap": "open-street-map",
    "Clean light": "carto-positron",
    "Terrain / outdoors": "outdoors",
    "Satellite": "satellite",
    "Satellite + streets": "satellite-streets",
}


def map_view_from_df(df):
    lat = pd.to_numeric(df.get("rep_lat", pd.Series(dtype=float)), errors="coerce").dropna()
    lon = pd.to_numeric(df.get("rep_lon", pd.Series(dtype=float)), errors="coerce").dropna()
    if not len(lat) or not len(lon):
        return {"lat": -13.5, "lon": 28.0}, 4.0
    centre = {"lat": float(lat.median()), "lon": float(lon.median())}
    span = max(float(lat.max()-lat.min()), float(lon.max()-lon.min()), 0.25)
    zoom = float(np.clip(7.7 - np.log2(span), 2.7, 8.5))
    return centre, zoom


def horizontal_colorbar(title, tickvals=None, ticktext=None):
    return dict(
        title=dict(text=title, side="top"),
        orientation="h",
        x=0.5, xanchor="center",
        y=-0.08, yanchor="top",
        len=0.58,
        thickness=14,
        tickvals=tickvals,
        ticktext=ticktext,
    )


def unit_for(hazard,horizon,map_mode):
    if "risk" in map_mode.lower() or "Probabilistic" in map_mode: return "%"
    if hazard=="Heatwave": return "°C"
    if hazard=="Flood – rainfall": return "mm"
    if hazard=="Flood – river discharge (GloFAS)": return "m³/s"
    if hazard=="Drought / dry anomaly": return "mm"
    return "%"


# ---------------------------------------------------------------------------
# Batch helpers and deterministic/long-range forecasts
# ---------------------------------------------------------------------------
def chunks(df,n):
    for i in range(0,len(df),n):
        yield df.iloc[i:i+n]


@st.cache_data(ttl=10800,show_spinner=False)
def regional_deterministic(records,source):
    pts=pd.DataFrame(records)
    endpoint=ECMWF_URL if source=="ECMWF IFS HRES" else GFS_URL
    out={}; statuses=[]
    for batch in chunks(pts,100):
        params={
            "latitude":",".join(batch.rep_lat.map(lambda x:f"{x:.5f}")),
            "longitude":",".join(batch.rep_lon.map(lambda x:f"{x:.5f}")),
            "daily":"temperature_2m_max,precipitation_sum",
            "forecast_days":15 if source=="ECMWF IFS HRES" else 16,
            "timezone":"UTC",
        }
        x,status=cached_json(endpoint,params,10800,110)
        statuses.append(status)
        arr=x if isinstance(x,list) else [x]
        for rec,p in zip(batch.to_dict("records"),arr):
            out[str(rec["REGION_CODE"])]={
                "tmax":value_series(p,"daily","temperature_2m_max"),
                "precip":value_series(p,"daily","precipitation_sum"),
            }
    return out,"/".join(sorted(set(statuses)))


@st.cache_data(ttl=21600,show_spinner=False)
def regional_long(records):
    pts=pd.DataFrame(records)
    out={};statuses=[]
    for batch in chunks(pts,60):
        params={
            "latitude":",".join(batch.rep_lat.map(lambda x:f"{x:.5f}")),
            "longitude":",".join(batch.rep_lon.map(lambda x:f"{x:.5f}")),
            "models":"ecmwf_seasonal_ensemble_mean_seamless",
            "weekly":"temperature_2m_anomaly,precipitation_anomaly",
            "monthly":"temperature_2m_anomaly,precipitation_anomaly",
            "forecast_days":217,"timezone":"UTC",
        }
        x,status=cached_json(SEASONAL_URL,params,21600,110)
        statuses.append(status)
        arr=x if isinstance(x,list) else [x]
        for rec,p in zip(batch.to_dict("records"),arr):
            out[str(rec["REGION_CODE"])]={
                "weekly_temp":value_series(p,"weekly","temperature_2m_anomaly"),
                "weekly_precip":value_series(p,"weekly","precipitation_anomaly"),
                "monthly_temp":value_series(p,"monthly","temperature_2m_anomaly"),
                "monthly_precip":value_series(p,"monthly","precipitation_anomaly"),
            }
    return out,"/".join(sorted(set(statuses)))


@st.cache_data(ttl=21600,show_spinner=False)
def regional_glofas(records,forecast_days):
    pts=pd.DataFrame(records)
    out={};statuses=[]
    for batch in chunks(pts,60):
        params={
            "latitude":",".join(batch.rep_lat.map(lambda x:f"{x:.5f}")),
            "longitude":",".join(batch.rep_lon.map(lambda x:f"{x:.5f}")),
            "daily":"river_discharge_median",
            "forecast_days":int(forecast_days),
            "cell_selection":"nearest",
        }
        x,status=cached_json(FLOOD_URL,params,21600,110)
        statuses.append(status)
        arr=x if isinstance(x,list) else [x]
        for rec,p in zip(batch.to_dict("records"),arr):
            out[str(rec["REGION_CODE"])]=value_series(p,"daily","river_discharge_median")
    return out,"/".join(sorted(set(statuses)))


# ---------------------------------------------------------------------------
# On-demand regional ensemble probabilities
# ---------------------------------------------------------------------------
def consecutive(arr,n=3):
    run=0
    for x in arr:
        run=run+1 if bool(x) else 0
        if run>=n:return True
    return False


@st.cache_data(ttl=10800,show_spinner=False)
def regional_probability(records,ensemble_system,horizon,period,temp_threshold,rain3_threshold,need_temp,need_rain):
    pts=pd.DataFrame(records)
    model="ecmwf_ifs025" if ensemble_system=="ECMWF IFS ENS" else "gfs_seamless"
    out={};statuses=[]
    s,e=daily_slice(horizon,period)
    variables=[]
    if need_temp: variables.append("temperature_2m_max")
    if need_rain: variables.append("precipitation_sum")

    # Small batches + cache reduce public-API pressure.
    for bi,batch in enumerate(chunks(pts,15)):
        params={
            "latitude":",".join(batch.rep_lat.map(lambda x:f"{x:.5f}")),
            "longitude":",".join(batch.rep_lon.map(lambda x:f"{x:.5f}")),
            "models":model,
            "daily":",".join(variables),
            "forecast_days":16,"timezone":"UTC",
        }
        x,status=cached_json(ENSEMBLE_URL,params,10800,120)
        statuses.append(status)
        arr=x if isinstance(x,list) else [x]
        for rec,payload in zip(batch.to_dict("records"),arr):
            hp=rp=np.nan
            if need_temp:
                t=member_frame(payload,"daily","temperature_2m_max")
                b=t.iloc[s:e]
                hits=[]
                for c in b.columns:
                    vals=b[c].to_numpy(float)
                    hits.append(consecutive(np.isfinite(vals)&(vals>=temp_threshold),3))
                hp=100*float(np.mean(hits)) if hits else np.nan
            if need_rain:
                p=member_frame(payload,"daily","precipitation_sum")
                roll=p.rolling(3,min_periods=3).sum()
                b=roll.iloc[max(0,s-2):e]
                hits=[bool((b[c]>=rain3_threshold).any()) for c in b.columns]
                rp=100*float(np.mean(hits)) if hits else np.nan
            out[str(rec["REGION_CODE"])]={"heat_p":hp,"rain_p":rp}
        if bi>0:
            time.sleep(.8)
    return out,"/".join(sorted(set(statuses)))


# ---------------------------------------------------------------------------
# Build regional map values / risk scores
# ---------------------------------------------------------------------------
def percentile_score(series,positive=True):
    s=pd.Series(series,dtype=float)
    if positive:
        x=s.where(s>0,0)
    else:
        x=(-s).where(s<0,0)
    ranks=x.rank(pct=True,method="average")*100
    return ranks.where(x>0,0)


def build_map_values(regions,hazard,horizon,period,map_mode,det_source,ensemble_system,temp_threshold,rain_threshold):
    records=regions.to_dict("records")
    rows=[]
    status=""

    if hazard=="Flood – river discharge (GloFAS)":
        fd=30 if horizon in ("Short range","Medium range") else 210
        data,status=regional_glofas(records,fd)
        s,e=discharge_slice(horizon,period)
        raw=[]
        for r in regions.itertuples():
            q=data.get(str(r.REGION_CODE),pd.Series(dtype=float)).iloc[s:e]
            v=float(q.max()) if len(q.dropna()) else np.nan
            raw.append(v)
        vals=pd.Series(raw,index=regions.index)
        if map_mode=="Physical magnitude":
            scores=vals
        else:
            scores=vals.rank(pct=True)*100
        for i,r in regions.iterrows():
            rows.append({**r.to_dict(),"value":float(scores.loc[i]) if pd.notna(scores.loc[i]) else np.nan})
        return pd.DataFrame(rows),status,{"glofas":data}

    if horizon in ("Short range","Medium range"):
        if map_mode=="Probabilistic risk classes" or hazard.startswith("Compound"):
            need_temp = hazard in ("Heatwave","Compound – Flood + Heatwave")
            need_rain = hazard in ("Flood – rainfall","Compound – Flood + Heatwave")
            probs,status=regional_probability(records,ensemble_system,horizon,period,temp_threshold,rain_threshold,need_temp,need_rain)
            for r in regions.itertuples():
                p=probs.get(str(r.REGION_CODE),{})
                if hazard=="Heatwave": v=p.get("heat_p",np.nan)
                elif hazard=="Flood – rainfall": v=p.get("rain_p",np.nan)
                else:
                    a,b=p.get("heat_p",np.nan),p.get("rain_p",np.nan)
                    v=min(a,b) if np.isfinite(a) and np.isfinite(b) else np.nan
                rows.append({**r._asdict(),"value":v})
            return pd.DataFrame(rows),status,{"prob":probs}

        data,status=regional_deterministic(records,det_source)
        s,e=daily_slice(horizon,period)
        for r in regions.itertuples():
            x=data.get(str(r.REGION_CODE),{})
            if hazard=="Heatwave":
                z=x.get("tmax",pd.Series(dtype=float)).iloc[s:e]
                v=float(z.max()) if len(z.dropna()) else np.nan
            else:
                p=x.get("precip",pd.Series(dtype=float))
                z=p.rolling(3,min_periods=3).sum().iloc[max(0,s-2):e]
                v=float(z.max()) if len(z.dropna()) else np.nan
            rows.append({**r._asdict(),"value":v})
        return pd.DataFrame(rows),status,{"det":data}

    # Long-range.
    data,status=regional_long(records)
    section,sl=long_slice(period)
    raw=[]
    aux=[]
    for r in regions.itertuples():
        x=data.get(str(r.REGION_CODE),{})
        tm=x.get(f"{section}_temp",pd.Series(dtype=float)).iloc[sl]
        pm=x.get(f"{section}_precip",pd.Series(dtype=float)).iloc[sl]
        t=float(tm.mean()) if len(tm.dropna()) else np.nan
        p=float(pm.mean()) if len(pm.dropna()) else np.nan

        # For sequential drought->flood, split the selected multi-period window.
        seq=np.nan
        if hazard=="Compound – Drought → Flood" and len(pm)>=2:
            cut=max(1,len(pm)//2)
            p1=float(pm.iloc[:cut].mean())
            p2=float(pm.iloc[cut:].mean()) if len(pm.iloc[cut:]) else np.nan
            seq=(p1,p2)

        raw.append((t,p))
        aux.append(seq)

    tser=pd.Series([x[0] for x in raw],index=regions.index)
    pser=pd.Series([x[1] for x in raw],index=regions.index)

    if hazard=="Heatwave":
        vals=tser if map_mode=="Physical anomaly" else percentile_score(tser,True)
    elif hazard=="Flood – rainfall":
        vals=pser if map_mode=="Physical anomaly" else percentile_score(pser,True)
    elif hazard=="Drought / dry anomaly":
        vals=pser if map_mode=="Physical anomaly" else percentile_score(pser,False)
    elif hazard=="Compound – Flood + Heatwave":
        hs=percentile_score(tser,True); ws=percentile_score(pser,True)
        vals=pd.concat([hs,ws],axis=1).min(axis=1)
    elif hazard=="Compound – Drought + Heatwave":
        hs=percentile_score(tser,True); ds=percentile_score(pser,False)
        vals=pd.concat([hs,ds],axis=1).min(axis=1)
    else:
        first=pd.Series([x[0] if isinstance(x,tuple) else np.nan for x in aux],index=regions.index)
        second=pd.Series([x[1] if isinstance(x,tuple) else np.nan for x in aux],index=regions.index)
        ds=percentile_score(first,False); ws=percentile_score(second,True)
        vals=pd.concat([ds,ws],axis=1).min(axis=1)

    for i,r in regions.iterrows():
        rows.append({**r.to_dict(),"value":float(vals.loc[i]) if pd.notna(vals.loc[i]) else np.nan})
    return pd.DataFrame(rows),status,{"long":data}


# ---------------------------------------------------------------------------
# Maps
# ---------------------------------------------------------------------------

def map_value_label(hazard, horizon, map_mode):
    if hazard.startswith("Compound"):
        return "Compound screening score"
    if "Probabilistic" in map_mode:
        return "Forecast probability"
    if "risk" in map_mode.lower():
        return "Relative risk-screening score"
    if hazard == "Heatwave":
        return "Forecast Tmax" if horizon in ("Short range","Medium range") else "Temperature anomaly"
    if hazard == "Flood – rainfall":
        return "Maximum 3-day precipitation" if horizon in ("Short range","Medium range") else "Precipitation anomaly"
    if hazard == "Flood – river discharge (GloFAS)":
        return "Peak ensemble-median discharge"
    if hazard == "Drought / dry anomaly":
        return "Precipitation anomaly"
    return "Forecast value"


def map_figure(
    geo, map_df, hazard, horizon, map_mode, focus, period, source_label,
    basemap_name="Streets / places", layer_opacity=0.64
):
    df = map_df.copy()
    df["REGION_CODE"] = df["REGION_CODE"].astype(str)
    unit = unit_for(hazard, horizon, map_mode)
    value_label = map_value_label(hazard, horizon, map_mode)
    risk_mode = (
        ("risk" in map_mode.lower())
        or map_mode == "Probabilistic risk classes"
        or hazard.startswith("Compound")
    )

    if risk_mode:
        df["RISK_CLASS"] = df["value"].map(risk_label)
        colorscale = [
            [0.00, "#2E7D32"], [0.0999, "#2E7D32"],
            [0.10, "#7CB342"], [0.2999, "#7CB342"],
            [0.30, "#F9A825"], [0.4999, "#F9A825"],
            [0.50, "#EF6C00"], [0.6999, "#EF6C00"],
            [0.70, "#C62828"], [0.8499, "#C62828"],
            [0.85, "#6A1B9A"], [1.00, "#6A1B9A"],
        ]
        zmin, zmax = 0, 100
        tickvals = [5,20,40,60,77.5,92.5]
        ticktext = ["No/minimal","Low","Moderate","High","Very high","Extreme"]
        colorbar_title = "%"
    else:
        df["RISK_CLASS"] = "Physical / anomaly value"
        vals = pd.to_numeric(df["value"], errors="coerce").dropna()
        anomaly = (
            horizon in ("Sub-seasonal","Seasonal")
            and hazard in ("Heatwave","Flood – rainfall","Drought / dry anomaly")
        )
        if anomaly:
            lim = max(.1, float(np.nanquantile(np.abs(vals), .98))) if len(vals) else 1.0
            zmin, zmax = -lim, lim
            if hazard == "Heatwave":
                colorscale = [
                    [0.00,"#1D4ED8"], [0.18,"#0EA5E9"], [0.36,"#22D3EE"],
                    [0.50,"#F8FAFC"],
                    [0.64,"#FDE047"], [0.82,"#F97316"], [1.00,"#DC2626"],
                ]
            else:
                colorscale = [
                    [0.00,"#9A3412"], [0.20,"#EA580C"], [0.38,"#FDBA74"],
                    [0.50,"#F8FAFC"],
                    [0.62,"#A5F3FC"], [0.80,"#0EA5E9"], [1.00,"#1D4ED8"],
                ]
        else:
            zmin = float(vals.quantile(.02)) if len(vals) else 0.0
            zmax = float(vals.quantile(.98)) if len(vals) else 1.0
            if zmax <= zmin:
                zmax = zmin + 1
            colorscale = "YlOrRd" if hazard == "Heatwave" else "Blues"
        tickvals = None
        ticktext = None
        colorbar_title = unit

    def value_string(v):
        if not np.isfinite(v): return "Data unavailable"
        if unit == "%": return f"{v:.1f}%"
        if unit == "°C": return f"{v:.1f} °C"
        if unit == "mm": return f"{v:.1f} mm"
        if unit == "m³/s": return f"{v:,.1f} m³/s"
        return f"{v:.1f}"

    df["VALUE_DISPLAY"] = [value_string(v) for v in pd.to_numeric(df["value"], errors="coerce")]
    df["SOURCE_DISPLAY"] = source_label
    df["HORIZON_DISPLAY"] = f"{horizon} · {period_display_label(horizon,period)}"

    custom = np.stack([
        df["REGION_NAME"].astype(str),
        df["ADMIN1"].astype(str),
        df["VALUE_DISPLAY"].astype(str),
        df["RISK_CLASS"].astype(str),
        df["HORIZON_DISPLAY"].astype(str),
        df["SOURCE_DISPLAY"].astype(str),
    ], axis=1)

    fig = go.Figure(go.Choroplethmap(
        geojson=geo,
        locations=df["REGION_CODE"],
        z=df["value"],
        featureidkey="properties.REGION_CODE",
        colorscale=colorscale,
        zmin=zmin, zmax=zmax,
        marker=dict(
            opacity=float(layer_opacity),
            line=dict(width=.7, color="rgba(255,255,255,.88)")
        ),
        colorbar=horizontal_colorbar(colorbar_title,tickvals=tickvals,ticktext=ticktext),
        customdata=custom,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "%{customdata[1]}<br>"
            + value_label + ": <b>%{customdata[2]}</b><br>"
            "Risk class: %{customdata[3]}<br>"
            "Window: %{customdata[4]}<br>"
            "Source: %{customdata[5]}<extra></extra>"
        ),
    ))

    focus_row = df[df["REGION_NAME"] == focus]
    if len(focus_row):
        r = focus_row.iloc[0]
        fig.add_trace(go.Scattermap(
            lon=[float(r["rep_lon"])], lat=[float(r["rep_lat"])],
            mode="markers+text", text=[focus], textposition="top center",
            marker=dict(size=10,color="#111827"),
            name="Focus area",
            customdata=[[r["VALUE_DISPLAY"],r["RISK_CLASS"]]],
            hovertemplate=(
                f"<b>{focus}</b><br>"
                + value_label + ": <b>%{customdata[0]}</b><br>"
                "Risk class: %{customdata[1]}<extra></extra>"
            ),
        ))

    centre,zoom=map_view_from_df(df)
    fig.update_layout(
        map=dict(
            style=BASEMAP_STYLES.get(basemap_name,"carto-voyager"),
            center=centre,zoom=zoom
        ),
        height=720,
        margin=dict(l=0,r=0,t=45,b=82),
        title=dict(text=f"{hazard} · {horizon} · {map_mode}",x=.01,xanchor="left",font=dict(size=16)),
        hoverlabel=dict(bgcolor="white",font_size=13,font_family="Arial"),
        legend=dict(orientation="h",y=-.04),
    )
    return fig


# ---------------------------------------------------------------------------
# Focus time series / exact timing
# ---------------------------------------------------------------------------
@st.cache_data(ttl=10800,show_spinner=False)
def focus_hourly(lat,lon,source):
    endpoint=ECMWF_URL if source=="ECMWF IFS HRES" else GFS_URL
    params={
        "latitude":round(float(lat),5),"longitude":round(float(lon),5),
        "hourly":"temperature_2m,precipitation","forecast_days":15 if source=="ECMWF IFS HRES" else 16,
        "timezone":"UTC",
    }
    x,status=cached_json(endpoint,params,10800,100)
    return value_series(x,"hourly","temperature_2m"),value_series(x,"hourly","precipitation"),status



@st.cache_data(ttl=10800,show_spinner=False)
def focus_daily_deterministic(lat,lon,source):
    endpoint=ECMWF_URL if source=="ECMWF IFS HRES" else GFS_URL
    params={
        "latitude":round(float(lat),5),"longitude":round(float(lon),5),
        "daily":"temperature_2m_max,precipitation_sum",
        "forecast_days":15 if source=="ECMWF IFS HRES" else 16,
        "timezone":"UTC",
    }
    x,status=cached_json(endpoint,params,10800,100)
    return value_series(x,"daily","temperature_2m_max"),value_series(x,"daily","precipitation_sum"),status


def _era5_daily_context(history, dates):
    """Map future forecast dates to ERA5 1981–2014 day-of-year climatology.
    This is historical context, not an observed value for the future date.
    """
    if history is None or history.empty:
        return pd.DataFrame(index=pd.DatetimeIndex(dates))
    h=history.copy().dropna(subset=["date"])
    h["md"]=h["date"].dt.strftime("%m-%d")
    g=h.groupby("md").agg(
        ERA5_Tmax_Clim_C=("tmax","mean"), ERA5_TX90_C=("tmax",lambda x:x.quantile(.90)),
        ERA5_Precip_Clim_mm=("precip","mean"), ERA5_Precip_P95_mm=("precip",lambda x:x.quantile(.95))
    )
    out=[]
    for d in pd.DatetimeIndex(dates):
        key=d.strftime("%m-%d")
        if key in g.index:
            row=g.loc[key].to_dict()
        elif key=="02-29" and "02-28" in g.index:
            row=g.loc["02-28"].to_dict()
        else:
            row={c:np.nan for c in g.columns}
        row["Date"]=d; out.append(row)
    return pd.DataFrame(out).set_index("Date") if out else pd.DataFrame()


def build_point_model_comparison(lat,lon,horizon,period):
    et,ep,es=focus_daily_deterministic(lat,lon,"ECMWF IFS HRES")
    gt,gp,gs=focus_daily_deterministic(lat,lon,"NOAA GFS")
    idx=et.index.union(ep.index).union(gt.index).union(gp.index).sort_values()
    df=pd.DataFrame(index=idx)
    df["ECMWF_Tmax_C"]=et.reindex(idx)
    df["GFS_Tmax_C"]=gt.reindex(idx)
    df["ECMWF_Precip_mm"]=ep.reindex(idx)
    df["GFS_Precip_mm"]=gp.reindex(idx)
    try:
        hist,_=focus_extreme_history(lat,lon)
        era=_era5_daily_context(hist,idx)
        df=df.join(era,how="left")
    except Exception:
        for c in ["ERA5_Tmax_Clim_C","ERA5_TX90_C","ERA5_Precip_Clim_mm","ERA5_Precip_P95_mm"]:
            df[c]=np.nan
    s,e=daily_slice(horizon,period)
    view=df.iloc[s:e].copy()
    view["ECMWF_Tmax_Anomaly_C"]=view["ECMWF_Tmax_C"]-view["ERA5_Tmax_Clim_C"]
    view["GFS_Tmax_Anomaly_C"]=view["GFS_Tmax_C"]-view["ERA5_Tmax_Clim_C"]
    view["ECMWF_Precip_Anomaly_mm"]=view["ECMWF_Precip_mm"]-view["ERA5_Precip_Clim_mm"]
    view["GFS_Precip_Anomaly_mm"]=view["GFS_Precip_mm"]-view["ERA5_Precip_Clim_mm"]
    return view, f"ECMWF {es} · NOAA GFS {gs}"


def point_model_comparison_figure(df,hazard,location_label):
    if df is None or df.empty:
        return None
    is_heat=hazard in ("Heatwave","Compound – Flood + Heatwave")
    if is_heat:
        fig=make_subplots(rows=2,cols=2,subplot_titles=(
            "Forecast Tmax vs ERA5 climatology","Forecast anomaly relative to ERA5 climatology",
            "ECMWF minus NOAA GFS","Selected-window summary"
        ),vertical_spacing=.16,horizontal_spacing=.10)
        fig.add_trace(go.Scatter(x=df.index,y=df["ECMWF_Tmax_C"],mode="lines+markers",name="ECMWF IFS",line=dict(color="#075985",width=3)),1,1)
        fig.add_trace(go.Scatter(x=df.index,y=df["GFS_Tmax_C"],mode="lines+markers",name="NOAA GFS",line=dict(color="#7C3AED",width=3)),1,1)
        fig.add_trace(go.Scatter(x=df.index,y=df["ERA5_Tmax_Clim_C"],mode="lines",name="ERA5 climatology",line=dict(color="#475569",dash="dash",width=2)),1,1)
        fig.add_trace(go.Scatter(x=df.index,y=df["ERA5_TX90_C"],mode="lines",name="ERA5 TX90",line=dict(color="#DC2626",dash="dot",width=2)),1,1)
        fig.add_trace(go.Bar(x=df.index,y=df["ECMWF_Tmax_Anomaly_C"],name="ECMWF anomaly",marker_color="#0284C7"),1,2)
        fig.add_trace(go.Bar(x=df.index,y=df["GFS_Tmax_Anomaly_C"],name="GFS anomaly",marker_color="#8B5CF6"),1,2)
        diff=df["ECMWF_Tmax_C"]-df["GFS_Tmax_C"]
        fig.add_trace(go.Bar(x=df.index,y=diff,name="ECMWF − GFS",marker_color="#0F766E"),2,1)
        vals=[df["ECMWF_Tmax_C"].max(),df["GFS_Tmax_C"].max(),df["ERA5_Tmax_Clim_C"].max()]
        fig.add_trace(go.Bar(x=["ECMWF max","GFS max","ERA5 climatology max"],y=vals,name="Window summary",marker_color=["#075985","#7C3AED","#64748B"]),2,2)
        fig.update_yaxes(title_text="Tmax (°C)",row=1,col=1)
        fig.update_yaxes(title_text="Anomaly (°C)",row=1,col=2)
        fig.update_yaxes(title_text="Difference (°C)",row=2,col=1)
        fig.update_yaxes(title_text="Tmax (°C)",row=2,col=2)
    else:
        fig=make_subplots(rows=2,cols=2,subplot_titles=(
            "Daily precipitation vs ERA5 climatology","Forecast anomaly relative to ERA5 climatology",
            "ECMWF minus NOAA GFS","Selected-window precipitation summary"
        ),vertical_spacing=.16,horizontal_spacing=.10)
        fig.add_trace(go.Bar(x=df.index,y=df["ECMWF_Precip_mm"],name="ECMWF IFS",marker_color="#075985",opacity=.72),1,1)
        fig.add_trace(go.Scatter(x=df.index,y=df["GFS_Precip_mm"],mode="lines+markers",name="NOAA GFS",line=dict(color="#7C3AED",width=3)),1,1)
        fig.add_trace(go.Scatter(x=df.index,y=df["ERA5_Precip_Clim_mm"],mode="lines",name="ERA5 climatology",line=dict(color="#475569",dash="dash",width=2)),1,1)
        fig.add_trace(go.Scatter(x=df.index,y=df["ERA5_Precip_P95_mm"],mode="lines",name="ERA5 daily P95",line=dict(color="#DC2626",dash="dot",width=2)),1,1)
        fig.add_trace(go.Bar(x=df.index,y=df["ECMWF_Precip_Anomaly_mm"],name="ECMWF anomaly",marker_color="#0284C7"),1,2)
        fig.add_trace(go.Bar(x=df.index,y=df["GFS_Precip_Anomaly_mm"],name="GFS anomaly",marker_color="#8B5CF6"),1,2)
        diff=df["ECMWF_Precip_mm"]-df["GFS_Precip_mm"]
        fig.add_trace(go.Bar(x=df.index,y=diff,name="ECMWF − GFS",marker_color="#0F766E"),2,1)
        vals=[df["ECMWF_Precip_mm"].sum(),df["GFS_Precip_mm"].sum(),df["ERA5_Precip_Clim_mm"].sum()]
        fig.add_trace(go.Bar(x=["ECMWF total","GFS total","ERA5 climatology total"],y=vals,name="Window summary",marker_color=["#075985","#7C3AED","#64748B"]),2,2)
        fig.update_yaxes(title_text="mm/day",row=1,col=1)
        fig.update_yaxes(title_text="Anomaly (mm/day)",row=1,col=2)
        fig.update_yaxes(title_text="Difference (mm/day)",row=2,col=1)
        fig.update_yaxes(title_text="Total (mm)",row=2,col=2)
    fig.update_layout(title=dict(text=f"ECMWF · NOAA GFS · ERA5 historical context — {location_label}",x=.01,xanchor="left",font=dict(size=16)),
                      height=720,barmode="group",margin=dict(l=25,r=10,t=70,b=35),legend=dict(orientation="h",y=-.10),hovermode="x unified")
    return fig

@st.cache_data(ttl=10800,show_spinner=False)
def focus_ensemble(lat,lon,system):
    model="ecmwf_ifs025" if system=="ECMWF IFS ENS" else "gfs_seamless"
    params={
        "latitude":round(float(lat),5),"longitude":round(float(lon),5),
        "models":model,"daily":"temperature_2m_max,precipitation_sum",
        "forecast_days":16,"timezone":"UTC",
    }
    x,status=cached_json(ENSEMBLE_URL,params,10800,100)
    return member_frame(x,"daily","temperature_2m_max"),member_frame(x,"daily","precipitation_sum"),status


@st.cache_data(ttl=2592000,show_spinner=False)
def focus_baseline(lat,lon):
    params={
        "latitude":round(float(lat),5),"longitude":round(float(lon),5),
        "start_date":"1981-01-01","end_date":"2014-12-31",
        "daily":"temperature_2m_max,precipitation_sum","models":"era5","timezone":"UTC",
    }
    x,status=cached_json(ARCHIVE_URL,params,2592000,100)
    d=x.get("daily",{})
    df=pd.DataFrame({
        "date":pd.to_datetime(d.get("time",[]),errors="coerce"),
        "tmax":pd.to_numeric(pd.Series(d.get("temperature_2m_max",[])),errors="coerce"),
        "precip":pd.to_numeric(pd.Series(d.get("precipitation_sum",[])),errors="coerce"),
    }).dropna(subset=["date"])
    df["month"]=df.date.dt.month
    tx90=df.groupby("month").tmax.quantile(.90).to_dict()
    df["rain3"]=df.precip.rolling(3,min_periods=3).sum()
    p95=df.groupby("month").rain3.quantile(.95).to_dict()
    return tx90,p95,status


def local_heat_prob(t,tx90,s,e):
    if t.empty:return np.nan
    b=t.iloc[s:e]; th=np.array([tx90.get(int(d.month),np.nan) for d in b.index]);hits=[]
    for c in b.columns:
        vals=b[c].to_numpy(float)
        hits.append(consecutive(np.isfinite(vals)&np.isfinite(th)&(vals>th),3))
    return 100*float(np.mean(hits)) if hits else np.nan


def local_rain_prob(p,p95,s,e):
    if p.empty:return np.nan
    b=p.rolling(3,min_periods=3).sum().iloc[max(0,s-2):e]
    th=np.array([p95.get(int(d.month),np.nan) for d in b.index]);hits=[]
    for c in b.columns:
        vals=b[c].to_numpy(float)
        hits.append(bool(np.any(np.isfinite(vals)&np.isfinite(th)&(vals>th))))
    return 100*float(np.mean(hits)) if hits else np.nan


def exact_window(index,horizon,period):
    if len(index)==0:return None,None
    d0=pd.Timestamp(index.min()).floor("D")
    if horizon=="Short range": return d0,d0+pd.Timedelta(days=3)-pd.Timedelta(hours=1)
    s,e=daily_slice(horizon,period)
    return d0+pd.Timedelta(days=s),d0+pd.Timedelta(days=e)-pd.Timedelta(hours=1)

def _first_series_from_payload(payload, horizon, hazard):
    """Return a representative forecast series only to recover the source-valid calendar.

    Values are never borrowed from this series for another location; it is used only for
    the common time index returned by the same API request.
    """
    if not isinstance(payload,dict):
        return pd.Series(dtype=float)
    if horizon in ("Short range","Medium range"):
        d=payload.get("det",{})
        if not d: return pd.Series(dtype=float)
        first=next(iter(d.values()),{})
        key="tmax" if hazard=="Heatwave" else "precip"
        return first.get(key,pd.Series(dtype=float))
    d=payload.get("long",{})
    if not d: return pd.Series(dtype=float)
    first=next(iter(d.values()),{})
    section,_=long_slice(period)
    key=f"{section}_temp" if hazard=="Heatwave" else f"{section}_precip"
    return first.get(key,pd.Series(dtype=float))


def forecast_validity(payload,horizon,period,hazard):
    """Calendar-validity metadata for the selected forecast window.

    Daily products are represented as full UTC days because Tmax and precipitation_sum
    are daily aggregates. Weekly/monthly anomaly products are represented by their
    aggregation interval; no artificial event hour is assigned to long-range outlooks.
    """
    ser=_first_series_from_payload(payload,horizon,hazard)
    idx=pd.DatetimeIndex(ser.index) if isinstance(ser,pd.Series) and len(ser) else pd.DatetimeIndex([])
    if horizon in ("Short range","Medium range"):
        if len(idx):
            s,e=daily_slice(horizon,period)
            view=idx[s:e]
            if len(view):
                start=pd.Timestamp(view.min()).floor("D")
                end=pd.Timestamp(view.max()).floor("D")+pd.Timedelta(hours=23,minutes=59)
                return start,end,"Daily forecast window"
        d0=pd.Timestamp.now(tz="UTC").tz_localize(None).floor("D")
        s,e=daily_slice(horizon,period)
        return d0+pd.Timedelta(days=s),d0+pd.Timedelta(days=e)-pd.Timedelta(minutes=1),"Daily forecast window"
    if len(idx):
        section,sl=long_slice(period)
        view=idx[sl]
        if len(view):
            start=pd.Timestamp(view.min()).floor("D")
            if section=="weekly":
                end=pd.Timestamp(view.max()).floor("D")+pd.Timedelta(days=6,hours=23,minutes=59)
                return start,end,"Weekly anomaly window"
            end=pd.Timestamp(view.max()).to_period("M").end_time.floor("min")
            return start,end,"Monthly anomaly window"
    return None,None,"Forecast window"


def format_valid_window(start,end):
    if start is None or end is None: return "—"
    s=pd.Timestamp(start); e=pd.Timestamp(end)
    if s.date()==e.date():
        return f"{s.strftime('%d %b %Y')} · 00:00–23:59 UTC"
    return f"{s.strftime('%d %b %Y')} → {e.strftime('%d %b %Y')} · UTC"


def _facility_time_choices(payload,horizon,period,hazard):
    ser=_first_series_from_payload(payload,horizon,hazard)
    if not isinstance(ser,pd.Series) or ser.empty:
        return []
    if horizon in ("Short range","Medium range"):
        s,e=daily_slice(horizon,period)
        return [pd.Timestamp(x) for x in ser.index[s:e]]
    _,sl=long_slice(period)
    return [pd.Timestamp(x) for x in ser.index[sl]]


def _facility_values_at_time(base_df,payload,horizon,hazard,when):
    """Replace the window-summary value with a time-specific facility value.

    Heat: daily Tmax or weekly/monthly temperature anomaly.
    Rain: rolling 3-day accumulation ending on the selected day for short/medium range;
    weekly/monthly precipitation anomaly for extended/seasonal range.
    """
    out=base_df.copy()
    store=(payload or {}).get("det",{}) if horizon in ("Short range","Medium range") else (payload or {}).get("long",{})
    vals=[]
    for r in out.itertuples():
        x=store.get(str(r.REGION_CODE),{})
        if horizon in ("Short range","Medium range"):
            if hazard=="Heatwave":
                ser=x.get("tmax",pd.Series(dtype=float))
                v=ser.get(when,np.nan) if hasattr(ser,"get") else np.nan
            elif hazard=="Flood – rainfall":
                ser=x.get("precip",pd.Series(dtype=float))
                roll=ser.rolling(3,min_periods=3).sum() if len(ser) else ser
                v=roll.get(when,np.nan) if hasattr(roll,"get") else np.nan
            else:
                v=np.nan
        else:
            section,_=long_slice(period)
            if hazard=="Heatwave": key=f"{section}_temp"
            elif hazard in ("Flood – rainfall","Drought / dry anomaly"): key=f"{section}_precip"
            else: key=None
            ser=x.get(key,pd.Series(dtype=float)) if key else pd.Series(dtype=float)
            v=ser.get(when,np.nan) if hasattr(ser,"get") else np.nan
        vals.append(float(v) if pd.notna(v) else np.nan)
    out["value"]=vals
    return out


def _time_specific_label(horizon,hazard,when):
    d=pd.Timestamp(when)
    if horizon in ("Short range","Medium range"):
        metric="Daily Tmax" if hazard=="Heatwave" else "3-day precipitation ending"
        return f"{metric} · {d.strftime('%d %b %Y')} · UTC"
    section="week" if horizon=="Sub-seasonal" else "month"
    if section=="week":
        return f"Weekly anomaly · {d.strftime('%d %b')}–{(d+pd.Timedelta(days=6)).strftime('%d %b %Y')} · UTC"
    return f"Monthly anomaly · {d.strftime('%B %Y')}"


# ---------------------------------------------------------------------------
# Focus GloFAS
# ---------------------------------------------------------------------------
@st.cache_data(ttl=86400,show_spinner=False)
def select_glofas_cell(seed_lat,seed_lon):
    offsets=[-.10,-.05,0,.05,.10]
    cand=[(seed_lat+dy,seed_lon+dx) for dy in offsets for dx in offsets]
    params={
        "latitude":",".join(f"{a:.5f}" for a,b in cand),
        "longitude":",".join(f"{b:.5f}" for a,b in cand),
        "daily":"river_discharge_mean","forecast_days":10,"cell_selection":"nearest",
    }
    x,status=cached_json(FLOOD_URL,params,86400,100)
    arr=x if isinstance(x,list) else [x]
    rows=[]
    for req,p in zip(cand,arr):
        s=value_series(p,"daily","river_discharge_mean")
        rows.append({"used_lat":float(p.get("latitude",req[0])),"used_lon":float(p.get("longitude",req[1])),
                     "score":float(s.median()) if len(s.dropna()) else -np.inf})
    return max(rows,key=lambda z:z["score"]),status


@st.cache_data(ttl=10800,show_spinner=False)
def focus_glofas(lat,lon):
    params={"latitude":float(lat),"longitude":float(lon),"daily":"river_discharge",
            "forecast_days":210,"ensemble":"true","cell_selection":"nearest"}
    x,status=cached_json(FLOOD_URL,params,10800,100)
    return member_frame(x,"daily","river_discharge"),status


@st.cache_data(ttl=2592000,show_spinner=False)
def focus_glofas_history(lat,lon):
    params={"latitude":float(lat),"longitude":float(lon),"start_date":"1984-01-01","end_date":"2021-12-31",
            "daily":"river_discharge","cell_selection":"nearest"}
    x,status=cached_json(FLOOD_URL,params,2592000,100)
    d=x.get("daily",{})
    return pd.DataFrame({"date":pd.to_datetime(d.get("time",[]),errors="coerce"),
                         "q":pd.to_numeric(pd.Series(d.get("river_discharge",[])),errors="coerce")}).dropna(),status


def q_levels(hist):
    if hist.empty:return {}
    x=hist.copy();x["year"]=x.date.dt.year
    annual=x.groupby("year").q.max().dropna().to_numpy()
    if len(annual)<15:return {}
    try:
        c,loc,scale=genextreme.fit(annual)
        return {rp:float(genextreme.ppf(1-1/rp,c,loc=loc,scale=scale)) for rp in (2,5,10,20,50,100)}
    except Exception:
        return {rp:float(np.quantile(annual,1-1/rp)) for rp in (2,5,10,20,50,100)}


def exceed_prob(q,threshold,s,e):
    if q.empty or not np.isfinite(threshold):return np.nan
    b=q.iloc[s:min(e,len(q))]
    return 100*float(np.mean([(b[c]>threshold).any() for c in b.columns])) if len(b) else np.nan


# ---------------------------------------------------------------------------
# Return-period forecast translation for SDM hand-off
# ---------------------------------------------------------------------------
@st.cache_data(ttl=2592000, show_spinner=False)
def focus_extreme_history(lat, lon):
    """
    Historical ERA5 daily Tmax / precipitation used only to define local
    extreme-value return levels. This is separate from the forecast itself.
    """
    params = {
        "latitude": round(float(lat), 5),
        "longitude": round(float(lon), 5),
        "start_date": "1981-01-01",
        "end_date": "2014-12-31",
        "daily": "temperature_2m_max,precipitation_sum",
        "models": "era5",
        "timezone": "UTC",
    }
    x, status = cached_json(ARCHIVE_URL, params, 2592000, 100)
    d = x.get("daily", {})
    df = pd.DataFrame({
        "date": pd.to_datetime(d.get("time", []), errors="coerce"),
        "tmax": pd.to_numeric(pd.Series(d.get("temperature_2m_max", [])), errors="coerce"),
        "precip": pd.to_numeric(pd.Series(d.get("precipitation_sum", [])), errors="coerce"),
    }).dropna(subset=["date"])
    return df, status


def gev_levels_from_annual(annual, rps=(2,5,10,20,50,100)):
    x = pd.to_numeric(pd.Series(annual), errors="coerce").dropna().to_numpy()
    if len(x) < 15:
        return {}
    try:
        c, loc, scale = genextreme.fit(x)
        return {rp: float(genextreme.ppf(1 - 1/rp, c, loc=loc, scale=scale)) for rp in rps}
    except Exception:
        return {rp: float(np.quantile(x, 1 - 1/rp)) for rp in rps}


def heat_return_levels_from_history(df):
    """
    Heat return-period severity metric:
    annual maximum of the 3-day running mean of daily Tmax (TX3d).
    This complements, rather than replaces, the REACH heatwave trigger
    Tmax > local TX90 for >=3 consecutive days.
    """
    vals = []
    x = df.dropna(subset=["date", "tmax"]).copy()
    x["year"] = x["date"].dt.year
    for _, g in x.groupby("year"):
        z = g.sort_values("date")["tmax"].rolling(3, min_periods=3).mean()
        if z.notna().any():
            vals.append(float(z.max()))
    return gev_levels_from_annual(vals)


def rainfall_1day_return_levels_from_history(df):
    """Annual maximum 1-day precipitation return levels, in mm/day."""
    vals=[]
    x=df.dropna(subset=["date","precip"]).copy()
    x["year"]=x["date"].dt.year
    for _,g in x.groupby("year"):
        z=g.sort_values("date")["precip"]
        if z.notna().any(): vals.append(float(z.max()))
    return gev_levels_from_annual(vals)


def ensemble_peak_1day_precip(p,s,e):
    """Maximum daily precipitation in the selected forecast window, per ensemble member."""
    if p.empty: return pd.Series(dtype=float)
    z=p.iloc[s:e]
    if z.empty: return pd.Series(dtype=float)
    return z.max(axis=0,skipna=True).dropna()


def return_period_threshold_table(levels,rp_result,unit,metric_name):
    rows=[]
    for rp in (2,5,10,20,50,100):
        rows.append({
            "Return period (years)":rp,
            "Annual exceedance probability (%)":100.0/rp,
            "Non-exceedance quantile F":1.0-1.0/rp,
            "Return-level value":levels.get(rp,np.nan),
            "Unit":unit,
            "Forecast P(exceed threshold) (%)":rp_result.get("prob_exceed",{}).get(rp,np.nan),
            "Metric":metric_name,
            "Stella variable":f"RL_RP{rp}",
        })
    return pd.DataFrame(rows)


def rainfall_return_levels_from_history(df):
    """
    Rainfall-rarity proxy for rapid/pluvial flood settings:
    annual maximum 3-day accumulated rainfall.
    It must not be labelled a physical flood return period until a hydrologic
    model converts rainfall to runoff/discharge/depth.
    """
    vals = []
    x = df.dropna(subset=["date", "precip"]).copy()
    x["year"] = x["date"].dt.year
    for _, g in x.groupby("year"):
        z = g.sort_values("date")["precip"].rolling(3, min_periods=3).sum()
        if z.notna().any():
            vals.append(float(z.max()))
    return gev_levels_from_annual(vals)


def ensemble_peak_metric(t, p, metric, s, e):
    if metric == "heat_tx3d":
        if t.empty:
            return pd.Series(dtype=float)
        z = t.rolling(3, min_periods=3).mean().iloc[max(0, s):e]
    else:
        if p.empty:
            return pd.Series(dtype=float)
        z = p.rolling(3, min_periods=3).sum().iloc[max(0, s):e]
    if z.empty:
        return pd.Series(dtype=float)
    return z.max(axis=0, skipna=True).dropna()


def return_period_forecast(peaks, levels):
    """
    Ensemble probability of exceeding each historical return level and
    a probability-weighted severity index for Stella/SDM.
    """
    peaks = pd.to_numeric(pd.Series(peaks), errors="coerce").dropna()
    if peaks.empty or not levels:
        return {}
    probs = {rp: 100.0 * float((peaks >= level).mean()) for rp, level in levels.items()}

    p2 = probs.get(2, np.nan) / 100
    p5 = probs.get(5, np.nan) / 100
    p10 = probs.get(10, np.nan) / 100
    p20 = probs.get(20, np.nan) / 100

    if all(np.isfinite(v) for v in (p2, p5, p10, p20)):
        classes = {
            "<2 y": max(0.0, 1 - p2),
            "2–5 y": max(0.0, p2 - p5),
            "5–10 y": max(0.0, p5 - p10),
            "10–20 y": max(0.0, p10 - p20),
            "≥20 y": max(0.0, p20),
        }
        total = sum(classes.values())
        if total > 0:
            classes = {k: v / total for k, v in classes.items()}
        weights = {"<2 y":0.0, "2–5 y":0.25, "5–10 y":0.50, "10–20 y":0.75, "≥20 y":1.0}
        severity = sum(classes[k] * weights[k] for k in classes)
        dominant = max(classes, key=classes.get)
    else:
        classes, severity, dominant = {}, np.nan, "Unavailable"

    return {
        "prob_exceed": probs,
        "classes": classes,
        "severity_index": severity,
        "dominant_class": dominant,
        "p50": float(peaks.quantile(.50)),
        "p90": float(peaks.quantile(.90)),
        "p10": float(peaks.quantile(.10)),
        "ensemble_max": float(peaks.max()),
    }


def sdm_rp_row(country, focus, hazard, horizon, period, rp_kind, rp, trigger_rp, trigger_probability, unit, levels=None, valid_start=None, valid_end=None):
    p_action = rp.get("prob_exceed", {}).get(trigger_rp, np.nan)
    return pd.DataFrame([{
        "Country": country,
        "Area": focus,
        "Hazard": hazard,
        "ForecastHorizon": horizon,
        "ValidPeriod": period,
        "ValidStart": fmt_dt(valid_start, horizon in ("Short range","Medium range")) if valid_start is not None else "",
        "ValidEnd": fmt_dt(valid_end, horizon in ("Short range","Medium range")) if valid_end is not None else "",
        "ReturnPeriodMetric": rp_kind,
        "DominantRPClass": rp.get("dominant_class", "Unavailable"),
        "ForecastSeverityIndex_0_1": rp.get("severity_index", np.nan),
        "P_GE_RP2_pct": rp.get("prob_exceed", {}).get(2, np.nan),
        "P_GE_RP5_pct": rp.get("prob_exceed", {}).get(5, np.nan),
        "P_GE_RP10_pct": rp.get("prob_exceed", {}).get(10, np.nan),
        "P_GE_RP20_pct": rp.get("prob_exceed", {}).get(20, np.nan),
        "P_GE_RP50_pct": rp.get("prob_exceed", {}).get(50, np.nan),
        "P_GE_RP100_pct": rp.get("prob_exceed", {}).get(100, np.nan),
        "RL_RP2": (levels or {}).get(2, np.nan),
        "RL_RP5": (levels or {}).get(5, np.nan),
        "RL_RP10": (levels or {}).get(10, np.nan),
        "RL_RP20": (levels or {}).get(20, np.nan),
        "RL_RP50": (levels or {}).get(50, np.nan),
        "RL_RP100": (levels or {}).get(100, np.nan),
        "ReturnLevelUnit": unit,
        "ActionTriggerRP_years": trigger_rp,
        "ActionProbability_pct": p_action,
        "ActionProbabilityThreshold_pct": trigger_probability,
        "EarlyWarningTrigger": int(np.isfinite(p_action) and p_action >= trigger_probability),
        "PhysicalP10": rp.get("p10", np.nan),
        "PhysicalP50": rp.get("p50", np.nan),
        "PhysicalP90": rp.get("p90", np.nan),
        "PhysicalUnit": unit,
    }])


# ---------------------------------------------------------------------------
# Forecast verification / hindcast reconstruction — REACH pilot sites only
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def verification_pilot_sites():
    """Return the four REACH pilot locations only."""
    z = pd.read_csv(ZAMBIA_POINTS, dtype={"DIST_CODE": str})
    z = z.rename(columns={"DISTRICT":"REGION_NAME","PROVINCE":"ADMIN1"})
    z["Country"] = "Zambia"

    b = pd.read_csv(BRAZIL_POINTS, dtype={"REGION_CODE": str})
    b["Country"] = "Brazil"

    keep_z = z[z["REGION_NAME"].isin(["Senanga","Sinazongwe"])][
        ["Country","REGION_NAME","ADMIN1","rep_lat","rep_lon"]
    ]
    keep_b = b[b["REGION_NAME"].isin(["Recife","Palmares"])][
        ["Country","REGION_NAME","ADMIN1","rep_lat","rep_lon"]
    ]
    out = pd.concat([keep_z, keep_b], ignore_index=True)
    out["Site"] = out["Country"] + " · " + out["REGION_NAME"]
    order = ["Zambia · Senanga","Zambia · Sinazongwe","Brazil · Recife","Brazil · Palmares"]
    out["__order"] = out["Site"].map({x:i for i,x in enumerate(order)})
    return out.sort_values("__order").drop(columns="__order").reset_index(drop=True)



@st.cache_data(ttl=31536000, show_spinner=False)
def archived_model_run_daily(lat, lon, run_date_iso, model_label):
    """
    Retrieve an archived operational model run at 00 UTC from Open-Meteo Single Runs.
    The daily verification suite includes Tmin, Tmean, Tmax and precipitation.
    """
    if model_label == "ECMWF IFS HRES":
        model_candidates = ["ecmwf_ifs"]
        max_days = 10
    else:
        model_candidates = ["gfs_seamless", "ncep_gfs025"]
        max_days = 11

    last_exc = None
    for model_id in model_candidates:
        for fd in (max_days, 10):
            params = {
                "latitude": round(float(lat),5),
                "longitude": round(float(lon),5),
                "run": f"{run_date_iso}T00:00",
                "models": model_id,
                "daily": "temperature_2m_min,temperature_2m_mean,temperature_2m_max,precipitation_sum",
                "forecast_days": int(fd),
                "timezone": "UTC",
            }
            try:
                x, status = cached_json(SINGLE_RUNS_URL, params, 31536000, 100)
                d = x.get("daily", {}) if isinstance(x, dict) else {}
                out = pd.DataFrame({
                    "date": pd.to_datetime(d.get("time", []), errors="coerce"),
                    "tmin": pd.to_numeric(pd.Series(d.get("temperature_2m_min", [])), errors="coerce"),
                    "tmean": pd.to_numeric(pd.Series(d.get("temperature_2m_mean", [])), errors="coerce"),
                    "tmax": pd.to_numeric(pd.Series(d.get("temperature_2m_max", [])), errors="coerce"),
                    "precip": pd.to_numeric(pd.Series(d.get("precipitation_sum", [])), errors="coerce"),
                }).dropna(subset=["date"])
                if not out.empty:
                    return out, f"{status} · {model_id}"
            except Exception as exc:
                last_exc = exc
    if last_exc:
        raise last_exc
    raise RuntimeError(f"{model_label} archived run unavailable")


@st.cache_data(ttl=31536000, show_spinner=False)
def archived_ifs_run_daily(lat, lon, run_date_iso):
    return archived_model_run_daily(lat, lon, run_date_iso, "ECMWF IFS HRES")


@st.cache_data(ttl=31536000, show_spinner=False)
def archived_gfs_run_daily(lat, lon, run_date_iso):
    return archived_model_run_daily(lat, lon, run_date_iso, "NOAA GFS")


@st.cache_data(ttl=31536000, show_spinner=False)
def verification_reference_daily(lat, lon, start_date_iso, end_date_iso):
    """ERA5 reference used only as the verifying historical state."""
    params = {
        "latitude": round(float(lat),5),
        "longitude": round(float(lon),5),
        "start_date": start_date_iso,
        "end_date": end_date_iso,
        "daily": "temperature_2m_min,temperature_2m_mean,temperature_2m_max,precipitation_sum",
        "models": "era5",
        "timezone": "UTC",
    }
    x, status = cached_json(ARCHIVE_URL, params, 31536000, 100)
    d = x.get("daily", {}) if isinstance(x, dict) else {}
    return pd.DataFrame({
        "date": pd.to_datetime(d.get("time", []), errors="coerce"),
        "tmin": pd.to_numeric(pd.Series(d.get("temperature_2m_min", [])), errors="coerce"),
        "tmean": pd.to_numeric(pd.Series(d.get("temperature_2m_mean", [])), errors="coerce"),
        "tmax": pd.to_numeric(pd.Series(d.get("temperature_2m_max", [])), errors="coerce"),
        "precip": pd.to_numeric(pd.Series(d.get("precipitation_sum", [])), errors="coerce"),
    }).dropna(subset=["date"]), status


@st.cache_data(ttl=2592000, show_spinner=False)
def verification_climatology(lat, lon):
    """
    Local monthly percentile thresholds from ERA5 1981–2014.
    TX percentiles use daily Tmax. Rain percentiles are provided for both
    1-day precipitation and rolling 3-day precipitation.
    """
    params = {
        "latitude": round(float(lat),5),
        "longitude": round(float(lon),5),
        "start_date": "1981-01-01",
        "end_date": "2014-12-31",
        "daily": "temperature_2m_min,temperature_2m_mean,temperature_2m_max,precipitation_sum",
        "models": "era5",
        "timezone": "UTC",
    }
    x, status = cached_json(ARCHIVE_URL, params, 2592000, 100)
    d = x.get("daily", {})
    df = pd.DataFrame({
        "date": pd.to_datetime(d.get("time", []), errors="coerce"),
        "tmin": pd.to_numeric(pd.Series(d.get("temperature_2m_min", [])), errors="coerce"),
        "tmean": pd.to_numeric(pd.Series(d.get("temperature_2m_mean", [])), errors="coerce"),
        "tmax": pd.to_numeric(pd.Series(d.get("temperature_2m_max", [])), errors="coerce"),
        "precip": pd.to_numeric(pd.Series(d.get("precipitation_sum", [])), errors="coerce"),
    }).dropna(subset=["date"])
    df = df.sort_values("date")
    df["month"] = df["date"].dt.month
    df["rain3"] = df["precip"].rolling(3, min_periods=3).sum()

    out = {"status": status}
    for pct in (90,95,99):
        q = pct/100.0
        out[f"TX{pct}"] = df.groupby("month")["tmax"].quantile(q).to_dict()
        out[f"P1D{pct}"] = df.groupby("month")["precip"].quantile(q).to_dict()
        out[f"P3D{pct}"] = df.groupby("month")["rain3"].quantile(q).to_dict()
    return out


def verification_threshold_table(lat, lon, event_date):
    clim = verification_climatology(lat, lon)
    m = int(pd.Timestamp(event_date).month)
    rows = []
    for pct in (90,95,99):
        rows.extend([
            {
                "Hazard family":"Heat",
                "Threshold":f"TX{pct}",
                "Definition":f"{pct}th percentile of daily Tmax for the event month",
                "Value":clim.get(f"TX{pct}",{}).get(m,np.nan),
                "Unit":"°C",
                "Use":("Primary REACH heatwave threshold" if pct==90 else "Sensitivity / severity comparison")
            },
            {
                "Hazard family":"Precipitation",
                "Threshold":f"P{pct} · 1-day",
                "Definition":f"{pct}th percentile of daily precipitation for the event month",
                "Value":clim.get(f"P1D{pct}",{}).get(m,np.nan),
                "Unit":"mm/day",
                "Use":"Daily heavy-rain comparison"
            },
            {
                "Hazard family":"Precipitation",
                "Threshold":f"P{pct} · 3-day",
                "Definition":f"{pct}th percentile of rolling 3-day precipitation for the event month",
                "Value":clim.get(f"P3D{pct}",{}).get(m,np.nan),
                "Unit":"mm / 3 days",
                "Use":("Primary 3-day heavy-rain screen" if pct==95 else "Sensitivity / severity comparison")
            },
        ])
    return pd.DataFrame(rows), clim


def _value_on_date(df, date_ts, col):
    if df.empty or col not in df:
        return np.nan
    x = df[df["date"].dt.normalize() == pd.Timestamp(date_ts).normalize()]
    if x.empty:
        return np.nan
    return float(x.iloc[0][col]) if pd.notna(x.iloc[0][col]) else np.nan


def _three_day_values(df, end_date, col):
    dates = pd.date_range(pd.Timestamp(end_date)-pd.Timedelta(days=2), pd.Timestamp(end_date), freq="D")
    vals = [_value_on_date(df, d, col) for d in dates]
    return dates, vals


def _consecutive_true(values, thresholds):
    if len(values) != len(thresholds):
        return False
    return all(np.isfinite(v) and np.isfinite(t) and v > t for v,t in zip(values,thresholds))


def verification_suite_from_hazard(hazard_name):
    heat_cont = [
        "Daily minimum temperature",
        "Daily mean temperature",
        "Daily maximum temperature",
        "3-day mean Tmax",
    ]
    heat_evt = [
        "Heatwave TX90 · 3 consecutive days",
        "Heatwave TX95 · 3 consecutive days",
        "Heatwave TX99 · 3 consecutive days",
    ]
    rain_cont = [
        "Daily precipitation",
        "3-day precipitation total",
        "3-day mean daily precipitation",
        "3-day maximum daily precipitation",
    ]
    rain_evt = [
        "3-day precipitation > P90",
        "3-day precipitation > P95",
        "3-day precipitation > P99",
    ]

    if hazard_name == "Heatwave":
        return heat_cont, heat_evt
    if hazard_name in ("Flood – rainfall","Flood – river discharge (GloFAS)"):
        return rain_cont, rain_evt
    if hazard_name == "Compound – Flood + Heatwave":
        return heat_cont + rain_cont, heat_evt + rain_evt
    if hazard_name == "Compound – Drought + Heatwave":
        return heat_cont + rain_cont, heat_evt
    return rain_cont, rain_evt


def verification_metric_from_hazard(hazard_name):
    """Short label retained for automatic header linkage."""
    continuous, events = verification_suite_from_hazard(hazard_name)
    if hazard_name == "Heatwave":
        return "Temperature + TX90/TX95/TX99"
    if hazard_name == "Flood – river discharge (GloFAS)":
        return "Rainfall precursor + GloFAS discharge diagnostics"
    if hazard_name == "Flood – rainfall":
        return "Precipitation + P90/P95/P99"
    if hazard_name == "Compound – Flood + Heatwave":
        return "Heat + precipitation indicator suite"
    return "Precipitation indicator suite"


def verification_leads_from_horizon(horizon_name):
    if horizon_name == "Short range":
        return (1,3)
    if horizon_name == "Medium range":
        return (4,7,10)
    return (1,3,5,7,10)


def _metric_threshold(metric, clim, event_ts):
    month = int(pd.Timestamp(event_ts).month)
    m = re.search(r"(90|95|99)", metric)
    if not m:
        return np.nan, "", ""
    pct = int(m.group(1))
    if metric.startswith("Heatwave"):
        return clim.get(f"TX{pct}",{}).get(month,np.nan), "°C", f"TX{pct}"
    return clim.get(f"P3D{pct}",{}).get(month,np.nan), "mm / 3 days", f"P{pct} · 3-day"


def build_pilot_hindcast(site_row, event_date, metric, model_label="ECMWF IFS HRES", lead_days=(1,3,5,7,10)):
    """
    Event-specific reconstruction for one operational model.
    Continuous metrics compare numerical values. Event metrics additionally
    classify Hit / Miss / False alarm / Correct negative.
    """
    lat = float(site_row["rep_lat"])
    lon = float(site_row["rep_lon"])
    event_ts = pd.Timestamp(event_date).normalize()
    start_ref = event_ts - pd.Timedelta(days=2)

    reference, ref_status = verification_reference_daily(
        lat, lon, start_ref.strftime("%Y-%m-%d"), event_ts.strftime("%Y-%m-%d")
    )
    clim = verification_climatology(lat, lon)

    win_dates, obs_tmax3 = _three_day_values(reference, event_ts, "tmax")
    _, obs_p3 = _three_day_values(reference, event_ts, "precip")

    obs = {
        "Daily minimum temperature": _value_on_date(reference,event_ts,"tmin"),
        "Daily mean temperature": _value_on_date(reference,event_ts,"tmean"),
        "Daily maximum temperature": _value_on_date(reference,event_ts,"tmax"),
        "3-day mean Tmax": float(np.nanmean(obs_tmax3)) if np.isfinite(obs_tmax3).any() else np.nan,
        "Daily precipitation": _value_on_date(reference,event_ts,"precip"),
        "3-day precipitation total": float(np.nansum(obs_p3)) if np.isfinite(obs_p3).any() else np.nan,
        "3-day mean daily precipitation": float(np.nanmean(obs_p3)) if np.isfinite(obs_p3).any() else np.nan,
        "3-day maximum daily precipitation": float(np.nanmax(obs_p3)) if np.isfinite(obs_p3).any() else np.nan,
    }

    threshold_value, threshold_unit, threshold_label = _metric_threshold(metric, clim, event_ts)

    # Reference event classification for threshold metrics.
    if metric.startswith("Heatwave"):
        pct = int(re.search(r"(90|95|99)",metric).group(1))
        th = [clim.get(f"TX{pct}",{}).get(int(pd.Timestamp(d).month),np.nan) for d in win_dates]
        obs_event = _consecutive_true(obs_tmax3, th)
        obs_value = obs["3-day mean Tmax"]
        value_unit = "°C (3-day mean Tmax)"
    elif metric.startswith("3-day precipitation >"):
        obs_event = bool(np.isfinite(obs["3-day precipitation total"]) and np.isfinite(threshold_value)
                         and obs["3-day precipitation total"] > threshold_value)
        obs_value = obs["3-day precipitation total"]
        value_unit = "mm / 3 days"
    else:
        obs_event = None
        obs_value = obs.get(metric,np.nan)
        value_unit = (
            "°C" if "temperature" in metric.lower() or "Tmax" in metric
            else ("mm / 3 days" if metric=="3-day precipitation total"
                  else "mm/day")
        )

    rows=[]
    for lead in lead_days:
        run_date = event_ts - pd.Timedelta(days=int(lead))
        try:
            fc,status = archived_model_run_daily(lat,lon,run_date.strftime("%Y-%m-%d"),model_label)
            archive_status=status
        except Exception as exc:
            rows.append({
                "Model":model_label,"LeadTimeDays":int(lead),
                "RunInitialisationUTC":f"{run_date.strftime('%Y-%m-%d')} 00:00",
                "Metric":metric,"ForecastValue":np.nan,"ReferenceValue":obs_value,"Unit":value_unit,
                "ThresholdLabel":threshold_label,"ThresholdValue":threshold_value,"ThresholdUnit":threshold_unit,
                "ErrorForecastMinusReference":np.nan,"AbsoluteError":np.nan,
                "ForecastEvent":"","ObservedEvent":("" if obs_event is None else ("Yes" if obs_event else "No")),
                "VerificationOutcome":"Archive unavailable","DataComposition":"","ArchiveStatus":str(exc)
            })
            continue

        fwin_dates, ftmax3 = _three_day_values(fc,event_ts,"tmax")
        _, fp3 = _three_day_values(fc,event_ts,"precip")

        # For 3-day metrics at 1-day lead, incorporate already observed antecedent dates.
        def mixed_three_day(col):
            vals=[]; used_obs=0
            for d in win_dates:
                if pd.Timestamp(d).normalize() < run_date.normalize():
                    vals.append(_value_on_date(reference,d,col)); used_obs+=1
                else:
                    vals.append(_value_on_date(fc,d,col))
            return vals,used_obs

        if metric == "Daily minimum temperature":
            fv=_value_on_date(fc,event_ts,"tmin"); used_obs=0
        elif metric == "Daily mean temperature":
            fv=_value_on_date(fc,event_ts,"tmean"); used_obs=0
        elif metric == "Daily maximum temperature":
            fv=_value_on_date(fc,event_ts,"tmax"); used_obs=0
        elif metric == "3-day mean Tmax":
            vals,used_obs=mixed_three_day("tmax")
            fv=float(np.nanmean(vals)) if np.isfinite(vals).any() else np.nan
        elif metric == "Daily precipitation":
            fv=_value_on_date(fc,event_ts,"precip"); used_obs=0
        elif metric == "3-day precipitation total":
            vals,used_obs=mixed_three_day("precip")
            fv=float(np.nansum(vals)) if np.isfinite(vals).any() else np.nan
        elif metric == "3-day mean daily precipitation":
            vals,used_obs=mixed_three_day("precip")
            fv=float(np.nanmean(vals)) if np.isfinite(vals).any() else np.nan
        elif metric == "3-day maximum daily precipitation":
            vals,used_obs=mixed_three_day("precip")
            fv=float(np.nanmax(vals)) if np.isfinite(vals).any() else np.nan
        elif metric.startswith("Heatwave"):
            vals,used_obs=mixed_three_day("tmax")
            pct=int(re.search(r"(90|95|99)",metric).group(1))
            th=[clim.get(f"TX{pct}",{}).get(int(pd.Timestamp(d).month),np.nan) for d in win_dates]
            fv=float(np.nanmean(vals)) if np.isfinite(vals).any() else np.nan
            fc_event=_consecutive_true(vals,th)
        elif metric.startswith("3-day precipitation >"):
            vals,used_obs=mixed_three_day("precip")
            fv=float(np.nansum(vals)) if np.isfinite(vals).any() else np.nan
            fc_event=bool(np.isfinite(fv) and np.isfinite(threshold_value) and fv>threshold_value)
        else:
            fv=np.nan; used_obs=0

        if metric.startswith("Heatwave") or metric.startswith("3-day precipitation >"):
            fe=fc_event; oe=obs_event
            fe_txt="Yes" if fe else "No"; oe_txt="Yes" if oe else "No"
            if fe and oe: outcome="Hit"
            elif (not fe) and oe: outcome="Miss"
            elif fe and (not oe): outcome="False alarm"
            else: outcome="Correct negative"
        else:
            fe_txt=oe_txt=outcome=""

        err=fv-obs_value if np.isfinite(fv) and np.isfinite(obs_value) else np.nan
        composition=(
            f"Archived {model_label} forecast"
            if used_obs==0 else
            f"Observed antecedent ({used_obs} d) + archived {model_label}"
        )

        rows.append({
            "Model":model_label,"LeadTimeDays":int(lead),
            "RunInitialisationUTC":f"{run_date.strftime('%Y-%m-%d')} 00:00",
            "Metric":metric,"ForecastValue":fv,"ReferenceValue":obs_value,"Unit":value_unit,
            "ThresholdLabel":threshold_label,"ThresholdValue":threshold_value,"ThresholdUnit":threshold_unit,
            "ErrorForecastMinusReference":err,
            "AbsoluteError":abs(err) if np.isfinite(err) else np.nan,
            "ForecastEvent":fe_txt,"ObservedEvent":oe_txt,"VerificationOutcome":outcome,
            "DataComposition":composition,"ArchiveStatus":archive_status
        })

    return pd.DataFrame(rows), {
        "reference_status":ref_status,
        "climatology":clim,
        "threshold_value":threshold_value,
        "threshold_label":threshold_label,
        "threshold_unit":threshold_unit,
    }


def current_glofas_verification_context(country, site_name, horizon_name, period_name):
    """
    Current hydrological forecast diagnostics for riverine pilot sites.
    This is deliberately labelled as current forecast context, not a historical hindcast.
    """
    pilot=PILOT.get((country,site_name))
    if not pilot:
        return pd.DataFrame(),pd.DataFrame(),{}
    seed_lat=pilot.get("river_seed_lat")
    seed_lon=pilot.get("river_seed_lon")
    if seed_lat is None or seed_lon is None:
        return pd.DataFrame(),pd.DataFrame(),{}

    best,_=select_glofas_cell(seed_lat,seed_lon)
    q,_=focus_glofas(best["used_lat"],best["used_lon"])
    hist,_=focus_glofas_history(best["used_lat"],best["used_lon"])
    levels=q_levels(hist)
    s,e=discharge_slice(horizon_name,period_name)
    b=q.iloc[s:min(e,len(q))]
    if b.empty:
        return pd.DataFrame(),pd.DataFrame(),best

    peaks=b.max(axis=0,skipna=True).dropna()
    stats=pd.DataFrame([
        ["Minimum ensemble peak",peaks.min(),"m³/s"],
        ["P10 ensemble peak",peaks.quantile(.10),"m³/s"],
        ["P25 ensemble peak",peaks.quantile(.25),"m³/s"],
        ["Mean ensemble peak",peaks.mean(),"m³/s"],
        ["Median / P50 ensemble peak",peaks.median(),"m³/s"],
        ["P75 ensemble peak",peaks.quantile(.75),"m³/s"],
        ["P90 ensemble peak",peaks.quantile(.90),"m³/s"],
        ["Maximum ensemble peak",peaks.max(),"m³/s"],
    ],columns=["Discharge indicator","Value","Unit"])

    rprows=[]
    for rp in (2,5,10,20,50,100):
        th=levels.get(rp,np.nan)
        rprows.append({
            "Return period (years)":rp,
            "Return-level discharge":th,
            "Unit":"m³/s",
            "Current forecast P(exceed) (%)":exceed_prob(q,th,s,e)
        })
    return stats,pd.DataFrame(rprows),best

def verification_skill_summary(df):
    """Goodness-of-fit / error summary for one model and one selected historical event."""
    x = df.copy()
    x["ForecastValue"] = pd.to_numeric(x["ForecastValue"], errors="coerce")
    x["ReferenceValue"] = pd.to_numeric(x["ReferenceValue"], errors="coerce")
    x = x[x["ForecastValue"].notna() & x["ReferenceValue"].notna()].copy()

    if x.empty:
        return {
            "MAE": np.nan, "RMSE": np.nan, "MeanBias": np.nan, "PercentBias": np.nan,
            "R2": np.nan, "R2Note": "No paired values", "BestLeadDays": np.nan,
            "Hits": 0, "Misses": 0, "FalseAlarms": 0, "CorrectNegatives": 0,
            "POD": np.nan, "FAR": np.nan, "Accuracy": np.nan
        }

    err = x["ForecastValue"] - x["ReferenceValue"]
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(np.square(err))))
    bias = float(np.mean(err))
    denom = float(np.sum(np.abs(x["ReferenceValue"])))
    pbias = float(100*np.sum(err)/denom) if denom > 0 else np.nan

    # R² is only meaningful when the verifying reference varies.
    obs = x["ReferenceValue"].to_numpy(float)
    pred = x["ForecastValue"].to_numpy(float)
    if len(obs) >= 2 and np.nanvar(obs) > 0:
        ss_res = float(np.nansum((obs-pred)**2))
        ss_tot = float(np.nansum((obs-np.nanmean(obs))**2))
        r2 = 1 - ss_res/ss_tot if ss_tot > 0 else np.nan
        r2_note = "Calculated"
    else:
        r2 = np.nan
        r2_note = "N/A for one event: the reference value is constant across lead times"

    outcomes = x["VerificationOutcome"].replace("", np.nan).dropna()
    hit = int((outcomes=="Hit").sum())
    miss = int((outcomes=="Miss").sum())
    fa = int((outcomes=="False alarm").sum())
    cn = int((outcomes=="Correct negative").sum())
    pod = 100*hit/(hit+miss) if (hit+miss) else np.nan
    far = 100*fa/(hit+fa) if (hit+fa) else np.nan
    acc = 100*(hit+cn)/len(outcomes) if len(outcomes) else np.nan

    best = x.loc[x["AbsoluteError"].idxmin()] if x["AbsoluteError"].notna().any() else None

    return {
        "MAE": mae,
        "RMSE": rmse,
        "MeanBias": bias,
        "PercentBias": pbias,
        "R2": r2,
        "R2Note": r2_note,
        "BestLeadDays": np.nan if best is None else float(best["LeadTimeDays"]),
        "Hits": hit,
        "Misses": miss,
        "FalseAlarms": fa,
        "CorrectNegatives": cn,
        "POD": pod,
        "FAR": far,
        "Accuracy": acc,
    }


def confusion_matrix_explanation():
    """Plain-language verification terminology shown in Documentation and Verification tabs."""
    return pd.DataFrame([
        ["Yes","Yes","Hit","True positive",
         "The forecast warned and the event occurred.",
         "Desired detection: preparedness was activated for a real event."],
        ["No","Yes","Miss","False negative",
         "The forecast did not warn, but the event occurred.",
         "Potentially serious for health preparedness because the system may be unprepared."],
        ["Yes","No","False alarm","False positive",
         "The forecast warned, but the event did not occur.",
         "May cause unnecessary action/cost; some false alarms can be acceptable if misses are costly."],
        ["No","No","Correct negative","True negative",
         "The forecast did not warn and no event occurred.",
         "Correctly avoided unnecessary activation."],
    ], columns=[
        "Forecast event","Observed event","Dashboard term","Statistical term",
        "Plain-language meaning","Early-warning interpretation"
    ])


# ---------------------------------------------------------------------------
# Climate drivers
# ---------------------------------------------------------------------------
@st.cache_data(ttl=43200,show_spinner=False)
def enso_table():
    r=requests.get(CPC_ENSO_URL,timeout=35,headers={"User-Agent":"REACH-EWS/FINAL-V5"});r.raise_for_status()
    for t in pd.read_html(StringIO(r.text)):
        x=t.copy();x.columns=[" ".join(map(str,c)).strip() if isinstance(c,tuple) else str(c) for c in x.columns]
        if "neutral" in " ".join(x.columns).lower() and "season" in " ".join(x.columns).lower():
            ren={}
            for c in x.columns:
                z=c.lower()
                if "season" in z:ren[c]="Season"
                elif "neutral" in z:ren[c]="Neutral"
                elif "niña" in z or "nina" in z:ren[c]="La Niña"
                elif "niño" in z or "nino" in z:ren[c]="El Niño"
            x=x.rename(columns=ren)
            keep=[c for c in ["Season","La Niña","Neutral","El Niño"] if c in x.columns];x=x[keep]
            for c in ["La Niña","Neutral","El Niño"]:
                if c in x:x[c]=pd.to_numeric(x[c].astype(str).str.replace("%","",regex=False),errors="coerce")
            return x.dropna(how="all")
    raise RuntimeError("ENSO table unavailable")


def parse_monthly_index_csv(text):
    df=pd.read_csv(StringIO(text))
    date_col=next((c for c in df.columns if "date" in str(c).lower()),None)
    if date_col:
        for c in df.columns:
            if c==date_col:continue
            v=pd.to_numeric(df[c],errors="coerce");valid=v[(v>-20)&(v<20)].dropna()
            if len(valid):
                i=valid.index[-1];return float(v.loc[i]),str(df.loc[i,date_col])
    years=pd.to_numeric(df.iloc[:,0],errors="coerce")
    rec=[]
    for i in range(len(df)):
        if not np.isfinite(years.iloc[i]):continue
        for m,c in enumerate(df.columns[1:13],1):
            v=pd.to_numeric(pd.Series([df.iloc[i][c]]),errors="coerce").iloc[0]
            if np.isfinite(v) and abs(v)<20:rec.append((int(years.iloc[i]),m,float(v)))
    if rec:
        y,m,v=rec[-1];return v,f"{y:04d}-{m:02d}"
    raise RuntimeError("Climate-index CSV could not be parsed")


@st.cache_data(ttl=43200,show_spinner=False)
def climate_index(url):
    r=requests.get(url,timeout=35,headers={"User-Agent":"REACH-EWS/FINAL-V5"});r.raise_for_status()
    return parse_monthly_index_csv(r.text)


# ---------------------------------------------------------------------------
# Seasonal climate-driver / anomaly visualisations
# ---------------------------------------------------------------------------

ENSO_STRENGTH_COLUMNS = [
    "Very strong La Niña","Strong La Niña","Moderate La Niña","Weak La Niña",
    "Neutral",
    "Weak El Niño","Moderate El Niño","Strong El Niño","Very strong El Niño",
]
ENSO_STRENGTH_COLORS = {
    "Very strong La Niña":"#172554","Strong La Niña":"#1E3A8A",
    "Moderate La Niña":"#2563EB","Weak La Niña":"#93C5FD",
    "Neutral":"#CBD5E1",
    "Weak El Niño":"#FCA5A5","Moderate El Niño":"#F97316",
    "Strong El Niño":"#DC2626","Very strong El Niño":"#7F1D1D",
}


def _flatten_html_columns(cols):
    out=[]
    for c in cols:
        if isinstance(c,tuple):
            out.append(" ".join(str(x) for x in c if str(x)!="nan").strip())
        else:
            out.append(str(c).strip())
    return out


@st.cache_data(ttl=43200,show_spinner=False)
def enso_strength_table():
    r=requests.get(CPC_ENSO_STRENGTH_URL,timeout=35,headers={"User-Agent":"REACH-EWS/FINAL"})
    r.raise_for_status()
    for t in pd.read_html(StringIO(r.text)):
        x=t.copy(); x.columns=_flatten_html_columns(x.columns)
        season_col=next((c for c in x.columns if "season" in c.lower()),x.columns[0])
        numeric=[]
        for c in x.columns:
            if c==season_col: continue
            v=pd.to_numeric(x[c].astype(str).str.replace("%","",regex=False),errors="coerce")
            if v.notna().sum()>=3: numeric.append(c)
        if len(numeric)>=9:
            y=x[[season_col]+numeric[:9]].copy()
            y.columns=["Season"]+ENSO_STRENGTH_COLUMNS
            for c in ENSO_STRENGTH_COLUMNS:
                y[c]=pd.to_numeric(y[c].astype(str).str.replace("%","",regex=False),errors="coerce")
            return y.dropna(how="all")
    raise RuntimeError("NOAA CPC ENSO strength table unavailable")


@st.cache_data(ttl=43200,show_spinner=False)
def enso_roni_outlook_table():
    r=requests.get(CPC_ENSO_OUTLOOK_URL,timeout=35,headers={"User-Agent":"REACH-EWS/FINAL"})
    r.raise_for_status()
    for t in pd.read_html(StringIO(r.text)):
        x=t.copy(); x.columns=_flatten_html_columns(x.columns)
        season_col=next((c for c in x.columns if "season" in c.lower()),x.columns[0])
        numeric=[]
        for c in x.columns:
            if c==season_col: continue
            v=pd.to_numeric(x[c],errors="coerce")
            if v.notna().sum()>=3: numeric.append(c)
        if len(numeric)>=7:
            y=x[[season_col]+numeric[:7]].copy()
            y.columns=["Season","P05","P15","P25","P50","P75","P85","P95"]
            for c in ["P05","P15","P25","P50","P75","P85","P95"]:
                y[c]=pd.to_numeric(y[c],errors="coerce")
            return y.dropna(how="all")
    raise RuntimeError("NOAA CPC RONI outlook table unavailable")


def enso_strength_class(v):
    if not np.isfinite(v): return "Unavailable"
    if v <= -2.0: return "Very strong La Niña"
    if v <= -1.5: return "Strong La Niña"
    if v <= -1.0: return "Moderate La Niña"
    if v <= -0.5: return "Weak La Niña"
    if v < 0.5: return "Neutral"
    if v < 1.0: return "Weak El Niño"
    if v < 1.5: return "Moderate El Niño"
    if v < 2.0: return "Strong El Niño"
    return "Very strong El Niño"


def _season_display_fields(x):
    def clean(v):
        s=str(v).strip().upper()
        m=re.search(r"(DJF|JFM|FMA|MAM|AMJ|MJJ|JJA|JAS|ASO|SON|OND|NDJ)",s)
        return m.group(1) if m else str(v).strip()
    out=x.copy()
    out["Season code"]=out["Season"].map(clean)
    out["Central month"]=out["Season code"].map(SEASON_CENTRAL_MONTH).fillna("")
    out["Display period"]=[f"{s} ({m})" if m else str(s) for s,m in zip(out["Season code"],out["Central month"])]
    return out


def enso_strength_figure(df):
    x=_season_display_fields(df)
    fig=go.Figure()
    for cat in ENSO_STRENGTH_COLUMNS:
        fig.add_trace(go.Bar(
            x=x["Display period"],y=x[cat],name=cat,
            marker_color=ENSO_STRENGTH_COLORS[cat],
            hovertemplate=f"{cat}: <b>%{{y:.1f}}%</b><extra></extra>"
        ))
    fig.update_layout(
        barmode="stack",height=430,margin=dict(l=20,r=10,t=55,b=25),
        title=dict(text="NOAA CPC ENSO strength probabilities",x=.01,xanchor="left",font=dict(size=17)),
        xaxis_title="3-month season (central month)",
        yaxis=dict(title="Probability (%)",range=[0,100]),
        legend=dict(orientation="h",y=1.16,x=0),hovermode="x unified"
    )
    return fig,x


def enso_roni_temporal_figure(df):
    x=_season_display_fields(df)
    y=pd.to_numeric(x["P50"],errors="coerce").to_numpy(float)
    pos=np.where(y>=0,y,np.nan); neg=np.where(y<0,y,np.nan)
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=x["Display period"],y=x["P25"],mode="lines",line=dict(width=0),showlegend=False,hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=x["Display period"],y=x["P75"],mode="lines",line=dict(width=0),
        fill="tonexty",fillcolor="rgba(148,163,184,.22)",name="25–75% RONI range",hoverinfo="skip"
    ))
    fig.add_trace(go.Scatter(
        x=x["Display period"],y=pos,mode="lines",line=dict(color="#B91C1C",width=1.4),
        fill="tozeroy",fillcolor="rgba(220,38,38,.72)",name="El Niño-side RONI"
    ))
    fig.add_trace(go.Scatter(
        x=x["Display period"],y=neg,mode="lines",line=dict(color="#1E3A8A",width=1.4),
        fill="tozeroy",fillcolor="rgba(30,58,138,.78)",name="La Niña-side RONI"
    ))
    classes=[enso_strength_class(v) for v in y]
    fig.add_trace(go.Scatter(
        x=x["Display period"],y=y,mode="lines+markers",line=dict(color="#111827",width=1.4),
        marker=dict(size=5,color="#111827"),
        customdata=np.stack([
            x["Central month"].astype(str),
            x["P25"].map(lambda v:f"{v:+.2f}" if pd.notna(v) else "—"),
            x["P75"].map(lambda v:f"{v:+.2f}" if pd.notna(v) else "—"),
            pd.Series(classes),
        ],axis=1),
        name="Median RONI",
        hovertemplate=(
            "<b>%{x}</b><br>Central month: %{customdata[0]}<br>"
            "Median RONI: <b>%{y:+.2f} °C</b><br>"
            "25–75% range: %{customdata[1]} to %{customdata[2]} °C<br>"
            "Strength class: <b>%{customdata[3]}</b><extra></extra>"
        )
    ))
    for level in [-2.0,-1.5,-1.0,-0.5,0.5,1.0,1.5,2.0]:
        fig.add_hline(y=level,line_width=.7,line_dash="dot",line_color="rgba(71,85,105,.35)")
    fig.add_hline(y=0,line_width=1.2,line_color="#111827")
    fig.update_layout(
        height=430,margin=dict(l=20,r=10,t=55,b=25),
        title=dict(text="Forecast RONI anomaly and ENSO-strength thresholds",x=.01,xanchor="left",font=dict(size=17)),
        xaxis_title="3-month season (central month)",yaxis_title="RONI anomaly (°C)",
        legend=dict(orientation="h",y=1.13,x=0),hovermode="x unified"
    )
    return fig,x

ENSO_PHASE_COLORS = {
    "La Niña": "#2563EB",
    "Neutral": "#94A3B8",
    "El Niño": "#DC2626",
}

SEASON_CENTRAL_MONTH = {
    "DJF":"Jan","JFM":"Feb","FMA":"Mar","MAM":"Apr","AMJ":"May","MJJ":"Jun",
    "JJA":"Jul","JAS":"Aug","ASO":"Sep","SON":"Oct","OND":"Nov","NDJ":"Dec",
}


def enso_probability_display(df):
    """Prepare NOAA CPC ENSO probabilities for plotting and download."""
    x = df.copy()
    keep = [c for c in ["Season","La Niña","Neutral","El Niño"] if c in x.columns]
    x = x[keep].copy()
    for c in ["La Niña","Neutral","El Niño"]:
        if c not in x.columns:
            x[c] = np.nan
        x[c] = pd.to_numeric(x[c], errors="coerce")

    # NOAA tables may expose either fractions or percentages.
    mx = pd.concat([x[c] for c in ["La Niña","Neutral","El Niño"]], ignore_index=True).max()
    if pd.notna(mx) and mx <= 1.5:
        for c in ["La Niña","Neutral","El Niño"]:
            x[c] = 100.0 * x[c]

    def clean_season(v):
        s = str(v).strip().upper()
        m = re.search(r"(DJF|JFM|FMA|MAM|AMJ|MJJ|JJA|JAS|ASO|SON|OND|NDJ)", s)
        return m.group(1) if m else str(v).strip()

    x["Season code"] = x["Season"].map(clean_season)
    x["Central month"] = x["Season code"].map(SEASON_CENTRAL_MONTH).fillna("")
    x["Display period"] = [
        f"{s} ({m})" if m else str(s)
        for s,m in zip(x["Season code"],x["Central month"])
    ]

    phases = ["La Niña","Neutral","El Niño"]
    x["Dominant phase"] = x[phases].idxmax(axis=1)
    x["Dominant probability (%)"] = x[phases].max(axis=1)
    return x.reset_index(drop=True)


def enso_probability_figure(df):
    """
    100%-stacked ENSO phase-probability bars.
    NOAA CPC outlook periods are overlapping 3-month seasons, not single-month forecasts.
    """
    x = enso_probability_display(df)
    fig = go.Figure()
    for phase in ["La Niña","Neutral","El Niño"]:
        fig.add_trace(go.Bar(
            x=x["Display period"],
            y=x[phase],
            name=phase,
            marker_color=ENSO_PHASE_COLORS[phase],
            hovertemplate=f"{phase}: <b>%{{y:.1f}}%</b><extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        height=390,
        margin=dict(l=20,r=10,t=50,b=20),
        title=dict(
            text="NOAA CPC ENSO outlook probabilities",
            x=.01, xanchor="left", font=dict(size=17)
        ),
        xaxis_title="3-month season (central month)",
        yaxis=dict(title="Probability (%)", range=[0,100]),
        legend=dict(orientation="h", y=1.11, x=0),
        hovermode="x unified",
    )
    return fig, x


def _seasonal_anomaly_series(long_data, region_code, horizon_name, variable):
    section = "weekly" if horizon_name == "Sub-seasonal" else "monthly"
    suffix = "temp" if variable == "Temperature anomaly" else "precip"
    series = (
        long_data.get(str(region_code), {})
        .get(f"{section}_{suffix}", pd.Series(dtype=float))
        .copy()
    )
    series = pd.to_numeric(series, errors="coerce")
    series.index = pd.to_datetime(series.index, errors="coerce")
    return series.dropna()


def seasonal_valid_label(series, horizon_name, period_name):
    section,sl=long_slice(period_name)
    sel=series.iloc[sl].dropna()
    if sel.empty: return period_display_label(horizon_name,period_name)
    d1=pd.Timestamp(sel.index.min()); d2=pd.Timestamp(sel.index.max())
    if horizon_name=="Seasonal":
        if len(sel)==1:
            return f"{d1.strftime('%B %Y')} · model timestamp {d1.strftime('%d %b %Y')}"
        return f"{d1.strftime('%b %Y')}–{d2.strftime('%b %Y')}"
    if len(sel)==1: return f"Week centred on {d1.strftime('%d %b %Y')}"
    return f"{d1.strftime('%d %b %Y')}–{d2.strftime('%d %b %Y')}"


def seasonal_anomaly_bar_figure(series, variable, focus_name, horizon_name, period_name=None):
    unit="°C" if variable=="Temperature anomaly" else "mm"
    if variable=="Temperature anomaly":
        colors=["#2563EB" if v<0 else "#DC2626" for v in series.to_numpy(float)]
        interpretation="blue = cooler than model climatology; red = warmer than model climatology"
    else:
        colors=["#B45309" if v<0 else "#0284C7" for v in series.to_numpy(float)]
        interpretation="brown = drier than model climatology; blue = wetter than model climatology"
    labels=[
        pd.Timestamp(x).strftime("%d %b %Y") if horizon_name=="Sub-seasonal"
        else pd.Timestamp(x).strftime("%B %Y")
        for x in series.index
    ]
    fig=go.Figure(go.Bar(
        x=labels,y=series.to_numpy(float),marker_color=colors,
        customdata=[[pd.Timestamp(t).strftime("%d %b %Y")] for t in series.index],
        hovertemplate=f"%{{customdata[0]}}<br>{variable}: <b>%{{y:+.2f}} {unit}</b><extra></extra>"
    ))
    fig.add_hline(y=0,line_color="#475569",line_width=1)
    fig.update_layout(
        height=390,margin=dict(l=20,r=10,t=55,b=25),
        title=dict(text=f"{focus_name} · {variable} · temporal anomaly",x=.01,xanchor="left",font=dict(size=17)),
        xaxis_title="Forecast month / period",yaxis_title=f"Anomaly ({unit})",showlegend=False
    )
    return fig,interpretation


def seasonal_anomaly_filled_figure(series, variable, focus_name, horizon_name, period_name=None):
    unit="°C" if variable=="Temperature anomaly" else "mm"
    y=series.to_numpy(float); pos=np.where(y>=0,y,np.nan); neg=np.where(y<0,y,np.nan)
    if variable=="Temperature anomaly":
        pos_line,pos_fill="#B91C1C","rgba(220,38,38,.72)"
        neg_line,neg_fill="#1E3A8A","rgba(30,58,138,.78)"
        pos_name,neg_name="Warmer than climatology","Cooler than climatology"
        interpretation="red = warmer than model climatology; blue = cooler than model climatology"
    else:
        pos_line,pos_fill="#0369A1","rgba(14,165,233,.72)"
        neg_line,neg_fill="#9A3412","rgba(234,88,12,.72)"
        pos_name,neg_name="Wetter than climatology","Drier than climatology"
        interpretation="blue = wetter than model climatology; orange/brown = drier than model climatology"
    labels=[
        pd.Timestamp(x).strftime("%d %b %Y") if horizon_name=="Sub-seasonal"
        else pd.Timestamp(x).strftime("%B %Y")
        for x in series.index
    ]
    exact=[pd.Timestamp(x).strftime("%d %b %Y") for x in series.index]
    fig=go.Figure()
    fig.add_trace(go.Scatter(
        x=labels,y=pos,mode="lines",line=dict(color=pos_line,width=1.2),
        fill="tozeroy",fillcolor=pos_fill,name=pos_name,
        customdata=[[d] for d in exact],
        hovertemplate=f"%{{customdata[0]}}<br>{variable}: <b>%{{y:+.2f}} {unit}</b><extra></extra>"
    ))
    fig.add_trace(go.Scatter(
        x=labels,y=neg,mode="lines",line=dict(color=neg_line,width=1.2),
        fill="tozeroy",fillcolor=neg_fill,name=neg_name,
        customdata=[[d] for d in exact],
        hovertemplate=f"%{{customdata[0]}}<br>{variable}: <b>%{{y:+.2f}} {unit}</b><extra></extra>"
    ))
    fig.add_trace(go.Scatter(x=labels,y=y,mode="lines",line=dict(color="#111827",width=1.1),name="Anomaly",showlegend=False,hoverinfo="skip"))
    fig.add_hline(y=0,line_color="#111827",line_width=1)
    fig.update_layout(
        height=390,margin=dict(l=20,r=10,t=55,b=25),
        title=dict(text=f"{focus_name} · {variable} · temporal anomaly",x=.01,xanchor="left",font=dict(size=17)),
        xaxis_title="Forecast month / period",yaxis_title=f"Anomaly ({unit})",
        legend=dict(orientation="h",y=1.12,x=0),hovermode="x unified"
    )
    return fig,interpretation


def seasonal_anomaly_map_data(regions_df, long_data, period_name, variable):
    section,sl=long_slice(period_name)
    suffix="temp" if variable=="Temperature anomaly" else "precip"
    rows=[]
    for r in regions_df.itertuples():
        s=long_data.get(str(r.REGION_CODE),{}).get(f"{section}_{suffix}",pd.Series(dtype=float))
        s=pd.to_numeric(s,errors="coerce").iloc[sl]
        rows.append({**r._asdict(),"value":float(s.mean()) if len(s.dropna()) else np.nan})
    return pd.DataFrame(rows)


def seasonal_anomaly_map_figure(
    geojson_obj, anomaly_df, variable, focus_name, horizon_name, period_name, source_label,
    basemap_name="Streets / places", layer_opacity=0.64, valid_label=None
):
    df=anomaly_df.copy(); df["REGION_CODE"]=df["REGION_CODE"].astype(str)
    vals=pd.to_numeric(df["value"],errors="coerce").dropna()
    lim=max(0.1 if variable=="Temperature anomaly" else 1.0,
            float(np.nanquantile(np.abs(vals),.98)) if len(vals) else 1.0)
    unit="°C" if variable=="Temperature anomaly" else "mm"
    if variable=="Temperature anomaly":
        colorscale=[
            [0.00,"#1D4ED8"],[0.18,"#0EA5E9"],[0.36,"#22D3EE"],[0.50,"#F8FAFC"],
            [0.64,"#FDE047"],[0.82,"#F97316"],[1.00,"#DC2626"]
        ]
        meaning="negative = cooler than model climatology · positive = warmer than model climatology"
    else:
        colorscale=[
            [0.00,"#9A3412"],[0.20,"#EA580C"],[0.38,"#FDBA74"],[0.50,"#F8FAFC"],
            [0.62,"#A5F3FC"],[0.80,"#0EA5E9"],[1.00,"#1D4ED8"]
        ]
        meaning="negative = drier than model climatology · positive = wetter than model climatology"
    df["DISPLAY"]=["Data unavailable" if not np.isfinite(v) else f"{v:+.2f} {unit}" for v in pd.to_numeric(df["value"],errors="coerce")]
    df["SIGNAL"]=[
        "Near model climatology" if not np.isfinite(v) or abs(v)<(0.1 if unit=="°C" else 1.0)
        else (("Warmer than climatology" if v>0 else "Cooler than climatology") if variable=="Temperature anomaly"
              else ("Wetter than climatology" if v>0 else "Drier than climatology"))
        for v in pd.to_numeric(df["value"],errors="coerce")
    ]
    period_text=valid_label or period_display_label(horizon_name,period_name)
    custom=np.stack([df["REGION_NAME"].astype(str),df["ADMIN1"].astype(str),df["DISPLAY"].astype(str),df["SIGNAL"].astype(str)],axis=1)
    fig=go.Figure(go.Choroplethmap(
        geojson=geojson_obj,locations=df["REGION_CODE"],z=df["value"],
        featureidkey="properties.REGION_CODE",colorscale=colorscale,zmin=-lim,zmax=lim,zmid=0,
        marker=dict(opacity=float(layer_opacity),line=dict(width=.65,color="rgba(255,255,255,.88)")),
        colorbar=horizontal_colorbar(f"{unit} anomaly"),
        customdata=custom,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"+variable+": <b>%{customdata[2]}</b><br>"
            "Interpretation: %{customdata[3]}<br>"
            f"Forecast period: {period_text}<br>Source: {source_label}<extra></extra>"
        )
    ))
    focus_row=df[df["REGION_NAME"]==focus_name]
    if len(focus_row):
        r=focus_row.iloc[0]
        fig.add_trace(go.Scattermap(
            lon=[float(r["rep_lon"])],lat=[float(r["rep_lat"])],
            mode="markers+text",text=[focus_name],textposition="top center",
            marker=dict(size=10,color="#111827"),name="Focus area",
            hovertemplate=f"<b>{focus_name}</b><br>{variable}: {r['DISPLAY']}<extra></extra>"
        ))
    centre,zoom=map_view_from_df(df)
    fig.update_layout(
        map=dict(style=BASEMAP_STYLES.get(basemap_name,"carto-voyager"),center=centre,zoom=zoom),
        height=650,margin=dict(l=0,r=0,t=58,b=88),
        title=dict(text=f"{variable} · spatial anomaly · {period_text}",x=.01,xanchor="left",font=dict(size=17)),
        hoverlabel=dict(bgcolor="white",font_size=13,font_family="Arial"),
        legend=dict(orientation="h",y=-.03)
    )
    return fig,meaning


# ---------------------------------------------------------------------------
# Optional local AI
# ---------------------------------------------------------------------------
def local_ai_rewrite(text,model):
    prompt=f"""Rewrite this verified climate-health briefing for non-technical decision makers.
Do not invent or change numbers, dates, sources, probabilities, hazard definitions or caveats.
Use exactly 5 short bullets: Forecast window; Main signal; Compound/ocean context; Uncertainty; Health action.
Briefing:
{text}"""
    r=requests.post("http://localhost:11434/api/generate",
                    json={"model":model,"prompt":prompt,"stream":False},timeout=35)
    r.raise_for_status()
    return r.json().get("response","").strip()


# ---------------------------------------------------------------------------
# UI: Country / geography first
# ---------------------------------------------------------------------------
st.markdown("""
<div class="hero-v13">
  <div class="eyebrow">REACH · Climate × Health · Early Warning</div>
  <h1>From forecast signal to health-system action</h1>
  <p class="sub">A decision-support portal for Zambia and Brazil that connects multi-horizon climate and hydrological forecasts with district/municipality screening, health-facility exposure, model verification and practical preparedness actions.</p>
  <div class="trust">Research decision support · linked forecast sources · official national warnings remain authoritative</div>
</div>
<div class="journey-wrap">
  <div class="journey-step"><b><span class="n">1</span>Monitor</b><span>See the current hazard signal and source status.</span></div>
  <div class="journey-step"><b><span class="n">2</span>Locate</b><span>Move from country → district/municipality → facility.</span></div>
  <div class="journey-step"><b><span class="n">3</span>Compare</b><span>Compare ECMWF, NOAA, ERA5 context and uncertainty.</span></div>
  <div class="journey-step"><b><span class="n">4</span>Health impact</b><span>Translate hazard exposure into health-system and population-health pathways.</span></div>
  <div class="journey-step"><b><span class="n">5</span>Act</b><span>Use the screened signal to support preparedness and continuity decisions.</span></div>
</div>
""",unsafe_allow_html=True)

st.markdown('<div class="landing-kicker">Start here</div><div class="landing-title">Choose geography, then let the dashboard cascade the same selection through maps, facilities, verification and briefing.</div>',unsafe_allow_html=True)
topc1,topc2,topc3=st.columns([1,1,2.4])
with topc1:
    country=st.selectbox("Country",["Zambia","Brazil"])
with topc2:
    if country=="Brazil":
        state_name=st.selectbox("Brazil state",list(BRAZIL_UFS),index=list(BRAZIL_UFS).index("Pernambuco"))
    else:
        state_name="—"
with topc3:
    if country=="Brazil":
        st.caption("Brazil uses the complete municipality boundary dataset you supplied. Live climate forecasts are requested state-by-state for stability; Pernambuco prioritises Recife and Palmares.")
    else:
        st.caption("Zambia uses the complete 116-district shapefile supplied for REACH.")

try:
    geo,regions=geography(country,state_name)
    geo_error=None
except Exception as exc:
    geo,regions={},pd.DataFrame()
    geo_error=str(exc)
    st.error(f"Geography could not be loaded: {exc}")

# Climate-driver cards are intentionally visible on the landing page.
enso_info=dmi_info=atlantic_info=None
try:
    enso=enso_table();row=enso.iloc[0]
    probs={k:float(row[k]) for k in ["La Niña","Neutral","El Niño"] if k in enso and pd.notna(row[k])}
    phase=max(probs,key=probs.get) if probs else "Unavailable"
    enso_info={"phase":phase,"prob":probs.get(phase,np.nan),"season":str(row.get("Season",""))}
except Exception: pass

if country=="Zambia":
    try:
        dmi,dmi_date=climate_index(DMI_CSV)
        dmi_phase="Positive IOD" if dmi>=.4 else ("Negative IOD" if dmi<=-.4 else "Near-neutral IOD")
        dmi_info={"value":dmi,"date":dmi_date,"phase":dmi_phase}
    except Exception: pass
else:
    try:
        tna,tna_date=climate_index(TNA_CSV);tsa,tsa_date=climate_index(TSA_CSV)
        atlantic_info={"tna":tna,"tsa":tsa,"gradient":tna-tsa,"date":tna_date}
    except Exception: pass

st.markdown('<div class="section">Forecast sources & climate context</div>',unsafe_allow_html=True)
cards=st.columns(6)
with cards[0]:
    st.markdown('<div class="source-compact"><span class="source-title">ECMWF</span><br><span class="source-note">IFS · ENS · EC46 · SEAS5</span></div>',unsafe_allow_html=True)
    st.link_button("Source", "https://open-meteo.com/en/docs/ecmwf-api", use_container_width=True)
with cards[1]:
    st.markdown('<div class="source-compact"><span class="source-title">NOAA</span><br><span class="source-note">GFS · GEFS · NMME</span></div>',unsafe_allow_html=True)
    st.link_button("Source", NMME_URL, use_container_width=True)
with cards[2]:
    st.markdown('<div class="source-compact"><span class="source-title">GloFAS</span><br><span class="source-note">River discharge / flood guidance</span></div>',unsafe_allow_html=True)
    st.link_button("Source", "https://open-meteo.com/en/docs/flood-api", use_container_width=True)
with cards[3]:
    etxt="Unavailable" if not enso_info else f"{enso_info['phase']} · {enso_info['prob']:.0f}%"
    st.markdown(f'<div class="source-compact"><span class="source-title">ENSO / RONI</span><br><span class="source-note">{etxt}</span></div>',unsafe_allow_html=True)
    st.link_button("NOAA CPC", CPC_ENSO_URL, use_container_width=True)
with cards[4]:
    if country=="Zambia":
        txt="Unavailable" if not dmi_info else f"{dmi_info['value']:+.2f} °C · {dmi_info['phase']}"
        st.markdown(f'<div class="source-compact"><span class="source-title">IOD / DMI</span><br><span class="source-note">{txt}</span></div>',unsafe_allow_html=True)
        st.link_button("NOAA PSL", DMI_WEB, use_container_width=True)
    else:
        txt="Unavailable" if not atlantic_info else f"TNA−TSA {atlantic_info['gradient']:+.2f} °C"
        st.markdown(f'<div class="source-compact"><span class="source-title">Tropical Atlantic</span><br><span class="source-note">{txt}</span></div>',unsafe_allow_html=True)
        st.link_button("NOAA PSL", "https://psl.noaa.gov/data/timeseries/month/", use_container_width=True)
with cards[5]:
    if country=="Zambia":
        st.markdown('<div class="source-card"><span class="source-title">National authority</span><br><span class="source-note">ZMD seasonal / warning products</span></div>',unsafe_allow_html=True)
        st.link_button("ZMD", ZMD_PRODUCTS, use_container_width=True)
    else:
        st.markdown('<div class="source-card"><span class="source-title">Brazil sources</span><br><span class="source-note">Municipality geometry · CEMADEN · APAC</span></div>',unsafe_allow_html=True)
        st.link_button("IBGE reference", IBGE_MALHAS, use_container_width=True)


# ---------------------------------------------------------------------------
# Main controls
# ---------------------------------------------------------------------------
if geo_error is None and not regions.empty:
    map_col,ctl=st.columns([3.05,1.25],gap="large")
    with ctl:
        st.markdown('<div class="panel">',unsafe_allow_html=True)
        st.markdown("### Forecast setup")
        horizon=st.selectbox("1 · Forecast horizon",list(HORIZONS),format_func=lambda h:f"{h} · {HORIZONS[h]['window']}")
        hazard=st.selectbox("2 · Hazard",hazards_for_horizon(horizon))
        period=st.selectbox("3 · Valid period",period_options(horizon),format_func=lambda p:period_display_label(horizon,p))

        if horizon in ("Short range","Medium range"):
            det_source=st.selectbox("4 · Deterministic model",["ECMWF IFS HRES","NOAA GFS"])
            ensemble_system=st.selectbox("5 · Ensemble for probability",["ECMWF IFS ENS","NOAA GEFS"])
        else:
            det_source="ECMWF EC46/SEAS5";ensemble_system="—"

        mode=st.selectbox("6 · Spatial map",map_modes(hazard,horizon))

        focus_names=regions.sort_values("REGION_NAME").REGION_NAME.tolist()
        preferred=[]
        if country=="Zambia": preferred=["Senanga","Sinazongwe"]
        elif state_name=="Pernambuco": preferred=["Recife","Palmares"]
        ordered=[x for x in preferred if x in focus_names]+[x for x in focus_names if x not in preferred]
        focus=st.selectbox("7 · Focus area",ordered)

        # Facilities remain nested under the selected pilot district/municipality.
        facility_registry=pd.DataFrame()
        facility_status=""
        facility_choice_code=None
        selected_facility=None
        focus_region_row=regions[regions["REGION_NAME"]==focus].iloc[0]
        if (country,focus) in PILOT:
            st.markdown("#### Health-facility drill-down")
            with st.spinner("Loading health-facility registry..."):
                facility_registry,facility_status=facilities_for_area(country,focus,str(focus_region_row.REGION_CODE))
            if not facility_registry.empty:
                facility_registry=facility_registry.sort_values(["FacilityName","FacilityType"]).reset_index(drop=True)
                label_map=facility_dropdown_labels(facility_registry)
                options=[FACILITY_OVERVIEW_OPTION]+facility_registry["REGION_CODE"].astype(str).tolist()
                facility_choice=st.selectbox(
                    "8 · Health facility",options,
                    format_func=lambda x: x if x==FACILITY_OVERVIEW_OPTION else label_map.get(str(x),str(x)),
                    help="The district/municipality remains the parent geography. Select a facility to move the point-specific forecast to that facility's coordinates."
                )
                if facility_choice!=FACILITY_OVERVIEW_OPTION:
                    facility_choice_code=str(facility_choice)
                    selected_facility=facility_registry[facility_registry["REGION_CODE"].astype(str)==facility_choice_code].iloc[0]
                st.caption(f"{len(facility_registry):,} mapped facilities available under {focus} · registry status: {facility_status}.")
                if country == "Brazil":
                    st.caption("Coordinate quality control: CNES points outside the selected municipality boundary are excluded from the map and gradient rather than moved to an invented location. Facility names remain available on hover; only the selected facility is labelled directly on dense Brazil contour plots.")
            else:
                st.warning(f"Facility registry is temporarily unavailable for {focus}. The district/municipality forecast remains fully available. ({facility_status})")
        else:
            st.caption("Facility drill-down is currently enabled for the four REACH pilot areas: Senanga, Sinazongwe, Recife and Palmares.")

        _state_context = f" · {state_name}" if country=="Brazil" else ""
        _facility_context = (selected_facility.FacilityName if selected_facility is not None else "Area overview")
        st.markdown(
            f'<div class="selection-context"><b>Current view:</b> {country}{_state_context} → {horizon} → {hazard} → {period_display_label(horizon,period)} → {focus} → {_facility_context}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("#### Map display")
        basemap_name=st.selectbox(
            "Background map",list(BASEMAP_STYLES),
            index=list(BASEMAP_STYLES).index("Streets / places"),
            help="Context only: forecast values do not change when the basemap changes."
        )
        layer_opacity=st.slider(
            "Forecast layer opacity",0.30,0.90,0.64,0.05,
            help="Lower opacity reveals more roads, rivers, settlements, terrain or imagery below the forecast layer."
        )
        st.caption("Basemaps provide geographic context beneath the forecast polygons; the model calculation is unchanged.")

        temp_threshold=35.0
        rain_threshold=50.0
        if mode=="Probabilistic risk classes" or hazard=="Compound – Flood + Heatwave":
            st.markdown("#### Spatial probability thresholds")
            if hazard in ("Heatwave","Compound – Flood + Heatwave"):
                temp_threshold=st.number_input("Tmax threshold (°C)",25.0,50.0,35.0,.5)
            if hazard in ("Flood – rainfall","Compound – Flood + Heatwave"):
                rain_threshold=st.number_input("3-day rain threshold (mm)",5.0,300.0,50.0,5.0)
            st.caption("These thresholds define the national/state probability map. The focus-area panel separately reports local-climatology TX90/P95 event probabilities.")

        st.markdown("#### Interpretation")
        if hazard=="Flood – river discharge (GloFAS)":
            st.write("GloFAS is a river-flow layer in m³/s. The focus-area panel additionally reports probabilities of exceeding local Q2/Q5/Q20 screening levels.")
        elif hazard=="Compound – Flood + Heatwave":
            st.write("Overlap screening = the lower of the flood and heat component signals. It is not a joint probability.")
        elif hazard=="Compound – Drought → Flood":
            st.write("Sequential screening: drier first part of the selected long-range window followed by wetter second part. It is not a joint probability.")
        elif hazard=="Compound – Drought + Heatwave":
            st.write("Compound dry-hot screening combines positive temperature anomaly with negative precipitation anomaly.")
        elif hazard=="Drought / dry anomaly":
            st.write("Dry anomaly is a seasonal/sub-seasonal screening signal. It is not a complete meteorological/hydrological drought index such as SPI/SPEI.")

        if st.button("↻ REFRESH ONLINE DATA",use_container_width=True):
            clear_cache();st.cache_data.clear();st.rerun()
        st.markdown("</div>",unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Map data / map
    # -----------------------------------------------------------------------
    with map_col:
        st.markdown('<div class="section">Spatial forecast outlook</div>',unsafe_allow_html=True)
        try:
            with st.spinner("Loading selected spatial forecast layer..."):
                map_df,map_status,payload=build_map_values(
                    regions,hazard,horizon,period,mode,det_source,ensemble_system,temp_threshold,rain_threshold
                )
            map_error=None
            _valid_start,_valid_end,_valid_kind=forecast_validity(payload,horizon,period,hazard)
            _valid_text=format_valid_window(_valid_start,_valid_end)
            st.caption(
                f"{country} · {state_name if country=='Brazil' else '116 districts'} · {hazard} · {horizon} · {period_display_label(horizon,period)} · "
                f"{mode} · {len(map_df)}/{len(regions)} areas · source status: {map_status}"
            )
            st.markdown(
                f'<div class="selection-context"><b>Forecast validity:</b> {_valid_text} &nbsp; · &nbsp; <b>Temporal meaning:</b> {_valid_kind}. '
                f'Values below must be interpreted against this valid period; UTC is used consistently across sources.</div>',
                unsafe_allow_html=True,
            )
            source_label = (
                det_source if horizon in ("Short range","Medium range") and hazard != "Flood – river discharge (GloFAS)"
                else ("GloFAS" if hazard == "Flood – river discharge (GloFAS)" else "ECMWF EC46 / SEAS5")
            )
            st.markdown(
                '<div class="hoverhint">🖱️ <b>Hover over any district or municipality</b> to see the exact forecast value, unit, risk class, forecast window and source.</div>',
                unsafe_allow_html=True,
            )
            st.plotly_chart(
                map_figure(geo,map_df,hazard,horizon,mode,focus,period,source_label,basemap_name,layer_opacity),
                use_container_width=True,
                config={"displayModeBar": True, "scrollZoom": True, "responsive": True},
            )
        except Exception as exc:
            map_df=pd.DataFrame();payload={};map_error=str(exc)
            st.error(f"Spatial layer unavailable: {exc}")

    # -----------------------------------------------------------------------
    # Summary statistics and risk classes
    # -----------------------------------------------------------------------
    if not map_df.empty:
        sm=stat_summary(map_df.value)
        fr=map_df[map_df.REGION_NAME==focus]
        fv=float(fr.value.iloc[0]) if len(fr) and pd.notna(fr.value.iloc[0]) else np.nan
        maxrow=map_df.loc[map_df.value.idxmax()] if map_df.value.notna().any() else None
        unit=unit_for(hazard,horizon,mode)

        st.markdown('<div class="section">Spatial summary</div>',unsafe_allow_html=True)
        cols=st.columns(7)
        cols[0].metric("Selected area",focus)
        cols[1].metric("Selected area value",fmt(fv,unit))
        cols[2].metric("Minimum",fmt(sm["min"],unit))
        cols[3].metric("Mean",fmt(sm["mean"],unit))
        cols[4].metric("Median",fmt(sm["median"],unit))
        cols[5].metric("Maximum",fmt(sm["max"],unit))
        cols[6].metric("Mapped range",fmt(sm["max"]-sm["min"],unit) if np.isfinite(sm["max"]) and np.isfinite(sm["min"]) else "—")
        st.caption(
            f"Highest-signal mapped area: {maxrow.REGION_NAME if maxrow is not None else '—'}. "
            "The selected district/municipality value is the forecast sampled at that area's representative point in the current workflow; "
            "minimum/mean/median/maximum summarize all mapped administrative areas in the current national/state view."
        )
        if unit=="%":
            st.caption(f"{focus}: {risk_label(fv)} · highest area: {maxrow.REGION_NAME if maxrow is not None else '—'} ({risk_label(sm['max'])}).")

    # -----------------------------------------------------------------------
    # Facility-level hazard/exposure screen nested under the selected pilot area
    # -----------------------------------------------------------------------
    facility_forecast_df=pd.DataFrame()
    facility_model_df=pd.DataFrame()
    long_facility_df=pd.DataFrame()
    selected_facility_value=np.nan
    selected_facility_unit=unit_for(hazard,horizon,mode)
    facility_screen_limited=False
    if not facility_registry.empty:
        facility_input,facility_screen_limited=facility_screen_subset(facility_registry,facility_choice_code)
        if not facility_input.empty:
            try:
                with st.spinner(f"Calculating {len(facility_input):,} facility-level forecast signals within {focus}..."):
                    facility_forecast_df,facility_forecast_status,_facility_payload=build_map_values(
                        facility_input,hazard,horizon,period,mode,det_source,ensemble_system,temp_threshold,rain_threshold
                    )
                st.markdown('<div class="section">Health-facility forecast drill-down</div>',unsafe_allow_html=True)
                st.markdown(
                    f'<div class="facility-note"><b>{focus} remains the parent district/municipality.</b> '
                    f'The facility layer evaluates the selected forecast at mapped facility coordinates. '
                    f'This is a <b>hazard/exposure screen</b>; it becomes an operational facility-risk assessment only when access, power, WASH, staffing, cold-chain or other readiness data are explicitly added.</div>',
                    unsafe_allow_html=True
                )
                if facility_screen_limited:
                    st.warning(
                        f"The registry contains more than {FACILITY_SCREEN_SOFT_LIMIT} mapped facilities. "
                        "To protect the public forecast APIs, the comparison screen uses the MCH/hospital-priority subset and a capped set; the selected facility is always retained."
                    )

                # Space–time facility view: preserve the original window summary, but allow
                # a stakeholder to move through the valid dates/weeks/months when the
                # selected metric has a defensible temporal slice.
                facility_temporal_label = f"Window summary · {format_valid_window(*forecast_validity(_facility_payload,horizon,period,hazard)[:2])}"
                facility_temporal_mode = "Window summary"
                _time_choices=[]
                _time_hazard = hazard if hazard in ("Heatwave","Flood – rainfall","Drought / dry anomaly") else None
                if selected_facility_unit in ("°C","mm") and _time_hazard is not None:
                    _time_choices=_facility_time_choices(_facility_payload,horizon,period,_time_hazard)
                if _time_choices:
                    st.markdown("#### Forecast time")
                    _temporal_options=["Window summary"]+_time_choices
                    def _fmt_time_opt(x):
                        if x=="Window summary":
                            return f"Window summary · {period_display_label(horizon,period)}"
                        return _time_specific_label(horizon,_time_hazard,x)
                    _temporal_pick=st.selectbox(
                        "Facility gradient / bar valid time",_temporal_options,format_func=_fmt_time_opt,
                        help="The selected time cascades to the facility metrics, map/table, bar chart and contour gradient. Window summary preserves the original period-aggregated view."
                    )
                    if _temporal_pick!="Window summary":
                        facility_temporal_mode="Time-specific"
                        facility_temporal_label=_time_specific_label(horizon,_time_hazard,_temporal_pick)
                        facility_forecast_df=_facility_values_at_time(
                            facility_forecast_df,_facility_payload,horizon,_time_hazard,pd.Timestamp(_temporal_pick)
                        )
                        if horizon in ("Short range","Medium range"):
                            if _time_hazard=="Heatwave":
                                st.caption("Daily Tmax is a daily aggregate, so an exact event hour is not assigned on the contour. Use the Time series & uncertainty tab for hourly model timing.")
                            else:
                                st.caption("Rainfall is shown as the rolling 3-day accumulation ending on the selected UTC date, consistent with the short/medium-range rainfall screening metric.")
                        else:
                            st.caption("Extended and seasonal products are weekly/monthly anomalies. The dashboard does not invent an exact event hour for these aggregated outlooks.")
                    else:
                        _fs,_fe,_fk=forecast_validity(_facility_payload,horizon,period,_time_hazard)
                        facility_temporal_label=f"{period_display_label(horizon,period)} · {format_valid_window(_fs,_fe)} · {_fk}"
                else:
                    _fs,_fe,_fk=forecast_validity(_facility_payload,horizon,period,hazard)
                    facility_temporal_label=f"{period_display_label(horizon,period)} · {format_valid_window(_fs,_fe)} · {_fk}"

                st.markdown(
                    f'<div class="selection-context"><b>Facility forecast valid time:</b> {facility_temporal_label}</div>',
                    unsafe_allow_html=True,
                )
                facility_forecast_df["ValidTime"] = facility_temporal_label
                facility_forecast_df["ForecastDisplay"]=[fmt(v,selected_facility_unit) for v in pd.to_numeric(facility_forecast_df["value"],errors="coerce")]
                if selected_facility_unit=="%":
                    facility_forecast_df["SignalClass"]=pd.to_numeric(facility_forecast_df["value"],errors="coerce").map(risk_label)
                else:
                    facility_forecast_df["SignalClass"]="Physical forecast / anomaly"
                drought_physical=(hazard=="Drought / dry anomaly" and horizon in ("Sub-seasonal","Seasonal") and "risk" not in mode.lower())
                facility_forecast_df=facility_forecast_df.sort_values("value",ascending=drought_physical,na_position="last").reset_index(drop=True)
                facility_forecast_df.insert(0,"Rank",np.arange(1,len(facility_forecast_df)+1))
                if facility_choice_code:
                    sel=facility_forecast_df[facility_forecast_df["REGION_CODE"].astype(str)==str(facility_choice_code)]
                    if not sel.empty:
                        selected_facility_value=float(sel.iloc[0]["value"]) if pd.notna(sel.iloc[0]["value"]) else np.nan
                top_facility=facility_forecast_df.iloc[0] if len(facility_forecast_df) else None
                fvals=pd.to_numeric(facility_forecast_df["value"],errors="coerce").dropna()
                fmin=float(fvals.min()) if len(fvals) else np.nan
                fmean=float(fvals.mean()) if len(fvals) else np.nan
                fmedian=float(fvals.median()) if len(fvals) else np.nan
                fmax=float(fvals.max()) if len(fvals) else np.nan
                frange=fmax-fmin if np.isfinite(fmax) and np.isfinite(fmin) else np.nan
                fm1,fm2,fm3,fm4,fm5,fm6=st.columns(6)
                fm1.metric("Parent area",focus)
                fm2.metric("Facilities screened",f"{len(facility_forecast_df):,}")
                fm3.metric("Selected facility",selected_facility.FacilityName if selected_facility is not None else "Overview")
                fm4.metric("Selected signal",fmt(selected_facility_value,selected_facility_unit) if selected_facility is not None else "—")
                fm5.metric("Facility mean",fmt(fmean,selected_facility_unit))
                fm6.metric("Facility range",f"{fmt(fmin,selected_facility_unit)} – {fmt(fmax,selected_facility_unit)}" if np.isfinite(fmin) and np.isfinite(fmax) else "—")
                st.caption(
                    f"Within mapped facilities under {focus}: minimum {fmt(fmin,selected_facility_unit)}, mean {fmt(fmean,selected_facility_unit)}, "
                    f"median {fmt(fmedian,selected_facility_unit)}, maximum {fmt(fmax,selected_facility_unit)}, range width {fmt(frange,selected_facility_unit)}. "
                    f"Highest current facility signal: {top_facility.FacilityName if top_facility is not None else '—'}."
                )
                st.markdown(
                    f'<div class="summary"><b>How to read this facility view</b><br>'
                    f'The values above apply to <b>{facility_temporal_label}</b>. The facility table and bars show direct point-specific forecast values. '
                    f'The gradient below is a visual interpolation between those facility points; it is not the native model grid. '
                    f'Use the highest or most unusual values as a screening signal, then check access, power, WASH, staffing, supplies and referral readiness before making an operational decision.</div>',
                    unsafe_allow_html=True,
                )
                if drought_physical:
                    st.caption("For a physical drought/dry-anomaly view, more-negative precipitation anomaly indicates a drier signal; the table is therefore ordered from most negative upward.")
                elif selected_facility_unit!="%":
                    st.caption("For physical heat, rainfall and discharge views, larger values generally indicate greater hazard magnitude. This is not a readiness or service-disruption score.")

                fleft,fright=st.columns([1.55,1.0],gap="large")
                with fleft:
                    st.plotly_chart(
                        facility_forecast_figure(geo,str(focus_region_row.REGION_CODE),facility_forecast_df,facility_choice_code,hazard,horizon,mode,period,
                                                 det_source if horizon in ("Short range","Medium range") and hazard!="Flood – river discharge (GloFAS)" else ("GloFAS" if hazard=="Flood – river discharge (GloFAS)" else "ECMWF EC46 / SEAS5"),
                                                 basemap_name),
                        use_container_width=True,config={"displayModeBar":True,"scrollZoom":True,"responsive":True}
                    )
                with fright:
                    table_cols=[c for c in ["Rank","FacilityName","FacilityType","ForecastDisplay","ValidTime","SignalClass","Source"] if c in facility_forecast_df]
                    st.dataframe(facility_forecast_df[table_cols].head(35),hide_index=True,use_container_width=True,height=520)

                st.markdown("#### Facility forecast values · bar comparison")
                st.caption(
                    "Bars are the direct point-specific forecast values sampled at mapped facility coordinates; they are not interpolated. "
                    "The selected facility is highlighted with a gold bar/star when it is in the displayed set."
                )
                facility_bar=facility_signal_bar_figure(
                    facility_forecast_df,"value",f"{focus} · facility {hazard.lower()} comparison · {facility_temporal_label}",selected_facility_unit,facility_choice_code
                )
                if facility_bar is not None:
                    st.plotly_chart(facility_bar,use_container_width=True,config={"displayModeBar":True,"responsive":True})

                # A consistent facility contour/gradient is shown for every forecast horizon.
                # This uses the currently selected forecast signal sampled at facility coordinates,
                # without replacing any of the existing model-comparison or long-range content below.
                if selected_facility_unit in ("°C","mm") and hazard in (
                    "Heatwave","Flood – rainfall","Drought / dry anomaly",
                    "Compound – Flood + Heatwave","Compound – Drought + Heatwave","Compound – Drought → Flood"
                ):
                    try:
                        st.markdown("#### Facility forecast gradient · selected forecast")
                        st.caption(
                            "The coloured field is a fully visible inverse-distance interpolation of the current facility-point forecast values. "
                            + ("Dark labelled contours show the forecast value. Brazil keeps facility names on hover and labels only the selected facility to avoid crowding; " if country=="Brazil" else "Dark labelled contours show the forecast value and Zambia labels each mapped facility directly; ")
                            + "The title carries the selected forecast-valid date/window so the surface is never interpreted without time. "
                            + "This is a visual interpolation of values sampled at facility coordinates, not the native forecast-model grid."
                        )
                        st.caption(f"**Valid time:** {facility_temporal_label}")
                        _is_diverging = (horizon in ("Sub-seasonal","Seasonal") or "anomaly" in str(mode).lower() or hazard=="Drought / dry anomaly")
                        _grad_title = f"{focus} · facility {hazard.lower()} gradient · {facility_temporal_label}"
                        if selected_facility_unit=="°C":
                            _generic_grad=facility_temperature_gradient_figure(
                                facility_forecast_df,"value",_grad_title,facility_choice_code,diverging=_is_diverging
                            )
                        else:
                            _generic_grad=facility_precipitation_gradient_figure(
                                facility_forecast_df,"value",_grad_title,facility_choice_code,diverging=_is_diverging
                            )
                        if _generic_grad is not None:
                            st.plotly_chart(_generic_grad,use_container_width=True,config={"displayModeBar":True,"responsive":True})
                        else:
                            st.caption(
                                "A contour gradient is not drawn because the current facility values do not contain enough spatial variation for a defensible surface. "
                                "The direct facility values remain available in the map, table and bar chart above."
                            )
                    except Exception as exc:
                        print(f"Facility selected-signal gradient error: {type(exc).__name__}: {exc}")
                        st.warning("The facility gradient could not be rendered for this selection; the direct facility values remain available above.")

                # Consistent facility gradients for extended-range and seasonal forecasts.
                if horizon in ("Sub-seasonal","Seasonal"):
                    try:
                        long_payload=_facility_payload.get("long",{}) if isinstance(_facility_payload,dict) else {}
                        long_facility_df=facility_longrange_component_values(facility_input,long_payload,period)
                        if not long_facility_df.empty:
                            st.markdown("#### Facility seasonal / sub-seasonal spatial gradients")
                            st.caption(
                                "Facility names and physical anomaly values are shown directly on the labelled contour surface. "
                                "The surface is an inverse-distance visual interpolation of ECMWF EC46/SEAS5 anomaly values sampled at facility coordinates; it is not the native model grid."
                            )
                            if hazard in ("Heatwave","Compound – Flood + Heatwave","Compound – Drought + Heatwave"):
                                tg=facility_temperature_gradient_figure(
                                    long_facility_df,"TempAnomaly_C",
                                    f"{focus} · facility temperature anomaly gradient · {period_display_label(horizon,period)}",
                                    facility_choice_code,diverging=True
                                )
                                if tg is not None:
                                    st.plotly_chart(tg,use_container_width=True,config={"displayModeBar":True,"responsive":True})
                                tb=facility_signal_bar_figure(
                                    long_facility_df,"TempAnomaly_C",
                                    f"{focus} · facility temperature anomaly · {period_display_label(horizon,period)}",
                                    "°C",facility_choice_code
                                )
                                if tb is not None:
                                    st.plotly_chart(tb,use_container_width=True,config={"displayModeBar":True,"responsive":True})
                            if hazard in ("Flood – rainfall","Drought / dry anomaly","Compound – Flood + Heatwave","Compound – Drought + Heatwave","Compound – Drought → Flood"):
                                pg=facility_precipitation_gradient_figure(
                                    long_facility_df,"PrecipAnomaly_mm",
                                    f"{focus} · facility precipitation anomaly gradient · {period_display_label(horizon,period)}",
                                    facility_choice_code,diverging=True
                                )
                                if pg is not None:
                                    st.plotly_chart(pg,use_container_width=True,config={"displayModeBar":True,"responsive":True})
                                pb=facility_signal_bar_figure(
                                    long_facility_df,"PrecipAnomaly_mm",
                                    f"{focus} · facility precipitation anomaly · {period_display_label(horizon,period)}",
                                    "mm",facility_choice_code
                                )
                                if pb is not None:
                                    st.plotly_chart(pb,use_container_width=True,config={"displayModeBar":True,"responsive":True})
                    except Exception as exc:
                        st.info(f"Facility long-range gradient is temporarily unavailable: {exc}")

                if horizon in ("Short range","Medium range") and hazard in ("Heatwave","Flood – rainfall","Compound – Flood + Heatwave"):
                    try:
                        with st.spinner("Comparing ECMWF IFS and NOAA GFS across facility locations..."):
                            facility_model_df,facility_model_status=facility_two_model_comparison(facility_input,horizon,period)
                        if not facility_model_df.empty:
                            st.markdown("#### Facility spatial model comparison")
                            st.caption(
                                ("Each forecast model is sampled at the health-facility coordinates. "
                                 + ("For Brazil, facility names are available on hover and only the selected facility is labelled so dense urban maps remain readable. " if country=="Brazil" else "Facility names are printed beside the points. ")
                                 + "Labelled contour lines show the interpolated value directly on the surface. "
                                 + "The coloured surface is an inverse-distance interpolation of facility point forecasts for visual interpretation; it is not the native ECMWF/GFS grid. "
                                 + "The bar charts below use the original sampled facility values, not the interpolation.")
                            )
                            selrow=facility_model_df[facility_model_df["REGION_CODE"].astype(str)==str(facility_choice_code)] if facility_choice_code else pd.DataFrame()

                            if hazard in ("Heatwave","Compound – Flood + Heatwave"):
                                st.markdown("##### Temperature · ECMWF IFS HRES vs NOAA GFS")
                                ecvals=pd.to_numeric(facility_model_df["ECMWF_Tmax_C"],errors="coerce").dropna()
                                gfvals=pd.to_numeric(facility_model_df["GFS_Tmax_C"],errors="coerce").dropna()
                                mc1,mc2,mc3,mc4=st.columns(4)
                                mc1.metric("ECMWF facility range","—" if ecvals.empty else f"{ecvals.min():.1f}–{ecvals.max():.1f} °C")
                                mc2.metric("NOAA GFS facility range","—" if gfvals.empty else f"{gfvals.min():.1f}–{gfvals.max():.1f} °C")
                                mc3.metric("Selected · ECMWF","—" if selrow.empty or pd.isna(selrow.iloc[0]["ECMWF_Tmax_C"]) else f"{float(selrow.iloc[0]['ECMWF_Tmax_C']):.1f} °C")
                                mc4.metric("Selected · NOAA GFS","—" if selrow.empty or pd.isna(selrow.iloc[0]["GFS_Tmax_C"]) else f"{float(selrow.iloc[0]['GFS_Tmax_C']):.1f} °C")
                                sc1,sc2=st.columns(2,gap="large")
                                with sc1:
                                    f1=facility_temperature_gradient_figure(facility_model_df,"ECMWF_Tmax_C","ECMWF IFS HRES · facility Tmax spatial gradient",facility_choice_code)
                                    if f1 is not None: st.plotly_chart(f1,use_container_width=True,config={"displayModeBar":True,"responsive":True})
                                with sc2:
                                    f2=facility_temperature_gradient_figure(facility_model_df,"GFS_Tmax_C","NOAA GFS · facility Tmax spatial gradient",facility_choice_code)
                                    if f2 is not None: st.plotly_chart(f2,use_container_width=True,config={"displayModeBar":True,"responsive":True})
                                heat_bars=facility_two_model_bar_figure(
                                    facility_model_df,"ECMWF_Tmax_C","GFS_Tmax_C",
                                    f"{focus} · facility Tmax · ECMWF vs NOAA GFS","°C",facility_choice_code
                                )
                                if heat_bars is not None:
                                    st.plotly_chart(heat_bars,use_container_width=True,config={"displayModeBar":True,"responsive":True})
                                diff_fig=facility_point_spatial_figure(facility_model_df,"Tmax_ECMWF_minus_GFS_C","Model difference at facilities · ECMWF minus NOAA GFS","°C",facility_choice_code,basemap_name,diverging=True)
                                st.plotly_chart(diff_fig,use_container_width=True,config={"displayModeBar":True,"scrollZoom":True,"responsive":True})

                            if hazard in ("Flood – rainfall","Compound – Flood + Heatwave"):
                                st.markdown("##### Precipitation · ECMWF IFS HRES vs NOAA GFS")
                                ervals=pd.to_numeric(facility_model_df["ECMWF_Rain3_mm"],errors="coerce").dropna()
                                grvals=pd.to_numeric(facility_model_df["GFS_Rain3_mm"],errors="coerce").dropna()
                                rc1,rc2,rc3,rc4=st.columns(4)
                                rc1.metric("ECMWF rainfall range","—" if ervals.empty else f"{ervals.min():.1f}–{ervals.max():.1f} mm")
                                rc2.metric("NOAA GFS rainfall range","—" if grvals.empty else f"{grvals.min():.1f}–{grvals.max():.1f} mm")
                                rc3.metric("Selected · ECMWF rain","—" if selrow.empty or pd.isna(selrow.iloc[0]["ECMWF_Rain3_mm"]) else f"{float(selrow.iloc[0]['ECMWF_Rain3_mm']):.1f} mm")
                                rc4.metric("Selected · NOAA GFS rain","—" if selrow.empty or pd.isna(selrow.iloc[0]["GFS_Rain3_mm"]) else f"{float(selrow.iloc[0]['GFS_Rain3_mm']):.1f} mm")
                                sc1,sc2=st.columns(2,gap="large")
                                with sc1:
                                    rf1=facility_precipitation_gradient_figure(facility_model_df,"ECMWF_Rain3_mm","ECMWF IFS HRES · facility 3-day rainfall spatial gradient",facility_choice_code)
                                    if rf1 is not None:
                                        st.plotly_chart(rf1,use_container_width=True,config={"displayModeBar":True,"responsive":True})
                                    else:
                                        st.caption("ECMWF facility rainfall values are spatially uniform in this valid window, so a labelled contour gradient would be artificial; the point map is shown instead.")
                                        st.plotly_chart(facility_point_spatial_figure(facility_model_df,"ECMWF_Rain3_mm","ECMWF IFS HRES · maximum 3-day rainfall at facilities","mm",facility_choice_code,basemap_name),use_container_width=True)
                                with sc2:
                                    rf2=facility_precipitation_gradient_figure(facility_model_df,"GFS_Rain3_mm","NOAA GFS · facility 3-day rainfall spatial gradient",facility_choice_code)
                                    if rf2 is not None:
                                        st.plotly_chart(rf2,use_container_width=True,config={"displayModeBar":True,"responsive":True})
                                    else:
                                        st.caption("NOAA GFS facility rainfall values are spatially uniform in this valid window, so a labelled contour gradient would be artificial; the point map is shown instead.")
                                        st.plotly_chart(facility_point_spatial_figure(facility_model_df,"GFS_Rain3_mm","NOAA GFS · maximum 3-day rainfall at facilities","mm",facility_choice_code,basemap_name),use_container_width=True)
                                rain_bars=facility_two_model_bar_figure(
                                    facility_model_df,"ECMWF_Rain3_mm","GFS_Rain3_mm",
                                    f"{focus} · facility maximum 3-day rainfall · ECMWF vs NOAA GFS","mm",facility_choice_code
                                )
                                if rain_bars is not None:
                                    st.plotly_chart(rain_bars,use_container_width=True,config={"displayModeBar":True,"responsive":True})
                                st.plotly_chart(facility_point_spatial_figure(facility_model_df,"Rain3_ECMWF_minus_GFS_mm","Model difference at facilities · ECMWF minus NOAA GFS","mm",facility_choice_code,basemap_name,diverging=True),use_container_width=True)
                            comp_cols=[c for c in ["FacilityName","ECMWF_Tmax_C","GFS_Tmax_C","Tmax_ECMWF_minus_GFS_C","ECMWF_Rain3_mm","GFS_Rain3_mm","Rain3_ECMWF_minus_GFS_mm"] if c in facility_model_df]
                            with st.expander("Facility model-comparison values",expanded=False):
                                st.dataframe(facility_model_df[comp_cols],hide_index=True,use_container_width=True)
                            st.caption(f"Model data status: {facility_model_status}")
                    except Exception as exc:
                        print(f"Facility spatial comparison error: {type(exc).__name__}: {exc}")
                        st.warning("The facility spatial comparison could not be rendered for this view. Please refresh the online data or try another forecast selection.")

                st.download_button(
                    "Download facility forecast/exposure CSV",
                    facility_forecast_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"REACH_Facility_Forecast_{country}_{safe_file_part(focus)}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",use_container_width=True,key="download_facility_forecast_screen"
                )
                if country=="Zambia":
                    with st.expander("District HMIS context · uploaded REACH data",expanded=False):
                        render_pilot_hmis_context(focus)
            except Exception as exc:
                st.warning(f"Facility comparison screen could not be calculated for this view: {exc}. A selected facility can still use its point location in the detailed tabs below.")

    # -----------------------------------------------------------------------
    # Focus tabs: point-specific time series / hydrology / drivers / briefing
    # -----------------------------------------------------------------------
    meta=regions[regions.REGION_NAME==focus].iloc[0].copy()
    analysis_label=focus
    analysis_level="District" if country=="Zambia" else "Municipality"
    facility_stats={}
    if isinstance(facility_forecast_df,pd.DataFrame) and not facility_forecast_df.empty and "value" in facility_forecast_df:
        _fv=pd.to_numeric(facility_forecast_df["value"],errors="coerce").dropna()
        if len(_fv):
            facility_stats={
                "min":float(_fv.min()),"mean":float(_fv.mean()),"median":float(_fv.median()),
                "max":float(_fv.max()),"range":float(_fv.max()-_fv.min()),"n":int(len(_fv))
            }

    analysis_facility_id=""
    analysis_facility_type=""
    analysis_registry_source=""
    if selected_facility is not None:
        meta["rep_lat"]=float(selected_facility.rep_lat)
        meta["rep_lon"]=float(selected_facility.rep_lon)
        analysis_label=str(selected_facility.FacilityName)
        analysis_level="Health facility"
        analysis_facility_id=str(selected_facility.FacilityID)
        analysis_facility_type=_meaningful_facility_type(selected_facility.FacilityType) or "Health facility"
        analysis_registry_source=str(selected_facility.Source)
        st.markdown(
            f'<div class="facility-focus"><b>Facility forecast focus:</b> {analysis_label} · {analysis_facility_type} · '
            f'parent area: {focus} · coordinates: {float(meta.rep_lat):.5f}, {float(meta.rep_lon):.5f} · registry: {analysis_registry_source}. '
            f'The detailed forecast tabs below now use the facility coordinates.</div>',unsafe_allow_html=True
        )
    point_compare_prefetch=pd.DataFrame()
    point_compare_status_prefetch=""
    if horizon in ("Short range","Medium range") and hazard!="Flood – river discharge (GloFAS)":
        try:
            point_compare_prefetch,point_compare_status_prefetch=build_point_model_comparison(meta.rep_lat,meta.rep_lon,horizon,period)
            if not point_compare_prefetch.empty:
                st.markdown(f"#### Selected-location valid-period summary · {analysis_label}")
                st.caption(
                    f"Analysis level: {analysis_level} · parent area: {focus}. These statistics summarize the daily forecast values inside the selected valid window at the selected coordinate."
                )
                if hazard in ("Heatwave","Compound – Flood + Heatwave"):
                    for _label,_col in (("ECMWF IFS HRES","ECMWF_Tmax_C"),("NOAA GFS","GFS_Tmax_C")):
                        _v=pd.to_numeric(point_compare_prefetch[_col],errors="coerce").dropna()
                        if len(_v):
                            _c=st.columns(4)
                            _c[0].metric(f"{_label} · minimum",f"{_v.min():.1f} °C")
                            _c[1].metric(f"{_label} · mean",f"{_v.mean():.1f} °C")
                            _c[2].metric(f"{_label} · maximum",f"{_v.max():.1f} °C")
                            _c[3].metric(f"{_label} · range",f"{(_v.max()-_v.min()):.1f} °C")
                if hazard in ("Flood – rainfall","Compound – Flood + Heatwave","Drought / dry anomaly"):
                    for _label,_col in (("ECMWF IFS HRES","ECMWF_Precip_mm"),("NOAA GFS","GFS_Precip_mm")):
                        if _col in point_compare_prefetch:
                            _v=pd.to_numeric(point_compare_prefetch[_col],errors="coerce").dropna()
                            if len(_v):
                                _c=st.columns(4)
                                _c[0].metric(f"{_label} · minimum",f"{_v.min():.1f} mm/day")
                                _c[1].metric(f"{_label} · mean",f"{_v.mean():.1f} mm/day")
                                _c[2].metric(f"{_label} · maximum",f"{_v.max():.1f} mm/day")
                                _c[3].metric(f"{_label} · range",f"{(_v.max()-_v.min()):.1f} mm/day")
                    _et=float(pd.to_numeric(point_compare_prefetch.get("ECMWF_Precip_mm"),errors="coerce").sum()) if "ECMWF_Precip_mm" in point_compare_prefetch else np.nan
                    _gt=float(pd.to_numeric(point_compare_prefetch.get("GFS_Precip_mm"),errors="coerce").sum()) if "GFS_Precip_mm" in point_compare_prefetch else np.nan
                    st.caption(f"Valid-window precipitation totals · ECMWF {fmt(_et,'mm')} · NOAA GFS {fmt(_gt,'mm')}.")
        except Exception as exc:
            point_compare_status_prefetch=f"unavailable: {exc}"

    analysis_slug=safe_file_part(analysis_label)
    tabs=st.tabs(["Time series & uncertainty","River hydrology","Climate drivers","Health impact outlook","Decision-maker briefing","Documentation · return periods · SDM","Downloads · CSV / Stella","Forecast verification · REACH pilots"])

    focus_probs={}
    timing={}
    glofas_info=None

    # Export containers used by the Download Centre.
    focus_timeseries_exports=[]
    glofas_timeseries_export=pd.DataFrame()
    sdm_df=pd.DataFrame()
    rp_export=pd.DataFrame()
    rp_table_main=pd.DataFrame()
    rp_table_daily=pd.DataFrame()
    rp_result={}
    rp_levels_main={}

    with tabs[0]:
        st.markdown(f"### Forecast time series · {analysis_label}")
        if horizon in ("Short range","Medium range") and hazard!="Flood – river discharge (GloFAS)":
            try:
                point_compare_df=point_compare_prefetch.copy()
                point_compare_status=point_compare_status_prefetch
                if point_compare_df.empty:
                    point_compare_df,point_compare_status=build_point_model_comparison(meta.rep_lat,meta.rep_lon,horizon,period)
                if not point_compare_df.empty:
                    st.markdown("#### Deterministic model comparison and ERA5 historical context")
                    st.caption(
                        "ECMWF IFS HRES and NOAA GFS are current forecasts at the selected district/municipality or facility coordinate. "
                        "ERA5 is shown as 1981–2014 historical climatology/threshold context for the same calendar days; it is not a future observation. "
                        "For past-event skill, use Forecast verification."
                    )
                    cmp_fig=point_model_comparison_figure(point_compare_df,hazard,analysis_label)
                    if cmp_fig is not None:
                        st.plotly_chart(cmp_fig,use_container_width=True,config={"displayModeBar":True,"responsive":True})
                    show_cols=[c for c in ["ECMWF_Tmax_C","GFS_Tmax_C","ERA5_Tmax_Clim_C","ERA5_TX90_C","ECMWF_Tmax_Anomaly_C","GFS_Tmax_Anomaly_C",
                                                    "ECMWF_Precip_mm","GFS_Precip_mm","ERA5_Precip_Clim_mm","ERA5_Precip_P95_mm","ECMWF_Precip_Anomaly_mm","GFS_Precip_Anomaly_mm"] if c in point_compare_df]
                    with st.expander("Daily model-comparison values",expanded=False):
                        table=point_compare_df[show_cols].copy(); table.index.name="Date"
                        st.dataframe(table.reset_index(),hide_index=True,use_container_width=True)
                    export_cmp=point_compare_df.reset_index().rename(columns={"index":"Date"})
                    export_cmp["Country"]=country
                    export_cmp["Area"]=analysis_label
                    export_cmp["ParentArea"]=focus
                    export_cmp["AnalysisLevel"]=analysis_level
                    export_cmp["ForecastSystem"]="ECMWF IFS HRES + NOAA GFS + ERA5 climatology"
                    focus_timeseries_exports.append(export_cmp)
                    st.caption(f"Current model data status: {point_compare_status}")
            except Exception as exc:
                st.info(f"Deterministic ECMWF/GFS/ERA5 comparison is temporarily unavailable: {exc}")
            try:
                tx90,p95,_=focus_baseline(meta.rep_lat,meta.rep_lon)
                s,e=daily_slice(horizon,period)
                cc=st.columns(2)
                for j,system in enumerate(["ECMWF IFS ENS","NOAA GEFS"]):
                    try:
                        t,p,_=focus_ensemble(meta.rep_lat,meta.rep_lon,system)

                        # Preserve a tidy daily ensemble-summary table for end-user download.
                        ts_idx = t.index.union(p.index).sort_values()
                        ts_export = pd.DataFrame({"Date": ts_idx})
                        ts_export["Country"] = country
                        ts_export["Area"] = analysis_label
                        ts_export["ParentArea"] = focus
                        ts_export["AnalysisLevel"] = analysis_level
                        ts_export["ForecastSystem"] = system
                        if not t.empty:
                            ts_export["Tmax_P10_C"] = t.reindex(ts_idx).quantile(.10,axis=1).to_numpy()
                            ts_export["Tmax_P50_C"] = t.reindex(ts_idx).median(axis=1).to_numpy()
                            ts_export["Tmax_P90_C"] = t.reindex(ts_idx).quantile(.90,axis=1).to_numpy()
                        if not p.empty:
                            ts_export["Precip_P10_mm_day"] = p.reindex(ts_idx).quantile(.10,axis=1).to_numpy()
                            ts_export["Precip_P50_mm_day"] = p.reindex(ts_idx).median(axis=1).to_numpy()
                            ts_export["Precip_P90_mm_day"] = p.reindex(ts_idx).quantile(.90,axis=1).to_numpy()
                        focus_timeseries_exports.append(ts_export)

                        if hazard in ("Heatwave","Compound – Flood + Heatwave"):
                            hp=local_heat_prob(t,tx90,s,e); focus_probs[system+"_heat"]=hp
                        else: hp=np.nan
                        if hazard in ("Flood – rainfall","Compound – Flood + Heatwave"):
                            rp=local_rain_prob(p,p95,s,e); focus_probs[system+"_rain"]=rp
                        else: rp=np.nan

                        with cc[j]:
                            if hazard=="Heatwave":
                                med=t.median(axis=1);lo=t.quantile(.10,axis=1);hi=t.quantile(.90,axis=1)
                                st.metric(f"{system} heatwave probability","—" if not np.isfinite(hp) else f"{hp:.0f}%")
                                fig=go.Figure()
                                fig.add_trace(go.Scatter(x=med.index,y=hi,line=dict(width=0),showlegend=False))
                                fig.add_trace(go.Scatter(x=med.index,y=lo,fill="tonexty",line=dict(width=0),name="10–90%"))
                                fig.add_trace(go.Scatter(x=med.index,y=med,mode="lines+markers",name="Median Tmax"))
                                fig.update_layout(height=310,yaxis_title="Tmax (°C)",margin=dict(l=20,r=10,t=25,b=20))
                                st.plotly_chart(fig,use_container_width=True)
                            elif hazard=="Flood – rainfall":
                                med=p.median(axis=1);hi=p.quantile(.90,axis=1)
                                st.metric(f"{system} heavy-rain probability","—" if not np.isfinite(rp) else f"{rp:.0f}%")
                                fig=go.Figure()
                                fig.add_trace(go.Bar(x=med.index,y=med,name="Median rain"))
                                fig.add_trace(go.Scatter(x=hi.index,y=hi,mode="lines+markers",name="90th percentile member"))
                                fig.update_layout(height=310,yaxis_title="mm/day",margin=dict(l=20,r=10,t=25,b=20))
                                st.plotly_chart(fig,use_container_width=True)
                            else:
                                cp=min(hp,rp) if np.isfinite(hp) and np.isfinite(rp) else np.nan
                                focus_probs[system+"_compound"]=cp
                                st.metric(f"{system} compound screening","—" if not np.isfinite(cp) else f"{cp:.0f}%")
                                st.caption(f"Heat {hp:.0f}% · heavy rain {rp:.0f}%." if np.isfinite(hp) and np.isfinite(rp) else "Component probability unavailable.")
                    except Exception as exc:
                        with cc[j]:st.warning(f"{system}: {exc}")

                # Exact deterministic timing.
                temp_hr,rain_hr,_=focus_hourly(meta.rep_lat,meta.rep_lon,det_source)
                idx=temp_hr.index if len(temp_hr) else rain_hr.index
                start,end=exact_window(idx,horizon,period)
                timing={"start":start,"end":end}
                if hazard in ("Heatwave","Compound – Flood + Heatwave"):
                    z=temp_hr[(temp_hr.index>=start)&(temp_hr.index<=end)].dropna()
                    if len(z):
                        timing["heat_peak_time"]=z.idxmax();timing["heat_peak"]=float(z.max())
                if hazard in ("Flood – rainfall","Compound – Flood + Heatwave"):
                    z=rain_hr[(rain_hr.index>=start-pd.Timedelta(hours=71))&(rain_hr.index<=end)].fillna(0)
                    r72=z.rolling(72,min_periods=72).sum()
                    valid=r72[(r72.index>=start)&(r72.index<=end)].dropna()
                    if len(valid):
                        pe=valid.idxmax();timing["rain72_start"]=pe-pd.Timedelta(hours=71);timing["rain72_end"]=pe;timing["rain72"]=float(valid.max())
                st.caption(f"Valid window: {fmt_dt(start)} to {fmt_dt(end)}.")
            except Exception as exc:
                st.warning(f"Focus ensemble/time-series data unavailable: {exc}")

        elif horizon in ("Sub-seasonal","Seasonal"):
            if selected_facility is not None:
                facility_point_record={
                    "REGION_CODE":str(facility_choice_code),"REGION_NAME":analysis_label,"ADMIN1":focus,
                    "rep_lat":float(meta.rep_lat),"rep_lon":float(meta.rep_lon)
                }
                focus_long_data,_focus_long_status=regional_long([facility_point_record])
                x=focus_long_data.get(str(facility_choice_code),{})
            else:
                focus_long_data=payload.get("long",{}) if isinstance(payload,dict) else {}
                x=focus_long_data.get(str(meta.REGION_CODE),{})
            section,sl=long_slice(period)
            tm=x.get(f"{section}_temp",pd.Series(dtype=float))
            pm=x.get(f"{section}_precip",pd.Series(dtype=float))

            long_idx = tm.index.union(pm.index).sort_values()
            if len(long_idx):
                long_export = pd.DataFrame({"Date": long_idx})
                long_export["Country"] = country
                long_export["Area"] = analysis_label
                long_export["ParentArea"] = focus
                long_export["AnalysisLevel"] = analysis_level
                long_export["ForecastSystem"] = "ECMWF EC46/SEAS5"
                long_export["Aggregation"] = section
                long_export["TemperatureAnomaly_C"] = tm.reindex(long_idx).to_numpy()
                long_export["PrecipitationAnomaly_mm"] = pm.reindex(long_idx).to_numpy()
                focus_timeseries_exports.append(long_export)

            c1,c2=st.columns(2)
            with c1:
                if len(tm):
                    fig=go.Figure(go.Scatter(x=tm.index,y=tm,mode="lines+markers",name="Temperature anomaly"))
                    fig.add_hline(y=0,line_dash="dash")
                    fig.update_layout(height=310,yaxis_title="°C anomaly",margin=dict(l=20,r=10,t=25,b=20))
                    st.plotly_chart(fig,use_container_width=True)
            with c2:
                if len(pm):
                    fig=go.Figure(go.Bar(x=pm.index,y=pm,name="Precipitation anomaly"))
                    fig.add_hline(y=0,line_dash="dash")
                    fig.update_layout(height=310,yaxis_title="Precipitation anomaly (mm)",margin=dict(l=20,r=10,t=25,b=20))
                    st.plotly_chart(fig,use_container_width=True)
            chosen=(tm if hazard in ("Heatwave","Compound – Drought + Heatwave") else pm).iloc[sl]
            if len(chosen):
                timing={"start":chosen.index.min(),"end":chosen.index.max()+ (pd.Timedelta(days=6) if section=="weekly" else pd.offsets.MonthEnd(0)),
                        "peak_time":chosen.abs().idxmax(),"peak_value":float(chosen.loc[chosen.abs().idxmax()])}
            st.info("Long-range time series are weekly/monthly anomaly outlooks; the dashboard does not invent an exact event hour months ahead.")
        else:
            st.info("Use the River hydrology tab for discharge time series.")

    with tabs[1]:
        st.markdown("### GloFAS river-flow forecast")
        if hazard=="Heatwave":
            st.info("River discharge is not part of the selected heatwave hazard.")
        else:
            pilot=PILOT.get((country,focus))
            if selected_facility is not None:
                seed_lat=float(meta.rep_lat); seed_lon=float(meta.rep_lon)
            else:
                seed_lat=pilot["river_seed_lat"] if pilot else float(meta.rep_lat)
                seed_lon=pilot["river_seed_lon"] if pilot else float(meta.rep_lon)
            try:
                best,_=select_glofas_cell(seed_lat,seed_lon)
                q,_=focus_glofas(best["used_lat"],best["used_lon"])
                hist,_=focus_glofas_history(best["used_lat"],best["used_lon"])
                levels=q_levels(hist);s,e=discharge_slice(horizon,period)
                med=q.median(axis=1);lo=q.quantile(.10,axis=1);hi=q.quantile(.90,axis=1)

                glofas_timeseries_export = pd.DataFrame({
                    "Date": med.index,
                    "Country": country,
                    "Area": analysis_label,
                    "ParentArea": focus,
                    "AnalysisLevel": analysis_level,
                    "ForecastSystem": "GloFAS",
                    "Discharge_P10_m3_s": lo.to_numpy(),
                    "Discharge_P50_m3_s": med.to_numpy(),
                    "Discharge_P90_m3_s": hi.to_numpy(),
                })

                b=med.iloc[s:min(e,len(med))];qst=stat_summary(b)
                peak=b.idxmax() if len(b.dropna()) else None
                p2=exceed_prob(q,levels.get(2,np.nan),s,e);p5=exceed_prob(q,levels.get(5,np.nan),s,e);p20=exceed_prob(q,levels.get(20,np.nan),s,e)
                fig=go.Figure()
                fig.add_trace(go.Scatter(x=med.index,y=hi,line=dict(width=0),showlegend=False))
                fig.add_trace(go.Scatter(x=med.index,y=lo,fill="tonexty",line=dict(width=0),name="10–90% ensemble"))
                fig.add_trace(go.Scatter(x=med.index,y=med,mode="lines",name="Median discharge"))
                for rr in (2,5,20):
                    if rr in levels:fig.add_hline(y=levels[rr],line_dash="dot",annotation_text=f"Q{rr}")
                fig.update_layout(height=360,yaxis_title="m³/s",margin=dict(l=20,r=10,t=25,b=20))
                st.plotly_chart(fig,use_container_width=True)
                qc=st.columns(6)
                qc[0].metric("Mean",fmt(qst["mean"],"m³/s"));qc[1].metric("Median",fmt(qst["median"],"m³/s"))
                qc[2].metric("Maximum",fmt(qst["max"],"m³/s"));qc[3].metric("P(Q>Q2)","—" if not np.isfinite(p2) else f"{p2:.0f}%")
                qc[4].metric("P(Q>Q5)","—" if not np.isfinite(p5) else f"{p5:.0f}%");qc[5].metric("P(Q>Q20)","—" if not np.isfinite(p20) else f"{p20:.0f}%")
                st.caption(f"Peak ensemble-median discharge date: {fmt_dt(peak,False)} · selected GloFAS cell {best['used_lat']:.4f}, {best['used_lon']:.4f}.")
                valid=not (focus=="Senanga" and np.isfinite(qst["median"]) and qst["median"]<50)
                if not valid:st.error("Senanga river-cell sanity check failed; do not present this flow as final Upper Zambezi guidance until the LISFLOOD pixel is verified.")
                glofas_info={"valid":valid,"mean":qst["mean"],"median":qst["median"],"max":qst["max"],"peak":peak,"p2":p2,"p5":p5,"p20":p20}
            except Exception as exc:
                st.warning(f"GloFAS unavailable: {exc}")

    with tabs[2]:
        st.markdown("### Ocean–atmosphere climate context")
        dc=st.columns(4)
        with dc[0]:
            if enso_info:
                st.metric("ENSO / RONI",enso_info["phase"],f"{enso_info['prob']:.0f}% · {enso_info['season']}")
            else:st.metric("ENSO / RONI","Unavailable")
            st.caption("Pacific climate-state context; not a district hazard probability.")
        with dc[1]:
            if country=="Zambia":
                if dmi_info:st.metric("IOD / DMI",f"{dmi_info['value']:+.2f} °C",dmi_info["phase"])
                else:st.metric("IOD / DMI","Unavailable")
            else:
                if atlantic_info:st.metric("Tropical Atlantic gradient",f"{atlantic_info['gradient']:+.2f} °C",f"TNA {atlantic_info['tna']:+.2f} · TSA {atlantic_info['tsa']:+.2f}")
                else:st.metric("Tropical Atlantic gradient","Unavailable")
        with dc[2]:
            st.metric("NMME","Seasonal cross-check");st.link_button("NOAA NMME",NMME_URL,use_container_width=True)
        with dc[3]:
            if country=="Zambia":st.metric("ZMD","National interpretation");st.link_button("ZMD",ZMD_PRODUCTS,use_container_width=True)
            else:st.metric("Brazil operational sources","CEMADEN / APAC");st.link_button("APAC",APAC_URL,use_container_width=True)
        st.info("Climate indices modify seasonal interpretation; they are not direct damage variables and are not used as deterministic flood/heat triggers.")

        # ---------------------------------------------------------------
        # ENSO phase / strength / RONI outlook
        # ---------------------------------------------------------------
        st.markdown("### ENSO outlook · phase, strength and RONI anomaly")
        enso_tabs=st.tabs(["Phase probabilities","Strength probabilities","RONI anomaly outlook"])

        with enso_tabs[0]:
            try:
                enso_visual_df=enso_table()
                enso_fig,enso_plot_df=enso_probability_figure(enso_visual_df)
                st.plotly_chart(enso_fig,use_container_width=True)
                st.caption("NOAA CPC 3-month seasons: blue = La Niña, grey = Neutral, red = El Niño. The month in brackets is the central month.")
                phase_view=enso_plot_df[["Season code","Central month","La Niña","Neutral","El Niño","Dominant phase","Dominant probability (%)"]].rename(
                    columns={"La Niña":"La Niña (%)","Neutral":"Neutral (%)","El Niño":"El Niño (%)"}
                )
                st.dataframe(phase_view.style.format({
                    "La Niña (%)":"{:.1f}","Neutral (%)":"{:.1f}","El Niño (%)":"{:.1f}","Dominant probability (%)":"{:.1f}"
                },na_rep="—"),hide_index=True,use_container_width=True)
                st.download_button("Download ENSO phase probabilities CSV",phase_view.to_csv(index=False).encode("utf-8"),
                                   file_name=f"REACH_ENSO_Phase_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                                   mime="text/csv",use_container_width=True,key="download_enso_phase_csv")
            except Exception as exc:
                st.warning(f"ENSO phase outlook is temporarily unavailable: {exc}")

        with enso_tabs[1]:
            try:
                strength_df=enso_strength_table()
                strength_fig,strength_plot_df=enso_strength_figure(strength_df)
                st.plotly_chart(strength_fig,use_container_width=True)
                st.caption("Official NOAA CPC categories: Weak, Moderate, Strong and Very Strong La Niña/El Niño, plus Neutral. Strength does not guarantee local impact magnitude.")
                strength_view=_season_display_fields(strength_plot_df)[["Season code","Central month"]+ENSO_STRENGTH_COLUMNS]
                st.dataframe(strength_view.style.format({c:"{:.1f}" for c in ENSO_STRENGTH_COLUMNS},na_rep="—"),
                             hide_index=True,use_container_width=True)
                st.download_button("Download ENSO strength probabilities CSV",strength_view.to_csv(index=False).encode("utf-8"),
                                   file_name=f"REACH_ENSO_Strength_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                                   mime="text/csv",use_container_width=True,key="download_enso_strength_csv")
            except Exception as exc:
                st.warning(f"ENSO strength outlook is temporarily unavailable: {exc}")

        with enso_tabs[2]:
            try:
                roni_df=enso_roni_outlook_table()
                roni_fig,roni_plot_df=enso_roni_temporal_figure(roni_df)
                st.plotly_chart(roni_fig,use_container_width=True)
                roni_view=_season_display_fields(roni_plot_df)[["Season code","Central month","P25","P50","P75"]].copy()
                roni_view["Median strength class"]=[enso_strength_class(v) for v in pd.to_numeric(roni_view["P50"],errors="coerce")]
                st.dataframe(roni_view.style.format({"P25":"{:+.2f}","P50":"{:+.2f}","P75":"{:+.2f}"},na_rep="—"),
                             hide_index=True,use_container_width=True)
                st.caption("Red/blue fill = forecast median RONI anomaly; grey envelope = 25–75% range; horizontal thresholds define ENSO strength categories.")
                st.download_button("Download RONI outlook CSV",roni_view.to_csv(index=False).encode("utf-8"),
                                   file_name=f"REACH_RONI_Outlook_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                                   mime="text/csv",use_container_width=True,key="download_roni_outlook_csv")
            except Exception as exc:
                st.warning(f"RONI anomaly outlook is temporarily unavailable: {exc}")

        # ---------------------------------------------------------------
        # Seasonal / sub-seasonal temporal + spatial anomaly visualisation
        # ---------------------------------------------------------------
        st.markdown("### Forecast anomaly visualisation")
        if horizon not in ("Sub-seasonal","Seasonal"):
            st.info("Select **Sub-seasonal** or **Seasonal** to activate linked temporal and spatial anomaly views.")
        else:
            av1,av2,av3=st.columns([1.15,1,1])
            with av1:
                anomaly_view=st.radio("Display",["Temporal + spatial","Temporal only","Spatial only"],
                                      horizontal=True,key="seasonal_anomaly_view_final")
            with av2:
                temporal_style=st.selectbox("Temporal style",["Filled anomaly time series","Bar plot"],
                                            key="seasonal_temporal_style")
            with av3:
                anomaly_variable=st.selectbox("Anomaly variable",["Temperature anomaly","Precipitation anomaly"],
                                              key="seasonal_anomaly_variable_final")

            spatial_long_data=payload.get("long",{}) if isinstance(payload,dict) else {}
            long_status_for_view=map_status if "map_status" in locals() else ""
            if not spatial_long_data:
                try:
                    with st.spinner("Loading seasonal anomaly fields..."):
                        spatial_long_data,long_status_for_view=regional_long(regions.to_dict("records"))
                except Exception as exc:
                    spatial_long_data={}
                    st.warning(f"Seasonal anomaly data are temporarily unavailable: {exc}")

            temporal_long_data=spatial_long_data
            temporal_focus_code=str(meta.REGION_CODE)
            if selected_facility is not None:
                try:
                    facility_point_record={
                        "REGION_CODE":str(facility_choice_code),"REGION_NAME":analysis_label,"ADMIN1":focus,
                        "rep_lat":float(meta.rep_lat),"rep_lon":float(meta.rep_lon)
                    }
                    temporal_long_data,_facility_long_status=regional_long([facility_point_record])
                    temporal_focus_code=str(facility_choice_code)
                except Exception:
                    temporal_long_data=spatial_long_data
                    temporal_focus_code=str(meta.REGION_CODE)

            if spatial_long_data:
                s_anom=_seasonal_anomaly_series(temporal_long_data,temporal_focus_code,horizon,anomaly_variable)
                if s_anom.empty:
                    st.info("No anomaly series is available for the selected focus area.")
                else:
                    valid_label=seasonal_valid_label(s_anom,horizon,period)
                    st.markdown(
                        f'<div class="hoverhint"><b>Selected forecast period:</b> {valid_label} · '
                        f'<b>Variable:</b> {anomaly_variable} · <b>Forecast point:</b> {analysis_label} · <b>Parent area:</b> {focus}</div>',
                        unsafe_allow_html=True
                    )

                    if anomaly_view in ("Temporal + spatial","Temporal only"):
                        st.markdown("#### Temporal anomaly outlook")
                        if temporal_style=="Filled anomaly time series":
                            fig,meaning=seasonal_anomaly_filled_figure(s_anom,anomaly_variable,analysis_label,horizon,period)
                        else:
                            fig,meaning=seasonal_anomaly_bar_figure(s_anom,anomaly_variable,analysis_label,horizon,period)
                        st.plotly_chart(fig,use_container_width=True)
                        sm_anom=stat_summary(s_anom)
                        unit_anom="°C" if anomaly_variable=="Temperature anomaly" else "mm"
                        ac=st.columns(4)
                        ac[0].metric("Minimum",fmt(sm_anom["min"],unit_anom))
                        ac[1].metric("Mean",fmt(sm_anom["mean"],unit_anom))
                        ac[2].metric("Median",fmt(sm_anom["median"],unit_anom))
                        ac[3].metric("Maximum",fmt(sm_anom["max"],unit_anom))
                        st.caption(f"{meaning}. Anomalies are relative to the forecast-system climatology; they are not event probabilities.")
                        series_export=pd.DataFrame({
                            "Date":s_anom.index,
                            "ForecastMonthOrPeriod":[pd.Timestamp(x).strftime("%B %Y") if horizon=="Seasonal" else pd.Timestamp(x).strftime("%d %b %Y") for x in s_anom.index],
                            "Country":country,"Area":analysis_label,"ParentArea":focus,"AnalysisLevel":analysis_level,"Horizon":horizon,"Variable":anomaly_variable,
                            "AnomalyValue":s_anom.to_numpy(float),"Unit":unit_anom,
                            "Source":"ECMWF EC46 / SEAS5 via Open-Meteo seasonal API"
                        })
                        st.download_button("Download temporal anomaly CSV",series_export.to_csv(index=False).encode("utf-8"),
                                           file_name=f"REACH_Anomaly_Temporal_{country}_{analysis_slug}_{anomaly_variable.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                                           mime="text/csv",use_container_width=True,key="download_temporal_anomaly_csv")

                    if anomaly_view in ("Temporal + spatial","Spatial only"):
                        st.markdown("#### Spatial anomaly outlook")
                        anomaly_map_df=seasonal_anomaly_map_data(regions,spatial_long_data,period,anomaly_variable)
                        fig,meaning=seasonal_anomaly_map_figure(
                            geo,anomaly_map_df,anomaly_variable,focus,horizon,period,"ECMWF EC46 / SEAS5",
                            basemap_name=basemap_name,layer_opacity=layer_opacity,valid_label=valid_label
                        )
                        st.plotly_chart(fig,use_container_width=True,
                                       config={"displayModeBar":True,"scrollZoom":True,"responsive":True})
                        st.caption(f"{meaning}. Horizontal colour scale is centred on zero. Basemap: {basemap_name}.")
                        map_export=anomaly_map_df[["REGION_CODE","REGION_NAME","ADMIN1","rep_lat","rep_lon","value"]].copy()
                        map_export["Country"]=country; map_export["Horizon"]=horizon; map_export["ValidPeriod"]=valid_label
                        map_export["Variable"]=anomaly_variable; map_export["Unit"]="°C" if anomaly_variable=="Temperature anomaly" else "mm"
                        map_export["Source"]="ECMWF EC46 / SEAS5 via Open-Meteo seasonal API"
                        st.download_button("Download spatial anomaly CSV",map_export.to_csv(index=False).encode("utf-8"),
                                           file_name=f"REACH_Spatial_Anomaly_{country}_{anomaly_variable.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                                           mime="text/csv",use_container_width=True,key="download_spatial_anomaly_csv_final")

                    st.caption(f"Forecast source status: {long_status_for_view}. Temporal and spatial panels are linked to the same selection.")

        st.markdown("### Forecast evidence and convergence")
        st.caption(
            "A professional forecast briefing should show both agreement and disagreement across sources. "
            "Model disagreement is decision-relevant information rather than something to hide."
        )

        if horizon in ("Short range","Medium range"):
            if hazard=="Heatwave":
                pa=focus_probs.get("ECMWF IFS ENS_heat",np.nan); pb=focus_probs.get("NOAA GEFS_heat",np.nan)
                signal_name="heatwave probability"
            elif hazard=="Flood – rainfall":
                pa=focus_probs.get("ECMWF IFS ENS_rain",np.nan); pb=focus_probs.get("NOAA GEFS_rain",np.nan)
                signal_name="heavy-rain probability"
            elif hazard=="Compound – Flood + Heatwave":
                pa=focus_probs.get("ECMWF IFS ENS_compound",np.nan); pb=focus_probs.get("NOAA GEFS_compound",np.nan)
                signal_name="compound screening signal"
            else:
                pa=pb=np.nan; signal_name="selected signal"

            if np.isfinite(pa) and np.isfinite(pb):
                diff=abs(pa-pb)
                if diff <= 10:
                    agreement="Strong agreement"
                elif diff <= 25:
                    agreement="Broad agreement"
                else:
                    agreement="Mixed signal / material disagreement"
                ccx=st.columns(3)
                ccx[0].metric("ECMWF ensemble",f"{pa:.0f}%")
                ccx[1].metric("NOAA GEFS",f"{pb:.0f}%")
                ccx[2].metric("Evidence convergence",agreement,f"{diff:.0f} percentage-point difference")
                st.caption(
                    f"Comparison is for the focus-area {signal_name}. Agreement does not remove forecast uncertainty; "
                    "it indicates whether two ensemble systems point in a similar direction."
                )
            else:
                st.info("A numeric two-model convergence score is not available for the selected hazard/view.")
        else:
            st.info(
                "Seasonal evidence is interpreted as a hierarchy: national authority products + ECMWF seasonal guidance + "
                "NMME cross-check + large-scale climate drivers. The portal does not manufacture a consensus percentage "
                "unless comparable tercile probabilities from each source have been ingested."
            )

        hierarchy = pd.DataFrame([
            ["1 · National / operational authority",
             "Country meteorological, hydrological and hazard-monitoring services",
             "Primary operational interpretation and official warning context."],
            ["2 · Dynamical forecast",
             "ECMWF IFS/ENS/EC46/SEAS5 and NOAA GFS/GEFS",
             "Physical forecast magnitude, probability and uncertainty."],
            ["3 · Hydrological evidence",
             "GloFAS plus local river/gauge information where available",
             "River-flow severity and return-period exceedance."],
            ["4 · Seasonal cross-check",
             "NMME and other multi-model seasonal products",
             "Checks whether the seasonal signal is consistent across systems."],
            ["5 · Climate-driver context",
             "ENSO/RONI, IOD/DMI, TNA/TSA and related indices",
             "Explains large-scale background; not used as a stand-alone local warning trigger."],
        ],columns=["Evidence level","Examples","Role"])
        st.dataframe(hierarchy,hide_index=True,use_container_width=True)

    with tabs[3]:
        st.markdown(f"### Health impact outlook · {analysis_label}")
        st.caption(
            "This page links the selected weather/climate forecast to plausible health-system and population-health pathways. "
            "It is a transparent screening layer, not a clinical diagnosis, disease-case forecast or validated prediction of service utilisation. "
            "Health outcomes should be upgraded to quantitative forecasts only after calibration against suitable surveillance/HMIS data."
        )
        _mapvals=pd.to_numeric(map_df.get("value",pd.Series(dtype=float)),errors="coerce") if isinstance(map_df,pd.DataFrame) else pd.Series(dtype=float)
        _facvals=(pd.to_numeric(facility_forecast_df.get("value",pd.Series(dtype=float)),errors="coerce")
                  if isinstance(facility_forecast_df,pd.DataFrame) else pd.Series(dtype=float))
        _selected_for_health=selected_facility_value if selected_facility is not None and np.isfinite(selected_facility_value) else fv
        _ho=health_impact_outlook(hazard,horizon,mode,_selected_for_health,_mapvals,_facvals)
        _hc=st.columns(5)
        _hc[0].metric("Forecast horizon",HORIZONS[horizon]["window"])
        _hc[1].metric("Health-screening status",_ho["level"])
        _hc[2].metric("Selected location",analysis_label)
        _hc[3].metric("Hazard signal",fmt(_selected_for_health,selected_facility_unit if selected_facility is not None else unit_for(hazard,horizon,mode)))
        _hc[4].metric("Higher-signal facilities",f"{_ho['exposed_facilities']} / {_ho['facility_n']}" if _ho['facility_n'] else "—")
        st.markdown(
            f'<div class="summary"><b>What this means now</b><br>{_ho["action"]}<br><br>'
            f'<b>Forecast period:</b> {period_display_label(horizon,period)}. '
            f'<b>Important:</b> “Routine” means no elevated <i>forecast-linked</i> signal in this screen; it does not mean that no illness, outbreak or service problem can occur.</div>',
            unsafe_allow_html=True,
        )
        h1,h2=st.columns(2,gap="large")
        with h1:
            st.markdown("#### Health-system access & continuity")
            st.write(_ho["pathways"]["system"])
            st.markdown("#### Maternal & child health services")
            st.write(_ho["pathways"]["mch"])
        with h2:
            st.markdown("#### General population health")
            st.write(_ho["pathways"]["population"])
            st.markdown("#### WASH / infectious-disease pathway")
            st.write(_ho["pathways"]["wash"])
        st.markdown("#### How the health link is calculated")
        st.write(
            "The current health-screening status uses the selected forecast signal and its position within the mapped forecast distribution, "
            "then applies hazard-specific exposure and service-continuity pathways. It does **not** infer case numbers. "
            "The next analytical step is to estimate and validate hazard–health response functions using historical HMIS/surveillance data, "
            "then use those calibrated models to forecast outcomes with uncertainty."
        )
        if country=="Zambia" and focus in ("Senanga","Sinazongwe"):
            st.markdown("#### Historical health-service context · uploaded REACH HMIS")
            st.caption(
                "The uploaded district-month HMIS series can be used as historical outcome/context data for model development. "
                "It is not a live facility-level feed and is therefore not presented as a real-time outcome forecast."
            )
            render_pilot_hmis_context(focus)
        elif country=="Brazil":
            st.markdown("#### Health-data connection status · Brazil")
            st.info(
                "The current deployed package has facility registry/geography for Brazil, but no validated live epidemiological or service-utilisation feed is yet connected to this forecast screen. "
                "A future adapter can connect official Brazilian health datasets and calibrate hazard–health relationships; until then, the dashboard reports pathways and preparedness implications rather than invented disease counts."
            )
        st.markdown("#### Recommended analytical architecture")
        st.markdown(
            "**Forecast hazard → population/facility exposure → access/readiness mediators → health-service utilisation/continuity → population-health outcomes.** "
            "Keep each layer explicit so users can see which outputs are directly observed, forecast, modelled or only screened."
        )

    with tabs[4]:
        st.markdown("### Decision-maker briefing")
        if map_df.empty:
            base_summary="Spatial forecast unavailable."
        else:
            unit=unit_for(hazard,horizon,mode)
            max_area=maxrow.REGION_NAME if maxrow is not None else "—"
            window=""
            if timing.get("start") is not None:
                window=f"The selected forecast/outlook window runs from {fmt_dt(timing.get('start'),horizon in ('Short range','Medium range'))} to {fmt_dt(timing.get('end'),horizon in ('Short range','Medium range'))}."
            peak=""
            if timing.get("heat_peak_time") is not None:
                peak=f"Peak hourly temperature at {analysis_label} is {fmt(timing.get('heat_peak',np.nan),'°C')} at {fmt_dt(timing.get('heat_peak_time'))}."
            if timing.get("rain72_start") is not None:
                peak+=f" The wettest 72-hour window at {analysis_label} is {fmt_dt(timing.get('rain72_start'))} to {fmt_dt(timing.get('rain72_end'))}, with {fmt(timing.get('rain72',np.nan),'mm / 72 h')}."
            if horizon in ("Sub-seasonal","Seasonal") and timing.get("peak_time") is not None:
                peak=f"The strongest selected anomaly period is around {fmt_dt(timing.get('peak_time'),False)} ({fmt(timing.get('peak_value',np.nan),unit)}). This is not an exact event date."

            interpretation=""
            if hazard=="Heatwave":
                interpretation="Higher temperature or warm-anomaly signals indicate increased heat concern; a focus-area heatwave probability is based on the local TX90 >=3-day event definition."
            elif hazard=="Flood – rainfall":
                interpretation="Rainfall accumulation is a flood precursor, not flood depth. Interpret it with antecedent wetness, runoff, river state and infrastructure exposure."
            elif hazard=="Flood – river discharge (GloFAS)":
                interpretation="River discharge is expressed in m³/s. For riverine sites, concern increases when ensemble flow approaches or exceeds local Q2/Q5/Q20 screening levels."
            elif hazard=="Drought / dry anomaly":
                interpretation="Negative precipitation anomaly means drier than the model climatology; it is not by itself a complete drought diagnosis."
            elif hazard=="Compound – Flood + Heatwave":
                interpretation="The compound map is an overlap screening score using the lower component signal. It is not a statistically estimated joint probability."
            elif hazard=="Compound – Drought + Heatwave":
                interpretation="The compound map screens for simultaneous warm and dry seasonal conditions using positive temperature and negative precipitation anomalies."
            else:
                interpretation="The sequential compound map screens for a drier first part of the forecast window followed by a wetter second part; it is not a joint probability."

            drivers=""
            if enso_info:drivers+=f" ENSO background: {enso_info['phase']} ({enso_info['prob']:.0f}% for {enso_info['season']})."
            if country=="Zambia" and dmi_info:drivers+=f" DMI {dmi_info['value']:+.2f} °C ({dmi_info['phase']})."
            if country=="Brazil" and atlantic_info:drivers+=f" Tropical Atlantic TNA−TSA gradient {atlantic_info['gradient']:+.2f} °C."
            drivers+=" These indices provide seasonal context rather than direct local hazard probabilities."

            hyd=""
            if glofas_info and glofas_info.get("valid"):
                hyd=f" GloFAS point-specific median discharge is {fmt(glofas_info['median'],'m³/s')}, maximum {fmt(glofas_info['max'],'m³/s')}, peak date {fmt_dt(glofas_info['peak'],False)}, with P(Q>Q2) {glofas_info['p2']:.0f}%."
            elif glofas_info and not glofas_info.get("valid"):
                hyd=" The selected GloFAS river cell failed the sanity check and should not be presented as final river guidance."

            facility_brief=""
            if selected_facility is not None:
                facility_signal=(fmt(selected_facility_value,selected_facility_unit) if np.isfinite(selected_facility_value) else "comparison value unavailable")
                _fstats=""
                if facility_stats:
                    _fstats=(
                        f" Across {facility_stats.get('n',0)} mapped facilities evaluated under {focus}, the forecast values range from "
                        f"{fmt(facility_stats.get('min',np.nan),selected_facility_unit)} to {fmt(facility_stats.get('max',np.nan),selected_facility_unit)}, "
                        f"with mean {fmt(facility_stats.get('mean',np.nan),selected_facility_unit)} and median {fmt(facility_stats.get('median',np.nan),selected_facility_unit)}."
                    )
                facility_brief=(
                    f"**Facility drill-down:** {analysis_label} ({analysis_facility_type}) is nested under {focus}. "
                    f"The facility-coordinate hazard/exposure signal is {facility_signal}.{_fstats} "
                    "Facility values are point-specific model samples; the spatial contour is a visual interpolation only. "
                    "This does not by itself represent operational readiness or service-disruption risk.\n\n"
                )
            base_summary=(
                f"**{country} · {horizon} · {hazard}**\n\n"
                f"**Forecast window:** {window}\n\n"
                f"**Spatial result:** Selected parent area **{focus}** has a representative-point forecast value of {fmt(fv,unit)}. "
                f"Across {len(map_df)} mapped administrative areas, values range from {fmt(sm['min'],unit)} to {fmt(sm['max'],unit)} "
                f"(range width {fmt(sm['max']-sm['min'],unit)}), with mean {fmt(sm['mean'],unit)} and median {fmt(sm['median'],unit)}. "
                f"The highest mapped signal is in **{max_area}**.\n\n"
                f"{facility_brief}"
                f"**Timing:** {peak}\n\n"
                f"**Interpretation:** {interpretation}{drivers}{hyd}\n\n"
                f"**Health-system implication:** {HORIZONS[horizon]['action']}"
            )

        st.markdown('<div class="summary">',unsafe_allow_html=True);st.markdown(base_summary);st.markdown("</div>",unsafe_allow_html=True)
        b1,b2=st.columns([1,2])
        with b1:
            engine=st.selectbox("Briefing engine",["Transparent verified summary","Optional local AI rewrite (Ollama)"])
            model=st.text_input("Local Ollama model",value="llama3.2:3b",disabled=engine.startswith("Transparent"))
            if engine.startswith("Optional") and st.button("Generate local-AI rewrite",use_container_width=True):
                try:st.session_state["v5_ai"]=local_ai_rewrite(base_summary,model)
                except Exception as exc:st.warning(f"Local AI unavailable: {exc}")
        with b2:
            editable=st.text_area("Editable briefing",value=st.session_state.get("v5_ai",base_summary) if engine.startswith("Optional") else base_summary,height=260)
            st.download_button("Download briefing",editable.encode(),file_name=f"REACH_EWS_{country}_{analysis_slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",mime="text/plain",use_container_width=True)


    with tabs[5]:
        st.markdown("## Documentation, return periods and system-dynamics integration")
        st.caption(
            "This section explains national spatial coverage, the nested district/municipality → facility workflow, data provenance, interpretation, return periods and how forecast information is transferred into the REACH System Dynamics Model (Stella)."
        )
        st.markdown(
            """
### Portal architecture · one connected decision journey

**Monitor → Locate → Compare → Health impact → Act → Verify**

The dashboard is intentionally organised as a cascade rather than a set of independent charts. A selection made at the geography or forecast level is carried into the spatial map, facility drill-down, model comparison, hydrology/climate context, **Health impact outlook**, decision briefing, downloads and verification wherever the underlying data support that view. The health-impact layer distinguishes forecast exposure from observed health data and does not claim disease cases or service disruption unless a calibrated health model supports that output. Facility results remain nested under the selected district/municipality.

The backend follows a source-adapter → cache/retry → harmonisation → forecast analytics → decision/output pattern. This keeps source provenance explicit and allows fail-soft use of cached data when an upstream forecast service is temporarily unavailable.
"""
        )

        st.markdown("### 1 · Geographic and health-facility coverage")
        st.markdown(
            """
**Administrative forecast coverage**
- **Zambia:** all **116 districts** are available for district-level forecast screening.
- **Brazil:** all **5,572 municipalities** are available for municipality-level forecast screening.
- **REACH facility drill-down pilots:** **Senanga** and **Sinazongwe** in Zambia; **Recife** and **Palmares** in Brazil.

**How the hierarchy works**
- A health facility is always nested under its parent district/municipality.
- The district/municipality value is the model value sampled at the administrative area's representative point in the current workflow.
- A facility value is the same forecast sampled at the facility's own latitude/longitude.
- Facility minimum/mean/median/maximum/range statistics refer to the mapped facilities evaluated within the selected parent area; they are **not** the min/max over every grid cell in the district.
- Labelled contour maps are an inverse-distance visual interpolation of facility point values. The bars and facility table show the direct sampled values. Zambia shows facility names directly on the contour when readable; dense Brazil maps keep names on hover and label only the selected facility.
- Brazil CNES facility coordinates are checked against the selected municipality boundary before spatial analysis. Out-of-boundary/offshore records are excluded rather than moved or guessed, so they cannot distort the gradient.
- Every forecast map and facility gradient is explicitly time-qualified. Short/medium-range daily values show a UTC valid date (daily Tmax is a daily aggregate; rainfall uses a rolling 3-day accumulation ending on the selected date). Sub-seasonal and seasonal values use weekly/monthly valid windows.
- The user can switch the facility display between the original window summary and an individual valid day/week/month; that choice cascades to facility metrics, table, bar chart and contour gradient.
- A model **issue/run time** is shown only when the upstream API exposes it reliably. The current public adapters always show forecast-valid time and do not invent an issuance timestamp.
"""
        )
        project_counts=zambia_project_facility_counts()
        cov_rows=[
            {"Country":"Zambia","REACH pilot":"Senanga","Bundled REACH facility-detail records":project_counts.get("Senanga") or "—","Runtime mapped registry":"Shown live in selector"},
            {"Country":"Zambia","REACH pilot":"Sinazongwe","Bundled REACH facility-detail records":project_counts.get("Sinazongwe") or "—","Runtime mapped registry":"Shown live in selector"},
            {"Country":"Brazil","REACH pilot":"Recife","Bundled REACH facility-detail records":"—","Runtime mapped registry":"CNES live"},
            {"Country":"Brazil","REACH pilot":"Palmares","Bundled REACH facility-detail records":"—","Runtime mapped registry":"CNES live"},
        ]
        st.dataframe(pd.DataFrame(cov_rows),hide_index=True,use_container_width=True)
        st.caption(
            "The bundled Zambia facility-detail workbook currently lists 21 Senanga facilities and 32 Sinazongwe facilities when readable in the deployed environment. "
            "The number that can be mapped/forecast can differ because a facility must have usable coordinates in the active registry. Brazil facility totals are read live from CNES and can change as the registry is updated."
        )
        if (country,focus) in PILOT and not facility_registry.empty:
            st.info(f"Current active pilot: {focus} · {len(facility_registry):,} mapped facilities available in this session · registry status: {facility_status}.")

        if st.button("Load / refresh live facility counts for all four REACH pilots",key="doc_load_all_facility_counts"):
            with st.spinner("Reading Zambia NSDI and Brazil CNES facility registries..."):
                live_cov,zm_nat,zm_nat_status=all_pilot_live_facility_counts()
            st.session_state["doc_live_facility_coverage"]=live_cov
            st.session_state["doc_zm_national_facility_count"]=zm_nat
            st.session_state["doc_zm_national_facility_status"]=zm_nat_status
        if "doc_live_facility_coverage" in st.session_state:
            st.markdown("**Live mapped facility coverage · current registry response**")
            st.dataframe(st.session_state["doc_live_facility_coverage"],hide_index=True,use_container_width=True)
            _zn=st.session_state.get("doc_zm_national_facility_count")
            _zs=st.session_state.get("doc_zm_national_facility_status","")
            if _zn is not None:
                st.metric("Zambia national NSDI facility registry count",f"{int(_zn):,}")
                st.caption(f"National facility source status: {_zs}. The app intentionally enables facility-level forecast drill-down only for the two Zambia REACH pilot districts in this release.")
            else:
                st.caption(f"Zambia national facility count was not returned by the registry in this session ({_zs}).")

        st.markdown("### 2 · How to interpret district/municipality and facility values")
        st.markdown(
            f"""
- **Selected parent area:** **{focus}**. The current parent-area forecast is **{fmt(fv,unit)}**.
- **Administrative summary:** the national/state Spatial summary reports the minimum, mean, median, maximum and mapped range across the administrative areas displayed.
- **Facility summary:** when a pilot facility registry is available, the Health-facility section reports minimum, mean, median, maximum and range across the mapped facilities under the selected parent area.
- **Selected facility:** if a facility is chosen, the detailed tabs use that facility's coordinates. The facility is still nested under **{focus}**.
- **ECMWF vs NOAA GFS:** side-by-side spatial surfaces/bars show model agreement or disagreement at facility points.
- **ERA5:** in future-forecast comparisons, ERA5 is a 1981–2014 historical climatology/threshold reference for the same calendar days, not a future observation. Historical forecast skill against ERA5 is handled separately in Forecast verification.
- **Operational risk boundary:** a high hazard/exposure value does not automatically mean a facility will fail. Operational risk requires explicit access/readiness evidence such as roads, power, WASH, staffing, commodities/cold chain and service availability.
"""
        )

        st.markdown("### 3 · Return-period forecast for the selected area")
        trigger_rp = st.selectbox(
            "Model return-period threshold",
            [2, 5, 10, 20, 50, 100],
            index=2,
            key="sdm_trigger_rp",
            help="Research configuration for Stella: the action rule uses the forecast probability of exceeding the selected historical return-period level."
        )
        trigger_probability = st.slider(
            "Probability threshold for preparedness action (%)",
            10, 90, 50, 5,
            key="sdm_trigger_probability"
        )

        rp_result = {}
        rp_kind = ""
        rp_unit = ""
        rp_note = ""
        rp_levels_main = {}
        rp_table_main = pd.DataFrame()
        rp_table_daily = pd.DataFrame()
        rp_start = timing.get("start")
        rp_end = timing.get("end")

        try:
            if hazard == "Flood – river discharge (GloFAS)":
                pilot = PILOT.get((country, focus))
                if selected_facility is not None:
                    seed_lat=float(meta.rep_lat); seed_lon=float(meta.rep_lon)
                else:
                    seed_lat = pilot["river_seed_lat"] if pilot else float(meta.rep_lat)
                    seed_lon = pilot["river_seed_lon"] if pilot else float(meta.rep_lon)
                best, _ = select_glofas_cell(seed_lat, seed_lon)
                q, _ = focus_glofas(best["used_lat"], best["used_lon"])
                hist, _ = focus_glofas_history(best["used_lat"], best["used_lon"])
                levels = q_levels(hist)
                s, e = discharge_slice(horizon, period)
                peaks = q.iloc[s:min(e, len(q))].max(axis=0, skipna=True)
                rp_result = return_period_forecast(peaks, levels)
                rp_kind = "River discharge return-period severity (GloFAS/LISFLOOD)"
                rp_unit = "m³/s"
                rp_levels_main = levels
                rp_table_main = return_period_threshold_table(levels,rp_result,rp_unit,"Annual-maximum river discharge")
                rp_note = (
                    "For riverine flooding, this is the main return-period forecast. "
                    "GloFAS operational flood summaries use Q2, Q5 and Q20. The REACH modelling scheme also calculates Q10 and Q50 for scenario classification and stress testing."
                )
                if len(q.index):
                    rp_start = q.index[s] if s < len(q.index) else q.index[0]
                    rp_end = q.index[min(max(e-1,0), len(q.index)-1)]

            elif horizon in ("Short range", "Medium range") and hazard in ("Heatwave", "Flood – rainfall", "Compound – Flood + Heatwave"):
                hist, _ = focus_extreme_history(meta.rep_lat, meta.rep_lon)
                t, p, _ = focus_ensemble(meta.rep_lat, meta.rep_lon, ensemble_system)
                s, e = daily_slice(horizon, period)

                if hazard == "Heatwave":
                    levels = heat_return_levels_from_history(hist)
                    peaks = ensemble_peak_metric(t, p, "heat_tx3d", s, e)
                    rp_result = return_period_forecast(peaks, levels)
                    rp_kind = "Heat severity return-period equivalent: annual-max 3-day mean Tmax (TX3d)"
                    rp_unit = "°C"
                    rp_levels_main = levels
                    rp_table_main = return_period_threshold_table(levels,rp_result,rp_unit,"Annual-maximum 3-day mean Tmax (TX3d)")
                    rp_note = (
                        "This is used alongside the heatwave occurrence definition (Tmax above the local TX90 threshold for at least 3 consecutive days). "
                        "Return period describes rarity of heat severity, not the probability that the TX90 event occurs."
                    )

                elif hazard == "Flood – rainfall":
                    # Rx1day: direct daily precipitation thresholds for Stella (mm/day).
                    levels_1d = rainfall_1day_return_levels_from_history(hist)
                    peaks_1d = ensemble_peak_1day_precip(p,s,e)
                    rp_result_1d = return_period_forecast(peaks_1d,levels_1d)
                    rp_table_daily = return_period_threshold_table(levels_1d,rp_result_1d,"mm/day","Annual-maximum 1-day precipitation (Rx1day)")

                    # Rx3day: dashboard flood-warning accumulation metric (mm/3 days).
                    levels = rainfall_return_levels_from_history(hist)
                    peaks = ensemble_peak_metric(t, p, "rain3d", s, e)
                    rp_result = return_period_forecast(peaks, levels)
                    rp_kind = "3-day rainfall return-period proxy"
                    rp_unit = "mm / 3 days"
                    rp_levels_main = levels
                    rp_table_main = return_period_threshold_table(levels,rp_result,rp_unit,"Annual-maximum 3-day precipitation (Rx3day)")
                    rp_note = (
                        "For rainfall-driven/flash-flood settings this is a rainfall-rarity proxy, not yet a physical flood return period. "
                        "Use discharge, runoff or inundation depth for the final flood RP when those data are available."
                    )

                else:
                    hlev = heat_return_levels_from_history(hist)
                    rlev = rainfall_return_levels_from_history(hist)
                    hpeaks = ensemble_peak_metric(t, p, "heat_tx3d", s, e)
                    rpeaks = ensemble_peak_metric(t, p, "rain3d", s, e)
                    hrp = return_period_forecast(hpeaks, hlev)
                    rrp = return_period_forecast(rpeaks, rlev)
                    st.info(
                        "Compound Flood + Heatwave keeps two separate return-period forecasts. "
                        "A single weighted 'compound return period' is not calculated because it would require a defensible joint dependence model."
                    )
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Heat component**")
                        st.metric("Dominant RP class", hrp.get("dominant_class","—"))
                        st.metric("RP severity index", fmt(hrp.get("severity_index",np.nan),""))
                        st.metric(f"P(heat severity ≥ {trigger_rp}-y level)", fmt(hrp.get("prob_exceed",{}).get(trigger_rp,np.nan),"%"))
                    with c2:
                        st.markdown("**Rainfall component**")
                        st.metric("Dominant RP class", rrp.get("dominant_class","—"))
                        st.metric("RP severity index", fmt(rrp.get("severity_index",np.nan),""))
                        st.metric(f"P(3-day rain ≥ {trigger_rp}-y level)", fmt(rrp.get("prob_exceed",{}).get(trigger_rp,np.nan),"%"))
                    rp_note = (
                        "For Stella, heat and flood warning inputs remain separate; a compound-hazard flag is used when their forecast windows overlap or the second hazard occurs before recovery."
                    )

            else:
                st.info(
                    "Monthly and seasonal anomaly forecasts are not converted into an exact event return period. "
                    "Seasonal and sub-seasonal signals support baseline preparedness; event return-period probabilities are updated when the hazard enters the shorter-range ensemble window. "
                    "GloFAS river discharge is an exception because its ensemble extends into longer lead times."
                )

            if rp_result:
                probs = rp_result.get("prob_exceed", {})
                st.markdown(f"**Metric:** {rp_kind}")
                st.write(rp_note)

                st.markdown("#### Return-period threshold values for the selected location")
                st.caption(
                    "Each return-level value is the physical threshold corresponding to that return period. "
                    "The threshold is fixed for the selected historical/reanalysis baseline and location; "
                    "the forecast probability of exceeding it changes with the selected forecast window."
                )
                if not rp_table_daily.empty:
                    st.markdown("**Daily precipitation return levels — direct daily Stella input**")
                    st.dataframe(rp_table_daily,hide_index=True,use_container_width=True)
                    st.caption("Rx1day is annual maximum 1-day precipitation in mm/day. This table is intended for Stella when a daily precipitation threshold is needed.")
                if not rp_table_main.empty:
                    st.markdown("**Primary hazard return levels**")
                    st.dataframe(rp_table_main,hide_index=True,use_container_width=True)
                if 100 in rp_levels_main:
                    st.caption("The 100-year level is a substantial extrapolation when the available historical/reanalysis record is much shorter than 100 years. Treat it as a stress-test threshold unless uncertainty bounds and local validation are available.")

                rcols = st.columns(6)
                rcols[0].metric("Dominant RP class", rp_result.get("dominant_class","—"))
                rcols[1].metric("SDM severity index", fmt(rp_result.get("severity_index",np.nan),""))
                rcols[2].metric("P(≥2-y)", fmt(probs.get(2,np.nan),"%"))
                rcols[3].metric("P(≥5-y)", fmt(probs.get(5,np.nan),"%"))
                rcols[4].metric("P(≥10-y)", fmt(probs.get(10,np.nan),"%"))
                rcols[5].metric("P(≥20-y)", fmt(probs.get(20,np.nan),"%"))
                st.caption(f"Additional stress-test exceedance probabilities: P(≥50-y) = {fmt(probs.get(50,np.nan),'%')} · P(≥100-y) = {fmt(probs.get(100,np.nan),'%')}")

                p_action = probs.get(trigger_rp, np.nan)
                action_on = bool(np.isfinite(p_action) and p_action >= trigger_probability)
                p_action_text = f"{p_action:.1f}%" if np.isfinite(p_action) else "—"
                box_class = "good" if action_on else "warn"
                st.markdown(
                    f'<div class="{box_class}"><b>Configured preparedness trigger:</b> '
                    f'P(RP ≥ {trigger_rp} y) = {p_action_text}; '
                    f'probability threshold = {trigger_probability}%. '
                    f'<b>EarlyWarningTrigger = {1 if action_on else 0}</b>.</div>',
                    unsafe_allow_html=True
                )

                st.markdown("#### Physical forecast summary for uncertainty runs")
                pc = st.columns(4)
                pc[0].metric("P10", fmt(rp_result.get("p10",np.nan),rp_unit))
                pc[1].metric("P50 / median", fmt(rp_result.get("p50",np.nan),rp_unit))
                pc[2].metric("P90 stress case", fmt(rp_result.get("p90",np.nan),rp_unit))
                pc[3].metric("Ensemble maximum", fmt(rp_result.get("ensemble_max",np.nan),rp_unit))
                st.caption(
                    "For Stella, use the probability-weighted return-period severity index as the main warning input; "
                    "use P50 as the central physical forecast and P90 as a stress/sensitivity run. "
                    "Keep the ensemble maximum as a diagnostic extreme rather than the principal SDM input."
                )

                sdm_df = sdm_rp_row(
                    country, analysis_label, hazard, horizon, period, rp_kind, rp_result,
                    trigger_rp, trigger_probability, rp_unit, rp_levels_main, rp_start, rp_end
                )
                sdm_df["ParentArea"] = focus
                sdm_df["AnalysisLevel"] = analysis_level
                sdm_df["FacilityID"] = analysis_facility_id
                sdm_df["FacilityType"] = analysis_facility_type
                sdm_df["FacilityRegistrySource"] = analysis_registry_source
                st.download_button(
                    "Download Stella/SDM return-period hand-off CSV",
                    sdm_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"REACH_SDM_RP_handoff_{country}_{analysis_slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="download_sdm_rp"
                )

                threshold_exports=[]
                if not rp_table_daily.empty:
                    xx=rp_table_daily.copy(); xx["Country"]=country; xx["Area"]=analysis_label; xx["ParentArea"]=focus; xx["AnalysisLevel"]=analysis_level; xx["Forecast horizon"]=horizon; xx["Valid period"]=period; threshold_exports.append(xx)
                if not rp_table_main.empty:
                    xx=rp_table_main.copy(); xx["Country"]=country; xx["Area"]=analysis_label; xx["ParentArea"]=focus; xx["AnalysisLevel"]=analysis_level; xx["Forecast horizon"]=horizon; xx["Valid period"]=period; threshold_exports.append(xx)
                if threshold_exports:
                    rp_export=pd.concat(threshold_exports,ignore_index=True)
                    st.download_button(
                        "Download return-level table for Stella",
                        rp_export.to_csv(index=False).encode("utf-8"),
                        file_name=f"REACH_ReturnLevels_{country}_{analysis_slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv",use_container_width=True,key="download_return_levels"
                    )
        except Exception as exc:
            st.warning(f"Return-period forecast could not be calculated for this view: {exc}")

        st.markdown("### 4 · Understanding 2-, 5-, 10-, 20-, 50- and 100-year return levels")
        st.markdown(
            """
A **return period** is a rarity label derived from an extreme-value distribution. If the annual exceedance probability is `p`, then approximately:

`Return period T = 1 / p`

For river discharge, **QT** means the discharge threshold associated with a T-year return period.

| Threshold | Historical annual exceedance probability | REACH interpretation |
|---|---:|---|
| Q2 | 50% | relatively frequent high-flow threshold |
| Q5 | 20% | less frequent flood-severity threshold |
| Q10 | 10% | major-event / anticipatory-action candidate |
| Q20 | 5% | severe rare-event threshold |
| Q50 | 2% | rare stress-test threshold |
| Q100 | 1% | very rare / high-uncertainty stress-test threshold |

**Key distinction:** `Q20 = 5% annual exceedance probability` describes historical rarity.  
`P(Q > Q20 in the next forecast window) = 40%` is a *forecast ensemble probability*. They are not the same probability.

GloFAS operational flood summaries use **2-, 5- and 20-year** return-period severity levels. The REACH modelling scheme uses **2-, 5-, 10- and 20-year** classes and can retain **50- and 100-year** levels as stress tests. Other return periods can be calculated from the fitted extreme-value distribution when needed.
"""
        )

        st.markdown("### 5 · Heatwave occurrence and return-period severity")
        st.markdown(
            """
The REACH framework uses **two complementary heat measures**:

1. **Heatwave occurrence:** daily Tmax above the fixed local **TX90** threshold for at least **3 consecutive days**.
2. **Return-period severity:** fit a GEV to the historical **annual maximum 3-day mean Tmax (TX3d)**, then classify the forecast ensemble against 2-, 5-, 10-, 20-, 50- and 100-year heat-severity return levels.

This keeps the 3-day heatwave definition while providing Stella with a return-period-compatible severity class.  
The return-period class is a *rarity/severity label*; actual heat impacts should still depend on duration, peak/cumulative exceedance, exposure and system vulnerability.
"""
        )

        st.markdown("### 6 · Data-source and climate-index glossary")
        glossary = pd.DataFrame([
            ["NOAA","National Oceanic and Atmospheric Administration","US agency providing weather, ocean and climate observations and forecasts."],
            ["CPC","Climate Prediction Center","NOAA centre that issues official ENSO/RONI probabilities and seasonal climate guidance."],
            ["PSL","Physical Sciences Laboratory","NOAA laboratory publishing climate-index time series, including DMI, TNA, TSA and NAO."],
            ["ECMWF","European Centre for Medium-Range Weather Forecasts","Provides the IFS deterministic and ensemble forecasts, sub-seasonal guidance and seasonal forecasts used in the portal."],
            ["IFS HRES","Integrated Forecasting System high-resolution forecast","ECMWF deterministic forecast used for short- and medium-range physical values."],
            ["IFS ENS","Integrated Forecasting System ensemble forecast","ECMWF ensemble used to quantify uncertainty and event probabilities."],
            ["EC46","ECMWF sub-seasonal / extended-range forecast","Weekly outlook guidance to about 46 days."],
            ["SEAS5","ECMWF Seasonal Forecast System 5","Monthly and seasonal ensemble guidance to several months."],
            ["GFS","Global Forecast System","NOAA deterministic global weather forecast."],
            ["GEFS","Global Ensemble Forecast System","NOAA ensemble system used as an independent uncertainty comparison."],
            ["NMME","North American Multi-Model Ensemble","Multi-model seasonal prediction system used as an independent seasonal cross-check."],
            ["GloFAS","Global Flood Awareness System","Copernicus/ECMWF river-flow forecasting system based on the LISFLOOD hydrological model."],
            ["LISFLOOD","LISFLOOD hydrological model","Hydrological model used by GloFAS to simulate river discharge."],
            ["ERA5","ECMWF Reanalysis version 5","Historical reanalysis used for local climatology, thresholds and extreme-value baselines."],
            ["ENSO","El Niño–Southern Oscillation","Coupled tropical Pacific ocean-atmosphere variability that changes seasonal climate odds."],
            ["RONI","Relative Oceanic Niño Index","NOAA's relative Niño-3.4 sea-surface-temperature index used for ENSO monitoring and prediction."],
            ["El Niño","Warm ENSO phase","Positive RONI/ENSO state; it changes regional climate odds but is not itself a flood or heatwave warning."],
            ["La Niña","Cold ENSO phase","Negative RONI/ENSO state; it changes regional climate odds but does not automatically imply flooding."],
            ["IOD","Indian Ocean Dipole","East-west sea-surface-temperature variability in the equatorial Indian Ocean."],
            ["DMI","Dipole Mode Index","Index of the IOD: western minus southeastern equatorial Indian Ocean SST anomaly."],
            ["TNA","Tropical Northern Atlantic Index","Monthly sea-surface-temperature anomaly over the tropical North Atlantic."],
            ["TSA","Tropical Southern Atlantic Index","Monthly sea-surface-temperature anomaly over the tropical South Atlantic."],
            ["TNA−TSA","REACH Tropical Atlantic diagnostic","Difference between TNA and TSA used as seasonal context for Brazil; not treated as a direct hazard trigger."],
            ["NAO","North Atlantic Oscillation","North-south North Atlantic pressure dipole; documented for completeness and not currently used as a primary REACH hazard driver."],
            ["SST","Sea-surface temperature","Temperature of the ocean surface used in large-scale climate indices."],
            ["TX90","90th percentile of daily maximum temperature","Fixed local heat threshold; a heatwave is identified when Tmax exceeds TX90 for at least 3 consecutive days."],
            ["P95","95th percentile","High-rainfall screening threshold; a percentile is not the same as a return period."],
            ["GEV","Generalized Extreme Value distribution","Statistical distribution used to estimate return levels from annual maxima."],
            ["AEP","Annual exceedance probability","Chance that an event exceeds a given return-period level in any year; approximately 1/T."],
            ["RP","Return period","Historical rarity label, expressed in years, derived from an extreme-value distribution."],
            ["SDM","System Dynamics Model","Stock-and-flow model implemented in Stella for district/facility system dynamics."],
            ["ABM","Agent-Based Model","Model of individual or household/facility agents and their decisions/interactions."],
            ["MCH","Maternal and child health","Health services and outcomes targeted by the REACH modelling framework."],
        ], columns=["Term","Expanded name","Meaning in REACH"])
        st.dataframe(glossary, hide_index=True, use_container_width=True)

        st.markdown("### Reading the seasonal visualisations")
        st.markdown(
            """
- **ENSO phase probabilities:** overlapping 3-month NOAA CPC outlook seasons for La Niña, Neutral and El Niño.
- **ENSO strength probabilities:** official Weak, Moderate, Strong and Very Strong La Niña/El Niño categories plus Neutral.
- **RONI anomaly outlook:** filled red/blue median RONI plot with 25–75% uncertainty and official strength thresholds.
- **Temporal anomaly outlook:** week-by-week or month-by-month temperature/precipitation anomaly, with month/date visible in the chart and hover.
- **Spatial anomaly outlook:** the same selected period mapped across districts/municipalities with a horizontal, zero-centred colour scale.
- **Basemap selector:** Streets/places, OpenStreetMap, clean light, terrain/outdoors, satellite and satellite+streets.
- **Opacity control:** reveals more geographic context without changing forecast values.
- **Anomaly ≠ event:** a positive temperature anomaly does not automatically mean heatwave; a positive precipitation anomaly does not automatically mean flooding.
"""
        )

        st.markdown("### 7 · Interpreting ENSO/RONI, IOD/DMI and Tropical Atlantic indices")
        st.markdown(
            """
- **RONI > +0.5 °C** supports an El Niño classification; **RONI < −0.5 °C** supports La Niña when the persistence criteria are met. NOAA now uses RONI for official ENSO monitoring/prediction. The red/grey/blue ENSO bars are probabilities of **El Niño / Neutral / La Niña**, not probabilities of flood or heatwave in a REACH district.
- **DMI > 0** indicates a positive Indian Ocean Dipole; **DMI < 0** indicates a negative IOD. The sign describes the east–west SST gradient; regional rainfall impacts must still be inferred from the dynamical forecast.
- **TNA** and **TSA** are tropical North/South Atlantic SST-anomaly indices. The portal displays **TNA−TSA** as a simple Brazil contextual diagnostic. Do not interpret its sign as a deterministic flood trigger.
- **NAO** describes the North Atlantic pressure dipole associated with the Icelandic Low and Azores High. It is documented for completeness but is not currently used in the REACH hazard equations.
"""
        )

        st.markdown("### 8 · REACH System Dynamics Model / Stella integration")
        st.info(
            "For Stella, the return-period table provides both the physical threshold value (for example °C, mm/day or m³/s) "
            "and the selected-window forecast probability of exceeding that threshold. This allows the model to use a physical rule, a probability rule, or both."
        )
        st.markdown(
            """
The REACH System Dynamics Model comprises **eight modules**:

1. Climate / hazards  
2. Infrastructure + power  
3. Funding mobilisation  
4. Commodities  
5. Staff + workload  
6. Population  
7. MCH utilisation  
8. Intervention / Early Warning System (EWS)

Forecast information enters **Module 08 (Intervention / EWS)**. **Module 01 (Climate / hazards)** retains the realised hazard event. This keeps forecast uncertainty separate from the physical event and its impacts.

**Operational inputs from the dashboard to Stella**

`ForecastSeverityIndex` = probability-weighted return-period severity on 0–1  
`P_GE_ActionRP` = forecast probability of exceeding the selected action RP  
`WarningLeadTimeDays` = time from forecast issue/retrieval to valid hazard window  
`ForecastPhysicalP50` = central physical forecast  
`ForecastPhysicalP90` = precautionary/stress-test physical forecast  
`ForecastRPClass` = dominant <2 / 2–5 / 5–10 / 10–20 / ≥20-year class  
`RL_RP2 ... RL_RP100` = physical threshold values corresponding to 2-, 5-, 10-, 20-, 50- and 100-year return periods

For a deterministic Stella run, the **probability-weighted return-period severity index** is the main warning input. **P50** represents the central physical forecast and **P90** is used for precautionary sensitivity or stress testing. The **ensemble maximum** is retained as diagnostic information rather than the principal model driver.

A transparent severity index is:

`Severity = 0·P(<2y) + 0.25·P(2–5y) + 0.50·P(5–10y) + 0.75·P(10–20y) + 1.00·P(≥20y)`

This index does not replace the physical hazard. Before impact, it supports preparedness. Once the event occurs, the Climate / hazards module uses realised discharge, flood depth, temperature, duration and related physical indicators to drive disruption and recovery.
"""
        )

        module_links = pd.DataFrame([
            ["01 Climate / hazards","Realised hazard event and physical severity","Observed/simulated discharge, flood depth, Tmax, duration and compound-event state."],
            ["02 Infrastructure + power","Pre-event protection and readiness","Infrastructure checks, power/WASH protection and route readiness before impact."],
            ["03 Funding mobilisation","Contingency and response finance","Supports timely release of preparedness and recovery resources."],
            ["04 Commodities","Pre-positioning and buffer stock","Supports stock, cold-chain, vaccine, fuel and equipment readiness."],
            ["05 Staff + workload","Staff readiness","Supports rota changes, surge staffing, outreach planning and heat-risk preparation."],
            ["06 Population","Population context and scaling","No direct forecast input in the current architecture; population supports ABM scaling and exposure context."],
            ["07 MCH utilisation","Service continuity support","Supports facility readiness and continuity of maternal and child health services."],
            ["08 Intervention / EWS","Forecast interpretation and preparedness","Receives forecast probabilities, return-period severity and lead time; owns EarlyWarningPreparednessLevel and the warning trigger."],
        ], columns=["Module","Role in the early-warning pathway","How forecast information is used"])
        st.dataframe(module_links, hide_index=True, use_container_width=True)

        st.markdown("### 9 · Lead-time action framework")
        st.markdown(
            """
Each forecast horizon supports a **different level of preparedness and action**:

- **Seasonal / sub-seasonal:** raise baseline preparedness, contingency budgets, procurement and maintenance planning.
- **Medium range:** pre-position commodities, confirm staffing/transport, inspect vulnerable infrastructure.
- **Short range:** activate operational warning, move critical stocks, alter outreach/referral plans and communicate locally.
- **Realised event:** switch from forecast probability to observed/simulated physical intensity and recovery dynamics.

This staged approach avoids using one seasonal mean or one extreme ensemble member as the input to every sector.
"""
        )

        st.markdown("### 10 · Evidence base and design precedents")
        papers = pd.DataFrame([
            ["Coughlan de Perez et al. (2015)","Links forecast probability and hazard magnitude to predefined early actions and financing.","Supports probability-and-severity thresholds for Module 08 action rules."],
            ["Forecast-based action trade-off study (2019)","Shows why different lead times can support different early actions.","Supports staged preparedness from seasonal to short range."],
            ["Ye et al. (2025)","Integrates physical flood modelling and ABM-derived indicators within System Dynamics, including return-period scenarios and uncertainty.","Provides a structural precedent for linking hazard outputs to multiple resilience sectors."],
            ["Liu et al. (2020)","Uses advance heat warning to activate health-system preparedness in a System Dynamics model.","Provides a direct precedent for warning-to-service-readiness pathways."],
            ["Feofilovs et al. (2024)","Uses probabilistic disaster-risk and return-time concepts within a System Dynamics framework.","Supports return-period scenario and uncertainty classification."],
        ], columns=["Study","Contribution","Application to REACH"])
        st.dataframe(papers, hide_index=True, use_container_width=True)

        st.markdown("### Verification indicators · temperature, precipitation and discharge")
        indicator_doc = pd.DataFrame([
            ["Tmin","Daily minimum temperature","°C","Lowest 2-m air temperature during the day."],
            ["Tmean","Daily mean temperature","°C","Average 2-m air temperature over the day."],
            ["Tmax","Daily maximum temperature","°C","Highest 2-m air temperature during the day."],
            ["3-day mean Tmax","Mean of daily Tmax across the 3-day event window","°C","Continuous heat-severity indicator used alongside event occurrence."],
            ["TX90","90th percentile of historical daily Tmax","°C","Primary REACH heatwave threshold; occurrence requires exceedance for at least 3 consecutive days."],
            ["TX95","95th percentile of historical daily Tmax","°C","Stricter heat sensitivity/severity comparison."],
            ["TX99","99th percentile of historical daily Tmax","°C","Extreme heat sensitivity/severity comparison."],
            ["P90 / P95 / P99 · 1-day","Historical daily-precipitation percentiles","mm/day","Heavy-rain percentile thresholds for daily precipitation."],
            ["P90 / P95 / P99 · 3-day","Historical rolling 3-day precipitation percentiles","mm / 3 days","Heavy-rain thresholds for accumulated rainfall; P95 is the main REACH 3-day screening threshold."],
            ["Discharge P10/P50/P90","Quantiles across the current GloFAS forecast ensemble","m³/s","Forecast uncertainty quantiles; these are not return periods."],
            ["Q2/Q5/Q10/Q20/Q50/Q100","Historical river-discharge return levels","m³/s","Return-period thresholds; different from ensemble P10/P50/P90."],
        ],columns=["Indicator","Definition","Unit","How to interpret"])
        st.dataframe(indicator_doc,hide_index=True,use_container_width=True)
        st.caption(
            "TX90/TX95/TX99 and precipitation P90/P95/P99 are percentile thresholds. "
            "They are not the same as 2-, 5-, 10- or 20-year return periods."
        )

        st.markdown("### Verification terminology · Hit, Miss, False alarm and Correct negative")
        st.markdown(
            """
The verification table compares what the forecast said with what actually occurred.
The same four outcomes are also known as the entries of a **confusion matrix**.
"""
        )
        st.dataframe(confusion_matrix_explanation(), hide_index=True, use_container_width=True)

        metric_glossary = pd.DataFrame([
            ["Forecast error","Forecast − reference","Negative = underprediction; positive = overprediction."],
            ["MAE","Mean absolute error","Average size of the forecast error, ignoring sign. Lower is better."],
            ["RMSE","Root mean square error","Like MAE, but gives more weight to large errors. Lower is better."],
            ["Mean bias","Average forecast − reference","Shows systematic overprediction (+) or underprediction (−). Closer to zero is better."],
            ["Percent bias (PBIAS)","100 × sum(forecast − reference) / sum(|reference|)","Relative systematic bias. Positive = overprediction; negative = underprediction."],
            ["R²","Coefficient of determination","Measures how well variation in observations is reproduced. It is not meaningful for one event when the reference value is the same at every lead time."],
            ["POD","Probability of detection = Hit/(Hit+Miss)","Of the observed events, the percentage that were successfully warned. Higher is better."],
            ["FAR","False-alarm ratio = False alarm/(Hit+False alarm)","Of all warnings issued, the percentage that were false alarms. Lower is better."],
            ["Accuracy","(Hit+Correct negative)/all classified cases","Overall proportion of classifications that were correct; interpret with event frequency."],
        ], columns=["Metric","Definition","Interpretation"])
        st.markdown("#### Verification and goodness-of-fit metrics")
        st.dataframe(metric_glossary, hide_index=True, use_container_width=True)
        st.caption(
            "For a single historical event, MAE, RMSE, bias and percent bias can compare forecasts across lead times. "
            "R² is shown only when the verifying reference contains enough variation; otherwise it is reported as not applicable rather than being manufactured."
        )

        st.markdown("### 11 · Forecast synthesis principle")
        st.markdown(
            """
A robust operational briefing should make **forecast discrepancies, convergence and source hierarchy visible**.
National/operational products provide the country context; global dynamical systems provide independent physical and probabilistic evidence;
hydrological forecasts provide river-specific evidence; and ocean-atmosphere indices explain the seasonal background.
Historical analogue relationships are supporting context and should not be treated as forecast probabilities for another country or season.
"""
        )

        st.markdown("### 12 · Source links")
        link_cols = st.columns(4)
        with link_cols[0]:
            st.link_button("NOAA CPC RONI / ENSO", CPC_ENSO_URL, use_container_width=True)
            st.link_button("NOAA PSL climate indices", NOAA_PSL_INDICES, use_container_width=True)
        with link_cols[1]:
            st.link_button("NOAA PSL DMI", DMI_WEB, use_container_width=True)
            st.link_button("NOAA PSL NAO", NOAA_NAO_URL, use_container_width=True)
        with link_cols[2]:
            st.link_button("GloFAS Flood Summary", GLOFAS_SUMMARY_URL, use_container_width=True)
            st.link_button("Forecast-based financing paper", FBF_PAPER_URL, use_container_width=True)
        with link_cols[3]:
            st.link_button("Ye et al. 2025", YE2025_URL, use_container_width=True)
            st.link_button("Liu et al. 2020", LIU2020_URL, use_container_width=True)


    with tabs[6]:
        st.markdown("## Download Centre · forecast data and Stella/SDM hand-off")
        st.caption(
            "Download the selected forecast in analysis-ready CSV format. "
            "The files preserve the forecast window, lead time, numerical values, uncertainty, return-period thresholds, "
            "forecast exceedance probabilities and health-system implication."
        )

        now_utc = pd.Timestamp.now(tz="UTC")
        valid_start = timing.get("start")
        valid_end = timing.get("end")

        def _lead_days(x):
            if x is None or pd.isna(x):
                return np.nan
            xx = pd.Timestamp(x)
            if xx.tzinfo is None:
                xx = xx.tz_localize("UTC")
            else:
                xx = xx.tz_convert("UTC")
            return max(0.0, (xx - now_utc).total_seconds()/86400.0)

        lead_days = _lead_days(valid_start)
        selected_unit = unit_for(hazard,horizon,mode)
        parent_area_value = fv if "fv" in locals() else np.nan
        selected_value = selected_facility_value if (selected_facility is not None and np.isfinite(selected_facility_value)) else parent_area_value
        selected_risk = risk_label(selected_value) if selected_unit=="%" and np.isfinite(selected_value) else ""
        highest_area = maxrow.REGION_NAME if ("maxrow" in locals() and maxrow is not None) else ""
        highest_value = sm["max"] if ("sm" in locals() and isinstance(sm,dict)) else np.nan

        # Focus ensemble probabilities.
        ec_prob = ge_prob = np.nan
        if hazard=="Heatwave":
            ec_prob=focus_probs.get("ECMWF IFS ENS_heat",np.nan); ge_prob=focus_probs.get("NOAA GEFS_heat",np.nan)
        elif hazard=="Flood – rainfall":
            ec_prob=focus_probs.get("ECMWF IFS ENS_rain",np.nan); ge_prob=focus_probs.get("NOAA GEFS_rain",np.nan)
        elif hazard=="Compound – Flood + Heatwave":
            ec_prob=focus_probs.get("ECMWF IFS ENS_compound",np.nan); ge_prob=focus_probs.get("NOAA GEFS_compound",np.nan)

        if np.isfinite(ec_prob) and np.isfinite(ge_prob):
            model_diff=abs(ec_prob-ge_prob)
            model_agreement="Strong agreement" if model_diff<=10 else ("Broad agreement" if model_diff<=25 else "Mixed signal / material disagreement")
        else:
            model_diff=np.nan; model_agreement=""

        summary_row = {
            "RetrievedUTC": now_utc.isoformat(),
            "Country": country,
            "AdministrativeLevel": analysis_level,
            "Area": analysis_label,
            "ParentArea": focus,
            "FacilityID": analysis_facility_id,
            "FacilityType": analysis_facility_type,
            "FacilityRegistrySource": analysis_registry_source,
            "Admin1": str(meta.ADMIN1),
            "Latitude": float(meta.rep_lat),
            "Longitude": float(meta.rep_lon),
            "Hazard": hazard,
            "ForecastHorizon": horizon,
            "SelectedPeriod": period,
            "ValidStart": fmt_dt(valid_start, horizon in ("Short range","Medium range")) if valid_start is not None else "",
            "ValidEnd": fmt_dt(valid_end, horizon in ("Short range","Medium range")) if valid_end is not None else "",
            "LeadAheadDays": lead_days,
            "DeterministicOrPrimaryModel": det_source,
            "EnsembleSystemSelected": ensemble_system,
            "MapMode": mode,
            "SelectedAreaForecastValue": selected_value,
            "SelectedAreaForecastUnit": selected_unit,
            "SelectedAreaRiskClass": selected_risk,
            "ParentAreaForecastValue": parent_area_value,
            "HighestSignalArea": highest_area,
            "HighestSignalValue": highest_value,
            "HighestSignalUnit": selected_unit,
            "ECMWFEnsembleEventProbability_pct": ec_prob,
            "NOAAGEFSEventProbability_pct": ge_prob,
            "ModelProbabilityDifference_pct_points": model_diff,
            "ModelAgreement": model_agreement,
            "HealthSystemImplication": HORIZONS[horizon]["action"],
            "DecisionMakerBriefing": base_summary if "base_summary" in locals() else "",
        }

        if timing.get("heat_peak_time") is not None:
            summary_row["HeatPeakTimeUTC"] = fmt_dt(timing.get("heat_peak_time"))
            summary_row["HeatPeakValue_C"] = timing.get("heat_peak",np.nan)
        if timing.get("rain72_start") is not None:
            summary_row["Wettest72hStartUTC"] = fmt_dt(timing.get("rain72_start"))
            summary_row["Wettest72hEndUTC"] = fmt_dt(timing.get("rain72_end"))
            summary_row["Wettest72hTotal_mm"] = timing.get("rain72",np.nan)
        if timing.get("peak_time") is not None and horizon in ("Sub-seasonal","Seasonal"):
            summary_row["StrongestAnomalyPeriod"] = fmt_dt(timing.get("peak_time"),False)
            summary_row["StrongestAnomalyValue"] = timing.get("peak_value",np.nan)

        if enso_info:
            summary_row["ENSO_Phase"] = enso_info.get("phase","")
            summary_row["ENSO_Probability_pct"] = enso_info.get("prob",np.nan)
            summary_row["ENSO_Season"] = enso_info.get("season","")
        if country=="Zambia" and dmi_info:
            summary_row["DMI_C"] = dmi_info.get("value",np.nan)
            summary_row["IOD_Phase"] = dmi_info.get("phase","")
        if country=="Brazil" and atlantic_info:
            summary_row["TNA_C"] = atlantic_info.get("tna",np.nan)
            summary_row["TSA_C"] = atlantic_info.get("tsa",np.nan)
            summary_row["TNA_minus_TSA_C"] = atlantic_info.get("gradient",np.nan)

        if glofas_info:
            summary_row["GloFAS_CellValidated"] = glofas_info.get("valid","")
            summary_row["GloFAS_Mean_m3_s"] = glofas_info.get("mean",np.nan)
            summary_row["GloFAS_Median_m3_s"] = glofas_info.get("median",np.nan)
            summary_row["GloFAS_Max_m3_s"] = glofas_info.get("max",np.nan)
            summary_row["GloFAS_PeakDate"] = fmt_dt(glofas_info.get("peak"),False)
            summary_row["GloFAS_P_GE_Q2_pct"] = glofas_info.get("p2",np.nan)
            summary_row["GloFAS_P_GE_Q5_pct"] = glofas_info.get("p5",np.nan)
            summary_row["GloFAS_P_GE_Q20_pct"] = glofas_info.get("p20",np.nan)

        # Add Stella-ready RP values and probabilities whenever calculated.
        if rp_result:
            summary_row["RP_Metric"] = rp_kind
            summary_row["ForecastSeverityIndex_0_1"] = rp_result.get("severity_index",np.nan)
            summary_row["DominantRPClass"] = rp_result.get("dominant_class","")
            summary_row["ForecastPhysicalP10"] = rp_result.get("p10",np.nan)
            summary_row["ForecastPhysicalP50"] = rp_result.get("p50",np.nan)
            summary_row["ForecastPhysicalP90"] = rp_result.get("p90",np.nan)
            summary_row["ForecastPhysicalUnit"] = rp_unit
            for rr in (2,5,10,20,50,100):
                summary_row[f"ReturnLevel_RP{rr}"] = rp_levels_main.get(rr,np.nan)
                summary_row[f"Forecast_P_GE_RP{rr}_pct"] = rp_result.get("prob_exceed",{}).get(rr,np.nan)

        summary_df = pd.DataFrame([summary_row])

        st.markdown("### A · Forecast result summary")
        st.dataframe(summary_df,hide_index=True,use_container_width=True)
        st.download_button(
            "Download forecast summary CSV",
            summary_df.to_csv(index=False).encode("utf-8"),
            file_name=f"REACH_Forecast_Summary_{country}_{analysis_slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="download_forecast_summary_csv",
        )

        cdl1,cdl2=st.columns(2)
        with cdl1:
            st.markdown("### B · Spatial forecast values")
            if not map_df.empty:
                spatial_export=map_df.copy()
                spatial_export["Country"]=country
                spatial_export["Hazard"]=hazard
                spatial_export["Horizon"]=horizon
                spatial_export["Period"]=period
                spatial_export["MapMode"]=mode
                spatial_export["Unit"]=selected_unit
                spatial_export["RetrievedUTC"]=now_utc.isoformat()
                st.download_button(
                    "Download all mapped areas CSV",
                    spatial_export.to_csv(index=False).encode("utf-8"),
                    file_name=f"REACH_Spatial_Forecast_{country}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="download_spatial_centre",
                )
            else:
                st.info("Spatial forecast table is not available for this selection.")

        with cdl2:
            st.markdown(f"### C · {'Facility' if selected_facility is not None else 'Focus-area'} time series")
            ts_frames=[x for x in focus_timeseries_exports if isinstance(x,pd.DataFrame) and not x.empty]
            if isinstance(glofas_timeseries_export,pd.DataFrame) and not glofas_timeseries_export.empty:
                ts_frames.append(glofas_timeseries_export)
            if ts_frames:
                # Use outer concatenation in long format to preserve different variables.
                ts_export_all=pd.concat(ts_frames,ignore_index=True,sort=False)
                st.download_button(
                    "Download forecast time-series CSV",
                    ts_export_all.to_csv(index=False).encode("utf-8"),
                    file_name=f"REACH_TimeSeries_{country}_{analysis_slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="download_timeseries_centre",
                )
            else:
                st.info("Time-series data are not available for this selected forecast focus.")

        st.markdown("### D · Return-period values and Stella/SDM inputs")
        d1,d2=st.columns(2)
        with d1:
            if isinstance(rp_export,pd.DataFrame) and not rp_export.empty:
                st.download_button(
                    "Download return-period threshold values CSV",
                    rp_export.to_csv(index=False).encode("utf-8"),
                    file_name=f"REACH_ReturnLevels_{country}_{analysis_slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="download_return_levels_centre",
                )
            else:
                st.info("Return-period thresholds are not available for this selected view.")
        with d2:
            if isinstance(sdm_df,pd.DataFrame) and not sdm_df.empty:
                st.download_button(
                    "Download Stella/SDM hand-off CSV",
                    sdm_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"REACH_Stella_SDM_Handoff_{country}_{analysis_slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="download_sdm_centre",
                )
            else:
                st.info("Stella return-period hand-off is not available for this selected view.")

        st.markdown("### E · Complete selected-data package")
        package_files={
            "forecast_summary.csv": summary_df.to_csv(index=False).encode("utf-8"),
        }
        if not map_df.empty:
            package_files["spatial_forecast.csv"]=spatial_export.to_csv(index=False).encode("utf-8")
        if ts_frames:
            package_files["focus_timeseries.csv"]=ts_export_all.to_csv(index=False).encode("utf-8")
        if isinstance(rp_export,pd.DataFrame) and not rp_export.empty:
            package_files["return_period_thresholds.csv"]=rp_export.to_csv(index=False).encode("utf-8")
        if isinstance(sdm_df,pd.DataFrame) and not sdm_df.empty:
            package_files["stella_sdm_handoff.csv"]=sdm_df.to_csv(index=False).encode("utf-8")
        if isinstance(facility_forecast_df,pd.DataFrame) and not facility_forecast_df.empty:
            package_files["facility_forecast_exposure.csv"]=facility_forecast_df.to_csv(index=False).encode("utf-8")
        if isinstance(facility_model_df,pd.DataFrame) and not facility_model_df.empty:
            package_files["facility_ecmwf_gfs_comparison.csv"]=facility_model_df.to_csv(index=False).encode("utf-8")
        if isinstance(long_facility_df,pd.DataFrame) and not long_facility_df.empty:
            package_files["facility_longrange_anomaly_components.csv"]=long_facility_df.to_csv(index=False).encode("utf-8")
        if isinstance(facility_registry,pd.DataFrame) and not facility_registry.empty:
            package_files["facility_registry.csv"]=facility_registry.to_csv(index=False).encode("utf-8")

        zip_buffer=BytesIO()
        with zipfile.ZipFile(zip_buffer,"w",zipfile.ZIP_DEFLATED) as zf:
            for fname,data in package_files.items():
                zf.writestr(fname,data)
        st.download_button(
            "Download all selected CSVs as ZIP",
            zip_buffer.getvalue(),
            file_name=f"REACH_Selected_Data_{country}_{analysis_slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
            mime="application/zip",
            use_container_width=True,
            key="download_all_csv_zip",
        )

        st.caption(
            "For Stella, the consolidated summary and SDM hand-off preserve the return-level values, forecast exceedance probabilities, "
            "lead time and physical P10/P50/P90 values. The spatial and time-series files are retained for audit, sensitivity analysis and reproducibility."
        )


    with tabs[7]:
        st.markdown("## Forecast verification · REACH pilot sites")
        st.caption(
            "Verification remains restricted to Senanga, Sinazongwe, Recife and Palmares. "
            "The site, hazard family and verification indicator suite are linked automatically to the main dashboard selection."
        )
        if selected_facility is not None:
            st.info(
                f"Facility focus is active for {analysis_label}. Historical forecast verification on this tab remains at the parent pilot-area level ({focus}); "
                "it should not be interpreted as a facility-specific hindcast unless a matched facility observation archive is added."
            )

        pilot_df=verification_pilot_sites()
        current_pilot=f"{country} · {focus}"
        pilot_choices=pilot_df["Site"].tolist()

        if current_pilot not in pilot_choices:
            st.info(
                "Select Senanga, Sinazongwe, Recife or Palmares as the focus area to activate historical forecast verification."
            )
        else:
            site_row=pilot_df[pilot_df["Site"]==current_pilot].iloc[0]
            continuous_metrics,event_metrics=verification_suite_from_hazard(hazard)
            auto_leads=verification_leads_from_horizon(horizon)
            suite_label=verification_metric_from_hazard(hazard)

            min_event_date=pd.Timestamp("2026-04-12").date()
            max_event_date=(pd.Timestamp.now(tz="UTC")-pd.Timedelta(days=11)).date()
            default_event_date=max(min_event_date,max_event_date-pd.Timedelta(days=60))

            h1,h2,h3,h4=st.columns(4)
            h1.metric("Pilot site",current_pilot)
            h2.metric("Linked hazard",hazard)
            h3.metric("Verification suite",suite_label)
            h4.metric("Lead times",", ".join(str(x) for x in auto_leads)+" d")

            if horizon in ("Sub-seasonal","Seasonal"):
                st.info(
                    "This pilot verification uses event-scale archived ECMWF IFS and NOAA GFS weather forecasts. "
                    "True sub-seasonal/seasonal skill assessment requires EC46/SEAS5 reforecast archives and remains separate."
                )

            event_date=st.date_input(
                "Historical event / verification date",
                value=default_event_date,min_value=min_event_date,max_value=max_event_date,
                key="verification_event_date_final_suite"
            )

            st.markdown(
                """
<div class="hoverhint">
<b>Reference and models:</b> archived ECMWF IFS HRES and NOAA/NCEP GFS runs are compared against ERA5.
Continuous indicators test numerical forecast accuracy; percentile-event indicators test whether each model would have issued a threshold-based warning.
</div>
""",unsafe_allow_html=True
            )

            # Threshold values for the selected event month.
            try:
                th_table,clim=verification_threshold_table(
                    float(site_row["rep_lat"]),float(site_row["rep_lon"]),event_date
                )
                relevant_heat=hazard in ("Heatwave","Compound – Flood + Heatwave","Compound – Drought + Heatwave")
                relevant_rain=hazard!="Heatwave"
                th_show=th_table[
                    ((th_table["Hazard family"]=="Heat") & relevant_heat) |
                    ((th_table["Hazard family"]=="Precipitation") & relevant_rain)
                ].copy()
                st.markdown("### Local percentile thresholds for the selected month")
                st.dataframe(
                    th_show.style.format({"Value":"{:.2f}"},na_rep="—"),
                    hide_index=True,use_container_width=True
                )
            except Exception as exc:
                st.warning(f"Percentile thresholds could not be calculated: {exc}")

            all_ec=[]
            all_gf=[]
            continuous_comparisons=[]
            event_comparisons=[]
            skill_frames=[]

            # -------------------------------------------------------------
            # Continuous metrics: Tmin, Tmean, Tmax, 3-day heat, rainfall.
            # -------------------------------------------------------------
            st.markdown("### Continuous indicator comparison · ECMWF vs NOAA GFS vs ERA5")
            for metric in continuous_metrics:
                try:
                    ec,meta_v=build_pilot_hindcast(
                        site_row,event_date,metric,"ECMWF IFS HRES",auto_leads
                    )
                    gf,_=build_pilot_hindcast(
                        site_row,event_date,metric,"NOAA GFS",auto_leads
                    )
                    all_ec.append(ec); all_gf.append(gf)

                    e=ec.rename(columns={
                        "ForecastValue":"ECMWF","ErrorForecastMinusReference":"ECMWF error",
                        "AbsoluteError":"ECMWF abs error"
                    })
                    g=gf.rename(columns={
                        "ForecastValue":"GFS","ErrorForecastMinusReference":"GFS error",
                        "AbsoluteError":"GFS abs error"
                    })
                    comp=e[["LeadTimeDays","Metric","ReferenceValue","Unit","ECMWF","ECMWF error","ECMWF abs error"]].merge(
                        g[["LeadTimeDays","GFS","GFS error","GFS abs error"]],on="LeadTimeDays",how="outer"
                    )
                    def _closer(r):
                        a=r.get("ECMWF abs error",np.nan);b=r.get("GFS abs error",np.nan)
                        if np.isfinite(a) and np.isfinite(b):
                            if abs(a-b)<1e-12:return "Equal"
                            return "ECMWF IFS" if a<b else "NOAA GFS"
                        if np.isfinite(a):return "ECMWF IFS"
                        if np.isfinite(b):return "NOAA GFS"
                        return "Unavailable"
                    comp["Closer model"]=comp.apply(_closer,axis=1)
                    continuous_comparisons.append(comp)

                    ecs=verification_skill_summary(ec)
                    gfs=verification_skill_summary(gf)
                    for model_name,sx in [("ECMWF IFS HRES",ecs),("NOAA GFS",gfs)]:
                        skill_frames.append(pd.DataFrame([{
                            "Metric":metric,"Model":model_name,
                            "MAE":sx["MAE"],"RMSE":sx["RMSE"],
                            "Mean bias":sx["MeanBias"],"Percent bias (%)":sx["PercentBias"],
                            "R²":sx["R2"],"R² note":sx["R2Note"],
                            "Best lead (days)":sx["BestLeadDays"]
                        }]))
                except Exception as exc:
                    st.warning(f"{metric} verification unavailable: {exc}")

            if continuous_comparisons:
                cont_all=pd.concat(continuous_comparisons,ignore_index=True,sort=False)
                st.dataframe(
                    cont_all[[
                        "Metric","LeadTimeDays","ReferenceValue","Unit",
                        "ECMWF","ECMWF error","GFS","GFS error","Closer model"
                    ]].style.format({
                        "ReferenceValue":"{:.2f}","ECMWF":"{:.2f}","ECMWF error":"{:+.2f}",
                        "GFS":"{:.2f}","GFS error":"{:+.2f}"
                    },na_rep="—"),
                    hide_index=True,use_container_width=True
                )

                # Automatic charts for each continuous indicator.
                st.markdown("#### Lead-time comparison charts")
                charts=list(dict.fromkeys(cont_all["Metric"].dropna().tolist()))
                for k in range(0,len(charts),2):
                    cols=st.columns(2)
                    for j,metric in enumerate(charts[k:k+2]):
                        d=cont_all[cont_all["Metric"]==metric].sort_values("LeadTimeDays")
                        with cols[j]:
                            fig=go.Figure()
                            fig.add_trace(go.Scatter(x=d["LeadTimeDays"],y=d["ECMWF"],mode="lines+markers",name="ECMWF IFS"))
                            fig.add_trace(go.Scatter(x=d["LeadTimeDays"],y=d["GFS"],mode="lines+markers",name="NOAA GFS"))
                            fig.add_trace(go.Scatter(x=d["LeadTimeDays"],y=d["ReferenceValue"],mode="lines+markers",
                                                     name="ERA5 reference",line=dict(dash="dash")))
                            fig.update_layout(
                                title=metric,height=300,
                                xaxis_title="Lead time before event (days)",
                                yaxis_title=str(d["Unit"].dropna().iloc[0]) if len(d["Unit"].dropna()) else "Value",
                                margin=dict(l=15,r=10,t=42,b=20),
                                legend=dict(orientation="h",y=1.13)
                            )
                            fig.update_xaxes(autorange="reversed")
                            st.plotly_chart(fig,use_container_width=True)

            if skill_frames:
                skill_all=pd.concat(skill_frames,ignore_index=True)
                st.markdown("### Goodness-of-fit / error statistics by indicator")
                st.dataframe(
                    skill_all.style.format({
                        "MAE":"{:.2f}","RMSE":"{:.2f}","Mean bias":"{:+.2f}",
                        "Percent bias (%)":"{:+.1f}","R²":"{:.3f}","Best lead (days)":"{:.0f}"
                    },na_rep="—"),
                    hide_index=True,use_container_width=True
                )
                st.caption(
                    "MAE/RMSE/bias compare numerical accuracy across lead times. "
                    "For a single event, the same ERA5 event value is repeated across lead times, so R² is usually not mathematically informative and is reported as N/A. "
                    "A meaningful R² requires multiple verifying dates/events."
                )

            # -------------------------------------------------------------
            # Event metrics: TX90/95/99 or rainfall P90/95/99.
            # -------------------------------------------------------------
            if event_metrics:
                st.markdown("### Percentile-event verification")
                for metric in event_metrics:
                    try:
                        ec,meta_v=build_pilot_hindcast(
                            site_row,event_date,metric,"ECMWF IFS HRES",auto_leads
                        )
                        gf,_=build_pilot_hindcast(
                            site_row,event_date,metric,"NOAA GFS",auto_leads
                        )
                        all_ec.append(ec);all_gf.append(gf)

                        e=ec.rename(columns={
                            "ForecastEvent":"ECMWF forecast event","VerificationOutcome":"ECMWF outcome",
                            "ForecastValue":"ECMWF physical value"
                        })
                        g=gf.rename(columns={
                            "ForecastEvent":"GFS forecast event","VerificationOutcome":"GFS outcome",
                            "ForecastValue":"GFS physical value"
                        })
                        comp=e[[
                            "LeadTimeDays","Metric","ThresholdLabel","ThresholdValue","ThresholdUnit",
                            "ReferenceValue","Unit","ObservedEvent",
                            "ECMWF physical value","ECMWF forecast event","ECMWF outcome"
                        ]].merge(
                            g[["LeadTimeDays","GFS physical value","GFS forecast event","GFS outcome"]],
                            on="LeadTimeDays",how="outer"
                        )
                        event_comparisons.append(comp)
                    except Exception as exc:
                        st.warning(f"{metric} event verification unavailable: {exc}")

                if event_comparisons:
                    evt_all=pd.concat(event_comparisons,ignore_index=True,sort=False)
                    st.dataframe(
                        evt_all.style.format({
                            "ThresholdValue":"{:.2f}","ReferenceValue":"{:.2f}",
                            "ECMWF physical value":"{:.2f}","GFS physical value":"{:.2f}"
                        },na_rep="—"),
                        hide_index=True,use_container_width=True
                    )

                    st.markdown("#### How to interpret the event outcomes")
                    st.dataframe(confusion_matrix_explanation(),hide_index=True,use_container_width=True)

                    # Summary counts by model.
                    counts=[]
                    for model_col,name in [("ECMWF outcome","ECMWF IFS HRES"),("GFS outcome","NOAA GFS")]:
                        s=evt_all[model_col].replace("",np.nan).dropna()
                        counts.append({
                            "Model":name,
                            "Hits":int((s=="Hit").sum()),
                            "Misses / false negatives":int((s=="Miss").sum()),
                            "False alarms / false positives":int((s=="False alarm").sum()),
                            "Correct negatives / true negatives":int((s=="Correct negative").sum())
                        })
                    st.dataframe(pd.DataFrame(counts),hide_index=True,use_container_width=True)

            # -------------------------------------------------------------
            # River-discharge diagnostics where physically relevant.
            # -------------------------------------------------------------
            if hazard=="Flood – river discharge (GloFAS)" and (country,focus) in [
                ("Zambia","Senanga"),("Brazil","Palmares")
            ]:
                st.markdown("### GloFAS river-discharge diagnostics")
                st.caption(
                    "These are current GloFAS ensemble diagnostics for the selected forecast horizon, not a historical hindcast. "
                    "A true discharge hindcast requires the GloFAS reforecast archive."
                )
                try:
                    qstats,qrp,qcell=current_glofas_verification_context(country,focus,horizon,period)
                    if not qstats.empty:
                        c1,c2=st.columns([1,1.35])
                        with c1:
                            st.dataframe(qstats.style.format({"Value":"{:.1f}"},na_rep="—"),
                                         hide_index=True,use_container_width=True)
                        with c2:
                            st.dataframe(qrp.style.format({
                                "Return-level discharge":"{:.1f}",
                                "Current forecast P(exceed) (%)":"{:.1f}"
                            },na_rep="—"),hide_index=True,use_container_width=True)
                        st.caption(
                            "Discharge P10/P50/P90 describe the spread of the current forecast ensemble. "
                            "Q2/Q5/Q10/Q20/Q50/Q100 are historical return-period thresholds; they are different concepts."
                        )
                except Exception as exc:
                    st.warning(f"GloFAS discharge diagnostics unavailable: {exc}")

            # -------------------------------------------------------------
            # Interpretation and downloads.
            # -------------------------------------------------------------
            st.markdown("### Interpretation")
            st.info(
                "Lower MAE and RMSE indicate a closer numerical forecast for the selected event. "
                "A negative bias means underprediction; a positive bias means overprediction. "
                "For threshold events, a Hit means the model warned and the event occurred; a Miss is a false negative; "
                "a False alarm is a false positive; and a Correct negative means no warning and no observed event. "
                "Model performance should ultimately be assessed across a catalogue of events, not one date alone."
            )

            export_frames=[]
            if all_ec: export_frames.extend(all_ec)
            if all_gf: export_frames.extend(all_gf)
            if export_frames:
                verify_all=pd.concat(export_frames,ignore_index=True,sort=False)
                verify_all.insert(0,"Country",site_row["Country"])
                verify_all.insert(1,"Site",site_row["REGION_NAME"])
                verify_all.insert(2,"Admin1",site_row["ADMIN1"])
                verify_all.insert(3,"VerificationDate",pd.Timestamp(event_date).strftime("%Y-%m-%d"))
                verify_all.insert(4,"ReferenceDataset","ERA5")
                st.download_button(
                    "Download complete verification CSV",
                    verify_all.to_csv(index=False).encode("utf-8"),
                    file_name=f"REACH_Verification_Complete_{site_row['Country']}_{site_row['REGION_NAME']}_{pd.Timestamp(event_date).strftime('%Y%m%d')}.csv",
                    mime="text/csv",use_container_width=True,key="download_complete_verification_suite"
                )

            if continuous_comparisons:
                st.download_button(
                    "Download continuous model-comparison CSV",
                    cont_all.to_csv(index=False).encode("utf-8"),
                    file_name=f"REACH_Verification_Continuous_{site_row['Country']}_{site_row['REGION_NAME']}_{pd.Timestamp(event_date).strftime('%Y%m%d')}.csv",
                    mime="text/csv",use_container_width=True,key="download_continuous_suite"
                )
            if event_comparisons:
                st.download_button(
                    "Download percentile-event comparison CSV",
                    evt_all.to_csv(index=False).encode("utf-8"),
                    file_name=f"REACH_Verification_Events_{site_row['Country']}_{site_row['REGION_NAME']}_{pd.Timestamp(event_date).strftime('%Y%m%d')}.csv",
                    mime="text/csv",use_container_width=True,key="download_event_suite"
                )

            sc1,sc2,sc3=st.columns(3)
            with sc1:
                st.link_button("Archived ECMWF / GFS runs","https://open-meteo.com/en/docs/single-runs-api",use_container_width=True)
            with sc2:
                st.link_button("ERA5 reference","https://open-meteo.com/en/docs/historical-weather-api",use_container_width=True)
            with sc3:
                st.link_button("GloFAS reforecasts","https://ewds.climate.copernicus.eu/datasets/cems-glofas-reforecast",use_container_width=True)

            st.caption(
                "TX90 is retained as the primary REACH heatwave definition. TX95/TX99 and precipitation P90/P95/P99 are shown as transparent sensitivity/severity comparisons. "
                "They do not replace the return-period analysis already provided elsewhere in the dashboard."
            )

    # -----------------------------------------------------------------------
    # Architecture and export
    # -----------------------------------------------------------------------
    st.markdown('<div class="section">Forecast-source architecture</div>',unsafe_allow_html=True)
    arch=pd.DataFrame([
        ["Short range","0–3 d","ECMWF IFS / NOAA GFS","ECMWF ENS / NOAA GEFS","GloFAS","Immediate action"],
        ["Medium range","4–15 d","ECMWF IFS / NOAA GFS","ECMWF ENS / NOAA GEFS","GloFAS","Pre-positioning"],
        ["Sub-seasonal","2–6 wk","ECMWF EC46","GEFS extended / multi-model context","GloFAS extended","Readiness planning"],
        ["Seasonal","1–7 mo","ECMWF SEAS5 + national products","NMME + ocean-index context","GloFAS seasonal","Strategic preparedness"],
    ],columns=["Horizon","Lead","Atmosphere","Probabilistic / multi-model","Hydrology","Health-system use"])
    st.dataframe(arch,hide_index=True,use_container_width=True)

    if not map_df.empty:
        exp=map_df.copy()
        exp["country"]=country;exp["hazard"]=hazard;exp["horizon"]=horizon;exp["period"]=period;exp["map_mode"]=mode;exp["unit"]=unit_for(hazard,horizon,mode)
        exp["retrieved_utc"]=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        st.download_button("Download spatial forecast table",exp.to_csv(index=False).encode(),file_name=f"REACH_EWS_V7_{country}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",mime="text/csv",use_container_width=True)

    st.markdown(f'<div class="good"><b>Selected health-system action:</b><br>{HORIZONS[horizon]["action"]}</div>',unsafe_allow_html=True)
    if (country,focus) in PILOT:
        pp=PILOT[(country,focus)]
        st.caption(f"{focus}: {pp['flood_type']} · {pp['logic']} · primary flood evidence: {pp['primary']}.")

    st.caption(
        "Forecast information remains separate from the realised Climate Module. "
        "Forecast -> EarlyWarningSignal / EarlyWarningClass / WarningLeadTimeDays -> District/municipal preparedness -> Facility readiness / care-seeking interfaces."
    )


st.markdown(
    """
<div class="footerbrand">
<b>REACH · Climate–Health Early Warning Data Portal</b><br><span style="color:#647B84">Monitor → Locate → Compare → Act</span><br>
Decision-support portal for anticipatory maternal and child health-system preparedness in Zambia and Brazil.
Forecast information remains separate from realised hazard severity; official national warning services remain authoritative.
</div>
""",
    unsafe_allow_html=True,
)
