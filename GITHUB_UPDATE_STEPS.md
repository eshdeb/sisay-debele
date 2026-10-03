# Update the existing GitHub / Streamlit app

Your existing Streamlit URL can stay the same.

## Recommended update

Upload/replace the **full contents of this release folder** in the existing GitHub repository. This ensures the new facility-support files and revised dependency list are deployed together.

Files that changed or were added in this release include:
- `streamlit_app.py`
- `requirements.txt`
- `README.md`
- `VERSION.txt`
- `preflight_check.py`
- `zambia_pilot_facility_details.xls`
- `zambia_pilot_hmis_context.csv`
- `SHA256SUMS.txt`

The Zambia/Brazil national geography files and `.streamlit/config.toml` remain part of the complete package.

## GitHub

1. Open the existing repository.
2. Choose **Add file → Upload files**.
3. Upload the **contents of the unzipped release folder** (do not upload only the outer ZIP as the app code).
4. Commit the files to `main`.
5. Streamlit Community Cloud should redeploy the existing app automatically.

## Local test before upload

```powershell
py preflight_check.py
py -m pip install -r requirements.txt
py -m streamlit run streamlit_app.py
```

Check at minimum:
- all seven main tabs are filled/high-contrast and visible
- Forecast setup selectors are filled and legible
- Zambia → Senanga → Health-facility drill-down
- Zambia → Sinazongwe → Health-facility drill-down
- Brazil → Pernambuco → Recife → Health-facility drill-down
- Brazil → Pernambuco → Palmares → Health-facility drill-down
- district/municipality overview remains the default
- facility selection updates point-specific time series/diagnostics
- Downloads include facility forecast/registry when a pilot registry is loaded
- Forecast verification remains clearly identified as parent pilot-area verification


## V10 checks

After deployment, also confirm:
- inactive analysis tabs render as light muted buttons with dark readable text; the active tab renders dark teal with white text
- Forecast setup selectboxes render as light blue-grey clickable fields with dark text and a large dark-teal chevron button on the right
- the right-hand dropdown button is clearly visible, comfortably wide, and easy to click
- Brazil facility dropdowns show facility names without unexplained numeric CNES type suffixes
- Heatwave short/medium range shows side-by-side ECMWF and NOAA GFS facility temperature-gradient plots with labelled contour values, grouped facility bars and a model-difference map
- Rainfall short/medium range shows labelled facility rainfall contours when values vary spatially, grouped ECMWF/GFS bars and a model-difference map
- Facility forecast screen includes a direct-value bar chart plus facility minimum/mean/median/maximum/range statistics
- Spatial summary shows selected area, selected value, minimum, mean, median, maximum and mapped range
- Documentation explains 116 Zambia districts, 5,572 Brazil municipalities, the four REACH pilot facility areas and the 21 Senanga / 32 Sinazongwe project-facility inventory counts
- the selected district/municipality or facility shows the 2×2 ECMWF/GFS/ERA5 historical-context comparison in Time series & uncertainty
- ERA5 is labelled as historical climatology/threshold context for future forecasts, while actual retrospective verification remains in Forecast verification
- the selected-data ZIP includes `facility_ecmwf_gfs_comparison.csv` when facility model comparison is available


V9 visual check: verify the gradient surface is lighter/transparent while contour numbers and facility names remain dark and fully readable; then test one Sub-seasonal and one Seasonal pilot view.


### V12 facility-gradient consistency
V12 keeps all existing portal content and restores a fully visible facility contour/gradient for the active temperature or precipitation forecast across short-range, medium-range, sub-seasonal and seasonal horizons. Facility names and dark contour-value labels are drawn directly on the surface. The surface is a visual IDW interpolation of forecast values sampled at facility coordinates and must not be interpreted as the native forecast-model grid. V12 also updates Plotly axis-title syntax for current Plotly 6.x compatibility and uses a restrained publication-style palette without fading the scientific gradient surface.
