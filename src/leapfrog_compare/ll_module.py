"""
Shiny module for the "ll" EPPASM comparison tab. Unlike the simmod/fitmod tabs
(a tidy time series rendered by comparison_module.py's plot_panel), `ll()`
returns a handful of named log-likelihood components for a single theta — so
this gets its own small data panel (PJNZ + region + EPP model selector, no
year range) and its own result panel (per-component eppasm-leapfrog minus
eppasm differences, as a chart + table), rather than reusing
plot_panel_ui/server.

The ll tab evaluates both packages at a theta fitted once with eppasm
(ll_runner.get_theta). Fitting takes a minute or two, so it runs as an
ExtendedTask — the UI stays responsive and shows progress — and the theta
panel shows which theta is in use.
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Callable

import pandas as pd
import plotly.graph_objects as go
from shiny import module, reactive, render, ui

from leapfrog_compare.comparison_module import PjnzChoicesGetter, PjnzFilesGetter
from leapfrog_compare.fitmod_runner import fitmod_cached
from leapfrog_compare.ll_runner import (
    DEFAULT_EPPMOD, EPPMOD_CHOICES, get_theta, list_eppasm_regions, run_ll_both, theta_cached,
)

# State of a background job (theta fit / fitmod run) — one of:
#   ("none", None)               nothing selected yet
#   ("not_cached", None)         no cached result, and none started
#   ("pending", JobProgress)     running in the background
#   ("error", message)
#   ("ready", value)             a Theta (ll tab) or run_fitmod_both() result
JobState = tuple[str, object]

_EPPASM_LABEL = "eppasm"
_EPPASM_LF_LABEL = "eppasm-leapfrog"

# A component "matches" when math.isclose(eppasm, eppasm_lf) under these.
_REL_TOL = 1e-6
_ABS_TOL = 1e-8


@module.ui
def ll_data_panel_ui(
    *,
    pjnz_choices: list[str] | dict[str, str],
    show_year_range: bool = False,
    year_min: int = 1970,
    year_max: int = 2030,
    run_fn_label: str = "Re-run models",
    rerun_busy_label: str | None = None,
    show_theta_controls: bool = False,
):
    """`rerun_busy_label` makes the run button a task button (busy + disabled
    while a background run is in flight) — for the fitmod tab."""
    children = [
        ui.h5("Filters"),
        ui.input_selectize(
            "pjnz", label="PJNZ", choices=pjnz_choices, selected=next(iter(pjnz_choices), None),
        ),
        ui.input_selectize("region", label="Region", choices=[]),
        ui.input_select("eppmod", label="EPP model", choices=EPPMOD_CHOICES, selected=DEFAULT_EPPMOD),
    ]
    if show_year_range:
        children += [
            ui.hr(),
            ui.input_slider(
                "year_range", "Year range", min=year_min, max=year_max,
                value=[year_min, year_max], step=1, sep="",
            ),
        ]
    children.append(ui.hr())
    if rerun_busy_label is not None:
        children.append(ui.input_task_button("rerun", run_fn_label, label_busy=rerun_busy_label))
    else:
        children.append(ui.input_action_button("rerun", run_fn_label))
    if show_theta_controls:
        children.append(ui.input_task_button(
            "regen_theta", "Regenerate theta", label_busy="Fitting theta…", type="secondary",
        ))
    return ui.sidebar(*children, width=320)


@module.ui
def job_status_ui():
    """Status / progress line for the fitmod tab's background run. Shares the
    data panel's module id, so ll_data_panel_server renders it."""
    return ui.output_ui("job_status")


