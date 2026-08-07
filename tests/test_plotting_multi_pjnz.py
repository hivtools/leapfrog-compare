"""Unit tests for `render_multi_pjnz_comparison` (the Multi PJNZ tab's render
function) using synthetic fixtures — no Shiny test harness, no real PJNZ files.
Asserts directly on the returned `go.Figure`'s trace properties.
"""
from types import SimpleNamespace

import numpy as np

from leapfrog_compare.plotting import ComparisonSource, render_multi_pjnz_comparison

_SOURCES = [
    ComparisonSource(key="dp_aim", label="Leapfrog DP/AIM", dash=None, primary=True),
    ComparisonSource(key="spectrum", label="Spectrum", dash="dash"),
]


def _totals_disagg(data, disagg_age, disagg_sex):
    """A disagg fn that ignores the flags and always returns one ("Total", data) series
    — mirrors the shape every real IndicatorDef.disagg entry has, with `data` standing
    in for the per-source ndarray already sliced out of `data_by_source`."""
    return [("Total", data)]


def _indicator_map(*, with_spectrum=True):
    disagg = {"dp_aim": _totals_disagg}
    if with_spectrum:
        disagg["spectrum"] = _totals_disagg
    return {"Indicator A": SimpleNamespace(disagg=disagg)}


def test_colour_is_consistent_per_stem_across_indicators():
    indicator_map = {
        "Indicator A": SimpleNamespace(disagg={"dp_aim": _totals_disagg}),
        "Indicator B": SimpleNamespace(disagg={"dp_aim": _totals_disagg}),
    }
    data_by_pjnz = {
        "fileA": {"dp_aim": np.array([1.0, 2.0, 3.0])},
        "fileB": {"dp_aim": np.array([4.0, 5.0, 6.0])},
    }
    output_years_by_pjnz = {"fileA": range(2000, 2003), "fileB": range(2000, 2003)}

    fig = render_multi_pjnz_comparison(
        indicator_map=indicator_map,
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=[_SOURCES[0]],
        selected_indicators=["Indicator A", "Indicator B"],
        pjnz_stems=["fileA", "fileB"],
        year_start=2000,
        year_end=2002,
        title="test",
    )

    colors_by_stem = {}
    for trace in fig.data:
        stem = trace.name.split(" — ")[0]
        colors_by_stem.setdefault(stem, set()).add(trace.line.color)

    assert set(colors_by_stem) == {"fileA", "fileB"}
    # Each stem gets exactly one colour, reused for every indicator row it appears in.
    assert all(len(colors) == 1 for colors in colors_by_stem.values())
    # Different stems get different colours.
    assert colors_by_stem["fileA"] != colors_by_stem["fileB"]


def test_dash_encodes_source_not_stem():
    data_by_pjnz = {
        "fileA": {
            "dp_aim": np.array([1.0, 2.0, 3.0]),
            "spectrum": np.array([10.0, 20.0, 30.0]),
        },
    }
    output_years_by_pjnz = {"fileA": range(2000, 2003)}

    fig = render_multi_pjnz_comparison(
        indicator_map=_indicator_map(),
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=_SOURCES,
        selected_indicators=["Indicator A"],
        pjnz_stems=["fileA"],
        year_start=2000,
        year_end=2002,
        title="test",
    )

    assert len(fig.data) == 2
    dash_by_source_label = {trace.name.split(" — ")[1]: trace.line.dash for trace in fig.data}
    assert dash_by_source_label["Leapfrog DP/AIM"] is None
    assert dash_by_source_label["Spectrum"] == "dash"
    # Same-stem traces still share a colour despite differing dash.
    colors = {trace.line.color for trace in fig.data}
    assert len(colors) == 1


