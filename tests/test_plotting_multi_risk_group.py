"""Unit tests for `render_multi_risk_group_comparison` (the Multi PJNZ tab's "Risk
groups"/"New infections" sub-tabs render function) using synthetic fixtures — no Shiny
test harness, no real PJNZ files. Asserts directly on the returned `go.Figure`'s trace
properties, same pattern as test_plotting_multi_pjnz.py.
"""
import numpy as np

from leapfrog_compare.plotting import ComparisonSource, render_multi_risk_group_comparison

_RISK_GROUPS = [("Low risk", 1), ("High risk", 2)]

_SOURCES = [
    ComparisonSource(key="goals", label="Leapfrog Goals", dash=None),
    ComparisonSource(key="spectrum", label="Spectrum", dash="dash"),
]


def _rg_compute(data, disagg_sex):
    """A compute fn that ignores disagg_sex and returns one ("Total", ndarray) row per
    risk group — mirrors the shape every real compute_rg_*/compute_new_infections_rg_*
    function has, with `data` standing in for the per-source dict already sliced out of
    `data_by_pjnz[stem]`."""
    return [(rg_name, "Total", data[rg_name]) for rg_name, _ in _RISK_GROUPS]


def test_disagg_sex_is_always_passed_as_false():
    seen = {}

    def _compute(data, disagg_sex):
        seen["disagg_sex"] = disagg_sex
        return [(rg_name, "Total", data[rg_name]) for rg_name, _ in _RISK_GROUPS]

    data_by_pjnz = {
        "fileA": {"goals": {"Low risk": np.array([1.0, 2.0]), "High risk": np.array([3.0, 4.0])}},
    }
    output_years_by_pjnz = {"fileA": range(2000, 2002)}

    render_multi_risk_group_comparison(
        risk_groups=_RISK_GROUPS,
        sources=[_SOURCES[0]],
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        compute_fns={"goals": _compute},
        pjnz_stems=["fileA"],
        year_start=2000,
        year_end=2001,
        title="test",
    )

    assert seen["disagg_sex"] is False


def test_colour_is_consistent_per_stem_across_risk_group_rows():
    data_by_pjnz = {
        "fileA": {"goals": {"Low risk": np.array([1.0, 2.0]), "High risk": np.array([3.0, 4.0])}},
        "fileB": {"goals": {"Low risk": np.array([5.0, 6.0]), "High risk": np.array([7.0, 8.0])}},
    }
    output_years_by_pjnz = {"fileA": range(2000, 2002), "fileB": range(2000, 2002)}

    fig = render_multi_risk_group_comparison(
        risk_groups=_RISK_GROUPS,
        sources=[_SOURCES[0]],
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        compute_fns={"goals": _rg_compute},
        pjnz_stems=["fileA", "fileB"],
        year_start=2000,
        year_end=2001,
        title="test",
    )

    colors_by_stem = {}
    for trace in fig.data:
        stem = trace.name.split(" — ")[0]
        colors_by_stem.setdefault(stem, set()).add(trace.line.color)

    assert set(colors_by_stem) == {"fileA", "fileB"}
    assert all(len(colors) == 1 for colors in colors_by_stem.values())
    assert colors_by_stem["fileA"] != colors_by_stem["fileB"]
    # One trace per (stem, risk group) — 2 stems x 2 risk groups.
    assert len(fig.data) == 4


def test_dash_encodes_source_not_stem():
    data_by_pjnz = {
        "fileA": {
            "goals": {"Low risk": np.array([1.0, 2.0]), "High risk": np.array([3.0, 4.0])},
            "spectrum": {"Low risk": np.array([10.0, 20.0]), "High risk": np.array([30.0, 40.0])},
        },
    }
    output_years_by_pjnz = {"fileA": range(2000, 2002)}

    fig = render_multi_risk_group_comparison(
        risk_groups=_RISK_GROUPS,
        sources=_SOURCES,
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        compute_fns={"goals": _rg_compute, "spectrum": _rg_compute},
        pjnz_stems=["fileA"],
        year_start=2000,
        year_end=2001,
        title="test",
    )

    assert len(fig.data) == 4  # 2 risk groups x 2 sources
    dash_by_source_label = {trace.name.split(" — ")[1]: trace.line.dash for trace in fig.data}
    assert dash_by_source_label["Leapfrog Goals"] is None
    assert dash_by_source_label["Spectrum"] == "dash"
    colors = {trace.line.color for trace in fig.data}
    assert len(colors) == 1


