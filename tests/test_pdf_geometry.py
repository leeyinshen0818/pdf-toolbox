from __future__ import annotations

import pytest

from pdf_toolbox.core.pdf_geometry import (
    A4_PORTRAIT,
    DEFAULT_FIT_DPI,
    LETTER_PORTRAIT,
    ExportSettings,
    MarginPreset,
    PageOrientation,
    PageSizeMode,
    calculate_page_layout,
    fit_rect_to_page,
)


def test_fit_mode_uses_image_aspect_ratio_without_margin() -> None:
    layout = calculate_page_layout(3000, 2000)

    assert layout.page_size.width / layout.page_size.height == pytest.approx(1.5)
    assert layout.page_size.width == pytest.approx(3000 / DEFAULT_FIT_DPI * 72)
    assert layout.image_rect.x0 == pytest.approx(0)
    assert layout.image_rect.y0 == pytest.approx(0)
    assert layout.image_rect.width == pytest.approx(layout.page_size.width)
    assert layout.image_rect.height == pytest.approx(layout.page_size.height)


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (800, 1200),
        (1200, 800),
        (900, 900),
    ],
)
def test_fit_mode_preserves_natural_image_shape(width: int, height: int) -> None:
    layout = calculate_page_layout(width, height, ExportSettings(page_size=PageSizeMode.FIT))

    assert layout.page_size.width / layout.page_size.height == pytest.approx(width / height)
    assert layout.image_rect.width == pytest.approx(layout.page_size.width)
    assert layout.image_rect.height == pytest.approx(layout.page_size.height)


def test_fit_mode_margin_enlarges_page_around_image() -> None:
    layout = calculate_page_layout(1000, 500, ExportSettings(margin=MarginPreset.SMALL))

    assert layout.image_rect.x0 > 0
    assert layout.image_rect.y0 > 0
    assert layout.page_size.width > layout.image_rect.width
    assert layout.page_size.height > layout.image_rect.height
    assert layout.image_rect.width / layout.image_rect.height == pytest.approx(2.0)


def test_a4_portrait_geometry() -> None:
    layout = calculate_page_layout(400, 200, ExportSettings(page_size=PageSizeMode.A4))

    assert layout.page_size == A4_PORTRAIT
    assert layout.image_rect.width / layout.image_rect.height == pytest.approx(2.0)
    assert layout.image_rect.x0 == pytest.approx(0)
    assert layout.image_rect.y0 > 0


def test_a4_landscape_geometry() -> None:
    layout = calculate_page_layout(
        400,
        200,
        ExportSettings(page_size=PageSizeMode.A4, orientation=PageOrientation.LANDSCAPE),
    )

    assert layout.page_size.width == pytest.approx(A4_PORTRAIT.height)
    assert layout.page_size.height == pytest.approx(A4_PORTRAIT.width)


def test_letter_portrait_geometry() -> None:
    layout = calculate_page_layout(200, 400, ExportSettings(page_size=PageSizeMode.LETTER))

    assert layout.page_size == LETTER_PORTRAIT
    assert layout.image_rect.width / layout.image_rect.height == pytest.approx(0.5)


def test_letter_landscape_geometry() -> None:
    layout = calculate_page_layout(
        200,
        400,
        ExportSettings(page_size=PageSizeMode.LETTER, orientation=PageOrientation.LANDSCAPE),
    )

    assert layout.page_size.width == pytest.approx(LETTER_PORTRAIT.height)
    assert layout.page_size.height == pytest.approx(LETTER_PORTRAIT.width)


def test_small_and_big_margins_use_different_insets() -> None:
    small = calculate_page_layout(1000, 1000, ExportSettings(page_size=PageSizeMode.A4, margin=MarginPreset.SMALL))
    big = calculate_page_layout(1000, 1000, ExportSettings(page_size=PageSizeMode.A4, margin=MarginPreset.BIG))

    assert small.image_rect.x0 > 0
    assert big.image_rect.x0 > small.image_rect.x0
    assert big.image_rect.width < small.image_rect.width


def test_fit_rect_rejects_invalid_source_dimensions() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        fit_rect_to_page(0, 100)
