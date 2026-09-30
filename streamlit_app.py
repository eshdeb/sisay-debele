from __future__ import annotations

_APP_NOTES = """
REACH Climate–Health Early Warning Data Portal · FINAL V5 · DOCUMENTED RP/SDM

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
- Selectable seasonal anomaly visualisation: focus-area bar plot or spatial anomaly map.
- Source portal with direct hyperlinks.
- Transparent decision-maker summary plus optional local Ollama rewrite.
- Pilot-site two-model historical verification: ECMWF IFS vs NOAA GFS against ERA5.

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
import zipfile

import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
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
a[data-testid="stLinkButton"]{background:#0B5A7A;color:white !important;border-radius:9px;border:0}
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


def period_options(horizon):
    if horizon=="Short range": return ["Next 3 days"]
    if horizon=="Medium range": return ["Days 4–7","Days 8–15","Full days 4–15"]
    if horizon=="Sub-seasonal": return ["Week 2","Week 3","Week 4","Week 5","Week 6","Weeks 2–6"]
    return ["Month 1","Month 2","Month 3","Month 4","Month 5","Month 6","Month 7","Months 1–3","Months 4–7"]


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


def map_figure(geo, map_df, hazard, horizon, map_mode, focus, period, source_label):
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
            colorscale = "RdBu_r" if hazard == "Heatwave" else "BrBG"
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
        if not np.isfinite(v):
            return "Data unavailable"
        if unit == "%": return f"{v:.1f}%"
        if unit == "°C": return f"{v:.1f} °C"
        if unit == "mm": return f"{v:.1f} mm"
        if unit == "m³/s": return f"{v:,.1f} m³/s"
        return f"{v:.1f}"

    df["VALUE_DISPLAY"] = [value_string(v) for v in pd.to_numeric(df["value"], errors="coerce")]
    df["SOURCE_DISPLAY"] = source_label
    df["HORIZON_DISPLAY"] = f"{horizon} · {period}"

    custom = np.stack([
        df["REGION_NAME"].astype(str),
        df["ADMIN1"].astype(str),
        df["VALUE_DISPLAY"].astype(str),
        df["RISK_CLASS"].astype(str),
        df["HORIZON_DISPLAY"].astype(str),
        df["SOURCE_DISPLAY"].astype(str),
    ], axis=1)

    fig = go.Figure(go.Choropleth(
        geojson=geo,
        locations=df["REGION_CODE"],
        z=df["value"],
        featureidkey="properties.REGION_CODE",
        colorscale=colorscale,
        zmin=zmin, zmax=zmax,
        marker_line_width=.45,
        marker_line_color="rgba(255,255,255,.80)",
        colorbar=dict(
            title=colorbar_title, thickness=16, len=.76,
            tickvals=tickvals, ticktext=ticktext,
        ),
        customdata=custom,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "%{customdata[1]}<br>"
            + value_label + ": <b>%{customdata[2]}</b><br>"
            "Risk class: %{customdata[3]}<br>"
            "Window: %{customdata[4]}<br>"
            "Source: %{customdata[5]}"
            "<extra></extra>"
        ),
    ))

    focus_row = df[df["REGION_NAME"] == focus]
    if len(focus_row):
        r = focus_row.iloc[0]
        fig.add_trace(go.Scattergeo(
            lon=[float(r["rep_lon"])], lat=[float(r["rep_lat"])],
            mode="markers+text", text=[focus], textposition="top center",
            marker=dict(size=8, color="#111827", line=dict(width=1, color="white")),
            name="Focus area",
            customdata=[[r["VALUE_DISPLAY"], r["RISK_CLASS"]]],
            hovertemplate=(
                f"<b>{focus}</b><br>"
                + value_label + ": <b>%{customdata[0]}</b><br>"
                "Risk class: %{customdata[1]}<extra></extra>"
            ),
        ))

    fig.update_geos(
        fitbounds="locations", visible=False, projection_type="mercator",
        showcountries=False, showcoastlines=False, showland=False,
        bgcolor="rgba(0,0,0,0)"
    )
    fig.update_layout(
        height=720,
        margin=dict(l=0,r=0,t=45,b=0),
        title=dict(text=f"{hazard} · {horizon} · {map_mode}", x=.01, xanchor="left", font=dict(size=16)),
        hoverlabel=dict(bgcolor="white", font_size=13, font_family="Arial"),
        legend=dict(orientation="h", y=-.02),
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


def seasonal_anomaly_bar_figure(series, variable, focus_name, horizon_name):
    """Bar plot of the full available focus-area anomaly outlook."""
    unit = "°C" if variable == "Temperature anomaly" else "mm"
    if variable == "Temperature anomaly":
        colors = ["#2563EB" if v < 0 else "#DC2626" for v in series.to_numpy(float)]
        interpretation = "blue = cooler than model climatology; red = warmer than model climatology"
    else:
        colors = ["#B45309" if v < 0 else "#0284C7" for v in series.to_numpy(float)]
        interpretation = "brown = drier than model climatology; blue = wetter than model climatology"

    labels = (
        [pd.Timestamp(x).strftime("%d %b") for x in series.index]
        if horizon_name == "Sub-seasonal"
        else [pd.Timestamp(x).strftime("%b %Y") for x in series.index]
    )

    fig = go.Figure(go.Bar(
        x=labels,
        y=series.to_numpy(float),
        marker_color=colors,
        customdata=[[pd.Timestamp(t).strftime("%d %b %Y")] for t in series.index],
        hovertemplate=f"%{{customdata[0]}}<br>{variable}: <b>%{{y:.2f}} {unit}</b><extra></extra>",
    ))
    fig.add_hline(y=0, line_color="#475569", line_width=1)
    fig.update_layout(
        height=410,
        margin=dict(l=20,r=10,t=55,b=25),
        title=dict(
            text=f"{focus_name} · {variable} · {horizon_name}",
            x=.01, xanchor="left", font=dict(size=17)
        ),
        xaxis_title="Forecast period",
        yaxis_title=f"{variable} ({unit})",
        showlegend=False,
    )
    return fig, interpretation


def seasonal_anomaly_map_data(regions_df, long_data, period_name, variable):
    """Area-level anomaly values for the valid period selected in the main forecast controls."""
    section, sl = long_slice(period_name)
    suffix = "temp" if variable == "Temperature anomaly" else "precip"
    rows = []
    for r in regions_df.itertuples():
        s = (
            long_data.get(str(r.REGION_CODE), {})
            .get(f"{section}_{suffix}", pd.Series(dtype=float))
        )
        s = pd.to_numeric(s, errors="coerce").iloc[sl]
        value = float(s.mean()) if len(s.dropna()) else np.nan
        rows.append({**r._asdict(), "value": value})
    return pd.DataFrame(rows)


def seasonal_anomaly_map_figure(
    geojson_obj, anomaly_df, variable, focus_name, horizon_name, period_name, source_label
):
    """
    District/municipality choropleth with a zero-centred diverging palette.
    This intentionally avoids interpolating a false smooth raster between administrative centroids.
    """
    df = anomaly_df.copy()
    df["REGION_CODE"] = df["REGION_CODE"].astype(str)
    vals = pd.to_numeric(df["value"], errors="coerce").dropna()
    lim = max(
        0.1 if variable == "Temperature anomaly" else 1.0,
        float(np.nanquantile(np.abs(vals), .98)) if len(vals) else 1.0
    )
    unit = "°C" if variable == "Temperature anomaly" else "mm"

    if variable == "Temperature anomaly":
        # SST-anomaly-style palette: blue/cyan -> white -> yellow/orange/red.
        colorscale = [
            [0.00,"#1D4ED8"], [0.18,"#0EA5E9"], [0.36,"#22D3EE"],
            [0.50,"#F8FAFC"],
            [0.64,"#FDE047"], [0.82,"#F97316"], [1.00,"#DC2626"],
        ]
        meaning = "negative = cooler than model climatology · positive = warmer than model climatology"
    else:
        # Dry -> neutral -> wet.
        colorscale = [
            [0.00,"#9A3412"], [0.20,"#EA580C"], [0.38,"#FDBA74"],
            [0.50,"#F8FAFC"],
            [0.62,"#A5F3FC"], [0.80,"#0EA5E9"], [1.00,"#1D4ED8"],
        ]
        meaning = "negative = drier than model climatology · positive = wetter than model climatology"

    def display(v):
        return "Data unavailable" if not np.isfinite(v) else f"{v:+.2f} {unit}"

    df["DISPLAY"] = [display(v) for v in pd.to_numeric(df["value"], errors="coerce")]
    df["SIGNAL"] = [
        "Near model climatology" if not np.isfinite(v) or abs(v) < (0.1 if unit=="°C" else 1.0)
        else (
            ("Warmer than climatology" if v>0 else "Cooler than climatology")
            if variable=="Temperature anomaly"
            else ("Wetter than climatology" if v>0 else "Drier than climatology")
        )
        for v in pd.to_numeric(df["value"], errors="coerce")
    ]

    custom = np.stack([
        df["REGION_NAME"].astype(str),
        df["ADMIN1"].astype(str),
        df["DISPLAY"].astype(str),
        df["SIGNAL"].astype(str),
    ], axis=1)

    fig = go.Figure(go.Choropleth(
        geojson=geojson_obj,
        locations=df["REGION_CODE"],
        z=df["value"],
        featureidkey="properties.REGION_CODE",
        colorscale=colorscale,
        zmin=-lim, zmax=lim, zmid=0,
        marker_line_width=.40,
        marker_line_color="rgba(255,255,255,.82)",
        colorbar=dict(
            title=f"{unit} anomaly",
            thickness=18,
            len=.78,
            tickformat="+.1f",
        ),
        customdata=custom,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "%{customdata[1]}<br>"
            + variable + ": <b>%{customdata[2]}</b><br>"
            "Interpretation: %{customdata[3]}<br>"
            f"Valid period: {period_name}<br>"
            f"Source: {source_label}"
            "<extra></extra>"
        )
    ))

    focus_row = df[df["REGION_NAME"] == focus_name]
    if len(focus_row):
        r = focus_row.iloc[0]
        fig.add_trace(go.Scattergeo(
            lon=[float(r["rep_lon"])], lat=[float(r["rep_lat"])],
            mode="markers+text", text=[focus_name], textposition="top center",
            marker=dict(size=8,color="#111827",line=dict(width=1,color="white")),
            name="Focus area",
            hovertemplate=f"<b>{focus_name}</b><br>{variable}: {r['DISPLAY']}<extra></extra>",
        ))

    fig.update_geos(
        fitbounds="locations", visible=False, projection_type="mercator",
        showcountries=False, showcoastlines=False, showland=False,
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        height=650,
        margin=dict(l=0,r=0,t=58,b=0),
        title=dict(
            text=f"{variable} · {horizon_name} · {period_name}",
            x=.01,xanchor="left",font=dict(size=17)
        ),
        hoverlabel=dict(bgcolor="white",font_size=13,font_family="Arial"),
        legend=dict(orientation="h",y=-.02),
    )
    return fig, meaning


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
<div class="hero">
<div class="brandline"><span class="brandmark">REACH</span><span class="brandtag">CLIMATE × HEALTH · EARLY WARNING</span></div>
<h1>Climate–Health Early Warning Data Portal</h1>
<p>Zambia + Brazil · maternal & child health-system preparedness · physical and probabilistic maps · compound hazards · river-flow forecasting</p>
</div>
""",unsafe_allow_html=True)
st.caption("RESEARCH DECISION-SUPPORT PORTAL · Forecasts update from linked sources. Official national warnings remain authoritative.")