def test_risk_group_rows_are_routed_by_name_not_source_order():
    data_by_pjnz = {
        "fileA": {"goals": {"Low risk": np.array([1.0, 2.0]), "High risk": np.array([3.0, 4.0])}},
    }
    output_years_by_pjnz = {"fileA": range(2000, 2002)}

    fig = render_multi_risk_group_comparison(
        risk_groups=_RISK_GROUPS,
        sources=[_SOURCES[0]],
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        compute_fns={"goals": _rg_compute},
        pjnz_stems=["fileA"],
        year_start=2000,
        year_end=2001,
        title="test",
    )

    assert len(fig.data) == 2
    y_by_row = {trace.yaxis: list(trace.y) for trace in fig.data}
    assert sorted(y_by_row.values()) == [[1.0, 2.0], [3.0, 4.0]]
    assert fig.layout.annotations[0].text == "Low risk"
    assert fig.layout.annotations[1].text == "High risk"


def test_each_file_line_stops_at_its_own_year_boundary_not_the_intersection():
    data_by_pjnz = {
        "fileA": {"goals": {"Low risk": np.array([0.0, 1.0, 2.0, 3.0, 4.0]), "High risk": np.array([0.0] * 5)}},
        "fileB": {"goals": {"Low risk": np.array([10.0, 11.0, 12.0, 13.0, 14.0]), "High risk": np.array([0.0] * 5)}},
    }
    output_years_by_pjnz = {
        "fileA": range(2000, 2005),
        "fileB": range(2002, 2007),
    }

    fig = render_multi_risk_group_comparison(
        risk_groups=_RISK_GROUPS,
        sources=[_SOURCES[0]],
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        compute_fns={"goals": _rg_compute},
        pjnz_stems=["fileA", "fileB"],
        year_start=2000,
        year_end=2006,
        title="test",
    )

    by_stem = {trace.name.split(" — ")[0]: trace for trace in fig.data if trace.yaxis == "y"}
    assert list(by_stem["fileA"].x) == [2000, 2001, 2002, 2003, 2004]
    assert list(by_stem["fileA"].y) == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert list(by_stem["fileB"].x) == [2002, 2003, 2004, 2005, 2006]
    assert list(by_stem["fileB"].y) == [10.0, 11.0, 12.0, 13.0, 14.0]


def test_missing_source_key_is_silently_skipped():
    data_by_pjnz = {
        "fileA": {"goals": {"Low risk": np.array([1.0, 2.0]), "High risk": np.array([3.0, 4.0])}},
    }
    output_years_by_pjnz = {"fileA": range(2000, 2002)}

    fig = render_multi_risk_group_comparison(
        risk_groups=_RISK_GROUPS,
        sources=_SOURCES,  # includes "spectrum", absent from compute_fns/data
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        compute_fns={"goals": _rg_compute},
        pjnz_stems=["fileA"],
        year_start=2000,
        year_end=2001,
        title="test",
    )

    assert len(fig.data) == 2  # 2 risk groups, "goals" source only
    assert all(trace.name.endswith("Leapfrog Goals") for trace in fig.data)


def test_missing_stem_data_is_silently_skipped():
    data_by_pjnz = {
        "fileA": {"goals": {"Low risk": np.array([1.0, 2.0]), "High risk": np.array([3.0, 4.0])}},
    }
    output_years_by_pjnz = {"fileA": range(2000, 2002)}

    fig = render_multi_risk_group_comparison(
        risk_groups=_RISK_GROUPS,
        sources=[_SOURCES[0]],
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        compute_fns={"goals": _rg_compute},
        pjnz_stems=["fileA", "fileB"],  # "fileB" has no data
        year_start=2000,
        year_end=2001,
        title="test",
    )

    assert len(fig.data) == 2
    assert all(trace.name.startswith("fileA") for trace in fig.data)


def test_needs_offset_align_source_is_reindexed_per_file():
    offset_source = ComparisonSource(key="spectrum", label="Spectrum", dash="dash", needs_offset_align=True)
    data_by_pjnz = {
        "fileA": {"spectrum": {"Low risk": np.array([100.0, 101.0, 102.0]), "High risk": np.array([0.0, 0.0, 0.0])}},
    }
    output_years_by_pjnz = {"fileA": range(2000, 2005)}

    fig = render_multi_risk_group_comparison(
        risk_groups=_RISK_GROUPS,
        sources=[offset_source],
        data_by_pjnz=data_by_pjnz,
        output_years_by_pjnz=output_years_by_pjnz,
        compute_fns={"spectrum": _rg_compute},
        pjnz_stems=["fileA"],
        year_start=2000,
        year_end=2004,
        title="test",
    )

    low_risk_trace = next(t for t in fig.data if t.yaxis == "y")
    assert low_risk_trace.line.dash == "dash"
    assert list(low_risk_trace.x) == [2000, 2001, 2002]
    assert list(low_risk_trace.y) == [100.0, 101.0, 102.0]
