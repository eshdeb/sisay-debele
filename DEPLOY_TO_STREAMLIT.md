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
