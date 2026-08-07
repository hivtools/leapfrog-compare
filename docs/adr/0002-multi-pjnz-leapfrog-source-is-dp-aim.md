# Multi PJNZ reuses each tab's existing `sources` list rather than inventing its own

`goals_simulation.hpp` documents `n_hv.total_population`, `new_infections_goals`, and
`total_deaths_hiv` as 15-49-only aggregates ("total population 15-49 both sexes") — the Goals
engine's core simulation only tracks the 15-49 adult risk-group population. It has no all-ages
new-infections/deaths data at all; `indicator_map.py`'s `"goals"` disagg key only exists on the
seven `(15-49)` indicators, never on the all-ages ones. This isn't a wiring gap — the data
structurally doesn't exist in `goals_output` for all ages.

Rather than build a Multi-PJNZ-specific source list that hardcodes "leapfrog = dp_aim," Multi
PJNZ's sub-tabs reuse the exact same `sources` lists the existing Goals/AIM tabs already define
(`_GOALS_SOURCES`: dp_aim solid / spectrum dashed / goals-native dotted — or `_AIM_SOURCES`:
dp_aim solid / spectrum_aim dashed — chosen by the Model switch). The missing-key-skip
convention every render function already relies on means this is safe to reuse verbatim:

- **All ages**: 2 visible lines either way (dp_aim, spectrum{,_aim}) — the Goals-native line
  silently renders nothing, since no all-ages indicator has a `"goals"` disagg entry.
- **15-49**: 3 visible lines under Model=Goals (dp_aim, spectrum, goals-native — matching the
  existing Goals tab's own 15-49 sub-tab exactly), 2 under Model=DP/AIM (no goals-native output
  exists for AIM-only files, matching `_AIM_SOURCES` having no `"goals"` entry at all).

Producing genuine all-ages new-infections/deaths from the Goals engine itself would require
extending its C++ simulation to track the 0-14 and 50+ populations — out of scope for this
comparison UI.
