# GitHub → Streamlit Community Cloud

## 1. Repository

Upload the **contents of this release folder**, not the outer ZIP itself, to the repository root.

Keep at root:
- `streamlit_app.py`
- `requirements.txt`
- `preflight_check.py`
- Zambia/Brazil national geography/data files
- `zambia_pilot_facility_details.xls`
- `zambia_pilot_hmis_context.csv`
- `.streamlit/config.toml`

## 2. Local check

```powershell
py preflight_check.py
py -m pip install -r requirements.txt
py -m streamlit run streamlit_app.py
```

Confirm the main tabs render as filled high-contrast controls and test the four pilot areas.

## 3. Deploy

In Streamlit Community Cloud:
1. Create/update the app from the GitHub repository and branch.
2. Set main file path to `streamlit_app.py`.
3. Select Python **3.12** in Advanced settings.
4. Deploy/reboot the app after the dependency update.

## 4. Post-deployment checks

Test:
- Zambia → Senanga → district overview, then individual facility
- Zambia → Sinazongwe → district overview, then individual facility
- Brazil → Pernambuco → Recife → municipality overview, then individual facility
- Brazil → Pernambuco → Palmares → municipality overview, then individual facility
- River hydrology
- Climate drivers
- Decision-maker briefing
- Documentation · return periods · SDM
- Downloads · CSV / Stella
- Forecast verification · REACH pilots

The Brazil facility registry is retrieved from the public CNES/DATASUS API at runtime. The Zambia facility registry can combine the bundled REACH project file with the public NSDI service. External provider outages/rate limits should not remove the parent district/municipality forecast.

## 5. Interpretation

Facility outputs are point-specific hazard/exposure signals. Do not label them operational facility risk unless readiness/access data are explicitly integrated.


## V9 checks

After deployment, also confirm:
- the top analysis tabs render with translucent professional fills while tab text/icons remain fully opaque and the active tab remains clearly highlighted
- Forecast setup selectboxes render as softer translucent teal/slate controls with larger readable text
- Brazil facility dropdowns show facility names without unexplained numeric CNES type suffixes
- Heatwave short/medium range shows side-by-side ECMWF and NOAA GFS facility temperature-gradient plots with labelled contour values, grouped facility bars and a model-difference map
- every facility contour/gradient prints facility names beside point markers as well as labelled contour values
- Sub-seasonal selections (Week 2 through Weeks 2–6) show facility temperature/precipitation anomaly gradients where relevant
- Seasonal selections (Month 1 through Month 7 and multi-month windows) show facility temperature/precipitation anomaly gradients where relevant
- facility bars use softer semi-transparent fills while value labels remain fully opaque; contour fills are transparent but contour numbers/facility names are dark and opaque
- Rainfall short/medium range shows labelled facility rainfall contours when values vary spatially, grouped ECMWF/GFS bars and a model-difference map
- Facility forecast screen includes a direct-value bar chart plus facility minimum/mean/median/maximum/range statistics
- Spatial summary shows selected area, selected value, minimum, mean, median, maximum and mapped range
- Documentation explains 116 Zambia districts, 5,572 Brazil municipalities, the four REACH pilot facility areas and the 21 Senanga / 32 Sinazongwe project-facility inventory counts
- the selected district/municipality or facility shows the 2×2 ECMWF/GFS/ERA5 historical-context comparison in Time series & uncertainty
- ERA5 is labelled as historical climatology/threshold context for future forecasts, while actual retrospective verification remains in Forecast verification
- the selected-data ZIP includes `facility_ecmwf_gfs_comparison.csv` when facility model comparison is available


## V10 selector accessibility check
After deployment, confirm that the full Forecast setup field is clickable and that the right-hand chevron appears inside a clearly visible dark-teal button area rather than a narrow pale strip. Also confirm that inactive tabs use dark text on light muted backgrounds and the selected tab uses white text on dark teal.


### V12 facility-gradient consistency
V12 keeps all existing portal content and restores a fully visible facility contour/gradient for the active temperature or precipitation forecast across short-range, medium-range, sub-seasonal and seasonal horizons. Facility names and dark contour-value labels are drawn directly on the surface. The surface is a visual IDW interpolation of forecast values sampled at facility coordinates and must not be interpreted as the native forecast-model grid. V12 also updates Plotly axis-title syntax for current Plotly 6.x compatibility and uses a restrained publication-style palette without fading the scientific gradient surface.
