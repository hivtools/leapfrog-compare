"""
Generic N-source comparison figure renderer, shared by every comparison tab.

Each tab supplies an ordered list of `ComparisonSource`s (e.g. DP/AIM, Spectrum,
Goals-native for the "Goals" tab; two R engines for the "EPPASM" tab) plus a
`data_by_source` dict keyed by each source's `key`. For every selected indicator,
`indicator_map[name].disagg` is looked up per source key — a missing key means
that source has no data for this indicator and is silently skipped, mirroring
the original None-checks this replaces.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from leapfrog_compare import series_utils
from leapfrog_compare.indicator_map import AGE_LABELS_SINGLE

_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
    "#c49c94", "#f7b6d2",
]


@dataclass
class ComparisonSource:
    key: str
    """Matches an IndicatorDef.disagg key, e.g. "dp_aim", "spectrum", "goals"."""
    label: str
    """Trace-name prefix, e.g. "Leapfrog DP/AIM"."""
    dash: str | None
    """Plotly line dash style: None (solid), "dash", or "dot"."""
    needs_offset_align: bool = False
    """True for sources whose own array is positionally offset from `first_year`
    (e.g. raw PJNZ modvars), rather than already aligned to `output_years`."""
    supports_age_facet: bool = True
    """False hides this source from the age-faceted grid entirely (e.g. EPPASM,
    which has no per-five-year-age-group breakdown)."""
    primary: bool = False
    """True for the source that drives the age-faceted grid's columns even when
    an indicator has no real age breakdown (repeats its flat total across every
    column, matching the original DP/AIM behavior). Non-primary sources are
    hidden entirely from the age-facet view for indicators lacking age labels."""
    default_visible: bool = False
    """True marks this source pre-checked in the Multi PJNZ tab's per-panel
    "Show lines" checkboxes. Read only by the Multi PJNZ panel servers via
    `default_visible_keys`/`visible_sources` below — single-PJNZ tabs render
    every configured source regardless of this flag."""


def default_visible_keys(sources: list[ComparisonSource]) -> list[str]:
    """Keys of the sources pre-checked in a Multi PJNZ panel's "Show lines"
    checkbox group."""
    return [s.key for s in sources if s.default_visible]


def visible_sources(sources: list[ComparisonSource], visible_keys) -> list[ComparisonSource]:
    """Filters `sources` down to those whose key is in `visible_keys`, preserving
    order. Used by the Multi PJNZ panel servers to apply the "Show lines"
    checkbox selection before rendering."""
    keys = set(visible_keys)
    return [s for s in sources if s.key in keys]


def _trace_label(source: ComparisonSource, demo: str) -> str:
    return source.label if demo == "Total" else f"{source.label} {demo}"


def _make_trace_helpers(line_width: float = 2):
    """Returns an `add_trace(fig, x, y, trace_name, color_key, dash, row, col)` closure
    that assigns a stable colour per `color_key` (shared across sources so e.g. every
    trace with `color_key == "Male"` gets the same colour regardless of which source
    drew it) and de-duplicates legend entries by trace name. `color_key` is usually a
    demographic-group label, but is just an arbitrary hashable string as far as this
    function is concerned — the Multi PJNZ tab passes a PJNZ stem instead, to colour by
    file rather than by demographic group."""
    key_colors: dict[str, str] = {}
    palette_idx = 0
    legend_shown: set[str] = set()

    def _color_for(color_key: str) -> str:
        nonlocal palette_idx
        if color_key not in key_colors:
            key_colors[color_key] = _PALETTE[palette_idx % len(_PALETTE)]
            palette_idx += 1
        return key_colors[color_key]

    def add_trace(fig, x, y, trace_name, color_key, dash, row, col):
        show_leg = trace_name not in legend_shown
        if show_leg:
            legend_shown.add(trace_name)
        fig.add_trace(
            go.Scatter(
                x=x, y=y, mode="lines", name=trace_name,
                line=dict(color=_color_for(color_key), width=line_width, dash=dash),
                legendgroup=trace_name, showlegend=show_leg,
            ),
            row=row, col=col,
        )

    return add_trace


def render_comparison(
    *,
    indicator_map: dict[str, Any],
    data_by_source: dict[str, Any],
    sources: list[ComparisonSource],
    selected_indicators: list[str],
    output_years: range,
    year_start: int,
    year_end: int,
    disagg_age: bool,
    disagg_sex: bool,
    title: str,
    age_labels: list[str],
) -> str:
    years_arr = np.array(list(output_years))
    mask = (years_arr >= year_start) & (years_arr <= year_end)
    x_years = years_arr[mask].tolist()
    first_year = int(min(output_years))
    n_inds = len(selected_indicators)
    n_cols_age = len(age_labels)
    age_label_set = set(age_labels)

    _add_trace = _make_trace_helpers(line_width=1.5 if disagg_age else 2)

    def _get_series(source: ComparisonSource, ind_def, *, age: bool, sex: bool):
        fn = ind_def.disagg.get(source.key)
        if fn is None:
            return []
        try:
            return fn(data_by_source[source.key], age, sex)
        except Exception as exc:
            print(f"[plotting] {source.key} disagg failed: {exc}")
            return []

    def _series_to_xy(source: ComparisonSource, values: np.ndarray):
        if source.needs_offset_align:
            return series_utils.align_offset(values, years_arr, first_year, mask)
        return x_years, values[mask].tolist()

    # ---------------------------------------------------------------
    # Age-faceted layout: rows = indicators, cols = age groups
    # ---------------------------------------------------------------
    if disagg_age:
        fig_width = max(1600, n_cols_age * 110)
        fig_height = max(300, n_inds * 220)

        fig = make_subplots(
            rows=n_inds,
            cols=n_cols_age,
            row_titles=list(selected_indicators),
            column_titles=age_labels,
            shared_xaxes="columns",
            shared_yaxes=False,
            vertical_spacing=max(0.015, 0.25 / max(n_inds, 1)),
            horizontal_spacing=0.01,
        )

        for ind_idx, indicator in enumerate(selected_indicators):
            row = ind_idx + 1
            ind_def = indicator_map[indicator]

            # Precompute the per-source series once per indicator, and decide which
            # sources participate at all (primary sources always do; others only if
            # they actually carry age-group labels) — but interleave by age column
            # (not by source) below, to match the original per-cell trace ordering.
            active_sources: list[tuple[ComparisonSource, list]] = []
            for source in sources:
                if not source.supports_age_facet:
                    continue
                all_series = _get_series(source, ind_def, age=True, sex=disagg_sex)
                if not source.primary and not series_utils.has_age_labels(all_series, age_label_set):
                    continue
                active_sources.append((source, all_series))

            for age_idx, age_label in enumerate(age_labels):
                col = age_idx + 1
                for source, all_series in active_sources:
                    for demo, values in series_utils.series_for_age_cell(all_series, age_label):
                        x, y = _series_to_xy(source, values)
                        if x:
                            _add_trace(fig, x, y, _trace_label(source, demo), demo, source.dash, row, col)

        fig.update_xaxes(showticklabels=False, showgrid=True, gridcolor="#e5e5e5")
        fig.update_yaxes(
            showgrid=True, gridcolor="#e5e5e5", rangemode="tozero",
            tickfont=dict(size=8),
        )
        for col in range(1, n_cols_age + 1):
            fig.update_xaxes(
                showticklabels=True, tickformat="d", tickangle=90,
                tickfont=dict(size=8), row=n_inds, col=col,
            )

        fig.update_layout(
            width=fig_width,
            height=fig_height,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hoverlabel=dict(namelength=-1),
            title_text=title,
            margin=dict(t=80, b=60, l=60, r=120),
            plot_bgcolor="white",
            paper_bgcolor="white",
        )
        return fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": False})

    # ---------------------------------------------------------------
    # Simple layout: one column, rows = indicators
    # ---------------------------------------------------------------
    fig_height = max(400, n_inds * 300)

    fig = make_subplots(
        rows=n_inds,
        cols=1,
        subplot_titles=list(selected_indicators),
        shared_xaxes=False,
        vertical_spacing=max(0.04, 0.3 / max(n_inds, 1)),
    )

    for ind_idx, indicator in enumerate(selected_indicators):
        row = ind_idx + 1
        ind_def = indicator_map[indicator]

        for source in sources:
            series = _get_series(source, ind_def, age=False, sex=disagg_sex)
            for demo, values in series:
                x, y = _series_to_xy(source, values)
                if x:
                    _add_trace(fig, x, y, _trace_label(source, demo), demo, source.dash, row, 1)

    fig.update_xaxes(
        showgrid=True, gridcolor="#e5e5e5",
        range=[year_start - 1, year_end + 1],
        tickformat="d", tickangle=45,
    )
    fig.update_yaxes(showgrid=True, gridcolor="#e5e5e5", rangemode="tozero")

    fig.update_layout(
        height=fig_height,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hoverlabel=dict(namelength=-1),
        title_text=title,
        margin=dict(t=80, b=40, l=60, r=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})


def render_age_profile(
    *,
    indicator_map: dict[str, Any],
    data_by_source: dict[str, Any],
    sources: list[ComparisonSource],
    selected_indicators: list[str],
    output_years: range,
    year: int,
    title: str,
) -> str:
    """Single-year age profile: one row per selected indicator, x-axis = single
    year of age (0-80), one line per (source, sex). Reuses each source's
    `indicator_map[indicator].age_profile` disagg function (same 3-arg
    (data, disagg_age, disagg_sex) shape as the regular `disagg` dict, just at
    single-year-of-age resolution instead of the 5-year display buckets) called
    with both flags True, then slices out the one requested year. A source with
    no age_profile entry for an indicator (e.g. Goals-tab "spectrum", which has
    no per-age breakdown for most HV_* modvars) is silently skipped, same
    missing-key convention as render_comparison."""
    first_year = int(min(output_years))
    year_idx = year - first_year
    ages = [int(a) for a in AGE_LABELS_SINGLE]
    age_label_set = set(AGE_LABELS_SINGLE)
    n_inds = len(selected_indicators)

    _add_trace = _make_trace_helpers(line_width=2)
    fig = make_subplots(
        rows=n_inds,
        cols=1,
        subplot_titles=list(selected_indicators),
        shared_xaxes=False,
        vertical_spacing=max(0.04, 0.3 / max(n_inds, 1)),
    )

    for ind_idx, indicator in enumerate(selected_indicators):
        row = ind_idx + 1
        ind_def = indicator_map[indicator]

        for source in sources:
            fn = ind_def.age_profile.get(source.key)
            data = data_by_source.get(source.key)
            if fn is None or data is None:
                continue
            try:
                all_series = fn(data, True, True)
            except Exception as exc:
                print(f"[plotting] {source.key} age-profile disagg failed for {indicator}: {exc}")
                continue
            if not series_utils.has_age_labels(all_series, age_label_set):
                continue

            by_sex: dict[str, list[float | None]] = {}
            for age_label in AGE_LABELS_SINGLE:
                for sex_label, values in series_utils.series_for_age_cell(all_series, age_label):
                    y = float(values[year_idx]) if 0 <= year_idx < len(values) else None
                    by_sex.setdefault(sex_label, []).append(y)

            for sex_label, y_values in by_sex.items():
                _add_trace(fig, ages, y_values, _trace_label(source, sex_label), sex_label, source.dash, row, 1)

    fig.update_xaxes(showgrid=True, gridcolor="#e5e5e5", title_text="Age", dtick=5)
    fig.update_yaxes(showgrid=True, gridcolor="#e5e5e5", rangemode="tozero")

    fig.update_layout(
        height=max(400, n_inds * 300),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hoverlabel=dict(namelength=-1),
        title_text=title,
        margin=dict(t=80, b=40, l=60, r=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})


def render_risk_group_comparison(
    *,
    risk_groups: list[tuple[str, int]],
    sources: list[ComparisonSource],
    data_by_source: dict[str, Any],
    compute_fns: dict[str, Any],
    output_years: range,
    year_start: int,
    year_end: int,
    disagg_sex: bool,
    title: str,
    y_title: str | None = None,
) -> str:
    """One row per risk group (not per indicator) — used by the Goals tab's "Risk
    groups" and "New infections" sub-tabs. Each `sources` entry's `compute_fns[key]`
    is called once and returns `list[(rg_name, demo, ndarray)]`, distributed into the
    row matching `rg_name`. Unlike `render_comparison`, there is no indicator selector
    or age-facet mode here — the risk-group axis always drives the rows. `y_title`
    labels the shared y-axis unit (e.g. "% of population", "New infections") since
    the subplot titles are risk-group names, not indicator names, and give no clue
    what's being measured otherwise."""
    years_arr = np.array(list(output_years))
    mask = (years_arr >= year_start) & (years_arr <= year_end)
    x_years = years_arr[mask].tolist()
    first_year = int(min(output_years))
    n_rg = len(risk_groups)
    rg_row = {rg_name: i + 1 for i, (rg_name, _rg) in enumerate(risk_groups)}

    _add_trace = _make_trace_helpers(line_width=2)

    fig = make_subplots(
        rows=n_rg,
        cols=1,
        subplot_titles=[rg_name for rg_name, _ in risk_groups],
        shared_xaxes=False,
        vertical_spacing=max(0.04, 0.3 / max(n_rg, 1)),
    )

    for source in sources:
        data = data_by_source.get(source.key)
        compute_fn = compute_fns.get(source.key)
        if data is None or compute_fn is None:
            continue
        try:
            series = compute_fn(data, disagg_sex)
        except Exception as exc:
            print(f"[plotting] risk-group {source.key} failed: {exc}")
            continue
        for rg_name, demo, values in series:
            if source.needs_offset_align:
                x, y = series_utils.align_offset(values, years_arr, first_year, mask)
            else:
                x, y = x_years, values[mask].tolist()
            if x:
                _add_trace(fig, x, y, _trace_label(source, demo), demo, source.dash, rg_row[rg_name], 1)

    fig.update_xaxes(
        showgrid=True, gridcolor="#e5e5e5",
        range=[year_start - 1, year_end + 1],
        tickformat="d", tickangle=45,
    )
    fig.update_yaxes(
        showgrid=True, gridcolor="#e5e5e5", rangemode="tozero",
        title_text=y_title, title_font=dict(size=11),
    )

    fig.update_layout(
        height=max(500, n_rg * 250),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hoverlabel=dict(namelength=-1),
        title_text=title,
        margin=dict(t=80, b=40, l=60, r=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})