@module.server
def ll_data_panel_server(
    input, output, session, *, pjnz_files: PjnzFilesGetter, pjnz_choices: PjnzChoicesGetter,
    run_fn=run_ll_both, show_year_range: bool = False, use_theta: bool = False,
    background_fitmod: bool = False,
):
    """Returns (data_run, pjnz_label, region_label, year_range, job_state).
    data_run() -> (result, error), exactly one of which is None; result is
    run_fn()'s return value. year_range is None unless show_year_range=True (the
    fitmod tab's refit `mod` time series needs it; the ll tab's single-point
    components don't).

    Two background-job modes (job_state() reports progress, see JobState; it's
    None outside these modes):
      - use_theta=True (the ll tab, paired with show_theta_controls=True in the
        UI): an eppasm-fitted theta is read from cache or fitted in the
        background (also on "Regenerate theta"), then run_fn(pjnz_path, theta,
        force=...) runs synchronously (a few seconds).
      - background_fitmod=True (the fitmod tab, paired with rerun_busy_label in
        the UI): run_fn(pjnz_path, region, eppmod=..., force=...) is read from
        cache, and only ever run — in the background — on the run button.
    Otherwise run_fn(pjnz_path, region, eppmod=..., force=...) runs synchronously.

    `pjnz_files`/`pjnz_choices` are reactive getters, as in comparison_module's
    data_panel_server, so the PJNZ dropdown and region list track PJNZ_DIR live."""
    _last_seen_rerun_clicks = 0
    _region_list_error = reactive.value(None)

    @reactive.calc
    def selection():
        """(pjnz_path, region, eppmod) once all three are chosen, else None."""
        pjnz_stem = input.pjnz()
        region = input.region()
        files = pjnz_files()
        if not pjnz_stem or pjnz_stem not in files or not region:
            return None
        return files[pjnz_stem], region, input.eppmod()

    job_state = None
    if use_theta:
        job_state = _background_job(
            selection=selection,
            trigger=input.regen_theta,
            button_id="regen_theta",
            is_cached=lambda sel: theta_cached(*sel),
            load=lambda sel: get_theta(*sel),
            run=lambda sel, progress: get_theta(*sel, force=True),
            auto_start=True,
        )
    elif background_fitmod:
        def _run_fitmod(sel, progress):
            return run_fn(sel[0], sel[1], eppmod=sel[2], force=True, on_step=progress.set_step)

        job_state = _background_job(
            selection=selection,
            trigger=input.rerun,
            button_id="rerun",
            is_cached=lambda sel: fitmod_cached(*sel),
            load=lambda sel: run_fn(sel[0], sel[1], eppmod=sel[2]),
            run=_run_fitmod,
            auto_start=False,
        )

        @output
        @render.ui
        def job_status():
            state, payload = job_state()
            sel = selection()
            if sel is None:
                return None
            label = f"{sel[0].stem} ({sel[1]}, {sel[2]})"
            if state == "pending":
                return _job_progress_ui(
                    payload,
                    title=f"Running fitmod() for {label}…",
                    detail=(
                        "eppasm then eppasm.lf, each with a reduced IMIS budget — roughly "
                        "10-20 minutes per package. This runs in the background: the rest "
                        "of the app stays usable, and results appear here when both finish."
                    ),
                )
            if state == "not_cached":
                return _status_box(
                    ui.strong("No cached fit. "),
                    f"Click 'Run fitmod' to fit both packages for {label} in the "
                    "background (roughly 10-20 minutes per package).",
                )
            if state == "ready":
                meta = payload["meta"]
                return ui.p(
                    "Cached fit — " + " · ".join(
                        f"{pkg}: {m['fit_time_s'] / 60:.1f} min, {m['n_resample']} resamples, "
                        f"{m['n_iterations']} IMIS iterations"
                        for pkg, m in meta.items()
                    ),
                    style="color:#6c757d; font-size:0.85em; margin:4px 0 8px;",
                )
            return None

    @reactive.effect
    def _update_region_choices():
        pjnz_stem = input.pjnz()
        files = pjnz_files()
        if not pjnz_stem or pjnz_stem not in files:
            return
        _region_list_error.set(None)
        try:
            regions = list_eppasm_regions(files[pjnz_stem])
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
        eppmod = input.eppmod()
        files = pjnz_files()
        if not pjnz_stem or pjnz_stem not in files:
            return None, None
        if not region:
            # Either regions haven't loaded yet (no error set) or listing them
            # failed (error set) — only the latter is worth surfacing.
            return None, _region_list_error.get()

        if background_fitmod:
            state, payload = job_state()
            if state == "ready":
                return payload, None
            return None, payload if state == "error" else None

        theta = None
        if use_theta:
            state, payload = job_state()
            if state != "ready":
                return None, payload if state == "error" else None
            theta = payload

        clicks = input.rerun()
        force = clicks > _last_seen_rerun_clicks
        _last_seen_rerun_clicks = clicks

        try:
            if theta is not None:
                return run_fn(files[pjnz_stem], theta, force=force), None
            return run_fn(files[pjnz_stem], region, eppmod=eppmod, force=force), None
        except Exception as exc:
            print(f"[ll_module] Failed to run {pjnz_stem} ({region}, {eppmod}): {exc}")
            return None, str(exc)

    @reactive.effect
    def _refresh_pjnz_choices():
        """Mirrors data_panel_server's: push new dropdown choices when PJNZ_DIR
        changes, keeping the current selection if it's still valid."""
        choices = pjnz_choices()
        keys = list(choices.keys()) if isinstance(choices, dict) else list(choices)
        with reactive.isolate():
            current = input.pjnz()
        selected = current if current in keys else (keys[0] if keys else None)
        ui.update_selectize("pjnz", choices=choices, selected=selected)

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

    return data_run, pjnz_label, region_label, year_range, job_state


