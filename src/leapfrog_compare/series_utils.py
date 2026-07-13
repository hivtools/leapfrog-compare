"""
Small pure helpers for reshaping disaggregated series lists for plotting.

A "series list" is `list[tuple[str, np.ndarray]]`: a demographic-group label
(e.g. "Total", "Male", "20-24", or a composite "20-24 / Male") paired with a
1-D array of values. These helpers are shared across all comparison tabs.
"""
from __future__ import annotations

import numpy as np


def series_for_age_cell(
    all_series: list[tuple[str, np.ndarray]],
    age_label: str,
) -> list[tuple[str, np.ndarray]]:
    """Extract series for one age-group column from a fully disaggregated series list."""
    cell: list[tuple[str, np.ndarray]] = []
    for label, values in all_series:
        if " / " in label:
            a_part, s_part = label.split(" / ", 1)
            if a_part == age_label:
                cell.append((s_part, values))
        elif label == age_label:
            cell.append(("Total", values))
    if not cell:
        # No age breakdown for this indicator (e.g. Births) — fall back to totals
        for label, values in all_series:
            if " / " not in label:
                cell.append((label, values))
    return cell


def has_age_labels(series: list[tuple[str, np.ndarray]], age_label_set: set[str]) -> bool:
    """True if any series label carries an age-group prefix — i.e. this source supports age disagg."""
    for label, _ in series:
        part = label.split(" / ")[0] if " / " in label else label
        if part in age_label_set:
            return True
    return False


def align_offset(
    spec_values: np.ndarray,
    years_arr: np.ndarray,
    first_year: int,
    mask: np.ndarray,
) -> tuple[list, list]:
    """Reindex a series whose own array is positionally offset from `first_year`
    (e.g. raw PJNZ modvars, which start at their own native year 0) onto `years_arr`."""
    year_idx = years_arr - first_year
    valid = (year_idx >= 0) & (year_idx < len(spec_values))
    combined = mask & valid
    return years_arr[combined].tolist(), spec_values[year_idx[combined].astype(int)].tolist()