def render_multi_risk_group_comparison(
    *,
    risk_groups: list[tuple[str, int]],
    sources: list[ComparisonSource],
    data_by_pjnz: dict[str, dict[str, Any]],
    output_years_by_pjnz: dict[str, range],
    compute_fns: dict[str, Any],
    pjnz_stems: list[str],
    year_start: int,
    year_end: int,
    title: str,
    y_title: str | None = None,
) -> go.Figure:
    """Multi-file counterpart of `render_risk_group_comparison`, used by the Multi PJNZ
    tab's "Risk groups"/"New infections" sub-tabs: one row per risk group (not per
    indicator), one line per (PJNZ file, source) pair per row. Colour encodes which PJNZ
    file a line belongs to, dash encodes source — same convention as
    `render_multi_pjnz_comparison`. Always calls `compute_fns[key](data, False)`
    (disagg_sex hard-off): v1 multi-file plots are totals-only, sex/age disaggregation
    dropped to keep colour free for file identity (ADR-0003) — same reasoning as
    `render_multi_pjnz_comparison` dropping the age-facet grid entirely.

    Each file's line is masked against its own `output_years_by_pjnz[stem]`, matching
    `render_multi_pjnz_comparison`'s union-year-range behavior. Returns the `go.Figure`
    directly, same as `render_multi_pjnz_comparison` — callers convert to HTML themselves.
    """
    n_rg = len(risk_groups)
    rg_row = {rg_name: i + 1 for i, (rg_name, _rg) in enumerate(risk_groups)}
    _add_trace = _make_trace_helpers(line_width=2)

    fig = make_subplots(
        rows=n_rg,
        cols=1,
        subplot_titles=[rg_name for rg_name, _ in risk_groups],
        shared_xaxes=False,
        vertical_spacing=max(0.04, 0.3 / max(n_rg, 1)),
    )

    for stem in pjnz_stems:
        data_by_source = data_by_pjnz.get(stem)
        output_years = output_years_by_pjnz.get(stem)
        if data_by_source is None or output_years is None:
            continue
        years_arr = np.array(list(output_years))
        mask = (years_arr >= year_start) & (years_arr <= year_end)
        first_year = int(min(output_years))

        for source in sources:
            data = data_by_source.get(source.key)
            compute_fn = compute_fns.get(source.key)
            if data is None or compute_fn is None:
                continue
            try:
                series = compute_fn(data, False)
            except Exception as exc:
                print(f"[plotting] multi risk-group {source.key} failed for {stem}: {exc}")
                continue
            for rg_name, _demo, values in series:
                if source.needs_offset_align:
                    x, y = series_utils.align_offset(values, years_arr, first_year, mask)
                else:
                    x, y = years_arr[mask].tolist(), values[mask].tolist()
                if x:
                    trace_name = f"{stem} — {source.label}"
                    _add_trace(fig, x, y, trace_name, stem, source.dash, rg_row[rg_name], 1)

    fig.update_xaxes(
        showgrid=True, gridcolor="#e5e5e5",
        range=[year_start - 1, year_end + 1],
        tickformat="d", tickangle=45,
    )
    fig.update_yaxes(
        showgrid=True, gridcolor="#e5e5e5", rangemode="tozero",
        title_text=y_title, title_font=dict(size=11),
    )

    fig.update_layout(
        height=max(500, n_rg * 250),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hoverlabel=dict(namelength=-1),
        title_text=title,
        margin=dict(t=80, b=40, l=60, r=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig


def render_multi_pjnz_comparison(
    *,
    indicator_map: dict[str, Any],
    data_by_pjnz: dict[str, dict[str, Any]],
    output_years_by_pjnz: dict[str, range],
    sources: list[ComparisonSource],
    selected_indicators: list[str],
    pjnz_stems: list[str],
    year_start: int,
    year_end: int,
    title: str,
) -> go.Figure:
    """Multi-file counterpart of `render_comparison`, used by the Multi PJNZ tab: one
    line per (PJNZ file, source) pair per indicator, totals-only (no age/sex
    disaggregation — v1 drops that entirely to free up the colour channel, see
    ADR-0003). Colour encodes which PJNZ file a line belongs to (keyed by stem via
    `_make_trace_helpers`); dash still encodes source, same convention as every other
    tab. Unlike `render_comparison`, this returns the `go.Figure` directly rather than
    an HTML string, so tests can assert on trace properties without a Shiny harness —
    callers that need HTML (the Shiny panel) call `.to_html(...)` themselves.

    Each file's line is masked against its own `output_years_by_pjnz[stem]`, not a
    shared range: `year_start`/`year_end` is the union across all selected files (the
    multi-select year-range slider), so a file whose native year range is narrower
    simply ends at its own boundary rather than being clipped to the intersection.
    """
    n_inds = len(selected_indicators)
    _add_trace = _make_trace_helpers(line_width=2)

    fig = make_subplots(
        rows=n_inds,
        cols=1,
        subplot_titles=list(selected_indicators),
        shared_xaxes=False,
        vertical_spacing=max(0.04, 0.3 / max(n_inds, 1)),
    )

    for ind_idx, indicator in enumerate(selected_indicators):
        row = ind_idx + 1
        ind_def = indicator_map[indicator]

        for stem in pjnz_stems:
            data_by_source = data_by_pjnz.get(stem)
            output_years = output_years_by_pjnz.get(stem)
            if data_by_source is None or output_years is None:
                continue
            years_arr = np.array(list(output_years))
            mask = (years_arr >= year_start) & (years_arr <= year_end)
            first_year = int(min(output_years))

            for source in sources:
                fn = ind_def.disagg.get(source.key)
                if fn is None:
                    continue
                try:
                    series = fn(data_by_source[source.key], False, False)
                except Exception as exc:
                    print(f"[plotting] multi-pjnz {source.key} disagg failed for {indicator} ({stem}): {exc}")
                    continue
                for _demo, values in series:
                    if source.needs_offset_align:
                        x, y = series_utils.align_offset(values, years_arr, first_year, mask)
                    else:
                        x, y = years_arr[mask].tolist(), values[mask].tolist()
                    if x:
                        trace_name = f"{stem} — {source.label}"
                        _add_trace(fig, x, y, trace_name, stem, source.dash, row, 1)

    fig.update_xaxes(
        showgrid=True, gridcolor="#e5e5e5",
        range=[year_start - 1, year_end + 1],
        tickformat="d", tickangle=45,
    )
    fig.update_yaxes(showgrid=True, gridcolor="#e5e5e5", rangemode="tozero")

    fig.update_layout(
        height=max(400, n_inds * 300),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hoverlabel=dict(namelength=-1),
        title_text=title,
        margin=dict(t=80, b=40, l=60, r=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig
