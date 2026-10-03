from pathlib import Path
import ast
import json
import py_compile
import pandas as pd

ROOT = Path(__file__).resolve().parent
APP = ROOT / "streamlit_app.py"

required = [
    "streamlit_app.py",
    "requirements.txt",
    ".streamlit/config.toml",
    "zambia_116_districts.geojson",
    "zambia_116_district_forecast_points.csv",
    "brazil_5572_municipalities_simplified.geojson",
    "brazil_5572_municipality_points.csv",
    "zambia_pilot_facility_details.xls",
    "zambia_pilot_hmis_context.csv",
    "DATA_SOURCES.md",
]

print("REACH EWS preflight check")
print("=" * 42)

missing = [x for x in required if not (ROOT / x).exists()]
if missing:
    raise SystemExit("Missing required file(s): " + ", ".join(missing))
print("[PASS] Required repository files are present.")

py_compile.compile(str(APP), doraise=True)
print("[PASS] streamlit_app.py compiles successfully.")

source = APP.read_text(encoding="utf-8")
tree = ast.parse(source)

imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for a in node.names:
            imports.add(a.asname or a.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        for a in node.names:
            imports.add(a.asname or a.name)

for needed in ["re", "json", "zipfile", "hashlib", "time", "BytesIO"]:
    if needed not in imports:
        raise SystemExit(f"Missing import required by the app: {needed}")
print("[PASS] Standard-library imports used by verification/download code are present.")

if "io.BytesIO()" in source:
    raise SystemExit("Old io.BytesIO() reference remains in app.")
print("[PASS] Download ZIP buffer uses BytesIO() consistently.")

if 'tickfont=dict(color="#1F2937",size=11),titlefont' in source:
    raise SystemExit("Obsolete Plotly contour colorbar titlefont property remains in app.")
print("[PASS] Plotly contour colorbar uses current title/font syntax.")

z_geo = json.loads((ROOT / "zambia_116_districts.geojson").read_text(encoding="utf-8"))
b_geo = json.loads((ROOT / "brazil_5572_municipalities_simplified.geojson").read_text(encoding="utf-8"))
z_pts = pd.read_csv(ROOT / "zambia_116_district_forecast_points.csv")
b_pts = pd.read_csv(ROOT / "brazil_5572_municipality_points.csv")

if len(z_geo.get("features", [])) != 116 or len(z_pts) != 116:
    raise SystemExit("Zambia geography check failed: expected 116 districts.")
print("[PASS] Zambia geography contains 116 districts.")

if len(b_geo.get("features", [])) != 5572 or len(b_pts) != 5572:
    raise SystemExit("Brazil geography check failed: expected 5,572 municipalities.")
print("[PASS] Brazil geography contains 5,572 municipalities.")

# Facility/HMIS support checks.
req_text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
if "xlrd" not in req_text:
    raise SystemExit("requirements.txt must include xlrd for the bundled legacy .xls facility file.")
print("[PASS] Facility workbook dependency (xlrd) is declared.")

hmis = pd.read_csv(ROOT / "zambia_pilot_hmis_context.csv")
if "district" not in hmis.columns or not {"Senanga", "Sinazongwe"}.issubset(set(hmis["district"].astype(str))):
    raise SystemExit("Pilot HMIS context check failed: expected Senanga and Sinazongwe district records.")
print(f"[PASS] Pilot HMIS context is present for Senanga and Sinazongwe ({len(hmis):,} rows).")

expected_text = [
    "Forecast verification · REACH pilot sites",
    "Daily minimum temperature",
    "Daily mean temperature",
    "Daily maximum temperature",
    "Heatwave TX90 · 3 consecutive days",
    "Heatwave TX95 · 3 consecutive days",
    "Heatwave TX99 · 3 consecutive days",
    "3-day precipitation > P90",
    "3-day precipitation > P95",
    "3-day precipitation > P99",
    "Downloads · CSV / Stella",
    "ENSO outlook · phase, strength and RONI anomaly",
    "Bar plot",
    "Spatial anomaly outlook",
    "Temperature anomaly",
    "Precipitation anomaly",
    "Temporal + spatial",
    "Satellite + streets",
    "ENSO strength probabilities",
    "RONI anomaly outlook",
    "Filled anomaly time series",
    "horizontal_colorbar",
    "Health-facility forecast drill-down",
    "District / municipality overview",
    "Facility forecast focus",
    "facility_forecast_exposure.csv",
    "facility_registry.csv",
    "FacilityRegistrySource",
    "Historical forecast verification on this tab remains at the parent pilot-area level",
    '[data-testid="stTabs"] [role="tab"]',
    '[data-testid="stSelectbox"] [role="combobox"]',
    'facility_temperature_gradient_figure',
    'facility_two_model_comparison',
    'ECMWF · NOAA GFS · ERA5 historical context',
    'ERA5 is shown as 1981–2014 historical climatology/threshold context',
    'facility_ecmwf_gfs_comparison.csv',
    'facility_contour_gradient_figure',
    'facility_precipitation_gradient_figure',
    'facility_signal_bar_figure',
    'facility_two_model_bar_figure',
    'showlabels=True',
    'Facility forecast values · bar comparison',
    'Geographic and health-facility coverage',
    'Load / refresh live facility counts for all four REACH pilots',
    'Mapped range',
    'facility_longrange_component_values',
    'Facility seasonal / sub-seasonal spatial gradients',
    'Facility names are printed beside the points',
    'mode="markers+text"',
    'diverging=True',
    'facility_longrange_anomaly_components.csv',
]
for text in expected_text:
    if text not in source:
        raise SystemExit(f"Expected final feature not found in app: {text}")
print("[PASS] Comprehensive verification and Stella/download features are present.")

print()
print("STATIC PREFLIGHT PASSED.")
print("Next local test:")
print("  py -m pip install -r requirements.txt")
print("  py -m streamlit run streamlit_app.py")