class JobProgress:
    """Progress of one background run. `step` is set from the worker thread
    (a plain attribute, read whenever the progress message re-renders)."""

    def __init__(self):
        self.started_at = time.monotonic()
        self.step = ""

    def set_step(self, step: str) -> None:
        self.step = step


def _background_job(
    *, selection, trigger, button_id: str, is_cached, load, run, auto_start: bool,
) -> Callable[[], JobState]:
    """Keeps a slow result for the current selection (see ll_data_panel_server):
    loaded from cache when there is one; otherwise computed in a background
    ExtendedTask — straight away if `auto_start`, else only on `trigger`. The
    `trigger` input always recomputes. `run(sel, progress)` runs in a worker
    thread. Must be called from within a module server function."""
    result = reactive.value(None)  # (selection, value) for the ready state
    error = reactive.value(None)
    progress = reactive.value(None)  # JobProgress while running

    @reactive.extended_task
    async def task(sel, prog):
        return sel, await asyncio.to_thread(run, sel, prog)

    def _start(sel):
        prog = JobProgress()
        progress.set(prog)
        task.invoke(sel, prog)

    @reactive.effect
    def _on_selection():
        sel = selection()
        # A run still going for the previous selection is abandoned (its R
        # process finishes in the background and caches its result).
        task.cancel()
        result.set(None)
        error.set(None)
        progress.set(None)
        if sel is None:
            return
        if is_cached(sel):
            try:
                result.set((sel, load(sel)))
            except Exception as exc:
                error.set(str(exc))
        elif auto_start:
            _start(sel)

    @reactive.effect
    @reactive.event(trigger)
    def _on_trigger():
        sel = selection()
        if sel is None:
            return
        task.cancel()
        result.set(None)
        error.set(None)
        _start(sel)

    @reactive.effect
    def _on_done():
        status = task.status()
        if status not in ("success", "error"):
            return
        progress.set(None)
        if status == "error":
            error.set(str(task.error.get()))
            return
        done_sel, value = task.value.get()
        with reactive.isolate():
            sel = selection()
        if done_sel == sel:
            result.set((sel, value))

    @reactive.effect
    def _sync_button():
        running = task.status() == "running"
        ui.update_task_button(button_id, state="busy" if running else "ready")

    @reactive.calc
    def state() -> JobState:
        if error.get() is not None:
            return "error", error.get()
        if result.get() is not None:
            return "ready", result.get()[1]
        if progress.get() is not None:
            return "pending", progress.get()
        if selection() is not None:
            return "not_cached", None
        return "none", None

    return state


def _status_box(*children, color: str = "#b6d4fe", background: str = "#e7f1ff"):
    return ui.div(
        *children,
        style=(
            f"border:1px solid {color}; background:{background}; border-radius:4px; "
            "padding:8px 12px; margin-bottom:12px; font-size:0.9em;"
        ),
    )


def _job_progress_ui(progress: JobProgress, *, title: str, detail: str):
    """Progress message for an in-flight background run, ticking once a second."""
    reactive.invalidate_later(1)
    elapsed = int(time.monotonic() - progress.started_at)
    return _status_box(
        ui.p(ui.strong(title + " "), f"{elapsed // 60}:{elapsed % 60:02d} elapsed", style="margin:0;"),
        ui.p(progress.step, style="margin:4px 0 0;") if progress.step else None,
        ui.p(detail, style="margin:4px 0 0; color:#6c757d; font-size:0.85em;"),
    )


def _theta_progress_ui(progress: JobProgress):
    return _job_progress_ui(
        progress,
        title="Fitting theta with eppasm…",
        detail=(
            "fitmod(optfit = TRUE): best of 1,000 prior draws, then BFGS to the "
            "posterior mode. Typically 20 seconds to a couple of minutes depending on the "
            "PJNZ; ll() runs as soon as it's done."
        ),
    )


