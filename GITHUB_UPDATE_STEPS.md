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
