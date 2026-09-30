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
