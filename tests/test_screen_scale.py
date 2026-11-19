from __future__ import annotations

import pytest

from pdf_toolbox.ui.screen_scale import compute_ui_scale, parse_scale_override


@pytest.mark.parametrize(
    "logical_width,os_scale,expected",
    [
        (1536, 1.25, 1.0),
        (1280, 1.5, 0.85),
        (1366, 1.0, 1.0),
        (1920, 1.0, 1.0),
        (2560, 1.0, 1.0),
        (1280, 1.0, 1.0),
    ],
)
def test_compute_ui_scale(logical_width: int, os_scale: float, expected: float) -> None:
    assert compute_ui_scale(logical_width, os_scale) == pytest.approx(expected)


def test_compute_ui_scale_clamps() -> None:
    # Never above 1.0 on large screens, never below 0.85 on tiny ones,
    # never below 1 / os_scale (no smaller than at 100% Windows scaling).
    assert compute_ui_scale(3840, 1.0) == 1.0
    assert compute_ui_scale(800, 2.0) == pytest.approx(0.85)
    assert compute_ui_scale(1000, 1.1) == pytest.approx(1.0 / 1.1)


@pytest.mark.parametrize(
    "value,expected",
    [("0.9", 0.9), ("0.1", 0.5), ("9", 1.5), ("abc", None), ("", None), (None, None)],
)
def test_scale_override_is_clamped(value, expected) -> None:
    assert parse_scale_override(value) == expected