topc1,topc2,topc3=st.columns([1,1,2.2])
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

st.markdown('<div class="section">Live data & climate-driver portal</div>',unsafe_allow_html=True)
cards=st.columns(6)
with cards[0]:
    st.markdown('<div class="source-card"><span class="source-title">ECMWF</span><br><span class="source-note">IFS · ENS · EC46 · SEAS5</span></div>',unsafe_allow_html=True)
    st.link_button("Source", "https://open-meteo.com/en/docs/ecmwf-api", use_container_width=True)
with cards[1]:
    st.markdown('<div class="source-card"><span class="source-title">NOAA</span><br><span class="source-note">GFS · GEFS · NMME</span></div>',unsafe_allow_html=True)
    st.link_button("Source", NMME_URL, use_container_width=True)
with cards[2]:
    st.markdown('<div class="source-card"><span class="source-title">GloFAS</span><br><span class="source-note">River discharge / flood guidance</span></div>',unsafe_allow_html=True)
    st.link_button("Source", "https://open-meteo.com/en/docs/flood-api", use_container_width=True)
with cards[3]:
    etxt="Unavailable" if not enso_info else f"{enso_info['phase']} · {enso_info['prob']:.0f}%"
    st.markdown(f'<div class="source-card"><span class="source-title">ENSO / RONI</span><br><span class="source-note">{etxt}</span></div>',unsafe_allow_html=True)
    st.link_button("NOAA CPC", CPC_ENSO_URL, use_container_width=True)
