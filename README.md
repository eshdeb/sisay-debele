# REACH Climate–Health Early Warning Data Portal

**Final GitHub / Streamlit release — 30 September 2026**

This repository contains the full REACH research decision-support dashboard:

- Zambia: 116 districts
- Brazil: 5,572 municipalities
- Pilot forecast verification: Senanga, Sinazongwe, Recife and Palmares
- Heatwave, rainfall-driven flood, river-discharge flood, drought and compound hazards
- ECMWF / NOAA model comparison
- GloFAS river-flow diagnostics
- ENSO/RONI, IOD/DMI and Tropical Atlantic context
- return-period thresholds and corresponding physical values
- Stella / SDM CSV hand-off
- downloadable forecast, spatial, time-series and verification data

## Final verification indicators

Heat:
- Tmin, Tmean and Tmax
- 3-day mean Tmax
- TX90, TX95 and TX99 event comparisons

Precipitation:
- daily precipitation
- 3-day total, mean and maximum daily precipitation
- P90, P95 and P99 comparisons

River discharge:
- ensemble min / P10 / P25 / mean / P50 / P75 / P90 / max
- Q2 / Q5 / Q10 / Q20 / Q50 / Q100 return levels and exceedance probabilities

## Local preflight

Before deployment:

```powershell
py preflight_check.py
```

Then:

```powershell
py -m pip install -r requirements.txt
py -m streamlit run streamlit_app.py
```

## Streamlit Community Cloud

Use `streamlit_app.py` as the app entry point.

Select Python **3.12** in Streamlit's Advanced settings.

No API keys are required for the current public-source configuration.

### Optional Ollama briefing rewrite
The transparent verified briefing works normally on Streamlit Cloud.
The optional local Ollama rewrite is designed for a computer running Ollama locally and will not normally work on Streamlit Community Cloud without a separately hosted AI endpoint.

## Scientific status

This is a REACH research decision-support prototype. Official national warning services remain authoritative.


## Seasonal climate visualisation

The Climate drivers tab now includes:

- NOAA CPC 3-month ENSO outlook bars for **La Niña / Neutral / El Niño**
- exact ENSO probability values and dominant phase for each outlook season
- a user-selectable **Bar plot of anomalies**
- a user-selectable **Spatial anomaly map**
- temperature anomaly in °C
- precipitation anomaly in mm
- CSV download for ENSO, focus-area anomaly series and spatial anomaly values

The spatial anomaly map uses district/municipality shading rather than interpolating a false smooth surface between administrative centroids.