def test_each_file_line_stops_at_its_own_year_boundary_not_the_intersection():
    # fileA: 2000-2004, fileB: 2002-2006 — union slider spans 2000-2006.
    data_by_pjnz = {
        "fileA": {"dp_aim": np.array([0.0, 1.0, 2.0, 3.0, 4.0])},
        "fileB": {"dp_aim": np.array([10.0, 11.0, 12.0, 13.0, 14.0])},
    }
    output_years_by_pjnz = {
        "fileA": range(2000, 2005),
        "fileB": range(2002, 2007),
    }

    fig = render_multi_pjnz_comparison(
        indicator_map=_indicator_map(with_spectrum=False),
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=[_SOURCES[0]],
        selected_indicators=["Indicator A"],
        pjnz_stems=["fileA", "fileB"],
        year_start=2000,
        year_end=2006,
        title="test",
    )

    by_stem = {trace.name.split(" — ")[0]: trace for trace in fig.data}
    assert list(by_stem["fileA"].x) == [2000, 2001, 2002, 2003, 2004]
    assert list(by_stem["fileA"].y) == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert list(by_stem["fileB"].x) == [2002, 2003, 2004, 2005, 2006]
    assert list(by_stem["fileB"].y) == [10.0, 11.0, 12.0, 13.0, 14.0]


def test_slider_narrower_than_a_files_range_still_masks_that_file():
    data_by_pjnz = {"fileA": {"dp_aim": np.array([0.0, 1.0, 2.0, 3.0, 4.0])}}
    output_years_by_pjnz = {"fileA": range(2000, 2005)}

    fig = render_multi_pjnz_comparison(
        indicator_map=_indicator_map(with_spectrum=False),
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=[_SOURCES[0]],
        selected_indicators=["Indicator A"],
        pjnz_stems=["fileA"],
        year_start=2001,
        year_end=2003,
        title="test",
    )

    assert len(fig.data) == 1
    assert list(fig.data[0].x) == [2001, 2002, 2003]
    assert list(fig.data[0].y) == [1.0, 2.0, 3.0]


def test_missing_source_key_is_silently_skipped():
    # "Indicator A" here has no "spectrum" disagg entry at all — matches the
    # missing-key-skip convention render_comparison already relies on.
    data_by_pjnz = {
        "fileA": {"dp_aim": np.array([1.0, 2.0]), "spectrum": np.array([9.0, 9.0])},
    }
    output_years_by_pjnz = {"fileA": range(2000, 2002)}

    fig = render_multi_pjnz_comparison(
        indicator_map=_indicator_map(with_spectrum=False),
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=_SOURCES,
        selected_indicators=["Indicator A"],
        pjnz_stems=["fileA"],
        year_start=2000,
        year_end=2001,
        title="test",
    )

    assert len(fig.data) == 1
    assert fig.data[0].name == "fileA — Leapfrog DP/AIM"


def test_needs_offset_align_source_is_reindexed_per_file():
    # Every real Spectrum ComparisonSource (`_GOALS_SOURCES`/`_AIM_SOURCES` in app.py)
    # sets needs_offset_align=True: its array is positionally offset from the file's
    # own first_year, rather than pre-aligned to output_years, and may be shorter than
    # output_years (e.g. Spectrum modvars ending before the leapfrog run's final year).
    offset_source = ComparisonSource(key="spectrum", label="Spectrum", dash="dash", needs_offset_align=True)
    data_by_pjnz = {
        # Only 3 values for a 5-year output_years range — positions 3 and 4 (years
        # 2003, 2004) have no backing data and must be dropped, not index-error.
        "fileA": {"spectrum": np.array([100.0, 101.0, 102.0])},
    }
    output_years_by_pjnz = {"fileA": range(2000, 2005)}

    fig = render_multi_pjnz_comparison(
        indicator_map={"Indicator A": SimpleNamespace(disagg={"spectrum": _totals_disagg})},
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=[offset_source],
        selected_indicators=["Indicator A"],
        pjnz_stems=["fileA"],
        year_start=2000,
        year_end=2004,
        title="test",
    )

    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.line.dash == "dash"
    assert list(trace.x) == [2000, 2001, 2002]
    assert list(trace.y) == [100.0, 101.0, 102.0]


