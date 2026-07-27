# leapfrog-compare

Interactive dashboard for comparing Spectrum modvar output against leapfrog model output across a set of PJNZ files, and for comparing the `eppasm`/`eppasm-leapfrog` R packages against each other.

---

## Overview

The dashboard has three top-level tabs, each an independent comparison over the same set of PJNZ files. Each top-level tab shares one PJNZ selector and year-range slider, and splits its plots across an inner row of sub-tabs — one per "type of plot":

- **AIM** — leapfrog-py's `run_model(..., "Spectrum", ...)` (a DP/AIM-only engine run) vs the Spectrum modvars read directly from the PJNZ. Sub-tabs: **All ages**, **15-49**.
- **Goals** — the leapfrog-goals model's `run_goals()` output (both its DP/AIM-derived arrays and its Goals-native pre-aggregated outputs) vs Spectrum modvars. Sub-tabs: **All ages**, **15-49**, **Risk groups**, **New infections**.
- **EPPASM** — `eppasm::simmod()` vs `eppasm.lf::simmod()` (the eppasm-leapfrog fork), run by shelling out to R. Sub-tabs: **All ages** (with its own age-faceted view, using EPPASM's coarser 9-group age scheme), **15-49**.

Each PJNZ is classified by inspecting the zip contents: a file containing a `.HV` member ran Spectrum's Goals/HIV module ("Goals"-capable); one without is "AIM"-only. The AIM tab only offers AIM-only PJNZ files, the Goals tab only offers Goals-capable ones, and the EPPASM tab offers all of them labelled `(Goals)` / `(AIM)`.

Adding a new sub-tab is just adding one more `SubTab(...)` (or `RiskGroupSubTab(...)`) entry to the matching top-level tab's list in `app.py` — no other wiring required.

The AIM and Goals tabs run entirely in-process and re-run live on every PJNZ selection change (no caching). The EPPASM tab shells out to R (much slower), so its results are cached to disk per (PJNZ, package) and only recomputed on first request or when you click **Re-run models** (shared across both of its sub-tabs, since they read the same underlying data).

```
1. Drop .PJNZ files into PJNZ_DIR
2. Edit config.py to point at that directory
3. uv run shiny run app.py
```

---

## Prerequisites

### 1. Python ≥ 3.11 and uv

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you haven't already.

### 2. R and the eppasm / eppasm-leapfrog packages (only needed for the EPPASM tab)

Install R and an `Rscript` executable on `PATH`. Then either:

- **Install both packages properly** (preferred — faster per-run): `R CMD INSTALL /path/to/eppasm` and `R CMD INSTALL /path/to/eppasm-leapfrog`. `eppasm-leapfrog` additionally requires the `leapfrog` R package (`>= 0.1.8`, from the `mrc-ide.r-universe.dev` repo) — the compiled-engine comparison in the EPPASM tab won't work until this is satisfied.
- **Or** point `EPPASM_DIR` / `EPPASM_LEAPFROG_DIR` in `config.py` at your local checkouts and set the matching `EPPASM_USE_LOCAL_CHECKOUT` / `EPPASM_LF_USE_LOCAL_CHECKOUT` flag to `True` — the R wrapper will load that package via `pkgload::load_all()` instead of an installed copy. Requires the `pkgload` R package.

The two flags are independent and explicit — there's no auto-detection of which copy is available; check `config.py`'s defaults against what's actually installed in your R environment.

---

## Setup

### 1. Install Python dependencies

```bash
uv sync
```

If you want to use in-development versions of `leapfrog-goals` or `leapfrog-py`, check them out locally and update the `[tool.uv.sources]` section in `pyproject.toml` to point at your local paths.

### 2. Edit `src/leapfrog_compare/config.py`

Set `PJNZ_DIR` to the folder containing your `.PJNZ` files:

```python
PJNZ_DIR = Path("/home/user/data/pjnz_files")
```

Review the EPPASM-tab settings (`EPPASM_DIR`, `EPPASM_LEAPFROG_DIR`, `EPPASM_USE_LOCAL_CHECKOUT`, `EPPASM_LF_USE_LOCAL_CHECKOUT`, `EPPASM_CACHE_DIR`, `R_EXECUTABLE`) if you plan to use that tab.

### 3. Launch the dashboard

```bash
uv run shiny run app.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

### 4. (Optional) Precompute EPPASM results

To populate the EPPASM cache for every PJNZ ahead of time instead of waiting for it on first tab visit:

```bash
uv run python scripts/precompute_eppasm.py [--force]
```

---

## Dashboard controls

Global controls (sidebar):
- **PJNZ** — select which projection to compare
- **Year range** — slider set automatically from the PJNZ projection years
- **Disaggregation** — optionally break down by five-year age group (All ages sub-tab only) and/or sex
- **Re-run models** (EPPASM tab only) — force a fresh R run instead of using the cached CSVs

Each facet shows one line per source, in a consistent dash style per source (solid / dashed / dotted) and a consistent colour per demographic group across sources. The **Risk groups** and **New infections** sub-tabs (Goals tab only) instead show one fixed panel per risk group, comparing Goals vs Spectrum.

---

## Project structure

```
leapfrog-compare/
├── app.py                             # Shiny for Python dashboard — composes the three tabs
├── pyproject.toml                     # uv/pip project metadata
├── r/
│   └── run_simmod.R                   # Rscript wrapper: runs simmod() for one package, writes a tidy CSV
├── scripts/
│   └── precompute_eppasm.py           # Batch-populate the EPPASM cache for every PJNZ
└── src/
    └── leapfrog_compare/
        ├── config.py                  # User configuration (PJNZ_DIR, EPPASM_* settings)
        ├── comparison_module.py       # Reusable Shiny module: one tab's UI + server logic
        ├── plotting.py                # Generic N-source comparison figure renderer (all tabs)
        ├── series_utils.py            # Shared series-reshaping helpers used by plotting.py
        ├── indicator_map.py           # Goals/Spectrum tabs' indicator ↔ compute-function mapping
        ├── eppasm_indicator_map.py    # EPPASM tab's indicator ↔ compute-function mapping
        ├── pjnz_runner.py             # PJNZ loading + leapfrog-goals model execution (Goals tab)
        ├── spectrum_runner.py         # PJNZ loading + leapfrog-py "Spectrum" model execution (Spectrum tab)
        └── eppasm_runner.py           # Shells out to r/run_simmod.R, caches results (EPPASM tab)
```

---

## Indicator reference

> **Leapfrog array dimensions** — most population-like outputs share the shape `(81, 2, n_years)`:
> - axis 0 = single-year ages 0–80
> - axis 1 = sex (0 = male, 1 = female)
> - axis 2 = projection years

---

### Total population *(all ages)*

| | Detail |
|---|---|
| **Leapfrog DP/AIM output** | `p_totpop` |
| **Leapfrog DP/AIM shape** | `(81, 2, n_years)` — ages × sex × years |
| **Leapfrog DP/AIM aggregation** | Sum over all ages and both sexes |
| **Spectrum modvar** | `DP_BigPop_V1` |
| **Spectrum PJNZ tag** | `<BigPop MV3>` |
| **Spectrum shape** | `(3, 81, 81)` — sex × age × year; index 0 = both, 1 = male, 2 = female |
| **Spectrum aggregation** | Rows 1 (male) + 2 (female) summed over all 81 age columns |

---

### Total Births *(all ages)*

| | Detail |
|---|---|
| **Leapfrog DP/AIM output** | `births` |
| **Leapfrog DP/AIM shape** | `(n_years,)` — total births per year |
| **Leapfrog DP/AIM aggregation** | Used directly (no aggregation) |
| **Spectrum modvar** | `DP_Births_V1` |
| **Spectrum PJNZ tag** | `<Births MV>` |
| **Spectrum shape** | `(3, 18, n_years)` — sex × 5-year age band × year; index 0 on *both* axes ("Both Sexes" / "All Ages") is a genuine pre-aggregated total |
| **Spectrum aggregation** | Read directly at `[0, 0, :]` — unlike `DP_BigPop_V1`, index 0 here is trustworthy and is how SpectrumEngine's own `GetDP_Births` accessor reads it; no sex or age disaggregation available |

---

### HIV population *(all ages)*

| | Detail |
|---|---|
| **Leapfrog DP/AIM output** | `p_hivpop` |
| **Leapfrog DP/AIM shape** | `(81, 2, n_years)` — ages × sex × years |
| **Leapfrog DP/AIM aggregation** | Sum over all ages and both sexes |
| **Spectrum modvar** | `HV_TotalAdultsHIV_V1` |
| **Spectrum PJNZ tag** | `<TotalAdultsHIV MV>` |
| **Spectrum shape** | `(3, 81)` — sex × year; index 0 = both, 1 = male, 2 = female |
| **Spectrum aggregation** | Rows 1 (male) + 2 (female); already age-aggregated |

---

### New HIV infections *(all ages)*

| | Detail |
|---|---|
| **Leapfrog DP/AIM output** | `p_infections` |
| **Leapfrog DP/AIM shape** | `(81, 2, n_years)` — ages × sex × years |
| **Leapfrog DP/AIM aggregation** | Sum over all ages and both sexes |
| **Spectrum modvar** | `HV_NewInfections_V1` |
| **Spectrum PJNZ tag** | `<NewInfections MV>` |
| **Spectrum shape** | `(3, 11, 5, 81)` — sex × risk group × vaccine state × year; index 0 = both, 1 = male, 2 = female |
| **Spectrum aggregation** | Rows 1 (male) + 2 (female) summed over risk-group and vaccine-state dimensions |

Sex disaggregation sums rows 1 and 2 over inner dims. Age disaggregation not available for Spectrum.

---

### AIDS deaths *(all ages)*

| | Detail |
|---|---|
| **Leapfrog DP/AIM output** | `p_hiv_deaths` |
| **Leapfrog DP/AIM shape** | `(81, 2, n_years)` — ages × sex × years |
| **Leapfrog DP/AIM aggregation** | Sum over all ages and both sexes |
| **Spectrum modvar (Goals tab)** | `HV_AIDSDeaths_V1` |
| **Spectrum PJNZ tag (Goals tab)** | `<AIDSDeaths MV>` |
| **Spectrum shape (Goals tab)** | `(3, 11, 5, 81)` — sex × risk group × vaccine state × year; index 0 = both, 1 = male, 2 = female |
| **Spectrum aggregation (Goals tab)** | Rows 1 (male) + 2 (female) summed over risk-group and vaccine-state dimensions |
| **Spectrum modvar (AIM tab)** | `AM_AIDSDeathsARTSingleAge_V1 + AM_AIDSDeathsNoARTSingleAge_V1` |
| **Spectrum shape (AIM tab)** | `(3, 81, n_years)` each — sex × single age × year; same shape family as `DP_BigPop_V1` |
| **Spectrum aggregation (AIM tab)** | Sum the two death arrays, then rows 1 (male) + 2 (female) summed over all ages (or per 5-year age band when age-faceted) |

Same sex-disaggregation behaviour as New HIV infections. Age disaggregation not available for Spectrum.

---

### Total number receiving ART (15-49) *(no Goals)*

| | Detail |
|---|---|
| **Leapfrog DP/AIM output** | `h_artpop` |
| **Leapfrog DP/AIM shape** | `(3, 7, 66, 2, n_years)` — ART duration stage × CD4 stage × single ages 15–80 × sex × years |
| **Leapfrog DP/AIM aggregation** | Sum over all ART duration stages, CD4 stages, ages 15–49 (first 35 age indices), and both sexes |
| **Spectrum modvar** | `HV_TotalAdultsART_V1` |
| **Spectrum PJNZ tag** | `<TotalAdultsART MV>` |
| **Spectrum shape** | `(3, 81)` — sex × year; index 0 = both, 1 = male, 2 = female |
| **Spectrum aggregation** | Rows 1 (male) + 2 (female); already age-aggregated |

ART duration stages: 0 = <6 months, 1 = 6–12 months, 2 = >12 months. Under-15 age groups return zero on the DP/AIM side. Age disaggregation not available for Spectrum.

---

### Total population 15–49 *(15–49; age disagg disabled)*

| | Detail |
|---|---|
| **Leapfrog DP/AIM** | `p_totpop` summed over ages 15–49 |
| **Spectrum** | `DP_BigPop_V1` rows 1+2 summed over age columns 15–49 |
| **Leapfrog Goals output** | `total_population` |
| **Leapfrog Goals shape** | `(n_years,)` — pre-computed 15–49 total; no sex disaggregation |

---

### New HIV infections 15–49 *(15–49; age disagg disabled)*

| | Detail |
|---|---|
| **Leapfrog DP/AIM** | `p_infections` summed over ages 15–49 |
| **Spectrum** | `HV_NewInfections_V1` (all-ages modvar; no 15–49 slice available) |
| **Leapfrog Goals output** | `new_infections_goals` |
| **Leapfrog Goals shape** | `(3, n_years)` — sex × year; index 0 = male, 1 = female, 2 = both |
| **Leapfrog Goals aggregation** | Index 2 (both) for total; indices 0 and 1 for sex disaggregation |

---

### AIDS deaths 15–49 *(15–49; age disagg disabled)*

| | Detail |
|---|---|
| **Leapfrog DP/AIM** | `p_hiv_deaths` summed over ages 15–49 |
| **Spectrum (Goals tab)** | `HV_AIDSDeaths_V1` (all-ages modvar; no 15–49 slice available) |
| **Spectrum (AIM tab)** | `AM_AIDSDeathsARTSingleAge_V1 + AM_AIDSDeathsNoARTSingleAge_V1`, each shape `(sex=3, single_age=81, T)`, summed over ages 15–49 (male index 1 + female index 2) |
| **Leapfrog Goals output** | `total_deaths_hiv` |
| **Leapfrog Goals shape** | `(n_years,)` — scalar total; no sex disaggregation (always shown as single total) |

---

### Prevalence (15–49) (%) *(15–49; age disagg disabled)*

| | Detail |
|---|---|
| **Leapfrog DP/AIM** | `100 × sum(p_hivpop[15:50]) / sum(p_totpop[15:50])` |
| **Spectrum modvar** | `HV_TotalAdultsHIVTag` and `DP_BigPopTag` |
| **Spectrum PJNZ tag** | `<TotalAdultsHIV MV>` and `<BigPop MV3>` |
| **Spectrum shape** | `(3, n_years)` and `(3, n_years)` 3 is n sexes both, male, female |
| **Spectrum aggregation** | Sum male and female total hiv / big pop |
| **Leapfrog Goals output** | `prevalence` × 100 |
| **Leapfrog Goals shape** | `(18, 3, n_years)` — risk group × sex × year |
| **Leapfrog Goals aggregation** | Last RG-aggregate row; sex index 0 = male, 1 = female, 2 = both |

---

### Incidence (15–49) (%) *(15–49; age disagg disabled)*

| | Detail |
|---|---|
| **Leapfrog DP/AIM** | `100 × sum(p_infections[15:50]) / (sum(p_totpop[15:50]) − sum(p_hivpop[15:50]))` |
| **Spectrum modvar** | `HV_Incidence_V1` × 100 |
| **Spectrum PJNZ tag** | `<Incidence MV>` |
| **Spectrum shape** | `(81,)` — one rate per projection year; no sex or age disaggregation |
| **Leapfrog Goals output** | `incidence_goals` × 100 |
| **Leapfrog Goals shape** | `(3, n_years)` — sex × year; index 0 = male, 1 = female, 2 = both |
| **Leapfrog Goals aggregation** | Index 2 (both) for total; indices 0 and 1 for sex disaggregation |

---

### Total PLHIV (15-49)

| | Detail |
|---|---|
| **Leapfrog DP/AIM** | `p_hivpop` limited to 15-49 |
| **Spectrum modvar** | `HV_TotalAdultsHIVTag` |
| **Spectrum PJNZ tag** | `<TotalAdultsHIV MV>` |
| **Spectrum shape** | (3, n_years) |
| **Leapfrog Goals output** | `total_plhiv` |
| **Leapfrog Goals shape** | (n_years) |
| **Leapfrog Goals aggregation** | None needed, already aggregated |

---

### Total on ART (15-49)

| | Detail |
|---|---|
| **Leapfrog DP/AIM** | `total_on_art` summed over ages 15–49 |
| **Spectrum modvar** | `HV_TotalAdultsART_V1` |
| **Spectrum PJNZ tag** | `<TotalAdultsART MV>` |
| **Spectrum shape** | `(3, 81)` — sex × year; index 0 = both, 1 = male, 2 = female |
| **Leapfrog Goals output** | none available |

---

### Risk groups *(risk groups tab)*

Five fixed subplots showing the fraction of the 15–49 population in each risk group over time, multiplied by 100 to give percent. Computed independently for Goals and Spectrum.

**Goals** — `adults` array, shape `(nVAC+1=5, nRG+1=18, nCD4+1=17, nNS+1=3, n_years)`, indexed as `adults[VAC_ALL, rg_idx, CD4_ALL, sex_idx]`:

| Constant | Value | Meaning |
|---|---|---|
| `VAC_ALL` | 4 | All vaccination states |
| `CD4_ALL` | 16 | All CD4 stages |
| `RG_ALL` | 17 | Total across all risk groups (denominator) |
| sex_idx | 0 = male, 1 = female | |

| Risk group | Goals `rg_idx` |
|---|---|
| Low risk | 1 (RG_LRH) |
| Medium risk | 2 (RG_MRH) |
| High risk | 3 (RG_HRH) |
| PWID | 4 (RG_IDU) |
| MSM | 5 (RG_MSM) |

**Spectrum** — `HV_Adults_V1`, shape `(sex, rg, hiv, vac, n_years)`, indexed as `hv_adults[sex_idx, rg_idx, HV_AllHIV, RN_AllVacc, :]`:

| Constant | Value | Source |
|---|---|---|
| `HV_AllHIV` | 19 | `SpectrumCommon.Const.HV.HVConst` |
| `HV_AllRisk` | 0 | `SpectrumCommon.Const.HV.HVConst` (denominator) |
| `RN_AllVacc` | 0 | `SpectrumCommon.Const.RN.RNConst` |
| sex_idx | 1 = male, 2 = female | (index 0 = both, not used) |

| Risk group | Spectrum `rg_idx` | Constant |
|---|---|---|
| Low risk | 2 | `HV_LRH` |
| Medium risk | 3 | `HV_MRH` |
| High risk | 4 | `HV_HRH` |
| PWID | 5 | `HV_IDU` |
| MSM | 6 | `HV_MSM` |

When sex disaggregation is off, male (index 1) + female (index 2) are summed in both numerator and denominator before dividing.

## Adding new indicators

Each `IndicatorDef` (in `indicator_map.py` for the AIM/Goals tabs, `eppasm_indicator_map.py` for the EPPASM tab) holds one `disagg` dict keyed by source id (`"dp_aim"`, `"spectrum"`, `"spectrum_aim"`, `"goals"`, `"eppasm"`, `"eppasm_lf"`), each value a function `(data, disagg_age, disagg_sex) -> list[(label, 1-D ndarray)]`. A source is simply omitted from the dict when it has no data for that indicator.

To add an AIM/Goals-tab indicator, edit [src/leapfrog_compare/indicator_map.py](src/leapfrog_compare/indicator_map.py):

1. Write a `"dp_aim"` disagg function. Use `_disagg_std(key)` for all-ages arrays, `_disagg_std_1549(key)` for 15–49 restricted (returns `[]` when age disagg is on), or `_no_age_disagg(fn)` to disable age disagg on any existing function.
2. Optionally write a `"spectrum"` disagg function for the Goals tab (HV_*-based modvars) and/or a `"spectrum_aim"` disagg function for the AIM tab (AM_*/DP_*-based modvars, via the `_am_disagg`/`_am_disagg_1549` factories) if a matching modvar exists (`_totals_only(fn)` if only a single combined value is available).
3. Optionally write a `"goals"` disagg function for Goals-native outputs (`_as_full_disagg(fn)` to adapt a `(data, disagg_sex)` function, hidden in the age-faceted view).
4. Add the indicator name to `ALL_AGES_INDICATOR_NAMES` or `FIFTEEN_49_INDICATOR_NAMES` so it's offered on the corresponding sub-tab.
5. Add an `IndicatorDef(disagg={...})` entry to `INDICATOR_MAP`.

To add an EPPASM-tab indicator, edit [src/leapfrog_compare/eppasm_indicator_map.py](src/leapfrog_compare/eppasm_indicator_map.py) and [r/run_simmod.R](r/run_simmod.R) (to emit the new derived series into the tidy CSV).

To add a new sub-tab to an existing top-level tab, add one more `SubTab(...)` (or `RiskGroupSubTab(...)`) entry to the matching list in `app.py` (e.g. `_GOALS_SUBTABS`) — no other wiring required. To add a new top-level tab entirely, write a `run_fn` returning `(data_by_source, output_years)`, a list of `plotting.ComparisonSource`s, and call `_build_tab_ui`/`_wire_tab_server` with a new set of `SubTab`s.

---

## Troubleshooting

**`leapfrog_goals` / `leapfrog_py` not found**
Re-run `uv sync`. Check that a compiled `.so` (Linux/Mac) or `.pyd` (Windows) file is present in the installed package.

**Dashboard shows "No PJNZ files found"**
Check that `PJNZ_DIR` in `config.py` points to a directory containing `.PJNZ` files (case-sensitive extension).

**A country's data looks truncated or goes NaN**
The Goals model may produce NaN values for some countries if a parameter causes a numerical instability. Check the terminal output for errors when the PJNZ is loaded.

**EPPASM tab shows an error for one package but not the other**
This is expected when only one of `eppasm` / `eppasm-leapfrog` is properly set up in your R environment (see Prerequisites) — the other source's plot still renders. Check the error text (surfaced from the R subprocess's stderr) for the specific missing dependency.

**EPPASM tab is slow on first load for a given PJNZ**
Expected — it's shelling out to R and running `simmod()` twice. Subsequent loads for the same PJNZ read from the `output/eppasm/` cache; use **Re-run models** or `scripts/precompute_eppasm.py --force` to refresh it.
