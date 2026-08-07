"""Unit tests for pure helpers in `indicator_map.py`."""
from leapfrog_compare.indicator_map import (
    CD4_LABELS_HC1, CD4_LABELS_HC2, cd4_facet_desc,
)


def test_cd4_facet_desc_hc1_is_cd4_distribution():
    assert cd4_facet_desc(CD4_LABELS_HC1) == "CD4 distribution"


def test_cd4_facet_desc_hc2_is_cd4_count():
    assert cd4_facet_desc(CD4_LABELS_HC2) == "CD4 count"


def test_cd4_facet_desc_total_row_is_total():
    assert cd4_facet_desc(["Total"]) == "total"
