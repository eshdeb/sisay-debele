# REACH EWS · Facility and health-data provenance

This release separates **forecast/hazard data**, **facility registry data**, and **health-service context** so the dashboard does not imply a level of evidence that the inputs do not support.

## Zambia facility registry

Primary runtime public source:
- Zambia NSDI Health Facilities ArcGIS layer
- Service layer: `https://www.map.gov.zm/arcgis/rest/services/Health/NSDI_Health/MapServer/0`

Bundled project source:
- `zambia_pilot_facility_details.xls`
- Used as a REACH project fallback/enrichment source for Senanga and Sinazongwe.

The app merges project and online registry records by normalised facility name and prefers the project record when the same named facility appears in both sources.

## Zambia HMIS context

Bundled compact file:
- `zambia_pilot_hmis_context.csv`

This is a Senanga/Sinazongwe subset of the uploaded district-month HMIS dataset. It is used for **district-level context only**. It is not attributed to individual facilities and is not used to manufacture a facility readiness score.

## Brazil facility registry

Runtime public source:
- CNES / DATASUS Open Data API
- Endpoint: `https://apidadosabertos.saude.gov.br/cnes/estabelecimentos`
- Documentation: `https://apidadosabertos.saude.gov.br/`

The app queries active establishments by municipality code for Recife and Palmares and uses reported facility coordinates for the point-specific forecast screen.

## Forecast sources

The existing EWS forecast architecture is retained. It includes ECMWF/Open-Meteo, NOAA/Open-Meteo, GloFAS/Open-Meteo and the climate-driver sources already documented in the dashboard.

## Interpretation rule

A facility point inherits no readiness assumptions from its location. The current facility output is therefore described as **facility-specific hazard/exposure**. An operational-risk score should only be introduced after explicit readiness/access inputs (for example staffing, electricity/backup, WASH, cold chain, service availability or access disruption) are integrated and documented.
