# REACH Climate–Health EWS · Design system

## Design objective

The portal should feel like a scientific decision-support product: calm, legible, trustworthy and operational. It should not look like a marketing dashboard or a collection of independent widgets.

## Information hierarchy

1. **Purpose and trust:** what the portal is for; official warning caveat.
2. **Decision journey:** Monitor → Locate → Time → Compare → Act.
3. **Geographic scope:** country/state and parent administrative area.
4. **Forecast configuration:** horizon, hazard, valid period, model/view.
5. **Primary spatial result:** the map is the dominant evidence surface.
6. **Summary and facility drill-down:** explain the selected result before deeper analysis.
7. **Evidence tabs:** time series, hydrology, climate drivers, briefing, documentation, downloads and verification.

## Colour vocabulary

The interface uses a restrained scientific palette rather than bright categorical UI colours.

- Deep navy: `#102F3B` — trust / primary header
- Deep teal: `#164D5C` — primary interaction
- Muted teal: `#2E6E6D` — secondary emphasis
- Sage: `#4E7B68` — action / context
- Muted gold: `#C99B3D` — selected / attention
- Clay: `#A86F5B` — warm secondary accent
- Ink: `#102A36` — main text
- Muted text: `#58707B`
- Canvas: `#F7FAFB`

Scientific map palettes remain variable-specific and must prioritise perceptual ordering, readable labels and sufficient contrast.

## Typography

- Use a clear sans-serif system font.
- Use sentence case for UI labels.
- Keep control labels visually stronger than explanatory notes.
- Use short headings and explanatory captions rather than large blocks of prose.

## Interaction rules

- Preserve one cascading selection context across the whole page.
- Keep dropdown arrows and click areas clearly visible.
- Never rely on colour alone for state or risk classification.
- Use tooltips/captions to explain scientific caveats at the point of interpretation.
- Keep the facility name and direct value available alongside interpolated contour surfaces.
- Keep selected facility highlighting consistent across maps and bars.

## Dashboard composition

Use multiple views only when each contributes a distinct decision perspective:

- map = where
- forecast-valid banner / time selector = when the mapped value applies
- summary metrics = how much
- bar comparison = which facility/area at the same valid time
- time series = how the signal evolves through time
- model comparison = agreement/disagreement
- verification = historical performance
- decision briefing = what to do with the evidence


## Temporal design rules

- Never display a forecast value without a visible valid date or valid interval nearby.
- Use UTC consistently in the cross-source interface; local-time conversion can be added later only with an explicit timezone label.
- A time selector must cascade to all facility views that represent the selected physical quantity.
- Daily, weekly and monthly products retain their native aggregation; do not imply an hourly event time when the source is aggregated.
- Keep model issue/run time visually distinct from forecast-valid time.

## Dense facility-map rule (V15)
Facility labels follow a density-aware rule rather than a one-style-fits-all rule.

- **Zambia pilots:** show facility names directly on the contour where they remain readable.
- **Brazil pilots:** show all facility names on hover; print only the selected facility name on the contour. Keep contour values visible.
- Do not reduce scientific signal opacity to solve label crowding. The gradient remains fully visible; clutter is solved through selective labelling and hover detail.
- Selected facilities must remain visually prominent without overwhelming neighbouring points.

The goal is a publication-quality first view with complete detail available through interaction.
