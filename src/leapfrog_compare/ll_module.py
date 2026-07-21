"""
Shiny module for the "ll" EPPASM comparison tab. Unlike the simmod/fitmod tabs
(a tidy time series rendered by comparison_module.py's plot_panel), `ll()`
returns a handful of named log-likelihood components for a single theta — so
this gets its own small data panel (PJNZ + region selector, no year range)
and its own result panel (grouped bar chart + table), rather than reusing
plot_panel_ui/server.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import plotly.graph_objects as go
from shiny import module, reactive, render, ui

from leapfrog_compare.ll_runner import list_eppasm_regions, run_ll_both

_EPPASM_LABEL = "eppasm"
_EPPASM_LF_LABEL = "eppasm-leapfrog"


@module.ui
def ll_data_panel_ui(
    *,
    pjnz_choices: list[str] | dict[str, str],
    show_year_range: bool = False,
    year_min: int = 1970,
    year_max: int = 2030,
    run_fn_label: str = "Re-run models",
):
    children = [
        ui.h5("Filters"),
        ui.input_selectize(
            "pjnz", label="PJNZ", choices=pjnz_choices, selected=next(iter(pjnz_choices), None),
        ),
        ui.input_selectize("region", label="Region", choices=[]),
    ]
    if show_year_range:
        children += [
            ui.hr(),
            ui.input_slider(
                "year_range", "Year range", min=year_min, max=year_max,
                value=[year_min, year_max], step=1, sep="",
            ),
        ]
    children += [ui.hr(), ui.input_action_button("rerun", run_fn_label)]
    return ui.sidebar(*children, width=320)


@module.server
def ll_data_panel_server(
    input, output, session, *, pjnz_files: dict[str, Path], run_fn=run_ll_both,
    show_year_range: bool = False,
):
    """Returns (data_run, pjnz_label, region_label, year_range). data_run() ->
    (result, error), exactly one of which is None; result is run_fn()'s return value.
    year_range is None unless show_year_range=True (the fitmod tab's refit `mod` time
    series needs it; the ll tab's single-point components don't)."""
    _last_seen_rerun_clicks = 0
    _region_list_error = reactive.value(None)

    @reactive.effect
    def _update_region_choices():
        pjnz_stem = input.pjnz()
        if not pjnz_stem or pjnz_stem not in pjnz_files:
            return
        _region_list_error.set(None)
        try:
            regions = list_eppasm_regions(pjnz_files[pjnz_stem])
        except Exception as exc:
            print(f"[ll_module] Failed to list regions for {pjnz_stem}: {exc}")
            ui.update_selectize("region", choices=[], selected=None)
            _region_list_error.set(str(exc))
            return
        ui.update_selectize("region", choices=regions, selected=next(iter(regions), None))

    @reactive.calc
    def data_run():
        nonlocal _last_seen_rerun_clicks
        pjnz_stem = input.pjnz()
        region = input.region()
        if not pjnz_stem or pjnz_stem not in pjnz_files:
            return None, None
        if not region:
            # Either regions haven't loaded yet (no error set) or listing them
            # failed (error set) — only the latter is worth surfacing.
            return None, _region_list_error.get()

        clicks = input.rerun()
        force = clicks > _last_seen_rerun_clicks
        _last_seen_rerun_clicks = clicks

        try:
            return run_fn(pjnz_files[pjnz_stem], region, force=force), None
        except Exception as exc:
            print(f"[ll_module] Failed to run {pjnz_stem} ({region}): {exc}")
            return None, str(exc)

    def pjnz_label():
        return input.pjnz()

    def region_label():
        return input.region()

    year_range = None
    if show_year_range:
        @reactive.effect
        def _update_year_slider():
            result, _ = data_run()
            if result is None:
                return
            _, output_years = result["mod"]
            y_min, y_max = int(min(output_years)), int(max(output_years))
            ui.update_slider("year_range", min=y_min, max=y_max, value=[y_min, y_max])

        def year_range():
            return input.year_range()

    return data_run, pjnz_label, region_label, year_range


@module.ui
def ll_result_panel_ui():
    return ui.div(
        ui.output_ui("ll_warning"),
        ui.output_ui("ll_plot"),
        ui.output_table("ll_table"),
        style="padding-top: 12px;",
    )


@module.server
def ll_result_panel_server(
    input,
    output,
    session,
    *,
    data_run: Callable[[], tuple],
    pjnz_label: Callable[[], str],
    region_label: Callable[[], str],
    no_pjnz_message: str = "No PJNZ files found, check 'PJNZ_DIR' in 'config.py'.",
):
    @output
    @render.ui
    def ll_warning():
        result, _ = data_run()
        if result is None or result.get("theta_match", True):
            return None
        return ui.div(
            ui.strong("Warning: "),
            "the two packages' independently-sampled theta did not match exactly — "
            "the ll() values below were computed on different parameter draws and "
            "are not a like-for-like comparison. This means the packages' prior "
            "specifications diverge for this PJNZ.",
            style=(
                "background:#f8d7da; border:1px solid #f1aeb5; border-radius:4px; "
                "padding:8px 12px; margin-bottom:12px; color:#842029; font-size:0.9em;"
            ),
        )

    @output
    @render.ui
    def ll_plot():
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

        df = result["components"]
        finite = df[df["eppasm"].apply(_is_finite) & df["eppasm_lf"].apply(_is_finite)]
        skipped = sorted(set(df["component"]) - set(finite["component"]))

        fig = go.Figure()
        fig.add_trace(go.Bar(name=_EPPASM_LABEL, x=finite["component"], y=finite["eppasm"]))
        fig.add_trace(go.Bar(name=_EPPASM_LF_LABEL, x=finite["component"], y=finite["eppasm_lf"]))
        fig.update_layout(
            barmode="group",
            title=f"ll() components — {pjnz_label()} ({region_label()})",
            yaxis_title="log-likelihood",
            height=420,
        )
        html = fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})

        note = (
            ui.p(
                f"Not plotted (-Inf in at least one package): {', '.join(skipped)}. "
                "See the table below for exact values.",
                style="color:#6c757d; font-size:0.85em;",
            )
            if skipped else None
        )
        return ui.div(ui.HTML(html), note)

    @output
    @render.table
    def ll_table():
        result, _ = data_run()
        if result is None:
            return None
        df = result["components"].copy()
        df["diff (eppasm_lf - eppasm)"] = df["eppasm_lf"] - df["eppasm"]
        return df


def _is_finite(value) -> bool:
    try:
        return value == value and value not in (float("inf"), float("-inf"))
    except TypeError:
        return False
