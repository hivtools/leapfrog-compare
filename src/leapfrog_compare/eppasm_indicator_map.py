"""
Indicator definitions for the EPPASM comparison tab (eppasm vs eppasm-leapfrog
`simmod()` output). Kept separate from `indicator_map.INDICATOR_MAP`: EPPASM
only models ages 15-80 (no child compartments), so reusing e.g. the literal
string "Total population" would misleadingly imply the same 0-80 scope as the
Goals/Spectrum tabs.

Each series in the `data` dict passed to these functions (produced by
`eppasm_runner.run_eppasm_both`) is `dict[age_group, dict[sex, np.ndarray]]`
keyed first by EPPASM's own coarse age groups (`EPPASM_AGE_LABELS`, or
"Total"), then by "male"/"female"/"both" (whichever the R wrapper emitted for
that indicator), each a 1-D array aligned to `output_years`.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Callable

import numpy as np

from leapfrog_compare.indicator_map import IndicatorDef

# EPPASM's own coarse age-group scheme (ages 15-80), matching `fp$ss$h.ag.span`
# in r/run_simmod.R: "15-16", "17-19", "20-24", ..., "45-49", "50+".
EPPASM_AGE_LABELS: list[str] = [
    "15-16", "17-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50+",
]


def _eppasm_disagg(key: str) -> Callable:
    """Disagg for a sex-and-age-split EPPASM series."""
    def fn(data: dict, disagg_age: bool, disagg_sex: bool) -> list[tuple[str, np.ndarray]]:
        series_by_age = data.get(key)
        if series_by_age is None:
            return []
        age_groups = EPPASM_AGE_LABELS if disagg_age else ["Total"]
        series: list[tuple[str, np.ndarray]] = []
        for age_label in age_groups:
            by_sex = series_by_age.get(age_label)
            if by_sex is None:
                continue
            prefix = f"{age_label} / " if disagg_age else ""
            if disagg_sex:
                if "male" in by_sex:
                    series.append((f"{prefix}Male", by_sex["male"]))
                if "female" in by_sex:
                    series.append((f"{prefix}Female", by_sex["female"]))
            elif "both" in by_sex:
                series.append((age_label if disagg_age else "Total", by_sex["both"]))
            elif "male" in by_sex and "female" in by_sex:
                series.append((age_label if disagg_age else "Total", by_sex["male"] + by_sex["female"]))
        return series
    return fn


def _eppasm_1549_rate(key: str) -> Callable:
    """Disagg for a combined-only 15-49 rate series (prevalence/incidence) — no age or sex split available."""
    def fn(data: dict, disagg_age: bool, disagg_sex: bool) -> list[tuple[str, np.ndarray]]:
        if disagg_age or disagg_sex:
            return []
        series_by_age = data.get(key)
        if series_by_age is None:
            return []
        by_sex = series_by_age.get("Total")
        if by_sex is None or "both" not in by_sex:
            return []
        return [("15-49", by_sex["both"])]
    return fn


EPPASM_INDICATOR_MAP: OrderedDict[str, IndicatorDef] = OrderedDict([
    ("Total population (15-80)", IndicatorDef(disagg={
        "eppasm": _eppasm_disagg("total_population"),
        "eppasm_lf": _eppasm_disagg("total_population"),
    })),
    ("HIV population (15-80)", IndicatorDef(disagg={
        "eppasm": _eppasm_disagg("hiv_population"),
        "eppasm_lf": _eppasm_disagg("hiv_population"),
    })),
    ("ART population (15-80)", IndicatorDef(disagg={
        "eppasm": _eppasm_disagg("art_population"),
        "eppasm_lf": _eppasm_disagg("art_population"),
    })),
    ("New HIV infections (15-80)", IndicatorDef(disagg={
        "eppasm": _eppasm_disagg("new_infections"),
        "eppasm_lf": _eppasm_disagg("new_infections"),
    })),
    ("AIDS deaths (15-80)", IndicatorDef(disagg={
        "eppasm": _eppasm_disagg("aids_deaths"),
        "eppasm_lf": _eppasm_disagg("aids_deaths"),
    })),
    ("Prevalence (15-49) (%)", IndicatorDef(disagg={
        "eppasm": _eppasm_1549_rate("prevalence_15to49"),
        "eppasm_lf": _eppasm_1549_rate("prevalence_15to49"),
    })),
    ("Incidence (15-49) (%)", IndicatorDef(disagg={
        "eppasm": _eppasm_1549_rate("incidence_15to49"),
        "eppasm_lf": _eppasm_1549_rate("incidence_15to49"),
    })),
])

# Named indicator groupings for the "All ages" / "15-49" plot sub-tabs, mirroring
# indicator_map.py's ALL_AGES_INDICATOR_NAMES / FIFTEEN_49_INDICATOR_NAMES split.
EPPASM_ALL_AGES_INDICATOR_NAMES: list[str] = [
    "Total population (15-80)", "HIV population (15-80)", "ART population (15-80)",
    "New HIV infections (15-80)", "AIDS deaths (15-80)",
]
EPPASM_FIFTEEN_49_INDICATOR_NAMES: list[str] = [
    "Prevalence (15-49) (%)", "Incidence (15-49) (%)",
]


def get_eppasm_indicator_names() -> list[str]:
    return list(EPPASM_INDICATOR_MAP.keys())
