# REACH Climate–Health Early Warning Data Portal

**Final GitHub / Streamlit release — 2 October 2026**  
**V7 · Labelled facility contours + facility bar comparisons + ECMWF/GFS/ERA5 context + refined accessible interface**

This repository contains the full REACH climate–health research decision-support dashboard.

## Coverage and core functions

- **Zambia:** all 116 districts
- **Brazil:** all 5,572 municipalities
- **REACH pilots:** Senanga, Sinazongwe, Recife and Palmares
- heatwave, rainfall-driven flood, river-discharge flood, drought and compound hazards
- short-, medium-, sub-seasonal and seasonal forecast workflows
- ECMWF / NOAA model comparison
- GloFAS river-flow diagnostics
- ENSO/RONI, IOD/DMI and Tropical Atlantic context
- return-period thresholds and physical return levels
- Stella / SDM CSV hand-off
- historical forecast verification for the four pilot areas
- downloadable spatial, time-series, facility and verification outputs

## Facility-level forecast drill-down

The four REACH pilot areas now support a nested facility workflow:

**Country → district/municipality → health facility**

The district/municipality overview remains the default and parent geography. Selecting a health facility moves point-specific forecast calculations to that facility's coordinates while preserving the parent-area spatial context.

For each pilot area, the dashboard can provide:

- mapped health-facility locations
- facility-specific hazard/exposure signal for the selected forecast setup
- comparison/ranking table across mapped facilities
- selected-facility time series and forecast diagnostics
- facility-coordinate river-flow diagnostics where relevant
- facility-specific return-period/SDM hand-off metadata
- downloadable facility forecast/exposure CSV and registry CSV

### Facility data sources

**Zambia**
- bundled REACH pilot facility file for Senanga and Sinazongwe
- public Zambia NSDI health-facility layer as an online registry/cross-check
- bundled REACH HMIS context for Senanga and Sinazongwe (district-month context only)

**Brazil**
- public CNES/DATASUS facility registry retrieved at runtime for Recife and Palmares

The public-source calls are cached. If an external registry is temporarily unavailable, the parent district/municipality forecast remains available. Zambia also retains the bundled project-facility fallback.

### Important scientific interpretation

The facility layer is deliberately labelled **facility-specific hazard/exposure**, not automatically **facility operational risk**. A facility operational-risk score requires explicit readiness/access inputs such as staffing, WASH, electricity/backup power, cold-chain functionality, service availability, road/access disruption or similar operational information.

The bundled Zambia HMIS extract is used only as **district-level health-service context**. It is not silently assigned to individual facilities.

## High-contrast modern interface

The seven main analysis tabs are now filled controls with bold white text so all tabs remain visible, including:

- Time series & uncertainty
- River hydrology
- Climate drivers
- Decision-maker briefing
- Documentation · return periods · SDM
- Downloads · CSV / Stella
- Forecast verification · REACH pilots

The tab strip wraps on narrower screens. The active tab has a distinct teal/navy style and focus border. Forecast-setup selectors, radio controls, download buttons and source buttons also use filled high-contrast styles. V7 softens the selector fill with semi-transparent teal/navy tones and increases label/selected-value font sizes so the controls remain prominent without feeling overly heavy.


## V7 visual, facility-summary and model-comparison revision

This release adds the visual analysis requested for district/municipality and facility forecasts without removing the existing numerical cards, maps, ensemble uncertainty, hydrology, climate drivers, SDM outputs or verification workflows.

### Facility spatial temperature gradients

For short- and medium-range heat forecasts, the dashboard now:

- samples **ECMWF IFS HRES** and **NOAA GFS** at each mapped health-facility coordinate
- displays the two models side by side
- creates a blue → cyan → yellow → orange → red **Tmax spatial gradient** with each facility plotted as a point
- highlights the selected facility
- shows an ECMWF-minus-GFS spatial difference map
- exposes the underlying point values in a table and downloadable CSV

The coloured gradient is an **inverse-distance interpolation of forecast values sampled at facility points**. V7 adds labelled contour lines so the temperature or precipitation value can be read directly on the surface. It is a visualisation layer and is not presented as the native model grid. If all facility precipitation values are effectively identical, the app does not invent a gradient; it falls back to the facility point map.

For rainfall-driven flood forecasts, the same section shows side-by-side labelled facility rainfall contours when spatial variation exists, a grouped ECMWF/GFS facility bar chart, and a model-difference map. Compound Flood + Heatwave now displays both the temperature and rainfall comparison panels.


