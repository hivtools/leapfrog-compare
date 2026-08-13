"""Unit tests for `ComparisonSource.default_visible` and the two helpers built
on it (`default_visible_keys`, `visible_sources`) that drive the Multi PJNZ
tab's per-panel "Show lines" checkboxes.
"""
from leapfrog_compare.plotting import ComparisonSource, default_visible_keys, visible_sources

_GOALS_SOURCES_LIKE = [
    ComparisonSource(key="dp_aim", label="Leapfrog DP/AIM", dash=None, default_visible=True),
    ComparisonSource(key="spectrum", label="Spectrum", dash="dash"),
    ComparisonSource(key="goals", label="Leapfrog Goals", dash="dot"),
]

_RISKGROUP_SOURCES_LIKE = [
    ComparisonSource(key="goals", label="Leapfrog Goals", dash=None, default_visible=True),
    ComparisonSource(key="spectrum", label="Spectrum", dash="dash"),
]


def test_default_visible_keys_is_dp_aim_only_for_goals_shaped_sources():
    assert default_visible_keys(_GOALS_SOURCES_LIKE) == ["dp_aim"]


def test_default_visible_keys_is_goals_for_riskgroup_shaped_sources():
    """Risk groups/New infections have no dp_aim-keyed source at all — Leapfrog
    Goals is the only leapfrog line, so it's the one marked default_visible."""
    assert default_visible_keys(_RISKGROUP_SOURCES_LIKE) == ["goals"]


def test_default_visible_keys_empty_when_nothing_marked():
    sources = [ComparisonSource(key="spectrum", label="Spectrum", dash="dash")]
    assert default_visible_keys(sources) == []


def test_visible_sources_filters_to_requested_keys_preserving_order():
    filtered = visible_sources(_GOALS_SOURCES_LIKE, ["goals", "dp_aim"])
    assert [s.key for s in filtered] == ["dp_aim", "goals"]


def test_visible_sources_returns_everything_when_all_keys_requested():
    filtered = visible_sources(_GOALS_SOURCES_LIKE, ["dp_aim", "spectrum", "goals"])
    assert filtered == _GOALS_SOURCES_LIKE


def test_visible_sources_empty_when_no_keys_requested():
    assert visible_sources(_GOALS_SOURCES_LIKE, []) == []
