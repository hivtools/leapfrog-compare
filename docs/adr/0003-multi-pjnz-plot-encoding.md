# Multi PJNZ plots: colour encodes file, dash still encodes source, year axis is a union

Every other comparison plot in this app colours traces by demographic group (Male/Female/Total)
and uses line dash to encode source (solid=leapfrog, dashed=Spectrum, dotted=Goals-native).
Multi PJNZ repurposes colour to encode *which PJNZ file* a line belongs to instead — sex/age
disaggregation is dropped from this view entirely (v1 is totals-only) so colour is free to use
this way without a third visual channel competing with dash. A future per-sex facet would add
sex as a row facet (like `render_risk_group_comparison` already facets by risk group), not as a
third encoding on the same axes.

Selected PJNZ files commonly have different first/final years (different countries' PJN
files). The year-range slider uses the **union** of all selected files' ranges, so each file's
line simply ends at its own native boundary — the same behavior a single-file line already has
today. We rejected clipping to the intersection: it would silently hide part of a file's
history the moment a shorter-range file joins the comparison, which is actively misleading for
a tool whose purpose is spotting whether an intervention changed a trajectory.