with cards[4]:
    if country=="Zambia":
        txt="Unavailable" if not dmi_info else f"{dmi_info['value']:+.2f} °C · {dmi_info['phase']}"
        st.markdown(f'<div class="source-card"><span class="source-title">IOD / DMI</span><br><span class="source-note">{txt}</span></div>',unsafe_allow_html=True)
        st.link_button("NOAA PSL", DMI_WEB, use_container_width=True)
    else:
        txt="Unavailable" if not atlantic_info else f"TNA−TSA {atlantic_info['gradient']:+.2f} °C"
        st.markdown(f'<div class="source-card"><span class="source-title">Tropical Atlantic</span><br><span class="source-note">{txt}</span></div>',unsafe_allow_html=True)
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
        period=st.selectbox("3 · Valid period",period_options(horizon))

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
            st.caption(
                f"{country} · {state_name if country=='Brazil' else '116 districts'} · {hazard} · {horizon} · {period} · "
                f"{mode} · {len(map_df)}/{len(regions)} areas · source status: {map_status}"
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
                map_figure(geo,map_df,hazard,horizon,mode,focus,period,source_label),
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
        cols=st.columns(6)
        vals=[fv,sm["min"],sm["mean"],sm["median"],sm["max"],np.nan]
        labels=[focus,"Minimum","Mean","Median","Maximum","Highest-signal area"]
        for i,(c,l,v) in enumerate(zip(cols,labels,vals)):
            if l=="Highest-signal area":
                c.metric(l,maxrow.REGION_NAME if maxrow is not None else "—")
            else:
                c.metric(l,fmt(v,unit))
        if unit=="%":
            st.caption(f"{focus}: {risk_label(fv)} · highest area: {maxrow.REGION_NAME if maxrow is not None else '—'} ({risk_label(sm['max'])}).")

    # -----------------------------------------------------------------------
    # Focus tabs: time series / GloFAS / climate drivers / briefing
    # -----------------------------------------------------------------------
    meta=regions[regions.REGION_NAME==focus].iloc[0]
    tabs=st.tabs(["Time series & uncertainty","River hydrology","Climate drivers","Decision-maker briefing","Documentation · return periods · SDM","Downloads · CSV / Stella","Forecast verification · REACH pilots"])

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
        st.markdown("### Focus-area forecast time series")
        if horizon in ("Short range","Medium range") and hazard!="Flood – river discharge (GloFAS)":
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
                        ts_export["Area"] = focus
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

        elif horizon in ("Sub-seasonal","Seasonal") and "long" in payload:
            x=payload["long"].get(str(meta.REGION_CODE),{})
            section,sl=long_slice(period)
            tm=x.get(f"{section}_temp",pd.Series(dtype=float))
            pm=x.get(f"{section}_precip",pd.Series(dtype=float))

            long_idx = tm.index.union(pm.index).sort_values()
            if len(long_idx):
                long_export = pd.DataFrame({"Date": long_idx})
                long_export["Country"] = country
                long_export["Area"] = focus
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
                    "Area": focus,
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
        # ENSO phase probabilities
        # ---------------------------------------------------------------
        st.markdown("### ENSO outlook · El Niño / Neutral / La Niña")
        try:
            enso_visual_df = enso_table()
            enso_fig, enso_plot_df = enso_probability_figure(enso_visual_df)
            st.plotly_chart(enso_fig, use_container_width=True)
            st.caption(
                "NOAA CPC ENSO outlook periods are overlapping 3-month seasons. "
                "The month shown in brackets is the central month of each season. "
                "NOAA CPC uses the category 'Neutral'; 'near-neutral' elsewhere in this portal is descriptive wording for other indices such as DMI."
            )

            enso_table_view = enso_plot_df[[
                "Season code","Central month","La Niña","Neutral","El Niño",
                "Dominant phase","Dominant probability (%)"
            ]].rename(columns={
                "La Niña":"La Niña (%)",
                "Neutral":"Neutral (%)",
                "El Niño":"El Niño (%)",
            })
            st.dataframe(
                enso_table_view.style.format({
                    "La Niña (%)":"{:.1f}",
                    "Neutral (%)":"{:.1f}",
                    "El Niño (%)":"{:.1f}",
                    "Dominant probability (%)":"{:.1f}",
                }, na_rep="—"),
                hide_index=True,
                use_container_width=True,
            )
            st.download_button(
                "Download ENSO outlook probabilities CSV",
                enso_table_view.to_csv(index=False).encode("utf-8"),
                file_name=f"REACH_ENSO_Outlook_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
                key="download_enso_outlook_csv",
            )
        except Exception as exc:
            st.warning(f"ENSO outlook plot is temporarily unavailable: {exc}")

        # ---------------------------------------------------------------
        # Selectable seasonal / sub-seasonal anomaly visualisation
        # ---------------------------------------------------------------
        st.markdown("### Forecast anomaly visualisation")
        if horizon not in ("Sub-seasonal","Seasonal"):
            st.info(
                "Select **Sub-seasonal** or **Seasonal** in Forecast setup to activate anomaly bars and spatial anomaly maps. "
                "ENSO climate-state probabilities remain visible above because they provide seasonal background context."
            )
        else:
            av1,av2 = st.columns([1,1])
            with av1:
                anomaly_view = st.radio(
                    "Visualisation",
                    ["Bar plot of anomalies","Spatial anomaly map"],
                    horizontal=True,
                    key="seasonal_anomaly_view",
                )
            with av2:
                anomaly_variable = st.selectbox(
                    "Anomaly variable",
                    ["Temperature anomaly","Precipitation anomaly"],
                    key="seasonal_anomaly_variable",
                )

            long_data = payload.get("long",{}) if isinstance(payload,dict) else {}
            long_status_for_view = map_status if "map_status" in locals() else ""
            if not long_data:
                try:
                    with st.spinner("Loading seasonal anomaly fields..."):
                        long_data,long_status_for_view = regional_long(regions.to_dict("records"))
                except Exception as exc:
                    long_data = {}
                    st.warning(f"Seasonal anomaly data are temporarily unavailable: {exc}")

            if long_data:
                focus_code = str(meta.REGION_CODE)
                if anomaly_view == "Bar plot of anomalies":
                    s_anom = _seasonal_anomaly_series(
                        long_data, focus_code, horizon, anomaly_variable
                    )
                    if s_anom.empty:
                        st.info("No anomaly series is available for the selected focus area.")
                    else:
                        fig, meaning = seasonal_anomaly_bar_figure(
                            s_anom, anomaly_variable, focus, horizon
                        )
                        st.plotly_chart(fig,use_container_width=True)
                        sm_anom = stat_summary(s_anom)
                        ac = st.columns(4)
                        unit_anom = "°C" if anomaly_variable=="Temperature anomaly" else "mm"
                        ac[0].metric("Minimum",fmt(sm_anom["min"],unit_anom))
                        ac[1].metric("Mean",fmt(sm_anom["mean"],unit_anom))
                        ac[2].metric("Median",fmt(sm_anom["median"],unit_anom))
                        ac[3].metric("Maximum",fmt(sm_anom["max"],unit_anom))
                        st.caption(
                            f"{meaning}. These are model anomalies relative to the forecast system climatology, not absolute temperature or rainfall."
                        )

                        series_export = pd.DataFrame({
                            "Date": s_anom.index,
                            "Country": country,
                            "Area": focus,
                            "Horizon": horizon,
                            "Variable": anomaly_variable,
                            "AnomalyValue": s_anom.to_numpy(float),
                            "Unit": unit_anom,
                            "Source":"ECMWF EC46 / SEAS5 via Open-Meteo seasonal API",
                        })
                        st.download_button(
                            "Download anomaly bar data CSV",
                            series_export.to_csv(index=False).encode("utf-8"),
                            file_name=f"REACH_Anomaly_Series_{country}_{focus}_{anomaly_variable.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                            mime="text/csv",
                            use_container_width=True,
                            key="download_anomaly_series_csv",
                        )
                else:
                    anomaly_map_df = seasonal_anomaly_map_data(
                        regions,long_data,period,anomaly_variable
                    )
                    fig, meaning = seasonal_anomaly_map_figure(
                        geo,anomaly_map_df,anomaly_variable,focus,horizon,period,
                        "ECMWF EC46 / SEAS5"
                    )
                    st.plotly_chart(fig,use_container_width=True)
                    st.caption(
                        f"{meaning}. The map shades districts/municipalities using a zero-centred diverging palette, similar to standard anomaly maps. "
                        "It does not interpolate a false smooth raster between administrative areas."
                    )
                    map_export = anomaly_map_df[[
                        "REGION_CODE","REGION_NAME","ADMIN1","rep_lat","rep_lon","value"
                    ]].copy()
                    map_export["Country"] = country
                    map_export["Horizon"] = horizon
                    map_export["ValidPeriod"] = period
                    map_export["Variable"] = anomaly_variable
                    map_export["Unit"] = "°C" if anomaly_variable=="Temperature anomaly" else "mm"
                    map_export["Source"] = "ECMWF EC46 / SEAS5 via Open-Meteo seasonal API"
                    st.download_button(
                        "Download spatial anomaly CSV",
                        map_export.to_csv(index=False).encode("utf-8"),
                        file_name=f"REACH_Spatial_Anomaly_{country}_{anomaly_variable.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="download_spatial_anomaly_csv",
                    )

                st.caption(
                    f"Forecast source status: {long_status_for_view}. "
                    "The seasonal/sub-seasonal anomaly layer is automatically linked to the country/state, focus area, horizon and valid period selected in the main dashboard."
                )

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
                peak=f"Peak hourly temperature in {focus} is {fmt(timing.get('heat_peak',np.nan),'°C')} at {fmt_dt(timing.get('heat_peak_time'))}."
            if timing.get("rain72_start") is not None:
                peak+=f" The wettest 72-hour window in {focus} is {fmt_dt(timing.get('rain72_start'))} to {fmt_dt(timing.get('rain72_end'))}, with {fmt(timing.get('rain72',np.nan),'mm / 72 h')}."
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
            drivers+=" These indices provide seasonal context rather than direct district hazard probabilities."

            hyd=""
            if glofas_info and glofas_info.get("valid"):
                hyd=f" GloFAS focus-area median discharge is {fmt(glofas_info['median'],'m³/s')}, maximum {fmt(glofas_info['max'],'m³/s')}, peak date {fmt_dt(glofas_info['peak'],False)}, with P(Q>Q2) {glofas_info['p2']:.0f}%."
            elif glofas_info and not glofas_info.get("valid"):
                hyd=" The selected GloFAS river cell failed the sanity check and should not be presented as final river guidance."

            base_summary=(
                f"**{country} · {horizon} · {hazard}**\n\n"
                f"**Forecast window:** {window}\n\n"
                f"**Spatial result:** Across {len(map_df)} areas, the selected map value ranges from {fmt(sm['min'],unit)} to {fmt(sm['max'],unit)}, "
                f"with mean {fmt(sm['mean'],unit)} and median {fmt(sm['median'],unit)}. {focus} is {fmt(fv,unit)}. "
                f"The highest mapped signal is in **{max_area}**.\n\n"
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
            st.download_button("Download briefing",editable.encode(),file_name=f"REACH_EWS_{country}_{focus}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",mime="text/plain",use_container_width=True)


    with tabs[4]:
        st.markdown("## Documentation, return periods and system-dynamics integration")
        st.caption(
            "This section explains the data sources, climate indices, return periods and how forecast information is transferred into the REACH System Dynamics Model (Stella). "
            "Seasonal climate indices provide large-scale context; the district or municipality warning is based on the forecast and hydrological evidence shown in the portal."
        )

        st.markdown("### 1 · Return-period forecast for the selected area")
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
                    country, focus, hazard, horizon, period, rp_kind, rp_result,
                    trigger_rp, trigger_probability, rp_unit, rp_levels_main, rp_start, rp_end
                )
                st.download_button(
                    "Download Stella/SDM return-period hand-off CSV",
                    sdm_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"REACH_SDM_RP_handoff_{country}_{focus}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="download_sdm_rp"
                )

                threshold_exports=[]
                if not rp_table_daily.empty:
                    xx=rp_table_daily.copy(); xx["Country"]=country; xx["Area"]=focus; xx["Forecast horizon"]=horizon; xx["Valid period"]=period; threshold_exports.append(xx)
                if not rp_table_main.empty:
                    xx=rp_table_main.copy(); xx["Country"]=country; xx["Area"]=focus; xx["Forecast horizon"]=horizon; xx["Valid period"]=period; threshold_exports.append(xx)
                if threshold_exports:
                    rp_export=pd.concat(threshold_exports,ignore_index=True)
                    st.download_button(
                        "Download return-level table for Stella",
                        rp_export.to_csv(index=False).encode("utf-8"),
                        file_name=f"REACH_ReturnLevels_{country}_{focus}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv",use_container_width=True,key="download_return_levels"
                    )
        except Exception as exc:
            st.warning(f"Return-period forecast could not be calculated for this view: {exc}")

        st.markdown("### 2 · Understanding 2-, 5-, 10-, 20-, 50- and 100-year return levels")
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

        st.markdown("### 3 · Heatwave occurrence and return-period severity")
        st.markdown(
            """
The REACH framework uses **two complementary heat measures**:

1. **Heatwave occurrence:** daily Tmax above the fixed local **TX90** threshold for at least **3 consecutive days**.
2. **Return-period severity:** fit a GEV to the historical **annual maximum 3-day mean Tmax (TX3d)**, then classify the forecast ensemble against 2-, 5-, 10-, 20-, 50- and 100-year heat-severity return levels.

This keeps the 3-day heatwave definition while providing Stella with a return-period-compatible severity class.  
The return-period class is a *rarity/severity label*; actual heat impacts should still depend on duration, peak/cumulative exceedance, exposure and system vulnerability.
"""
        )

        st.markdown("### 4 · Data-source and climate-index glossary")
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
- **ENSO probability bars:** each bar is an overlapping 3-month NOAA CPC outlook season and sums to approximately 100%. Blue is La Niña, grey is Neutral and red is El Niño. The largest segment is the dominant climate-state probability for that season.
- **Anomaly bar plot:** shows the focus area's week-by-week (sub-seasonal) or month-by-month (seasonal) anomaly. Temperature is in °C relative to model climatology; precipitation is in mm relative to model climatology.
- **Spatial anomaly map:** shades the selected country's districts or the selected Brazilian state's municipalities for the chosen valid period. Temperature uses a blue-to-red zero-centred scale; precipitation uses dry brown/orange to wet cyan/blue.
- **Anomaly ≠ event:** a positive temperature anomaly does not automatically mean a heatwave, and a positive precipitation anomaly does not automatically mean flooding.
"""
        )

        st.markdown("### 5 · Interpreting ENSO/RONI, IOD/DMI and Tropical Atlantic indices")
        st.markdown(
            """
- **RONI > +0.5 °C** supports an El Niño classification; **RONI < −0.5 °C** supports La Niña when the persistence criteria are met. NOAA now uses RONI for official ENSO monitoring/prediction. The red/grey/blue ENSO bars are probabilities of **El Niño / Neutral / La Niña**, not probabilities of flood or heatwave in a REACH district.
- **DMI > 0** indicates a positive Indian Ocean Dipole; **DMI < 0** indicates a negative IOD. The sign describes the east–west SST gradient; regional rainfall impacts must still be inferred from the dynamical forecast.
- **TNA** and **TSA** are tropical North/South Atlantic SST-anomaly indices. The portal displays **TNA−TSA** as a simple Brazil contextual diagnostic. Do not interpret its sign as a deterministic flood trigger.
- **NAO** describes the North Atlantic pressure dipole associated with the Icelandic Low and Azores High. It is documented for completeness but is not currently used in the REACH hazard equations.
"""
        )

        st.markdown("### 6 · REACH System Dynamics Model / Stella integration")
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

        st.markdown("### 7 · Lead-time action framework")
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

        st.markdown("### 8 · Evidence base and design precedents")
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

        st.markdown("### 9 · Forecast synthesis principle")
        st.markdown(
            """
A robust operational briefing should make **forecast discrepancies, convergence and source hierarchy visible**.
National/operational products provide the country context; global dynamical systems provide independent physical and probabilistic evidence;
hydrological forecasts provide river-specific evidence; and ocean-atmosphere indices explain the seasonal background.
Historical analogue relationships are supporting context and should not be treated as forecast probabilities for another country or season.
"""
        )

        st.markdown("### 10 · Source links")
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


    with tabs[5]:
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
        selected_value = fv if "fv" in locals() else np.nan
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
            "AdministrativeLevel": "District" if country=="Zambia" else "Municipality",
            "Area": focus,
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
            file_name=f"REACH_Forecast_Summary_{country}_{focus}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
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
            st.markdown("### C · Focus-area time series")
            ts_frames=[x for x in focus_timeseries_exports if isinstance(x,pd.DataFrame) and not x.empty]
            if isinstance(glofas_timeseries_export,pd.DataFrame) and not glofas_timeseries_export.empty:
                ts_frames.append(glofas_timeseries_export)
            if ts_frames:
                # Use outer concatenation in long format to preserve different variables.
                ts_export_all=pd.concat(ts_frames,ignore_index=True,sort=False)
                st.download_button(
                    "Download forecast time-series CSV",
                    ts_export_all.to_csv(index=False).encode("utf-8"),
                    file_name=f"REACH_TimeSeries_{country}_{focus}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="download_timeseries_centre",
                )
            else:
                st.info("Focus-area time-series data are not available for this selection.")

        st.markdown("### D · Return-period values and Stella/SDM inputs")
        d1,d2=st.columns(2)
        with d1:
            if isinstance(rp_export,pd.DataFrame) and not rp_export.empty:
                st.download_button(
                    "Download return-period threshold values CSV",
                    rp_export.to_csv(index=False).encode("utf-8"),
                    file_name=f"REACH_ReturnLevels_{country}_{focus}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
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
                    file_name=f"REACH_Stella_SDM_Handoff_{country}_{focus}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
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

        zip_buffer=BytesIO()
        with zipfile.ZipFile(zip_buffer,"w",zipfile.ZIP_DEFLATED) as zf:
            for fname,data in package_files.items():
                zf.writestr(fname,data)
        st.download_button(
            "Download all selected CSVs as ZIP",
            zip_buffer.getvalue(),
            file_name=f"REACH_Selected_Data_{country}_{focus}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
            mime="application/zip",
            use_container_width=True,
            key="download_all_csv_zip",
        )

        st.caption(
            "For Stella, the consolidated summary and SDM hand-off preserve the return-level values, forecast exceedance probabilities, "
            "lead time and physical P10/P50/P90 values. The spatial and time-series files are retained for audit, sensitivity analysis and reproducibility."
        )


    with tabs[6]:
        st.markdown("## Forecast verification · REACH pilot sites")
        st.caption(
            "Verification remains restricted to Senanga, Sinazongwe, Recife and Palmares. "
            "The site, hazard family and verification indicator suite are linked automatically to the main dashboard selection."
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
        st.download_button("Download spatial forecast table",exp.to_csv(index=False).encode(),file_name=f"REACH_EWS_V5_{country}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",mime="text/csv",use_container_width=True)

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
<b>REACH · Climate–Health Early Warning Data Portal</b><br>
Decision-support portal for anticipatory maternal and child health-system preparedness in Zambia and Brazil.
Forecast information remains separate from realised hazard severity; official national warning services remain authoritative.
</div>
""",
    unsafe_allow_html=True,
)
