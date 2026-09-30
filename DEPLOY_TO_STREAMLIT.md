# GitHub → Streamlit Community Cloud

## 1. Create the GitHub repository

Suggested repository name:

`reach-climate-health-ews`

Upload the **contents of this folder**, not the outer ZIP itself.

Keep these files at the repository root:

- `streamlit_app.py`
- `requirements.txt`
- `preflight_check.py`
- the four Zambia/Brazil geography/data files
- `.streamlit/config.toml`

## 2. Check locally before pushing

From PowerShell in the folder:

```powershell
py preflight_check.py
py -m pip install -r requirements.txt
py -m streamlit run streamlit_app.py
```

Check the main tabs and specifically open:

`Forecast verification · REACH pilots`

Confirm that Tmin/Tmean/Tmax and TX90/TX95/TX99 appear without warning boxes.

## 3. Deploy

In Streamlit Community Cloud:

1. Click **Create app**.
2. Select the GitHub repository and branch.
3. Set the main file path to `streamlit_app.py`.
4. Open **Advanced settings** and select Python **3.12**.
5. Deploy.

## 4. After deployment

Test:
- Zambia → Senanga → Heatwave
- Zambia → Sinazongwe → Flood – rainfall
- Brazil → Pernambuco → Recife
- Brazil → Pernambuco → Palmares
- Downloads · CSV / Stella
- Forecast verification · REACH pilots

If an external forecast provider is temporarily unavailable or rate-limits a request, the dashboard may show a source-specific availability message. That is separate from a Python-code error.

## 5. Sharing

Once Streamlit gives you the `.streamlit.app` URL, send that link to the team.