def test_goals_model_15_49_indicator_gets_three_lines_per_file():
    # Mirrors app.py's _GOALS_SOURCES: dp_aim solid, spectrum dashed, goals-native
    # dotted — all three present for a 15-49 indicator (per ADR-0002).
    goals_sources = [
        ComparisonSource(key="dp_aim", label="Leapfrog DP/AIM", dash=None, primary=True),
        ComparisonSource(key="spectrum", label="Spectrum", dash="dash", needs_offset_align=True),
        ComparisonSource(key="goals", label="Leapfrog Goals", dash="dot"),
    ]
    indicator_map = {
        "New HIV infections (15-49)": SimpleNamespace(disagg={
            "dp_aim": _totals_disagg,
            "spectrum": _totals_disagg,
            "goals": _totals_disagg,
        }),
    }
    data_by_pjnz = {
        "fileA": {
            "dp_aim": np.array([1.0, 2.0, 3.0]),
            "spectrum": np.array([1.0, 2.0, 3.0]),
            "goals": np.array([1.0, 2.0, 3.0]),
        },
    }
    output_years_by_pjnz = {"fileA": range(2000, 2003)}

    fig = render_multi_pjnz_comparison(
        indicator_map=indicator_map,
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=goals_sources,
        selected_indicators=["New HIV infections (15-49)"],
        pjnz_stems=["fileA"],
        year_start=2000,
        year_end=2002,
        title="test",
    )

    assert len(fig.data) == 3
    dash_by_label = {trace.name.split(" — ")[1]: trace.line.dash for trace in fig.data}
    assert dash_by_label["Leapfrog DP/AIM"] is None
    assert dash_by_label["Spectrum"] == "dash"
    assert dash_by_label["Leapfrog Goals"] == "dot"
    # All three lines belong to the same file, so they share one colour.
    assert len({trace.line.color for trace in fig.data}) == 1


def test_aim_model_15_49_indicator_gets_two_lines_per_file_no_goals_native():
    # Mirrors app.py's _AIM_SOURCES: no "goals" source at all, since Goals-native
    # output doesn't exist for AIM-only files.
    aim_sources = [
        ComparisonSource(key="dp_aim", label="Leapfrog AIM", dash=None, primary=True),
        ComparisonSource(key="spectrum_aim", label="Spectrum", dash="dash", needs_offset_align=True),
    ]
    # Indicator map still has a "goals" disagg entry (as the real INDICATOR_MAP does
    # for 15-49 indicators) — it must be ignored since no "goals" source is passed.
    indicator_map = {
        "New HIV infections (15-49)": SimpleNamespace(disagg={
            "dp_aim": _totals_disagg,
            "spectrum_aim": _totals_disagg,
            "goals": _totals_disagg,
        }),
    }
    data_by_pjnz = {
        "fileA": {
            "dp_aim": np.array([1.0, 2.0, 3.0]),
            "spectrum_aim": np.array([1.0, 2.0, 3.0]),
        },
    }
    output_years_by_pjnz = {"fileA": range(2000, 2003)}

    fig = render_multi_pjnz_comparison(
        indicator_map=indicator_map,
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=aim_sources,
        selected_indicators=["New HIV infections (15-49)"],
        pjnz_stems=["fileA"],
        year_start=2000,
        year_end=2002,
        title="test",
    )

    assert len(fig.data) == 2
    dash_by_label = {trace.name.split(" — ")[1]: trace.line.dash for trace in fig.data}
    assert dash_by_label["Leapfrog AIM"] is None
    assert dash_by_label["Spectrum"] == "dash"
    assert "Leapfrog Goals" not in dash_by_label


def test_missing_stem_data_is_silently_skipped():
    # A stem listed in pjnz_stems but absent from data_by_pjnz (e.g. its run failed)
    # should not raise, and simply contributes no traces.
    data_by_pjnz = {"fileA": {"dp_aim": np.array([1.0, 2.0])}}
    output_years_by_pjnz = {"fileA": range(2000, 2002)}

    fig = render_multi_pjnz_comparison(
        indicator_map=_indicator_map(with_spectrum=False),
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=[_SOURCES[0]],
        selected_indicators=["Indicator A"],
        pjnz_stems=["fileA", "fileB"],
        year_start=2000,
        year_end=2001,
        title="test",
    )

    assert len(fig.data) == 1
    assert fig.data[0].name == "fileA — Leapfrog DP/AIM"
