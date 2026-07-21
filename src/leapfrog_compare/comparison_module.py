"""
Reusable Shiny modules for a comparison tab made of a shared data panel (PJNZ +
year-range selector, one per top-level tab) and any number of plot panels
(indicator selector + disaggregation checkboxes + rendered plot, one per inner
sub-tab), all reading from the SAME underlying data load. This lets a
top-level tab expose an arbitrary, easily-extended set of inner "plot type"
sub-tabs (e.g. "All ages", "15-49", "Risk groups", ...) without re-selecting
the PJNZ or re-running the model per sub-tab.

Typical wiring for one top-level tab with two sub-tabs:

    data_run, year_range = data_panel_server("goals_data", pjnz_files=..., run_fn=...)
    plot_panel_server("goals_allages", data_run=data_run, year_range=year_range,
                       indicator_map=..., sources=..., age_labels=...)
    plot_panel_server("goals_1549", data_run=data_run, year_range=year_range,
                       indicator_map=..., sources=..., age_labels=..., show_age_checkbox=False)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from shiny import module, reactive, render, ui

from leapfrog_compare.plotting import ComparisonSource, render_comparison, render_risk_group_comparison

# (data_by_source, output_years)
RunFn = Callable[[Path], tuple[dict[str, Any], range]]
# (data_by_source, output_years), takes a `force` kwarg to bypass any cache
RunFnWithForce = Callable[..., tuple[dict[str, Any], range]]


# ---------------------------------------------------------------------------
# Data panel: PJNZ selector + year range, shared across a top-level tab's sub-tabs
# ---------------------------------------------------------------------------

@module.ui
def data_panel_ui(
    *,
    pjnz_choices: list[str] | dict[str, str],
    year_min: int,
    year_max: int,
    show_rerun_button: bool = False,
):
    children = [
        ui.h5("Filters"),
        ui.input_selectize(
            "pjnz",
            label="PJNZ",
            choices=pjnz_choices,
            selected=next(iter(pjnz_choices), None),
        ),
        ui.hr(),
        ui.input_slider(
            "year_range",
            "Year range",
            min=year_min,
            max=year_max,
            value=[year_min, year_max],
            step=1,
            sep="",
        ),
    ]
    if show_rerun_button:
        children += [ui.hr(), ui.input_action_button("rerun", "Re-run models")]
    return ui.sidebar(*children, width=320)


@module.server
def data_panel_server(
    input,
    output,
    session,
    *,
    pjnz_files: dict[str, Path],
    run_fn: RunFn | RunFnWithForce,
    show_rerun_button: bool = False,
):
    """Returns (data_run, year_range, pjnz_label) — plain callables, each
    readable from any other module's server function to establish the same
    reactive dependency as if called locally."""
    _last_seen_rerun_clicks = 0

    @reactive.calc
    def data_run():
        """Returns (result, error_str). Exactly one of the two will be None."""
        nonlocal _last_seen_rerun_clicks
        pjnz_stem = input.pjnz()
        if not pjnz_stem or pjnz_stem not in pjnz_files:
            return None, None

        force = False
        if show_rerun_button:
            clicks = input.rerun()
            if clicks > _last_seen_rerun_clicks:
                force = True
            _last_seen_rerun_clicks = clicks

        try:
            if show_rerun_button:
                return run_fn(pjnz_files[pjnz_stem], force=force), None
            return run_fn(pjnz_files[pjnz_stem]), None
        except Exception as exc:
            print(f"[comparison_module] Failed to run {pjnz_stem}: {exc}")
            return None, str(exc)

    @reactive.effect
    def _update_year_slider():
        result, _ = data_run()
        if result is None:
            return
        _, output_years = result
        y_min, y_max = int(min(output_years)), int(max(output_years))
        ui.update_slider("year_range", min=y_min, max=y_max, value=[y_min, y_max])

    def year_range():
        return input.year_range()

    def pjnz_label():
        return input.pjnz()

    return data_run, year_range, pjnz_label


# ---------------------------------------------------------------------------
# Plot panel: indicator selector + disaggregation checkboxes + rendered plot
# ---------------------------------------------------------------------------

@module.ui
def plot_panel_ui(
    *,
    indicator_names: list[str],
    default_indicators: list[str],
    show_age_checkbox: bool = True,
):
    disagg_children = []
    if show_age_checkbox:
        disagg_children.append(ui.input_checkbox("disagg_age", "By age group", value=False))
    disagg_children.append(ui.input_checkbox("disagg_sex", "By sex", value=False))

    return ui.div(
        ui.input_selectize(
            "indicators",
            label="Indicators",
            choices=indicator_names,
            multiple=True,
            selected=default_indicators,
            options={"plugins": ["remove_button"]},
        ),
        ui.div(*disagg_children, style="display: flex; gap: 20px; margin: 6px 0 12px 0;"),
        ui.div(
            ui.output_ui("comparison_plot"),
            style="overflow-x: auto; overflow-y: auto;",
        ),
        style="padding-top: 12px;",
    )


@module.server
def plot_panel_server(
    input,
    output,
    session,
    *,
    data_run: Callable[[], tuple],
    year_range: Callable[[], tuple[int, int]],
    pjnz_label: Callable[[], str],
    indicator_map: dict[str, Any],
    sources: list[ComparisonSource],
    age_labels: list[str],
    show_age_checkbox: bool = True,
    no_pjnz_message: str = "No PJNZ files found, check 'PJNZ_DIR' in 'config.py'.",
):
    @output
    @render.ui
    def comparison_plot():
        result, error = data_run()
        if result is None:
            if error:
                return ui.div(
                    ui.p(
                        f"Error running model for '{pjnz_label()}':",
                        style="font-weight:bold; color:#c0392b; margin-bottom:4px;",
                    ),
                    ui.pre(error, style="white-space:pre-wrap; color:#c0392b; font-size:0.85em;"),
                )
            return ui.p(no_pjnz_message)

        data_by_source, output_years = result
        selected_indicators = input.indicators()
        year_start, year_end = year_range()
        disagg_age = input.disagg_age() if show_age_checkbox else False
        disagg_sex = input.disagg_sex()

        if not selected_indicators:
            return ui.p("Select at least one indicator.")

        html = render_comparison(
            indicator_map=indicator_map,
            data_by_source=data_by_source,
            sources=sources,
            selected_indicators=selected_indicators,
            output_years=output_years,
            year_start=year_start,
            year_end=year_end,
            disagg_age=disagg_age,
            disagg_sex=disagg_sex,
            title=f"Comparison — {pjnz_label()}",
            age_labels=age_labels,
        )
        return ui.HTML(html)


# ---------------------------------------------------------------------------
# Risk-group panel: "By sex" checkbox only (no indicator selector, no age
# faceting) + a one-row-per-risk-group rendered plot. Used by the Goals tab's
# "Risk groups" and "New infections" sub-tabs.
# ---------------------------------------------------------------------------

@module.ui
def risk_group_panel_ui():
    return ui.div(
        ui.div(
            ui.input_checkbox("disagg_sex", "By sex", value=False),
            style="margin: 6px 0 12px 0;",
        ),
        ui.div(
            ui.output_ui("comparison_plot"),
            style="overflow-x: auto; overflow-y: auto;",
        ),
        style="padding-top: 12px;",
    )


@module.server
def risk_group_panel_server(
    input,
    output,
    session,
    *,
    data_run: Callable[[], tuple],
    year_range: Callable[[], tuple[int, int]],
    pjnz_label: Callable[[], str],
    risk_groups: list[tuple[str, int]],
    sources: list[ComparisonSource],
    compute_fns: dict[str, Any],
    title_prefix: str,
    no_pjnz_message: str = "No PJNZ files found, check 'PJNZ_DIR' in 'config.py'.",
):
    @output
    @render.ui
    def comparison_plot():
        result, error = data_run()
        if result is None:
            if error:
                return ui.div(
                    ui.p(
                        f"Error running model for '{pjnz_label()}':",
                        style="font-weight:bold; color:#c0392b; margin-bottom:4px;",
                    ),
                    ui.pre(error, style="white-space:pre-wrap; color:#c0392b; font-size:0.85em;"),
                )
            return ui.p(no_pjnz_message)

        data_by_source, output_years = result
        year_start, year_end = year_range()
        disagg_sex = input.disagg_sex()

        html = render_risk_group_comparison(
            risk_groups=risk_groups,
            sources=sources,
            data_by_source=data_by_source,
            compute_fns=compute_fns,
            output_years=output_years,
            year_start=year_start,
            year_end=year_end,
            disagg_sex=disagg_sex,
            title=f"{title_prefix} — {pjnz_label()}",
        )
        return ui.HTML(html)


# ---------------------------------------------------------------------------
# Facet panel: indicator dropdown (single-select) + "By sex" checkbox + a
# one-row-per-facet-group rendered plot (render_risk_group_comparison), where
# the facet group is CD4 stage rather than risk group and which indicator's
# compute_fns/labels are active is chosen dynamically via the dropdown. Used
# by the AIM/Goals tabs' "0-14" sub-tabs.
# ---------------------------------------------------------------------------

@module.ui
def facet_panel_ui(*, indicator_names: list[str]):
    return ui.div(
        ui.input_selectize(
            "indicator",
            label="Indicator",
            choices=indicator_names,
            selected=indicator_names[0] if indicator_names else None,
        ),
        ui.div(
            ui.input_checkbox("disagg_sex", "By sex", value=False),
            style="margin: 6px 0 12px 0;",
        ),
        ui.div(
            ui.output_ui("comparison_plot"),
            style="overflow-x: auto; overflow-y: auto;",
        ),
        style="padding-top: 12px;",
    )


@module.server
def facet_panel_server(
    input,
    output,
    session,
    *,
    data_run: Callable[[], tuple],
    year_range: Callable[[], tuple[int, int]],
    pjnz_label: Callable[[], str],
    # Indicator name -> object with `.cd4_labels: list[str]` and
    # `.compute_fns: dict[str, Callable]` (duck-typed to
    # indicator_map.ChildCD4IndicatorDef).
    facet_map: dict[str, Any],
    sources: list[ComparisonSource],
    title_prefix: str,
    no_pjnz_message: str = "No PJNZ files found, check 'PJNZ_DIR' in 'config.py'.",
):
    @output
    @render.ui
    def comparison_plot():
        result, error = data_run()
        if result is None:
            if error:
                return ui.div(
                    ui.p(
                        f"Error running model for '{pjnz_label()}':",
                        style="font-weight:bold; color:#c0392b; margin-bottom:4px;",
                    ),
                    ui.pre(error, style="white-space:pre-wrap; color:#c0392b; font-size:0.85em;"),
                )
            return ui.p(no_pjnz_message)

        indicator = input.indicator()
        if not indicator or indicator not in facet_map:
            return ui.p("Select an indicator.")

        data_by_source, output_years = result
        year_start, year_end = year_range()
        ind_def = facet_map[indicator]

        html = render_risk_group_comparison(
            risk_groups=[(lbl, i) for i, lbl in enumerate(ind_def.cd4_labels)],
            sources=sources,
            data_by_source=data_by_source,
            compute_fns=ind_def.compute_fns,
            output_years=output_years,
            year_start=year_start,
            year_end=year_end,
            disagg_sex=input.disagg_sex(),
            title=f"{title_prefix} — {indicator} — {pjnz_label()}",
        )
        return ui.HTML(html)
