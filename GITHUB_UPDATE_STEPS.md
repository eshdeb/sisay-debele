# Update the existing GitHub / Streamlit app

Your existing Streamlit URL can stay the same.

## Replace these files in GitHub
At minimum:
- `streamlit_app.py`
- `README.md`
- `VERSION.txt`
- `preflight_check.py`

The complete ZIP also includes the unchanged geography files and `.streamlit/config.toml`.

## GitHub
1. Open your existing repository.
2. Choose **Add file → Upload files**.
3. Upload the updated files.
4. Commit directly to `main`.
5. Streamlit Community Cloud should automatically redeploy the existing app.

## Local test
```powershell
py preflight_check.py
py -m pip install -r requirements.txt
py -m streamlit run streamlit_app.py
```

Check:
- main spatial map basemap + opacity
- Seasonal → Climate drivers → Phase / Strength / RONI
- Seasonal → Forecast anomaly visualisation → Temporal + spatial
- Temperature and precipitation anomaly
- Forecast verification
- Downloads / CSV / Stella
