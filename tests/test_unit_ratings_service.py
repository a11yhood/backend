"""Unit tests for shared ratings service helpers."""

import pytest

from services.ratings import compute_display_rating

pytestmark = pytest.mark.unit


def test_compute_display_rating_weighted_blend_and_fallbacks():
    assert compute_display_rating(4.0, 2.0) == 3.0
    assert compute_display_rating(4.0, 2.0, 3) == pytest.approx(3.5)
    assert compute_display_rating(4.0, None) == 4.0
    assert compute_display_rating(None, 2.0) == 2.0
    assert compute_display_rating(None, None) is None