@module.ui
def ll_result_panel_ui():
    return ui.div(
        ui.output_ui("ll_summary"),
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
    expect_match: bool = True,
    theta_state: Callable[[], JobState] | None = None,
    no_pjnz_message: str = "No PJNZ files found, check 'PJNZ_DIR' in 'config.py'.",
):
    """`expect_match=False` is for the fitmod tab, where each package's ll() is
    at its own posterior-mean theta, so differences are reported but not
    judged against the tolerance. `theta_state` (the ll tab) shows fitting
    progress while there's no result yet."""

    @reactive.calc
    def compared():
        result, _ = data_run()
        return None if result is None else _compare_components(result["components"])

    @output
    @render.ui
    def ll_summary():
        result, _ = data_run()
        df = compared()
        if df is None:
            return None
        details = [f"EPP model: {result['eppmod']}"] if result.get("eppmod") else []
        if result.get("theta_source"):
            details.append(f"theta: {result['theta_source']}")
        detail_line = ui.p(" · ".join(details), style="color:#6c757d; font-size:0.85em; margin:4px 0 0;")

        if not expect_match:
            headline = ui.p(
                "Each package's ll() is evaluated at its own posterior-mean theta, "
                "so differences are expected.",
                style="margin:0;",
            )
        else:
            n_differ = int((~df["match"]).sum())
            tol = f"(rel {_REL_TOL:g}, abs {_ABS_TOL:g})"
            if n_differ == 0:
                headline = ui.p(
                    ui.strong("✓ All match: "),
                    f"all {len(df)} components agree within tolerance {tol}.",
                    style="margin:0; color:#0f5132;",
                )
            else:
                differing = ", ".join(df.loc[~df["match"], "component"])
                headline = ui.p(
                    ui.strong(f"✗ {n_differ} of {len(df)} components differ "),
                    f"beyond tolerance {tol}: {differing}.",
                    style="margin:0; color:#842029;",
                )
        return ui.div(
            headline, detail_line,
            style=(
                "border:1px solid #dee2e6; border-radius:4px; padding:8px 12px; "
                "margin-bottom:12px; font-size:0.9em;"
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
            if theta_state is not None:
                state, payload = theta_state()
                if state == "pending":
                    return _theta_progress_ui(payload)
            return ui.p(no_pjnz_message)

        df = compared()
        finite = df[df["diff"].apply(_is_finite)]
        skipped = sorted(set(df["component"]) - set(finite["component"]))

        # Plain lists, not pandas/numpy: plotly.py 6 serialises arrays as base64
        # typed arrays, which the plotly.js 1.x the app loads can't decode.
        fig = go.Figure(go.Bar(
            x=finite["component"].tolist(),
            y=finite["diff"].tolist(),
            marker_color="#1f77b4",
            customdata=finite[["eppasm", "eppasm_lf", "rel_diff"]].to_numpy().tolist(),
            hovertemplate=(
                "<b>%{x}</b><br>"
                f"{_EPPASM_LF_LABEL} − {_EPPASM_LABEL}: %{{y:.3e}}<br>"
                "relative: %{customdata[2]:.3e}<br>"
                f"{_EPPASM_LABEL}: %{{customdata[0]:.6g}}<br>"
                f"{_EPPASM_LF_LABEL}: %{{customdata[1]:.6g}}"
                "<extra></extra>"
            ),
        ))
        fig.update_layout(
            title=f"ll() difference ({_EPPASM_LF_LABEL} − {_EPPASM_LABEL}) — {pjnz_label()} ({region_label()})",
            yaxis_title="Δ log-likelihood",
            yaxis=dict(exponentformat="e", zeroline=True, zerolinecolor="#888", gridcolor="#e5e5e5"),
            plot_bgcolor="white",
            paper_bgcolor="white",
            height=380,
        )
        html = fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})

        note = (
            ui.p(
                f"Not plotted (non-finite in at least one package): {', '.join(skipped)}. "
                "See the table below for exact values.",
                style="color:#6c757d; font-size:0.85em;",
            )
            if skipped else None
        )
        return ui.div(ui.HTML(html), note)

    @output
    @render.table
    def ll_table():
        df = compared()
        if df is None:
            return None
        out = df[["component", "eppasm", "eppasm_lf", "diff", "rel_diff"]].copy()
        for col in ("eppasm", "eppasm_lf"):
            out[col] = out[col].map(lambda v: f"{v:.10g}")
        for col in ("diff", "rel_diff"):
            out[col] = out[col].map(lambda v: f"{v:.3e}" if _is_finite(v) else "—")
        out = out.rename(columns={
            "eppasm": _EPPASM_LABEL,
            "eppasm_lf": _EPPASM_LF_LABEL,
            "diff": f"diff ({_EPPASM_LF_LABEL} − {_EPPASM_LABEL})",
            "rel_diff": "relative diff",
        })
        if expect_match:
            out["status"] = df["status"]
        return out


