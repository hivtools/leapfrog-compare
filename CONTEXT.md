# Leapfrog Compare

A Shiny dashboard for comparing Leapfrog's C++ model outputs (DP/AIM, Goals, EPPASM-leapfrog)
against Spectrum's reference outputs, per PJNZ file, to verify the leapfrog ports behave
correctly — including under interventions/scenarios encoded as different PJNZ files.

## Language

**Multi PJNZ tab**:
The top-level tab comparing leapfrog vs Spectrum output across two or more PJNZ files at
once, to check that an intervention encoded in one file changes the trajectory as expected
relative to another. Distinct from the AIM/Goals/EPPASM tabs, which each compare sources
for a single, individually-selected PJNZ file.
_Avoid_: "Compare tab", "scenario comparison" (no "scenario" concept exists elsewhere in
this codebase — PJNZ file is the unit of comparison).

**Model switch**:
The Multi PJNZ tab's control choosing which engine pair is being compared: **Goals** (leapfrog
Goals output vs Spectrum's HV_*-based modvars) or **DP/AIM** (leapfrog AIM output vs Spectrum's
AM_*/DP_*-based modvars). Determines both which PJNZ files are selectable (Goals-classified vs
AIM-only, via `is_goals_pjnz`) and which run function produces their data.

**Leapfrog line (Multi PJNZ tab)**:
On the Multi PJNZ tab, `dp_aim` (DP/AIM engine output) is always present as a leapfrog line.
Under the Goals model switch, the Goals-native engine output (`goals` key) is a *second*,
separate leapfrog line where it exists (15-49 only, per ADR-0002) — the two are never the same
line and both can be on screen at once, exactly as on the existing Goals tab's own 15-49
sub-tab.
