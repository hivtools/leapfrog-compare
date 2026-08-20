"""Unit tests for `render_averted_barchart` (the Multi PJNZ tab's "Averted"
sub-tab render function) using synthetic fixtures — no Shiny test harness, no
real PJNZ files. Asserts directly on the returned `go.Figure`'s trace properties.
"""
from types import SimpleNamespace

import numpy as np

from leapfrog_compare.plotting import ComparisonSource, render_averted_barchart

_SOURCES = [
    ComparisonSource(key="dp_aim", label="Leapfrog DP/AIM", dash=None, primary=True),
    ComparisonSource(key="spectrum", label="Spectrum", dash="dash"),
]


def _totals_disagg(data, disagg_age, disagg_sex):
    """Mirrors every real IndicatorDef.disagg entry's shape called with both
    flags off: a single ("Total", ndarray) series, `data` standing in for the
    per-source ndarray already sliced out of `data_by_source`."""
    return [("Total", data)]


def _indicator_map(*, with_spectrum=True):
    disagg = {"dp_aim": _totals_disagg}
    if with_spectrum:
        disagg["spectrum"] = _totals_disagg
    return {"Indicator A": SimpleNamespace(disagg=disagg)}


def test_bar_value_is_baseline_minus_pjnz_total():
    data_by_pjnz = {
        "baseline": {"dp_aim": np.array([10.0, 10.0, 10.0])},
        "fileA": {"dp_aim": np.array([1.0, 2.0, 3.0])},
    }
    output_years_by_pjnz = {"baseline": range(2000, 2003), "fileA": range(2000, 2003)}

    fig = render_averted_barchart(
        indicator_map=_indicator_map(with_spectrum=False),
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=[_SOURCES[0]],
        indicator="Indicator A",
        baseline_stem="baseline",
        pjnz_stems=["baseline", "fileA"],
        year_start=2000,
        year_end=2002,
        title="test",
    )

    assert len(fig.data) == 1
    trace = fig.data[0]
    assert list(trace.x) == ["fileA"]
    # baseline total = 30, fileA total = 6 -> averted = 24
    assert list(trace.y) == [24.0]


def test_baseline_excluded_from_x_axis():
    data_by_pjnz = {
        "baseline": {"dp_aim": np.array([5.0, 5.0])},
        "fileA": {"dp_aim": np.array([1.0, 1.0])},
        "fileB": {"dp_aim": np.array([2.0, 2.0])},
    }
    output_years_by_pjnz = {s: range(2000, 2002) for s in data_by_pjnz}

    fig = render_averted_barchart(
        indicator_map=_indicator_map(with_spectrum=False),
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=[_SOURCES[0]],
        indicator="Indicator A",
        baseline_stem="baseline",
        pjnz_stems=["baseline", "fileA", "fileB"],
        year_start=2000,
        year_end=2001,
        title="test",
    )

    assert len(fig.data) == 1
    assert "baseline" not in fig.data[0].x
    assert set(fig.data[0].x) == {"fileA", "fileB"}


def test_dp_aim_is_blue_and_spectrum_is_orange():
    data_by_pjnz = {
        "baseline": {"dp_aim": np.array([10.0]), "spectrum": np.array([10.0])},
        "fileA": {"dp_aim": np.array([4.0]), "spectrum": np.array([6.0])},
    }
    output_years_by_pjnz = {"baseline": range(2000, 2001), "fileA": range(2000, 2001)}

    fig = render_averted_barchart(
        indicator_map=_indicator_map(),
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=_SOURCES,
        indicator="Indicator A",
        baseline_stem="baseline",
        pjnz_stems=["baseline", "fileA"],
        year_start=2000,
        year_end=2000,
        title="test",
    )

    assert len(fig.data) == 2
    color_by_name = {trace.name: trace.marker.color for trace in fig.data}
    assert color_by_name["Leapfrog DP/AIM"] == "#1f77b4"
    assert color_by_name["Spectrum"] == "#ff7f0e"


def test_missing_source_key_skips_that_source_without_shifting_the_others_colour():
    # "Indicator A" has no "spectrum" disagg entry — dp_aim (sources[0]) must
    # still get the first palette colour, not be shifted because spectrum
    # (sources[1]) was skipped.
    data_by_pjnz = {
        "baseline": {"dp_aim": np.array([10.0])},
        "fileA": {"dp_aim": np.array([4.0])},
    }
    output_years_by_pjnz = {"baseline": range(2000, 2001), "fileA": range(2000, 2001)}

    fig = render_averted_barchart(
        indicator_map=_indicator_map(with_spectrum=False),
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=_SOURCES,
        indicator="Indicator A",
        baseline_stem="baseline",
        pjnz_stems=["baseline", "fileA"],
        year_start=2000,
        year_end=2000,
        title="test",
    )

    assert len(fig.data) == 1
    assert fig.data[0].name == "Leapfrog DP/AIM"
    assert fig.data[0].marker.color == "#1f77b4"


def test_missing_baseline_returns_empty_figure():
    fig = render_averted_barchart(
        indicator_map=_indicator_map(with_spectrum=False),
        data_by_pjnz={"fileA": {"dp_aim": np.array([1.0])}},
        output_years_by_pjnz={"fileA": range(2000, 2001)},
        sources=[_SOURCES[0]],
        indicator="Indicator A",
        baseline_stem="baseline",
        pjnz_stems=["fileA"],
        year_start=2000,
        year_end=2000,
        title="test",
    )
    assert len(fig.data) == 0


def test_file_missing_data_for_one_source_is_dropped_from_that_bar_only():
    data_by_pjnz = {
        "baseline": {"dp_aim": np.array([10.0]), "spectrum": np.array([10.0])},
        "fileA": {"dp_aim": np.array([4.0])},  # no spectrum data for fileA
    }
    output_years_by_pjnz = {"baseline": range(2000, 2001), "fileA": range(2000, 2001)}

    fig = render_averted_barchart(
        indicator_map=_indicator_map(),
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=_SOURCES,
        indicator="Indicator A",
        baseline_stem="baseline",
        pjnz_stems=["baseline", "fileA"],
        year_start=2000,
        year_end=2000,
        title="test",
    )

    by_name = {trace.name: trace for trace in fig.data}
    assert list(by_name["Leapfrog DP/AIM"].x) == ["fileA"]
    # Spectrum has no data at all for the only non-baseline file -> no trace drawn.
    assert "Spectrum" not in by_name


def test_year_range_restricts_aggregation():
    data_by_pjnz = {
        "baseline": {"dp_aim": np.array([10.0, 10.0, 10.0])},
        "fileA": {"dp_aim": np.array([1.0, 1.0, 1.0])},
    }
    output_years_by_pjnz = {"baseline": range(2000, 2003), "fileA": range(2000, 2003)}

    fig = render_averted_barchart(
        indicator_map=_indicator_map(with_spectrum=False),
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        sources=[_SOURCES[0]],
        indicator="Indicator A",
        baseline_stem="baseline",
        pjnz_stems=["baseline", "fileA"],
        year_start=2000,
        year_end=2001,  # only 2 of the 3 years
        title="test",
    )

    # baseline total over 2000-2001 = 20, fileA total = 2 -> averted = 18
    assert list(fig.data[0].y) == [18.0]
