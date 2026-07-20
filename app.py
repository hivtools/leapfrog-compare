"""
Interactive comparison dashboard — AIM vs Goals vs EPPASM leapfrog comparisons.

Usage:
    uv run shiny run app.py
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shiny import App, ui

import leapfrog_compare.config as config
from leapfrog_compare.comparison_module import (
    data_panel_server, data_panel_ui, plot_panel_server, plot_panel_ui,
    risk_group_panel_server, risk_group_panel_ui,
)
from leapfrog_compare.eppasm_indicator_map import (
    EPPASM_ALL_AGES_INDICATOR_NAMES, EPPASM_FIFTEEN_49_INDICATOR_NAMES,
    EPPASM_AGE_LABELS, EPPASM_INDICATOR_MAP,
)
from leapfrog_compare.eppasm_runner import run_eppasm_both
from leapfrog_compare.indicator_map import (
    AGE_LABELS, ALL_AGES_INDICATOR_NAMES, FIFTEEN_49_INDICATOR_NAMES, INDICATOR_MAP,
    RISK_GROUPS, compute_new_infections_rg_goals, compute_new_infections_rg_spectrum,
    compute_rg_goals, compute_rg_spectrum,
)
from leapfrog_compare.pjnz_classify import is_goals_pjnz
from leapfrog_compare.pjnz_runner import run_pjnz
from leapfrog_compare.plotting import ComparisonSource
from leapfrog_compare.spectrum_runner import run_spectrum

_DEFAULT_YEAR_MIN = 1970
_DEFAULT_YEAR_MAX = 2030

_pjnz_files: dict[str, Path] = {
    p.stem: p
    for p in sorted(config.PJNZ_DIR.expanduser().glob("*.PJNZ"))
}
_pjnz_stems = list(_pjnz_files.keys())

# Classify each PJNZ as "Goals" (has a .HV member — ran Spectrum's Goals/HIV
# module) or "AIM" (doesn't). The AIM tab only offers AIM-only files, the Goals
# tab only offers Goals-capable files, and EPPASM offers all of them labelled.
_pjnz_is_goals: dict[str, bool] = {stem: is_goals_pjnz(path) for stem, path in _pjnz_files.items()}
_pjnz_stems_goals = [s for s in _pjnz_stems if _pjnz_is_goals[s]]
_pjnz_stems_aim = [s for s in _pjnz_stems if not _pjnz_is_goals[s]]
_pjnz_choices_eppasm: dict[str, str] = {
    s: f"{s} (Goals)" if _pjnz_is_goals[s] else f"{s} (AIM)" for s in _pjnz_stems
}

_GOALS_SOURCES = [
    ComparisonSource(key="dp_aim", label="Leapfrog DP/AIM", dash=None, primary=True),
    ComparisonSource(key="spectrum", label="Spectrum", dash="dash", needs_offset_align=True),
    ComparisonSource(key="goals", label="Leapfrog Goals", dash="dot", supports_age_facet=False),
]

_AIM_SOURCES = [
    ComparisonSource(key="dp_aim", label="Leapfrog AIM", dash=None, primary=True),
    ComparisonSource(key="spectrum_aim", label="Spectrum", dash="dash", needs_offset_align=True),
]

_EPPASM_SOURCES = [
    ComparisonSource(key="eppasm", label="eppasm", dash=None, primary=True),
    ComparisonSource(key="eppasm_lf", label="eppasm-leapfrog", dash="dash"),
]


def _goals_run_fn(pjnz_path: Path):
    modvars, goals_output, output_years = run_pjnz(pjnz_path)
    return {"dp_aim": goals_output, "spectrum": modvars, "goals": goals_output}, output_years


def _aim_run_fn(pjnz_path: Path):
    modvars, leapfrog_output, output_years = run_spectrum(pjnz_path)
    return {"dp_aim": leapfrog_output, "spectrum_aim": modvars}, output_years


def _eppasm_run_fn(pjnz_path: Path, force: bool = False):
    return run_eppasm_both(pjnz_path, force=force)


# ---------------------------------------------------------------------------
# Sub-tab definitions: adding a new "type of plot" to a top-level tab is just
# adding one more SubTab here (and one more entry in the matching TOP_TABS list).
# ---------------------------------------------------------------------------

@dataclass
class SubTab:
    id: str
    label: str
    indicator_names: list[str]
    default_indicators: list[str]
    indicator_map: dict
    sources: list[ComparisonSource]
    age_labels: list[str]
    show_age_checkbox: bool = True


@dataclass
class RiskGroupSubTab:
    """A sub-tab with the dedicated one-row-per-risk-group layout (no indicator
    selector, no age faceting) — see plotting.render_risk_group_comparison."""
    id: str
    label: str
    compute_fns: dict[str, Any]
    title_prefix: str


_GOALS_RISKGROUP_SOURCES = [
    ComparisonSource(key="goals", label="Leapfrog Goals", dash=None),
    ComparisonSource(key="spectrum", label="Spectrum", dash="dash"),
]


_AIM_SUBTABS = [
    SubTab(
        id="aim_allages", label="All ages",
        indicator_names=ALL_AGES_INDICATOR_NAMES, default_indicators=ALL_AGES_INDICATOR_NAMES[:3],
        indicator_map=INDICATOR_MAP, sources=_AIM_SOURCES, age_labels=AGE_LABELS,
    ),
    SubTab(
        id="aim_1549", label="15-49",
        indicator_names=FIFTEEN_49_INDICATOR_NAMES, default_indicators=FIFTEEN_49_INDICATOR_NAMES,
        indicator_map=INDICATOR_MAP, sources=_AIM_SOURCES, age_labels=AGE_LABELS,
        show_age_checkbox=False,
    ),
]

_GOALS_SUBTABS = [
    SubTab(
        id="goals_allages", label="All ages",
        indicator_names=ALL_AGES_INDICATOR_NAMES, default_indicators=ALL_AGES_INDICATOR_NAMES[:3],
        indicator_map=INDICATOR_MAP, sources=_GOALS_SOURCES, age_labels=AGE_LABELS,
    ),
    SubTab(
        id="goals_1549", label="15-49",
        indicator_names=FIFTEEN_49_INDICATOR_NAMES, default_indicators=FIFTEEN_49_INDICATOR_NAMES,
        indicator_map=INDICATOR_MAP, sources=_GOALS_SOURCES, age_labels=AGE_LABELS,
        show_age_checkbox=False,
    ),
]

_GOALS_RISKGROUP_SUBTABS = [
    RiskGroupSubTab(
        id="goals_riskgroups", label="Risk groups",
        compute_fns={"goals": compute_rg_goals, "spectrum": compute_rg_spectrum},
        title_prefix="Risk groups",
    ),
    RiskGroupSubTab(
        id="goals_newinfections", label="New infections",
        compute_fns={"goals": compute_new_infections_rg_goals, "spectrum": compute_new_infections_rg_spectrum},
        title_prefix="New infections by risk group",
    ),
]

_EPPASM_SUBTABS = [
    SubTab(
        id="eppasm_allages", label="All ages",
        indicator_names=EPPASM_ALL_AGES_INDICATOR_NAMES, default_indicators=EPPASM_ALL_AGES_INDICATOR_NAMES[:3],
        indicator_map=EPPASM_INDICATOR_MAP, sources=_EPPASM_SOURCES, age_labels=EPPASM_AGE_LABELS,
    ),
    SubTab(
        id="eppasm_1549", label="15-49",
        indicator_names=EPPASM_FIFTEEN_49_INDICATOR_NAMES, default_indicators=EPPASM_FIFTEEN_49_INDICATOR_NAMES,
        indicator_map=EPPASM_INDICATOR_MAP, sources=_EPPASM_SOURCES, age_labels=EPPASM_AGE_LABELS,
        show_age_checkbox=False,
    ),
]


# ---------------------------------------------------------------------------
# UI / server composition: one nav_panel per top-level tab, one inner
# navset_tab per top-level tab's SubTabs, sharing a single data_panel.
# ---------------------------------------------------------------------------

def _build_tab_ui(
    top_id: str,
    title: str,
    sub_tabs: list[SubTab],
    *,
    pjnz_choices: list[str] | dict[str, str] = _pjnz_stems,
    show_rerun_button: bool = False,
    risk_group_subtabs: list[RiskGroupSubTab] = (),
    wip_note: str | None = None,
):
    banner = (
        [ui.div(
            ui.strong("Work in progress: "),
            wip_note,
            style=(
                "background:#fff3cd; border:1px solid #ffe08a; border-radius:4px; "
                "padding:8px 12px; margin-bottom:12px; color:#664d03; font-size:0.9em;"
            ),
        )]
        if wip_note else []
    )
    return ui.nav_panel(
        title,
        *banner,
        ui.layout_sidebar(
            data_panel_ui(
                top_id,
                pjnz_choices=pjnz_choices,
                year_min=_DEFAULT_YEAR_MIN,
                year_max=_DEFAULT_YEAR_MAX,
                show_rerun_button=show_rerun_button,
            ),
            ui.navset_tab(*[
                ui.nav_panel(
                    st.label,
                    plot_panel_ui(
                        st.id,
                        indicator_names=st.indicator_names,
                        default_indicators=st.default_indicators,
                        show_age_checkbox=st.show_age_checkbox,
                    ),
                )
                for st in sub_tabs
            ], *[
                ui.nav_panel(rgt.label, risk_group_panel_ui(rgt.id))
                for rgt in risk_group_subtabs
            ]),
            fillable=True,
        ),
    )


def _wire_tab_server(
    top_id: str,
    run_fn,
    sub_tabs: list[SubTab],
    *,
    show_rerun_button: bool = False,
    risk_group_subtabs: list[RiskGroupSubTab] = (),
):
    data_run, year_range, pjnz_label = data_panel_server(
        top_id, pjnz_files=_pjnz_files, run_fn=run_fn, show_rerun_button=show_rerun_button,
    )
    for st in sub_tabs:
        plot_panel_server(
            st.id,
            data_run=data_run,
            year_range=year_range,
            pjnz_label=pjnz_label,
            indicator_map=st.indicator_map,
            sources=st.sources,
            age_labels=st.age_labels,
            show_age_checkbox=st.show_age_checkbox,
        )
    for rgt in risk_group_subtabs:
        risk_group_panel_server(
            rgt.id,
            data_run=data_run,
            year_range=year_range,
            pjnz_label=pjnz_label,
            risk_groups=RISK_GROUPS,
            sources=_GOALS_RISKGROUP_SOURCES,
            compute_fns=rgt.compute_fns,
            title_prefix=rgt.title_prefix,
        )


app_ui = ui.page_navbar(
    _build_tab_ui(
        "aim", "AIM", _AIM_SUBTABS, pjnz_choices=_pjnz_stems_aim,
        wip_note=(
            "the Spectrum comparison uses the model run from the PJNZ inputs — "
            "Spectrum's own output indicators are not yet extracted from the PJNZ. "
            "That will be added in the future."
        ),
    ),
    _build_tab_ui(
        "goals", "Goals", _GOALS_SUBTABS,
        pjnz_choices=_pjnz_stems_goals, risk_group_subtabs=_GOALS_RISKGROUP_SUBTABS,
    ),
    _build_tab_ui(
        "eppasm", "EPPASM", _EPPASM_SUBTABS,
        pjnz_choices=_pjnz_choices_eppasm, show_rerun_button=True,
    ),
    id="main_nav",
    title="Leapfrog Comparison",
    header=ui.head_content(ui.tags.script(src="https://cdn.plot.ly/plotly-latest.min.js")),
    fillable=True,
)


def server(input, output, session):
    _wire_tab_server("aim", _aim_run_fn, _AIM_SUBTABS)
    _wire_tab_server("goals", _goals_run_fn, _GOALS_SUBTABS, risk_group_subtabs=_GOALS_RISKGROUP_SUBTABS)
    _wire_tab_server("eppasm", _eppasm_run_fn, _EPPASM_SUBTABS, show_rerun_button=True)


app = App(app_ui, server)
