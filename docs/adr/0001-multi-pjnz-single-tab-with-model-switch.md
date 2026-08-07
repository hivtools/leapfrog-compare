# Multi PJNZ is one tab with a Model switch, not a compare sub-tab per existing top-level tab

The request was to compare 2+ PJNZ files' leapfrog-vs-Spectrum output, initially for Goals,
later also for DP/AIM. We considered adding a "compare" sub-tab under each of the existing
Goals/AIM top-level tabs, but every existing sub-tab shares its parent tab's single-PJNZ-select
sidebar (`data_panel_ui`) — multi-select fundamentally doesn't fit that shared sidebar.

Instead, Multi PJNZ is a single new top-level tab with its own multi-select PJNZ sidebar, plus
a "Model" switch (Goals / DP/AIM) that swaps which PJNZ files are selectable (via the existing
`is_goals_pjnz` classification) and which run function (`_goals_run_fn` / `_aim_run_fn`)
produces each file's data. Both run functions already normalize their leapfrog output under
the same `"dp_aim"` key, so the rendering/indicator code is identical either way — only the
file pool, run function, and Spectrum source key (`spectrum` vs `spectrum_aim`) change.

This gives Goals-first delivery without duplicating the comparison UI/rendering code per
top-level tab, at the cost of Multi PJNZ being a slightly different shape (tab + switch) than
the sub-tab pattern used elsewhere.