### Facility bar charts and summary statistics

V7 adds direct-value bar charts so the facility forecasts are not only visible in tables or maps. The active facility forecast screen now shows:

- a horizontal bar comparison of the direct point-specific forecast values across mapped facilities
- the selected facility highlighted with a star/gold emphasis
- grouped **ECMWF IFS HRES vs NOAA GFS** facility bars for temperature and rainfall
- parent-area name, number of facilities screened, selected facility value, facility mean and facility range
- an explanatory line giving facility minimum, mean, median, maximum and range width
- a selected-location valid-period summary showing ECMWF and GFS minimum, mean, maximum and range; rainfall views also report valid-window totals

The national/state spatial summary also now shows the selected administrative area, selected value, minimum, mean, median, maximum and mapped range. The selected district/municipality value is a representative-point forecast for that administrative area; the national/state summary statistics describe the mapped administrative areas, not every model-grid pixel inside the selected polygon.

### Geography and facility coverage documented in the app

The Documentation tab now states the hierarchy and coverage explicitly:

- **Zambia:** 116 districts available for district-level forecasts
- **Brazil:** 5,572 municipalities available for municipality-level forecasts
- **Zambia REACH facility pilots:** Senanga and Sinazongwe
- **Brazil REACH facility pilots:** Recife and Palmares
- the bundled Zambia facility-detail workbook lists **21 Senanga facilities** and **32 Sinazongwe facilities**
- live mapped facility counts can differ because the active registry must provide usable coordinates
- Brazil pilot counts are obtained live from CNES/DATASUS
- a Documentation control can refresh live counts for all four pilots and the Zambia national NSDI facility registry

This distinction prevents a registry total from being confused with the number of facilities that can actually receive a point forecast in the current session.

### District / municipality / facility model comparison

For short- and medium-range forecasts, the Time series & uncertainty tab now includes a 2×2 comparison panel for the currently selected district, municipality or facility:

1. ECMWF IFS HRES and NOAA GFS forecast values with **ERA5 historical climatology/threshold context**
2. ECMWF and GFS anomalies relative to the ERA5 day-of-year climatology
3. ECMWF-minus-GFS model difference through the valid window
4. selected-window summary bars

ERA5 is historical reference context (1981–2014) for a future forecast. It is **not** labelled as a future observed value. For retrospective forecast skill against actual ERA5, use the dedicated **Forecast verification · REACH pilots** tab.

### Facility names

The Brazil selector now prioritises the actual **CNES establishment name**. Unexplained numeric labels such as “CNES type 39” are no longer appended to the dropdown. A facility identifier is only appended where duplicate facility names would otherwise be ambiguous.

## Verification indicators

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

Historical verification remains at the **pilot-area** level unless a matched facility observation archive is added; selecting a facility does not manufacture facility-specific hindcast observations.

## Seasonal climate visualisation

The Climate drivers tab includes:

- NOAA CPC 3-month ENSO outlook probabilities for La Niña / Neutral / El Niño
- ENSO strength probabilities
- filled RONI anomaly outlook
- selectable temporal anomaly visualisation
- spatial anomaly maps by district/municipality
- temperature anomaly in °C and precipitation anomaly in mm
- downloadable focus-area/facility time series and spatial anomaly values

Basemap changes affect only visual context; forecast calculations are unchanged.

## Repository files added for the facility revision

- `zambia_pilot_facility_details.xls` — REACH pilot facility details used as a Zambia project fallback/enrichment source
- `zambia_pilot_hmis_context.csv` — compact Senanga/Sinazongwe district HMIS context derived from the uploaded dataset
- `DATA_SOURCES.md` — provenance and interpretation rules for facility/HMIS integration

`xlrd` is included in `requirements.txt` so the legacy `.xls` facility workbook can be read on Streamlit Cloud.

## Local preflight

```powershell
py preflight_check.py
py -m pip install -r requirements.txt
py -m streamlit run streamlit_app.py
```

## Streamlit Community Cloud

Use `streamlit_app.py` as the app entry point and Python **3.12** in Advanced settings. No API keys are required for the current public-source configuration.

The optional local Ollama briefing rewrite is intended for a computer running Ollama locally and will not normally work on Streamlit Community Cloud without a separately hosted AI endpoint. The transparent verified briefing remains available without Ollama.

## Scientific status

This is a REACH research decision-support prototype. Official national warning services remain authoritative. Facility-point outputs should be interpreted with the source, forecast horizon, spatial scale and data-availability limitations shown in the dashboard.