@module.ui
def theta_panel_ui():
    return ui.div(
        ui.output_ui("theta_status"),
        ui.output_table("theta_table"),
        style="padding-top: 12px;",
    )


@module.server
def theta_panel_server(
    input, output, session, *, theta_state: Callable[[], JobState],
):
    """Shows the eppasm-fitted theta the ll tab is evaluating, and how it was fitted."""

    @output
    @render.ui
    def theta_status():
        state, payload = theta_state()
        if state == "pending":
            return _theta_progress_ui(payload)
        if state == "error":
            return ui.div(
                ui.p("Fitting theta failed:", style="font-weight:bold; color:#c0392b; margin-bottom:4px;"),
                ui.pre(payload, style="white-space:pre-wrap; color:#c0392b; font-size:0.85em;"),
            )
        if state in ("none", "not_cached"):
            return ui.p("Select a PJNZ and region.")

        meta = payload.meta
        converged = meta["convergence"] == 0
        rows = [
            ("PJNZ / region", f"{payload.pjnz_stem} / {payload.region}"),
            ("EPP model", payload.eppmod),
            ("Fitted with", f"{meta['package']} {meta['package_version']} — {meta['method']}"),
            ("Log posterior", f"{meta['log_posterior']:.4f}"),
            (
                "Optimiser",
                ("✓ converged" if converged else f"✗ not converged (code {meta['convergence']})")
                + f", {meta['fn_evaluations']} function evaluations"
                + (f" — {meta['optim_message']}" if meta.get("optim_message") else ""),
            ),
            ("Prior draws for start", f"{meta['b0']:,} (seed {meta['seed']})"),
            ("Fit time", f"{meta['fit_time_s']:.1f} s"),
            ("Generated", meta["generated_at"]),
            ("Cached at", str(payload.path)),
        ]
        return ui.tags.dl(
            *[
                part for label, value in rows
                for part in (ui.tags.dt(label, class_="col-sm-3"), ui.tags.dd(value, class_="col-sm-9 mb-1"))
            ],
            class_="row",
            style="font-size:0.9em; margin-bottom:12px;",
        )

    @output
    @render.table
    def theta_table():
        state, payload = theta_state()
        if state != "ready":
            return None
        out = payload.df.copy()
        out["value"] = out["value"].map(lambda v: f"{v:.10g}")
        return out.rename(columns={"index": "#", "name": "parameter"})


def _compare_components(components: pd.DataFrame) -> pd.DataFrame:
    """Adds diff / rel_diff / match / status columns to the wide
    (component, eppasm, eppasm_lf) frame. Two identical infinities (e.g. both
    -Inf) count as a match; a NaN or one-sided infinity never does. Drops the
    "total" row that results cached before it was removed still carry."""
    df = components[components["component"] != "total"].reset_index(drop=True)
    df["diff"] = df["eppasm_lf"] - df["eppasm"]
    df["rel_diff"] = [
        d / abs(e) if _is_finite(d) and _is_finite(e) and e != 0 else float("nan")
        for d, e in zip(df["diff"], df["eppasm"])
    ]

    def _status(e, lf) -> tuple[bool, str]:
        if _is_finite(e) and _is_finite(lf):
            ok = math.isclose(e, lf, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)
            return ok, "✓ match" if ok else "✗ differs"
        if e == lf:  # same infinity
            return True, f"✓ match (both {e})"
        return False, "✗ differs (non-finite)"

    statuses = [_status(e, lf) for e, lf in zip(df["eppasm"], df["eppasm_lf"])]
    df["match"] = [ok for ok, _ in statuses]
    df["status"] = [label for _, label in statuses]
    return df


def _is_finite(value) -> bool:
    try:
        return math.isfinite(value)
    except TypeError:
        return False
