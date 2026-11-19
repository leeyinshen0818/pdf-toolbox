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
    preview_rects,
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


def test_preview_rects_for_fit_fill_the_box_with_the_image() -> None:
    # 300x150 px at 150 dpi is a 144x72 pt page; a 400x400 box scales it by 400/144.
    layout = calculate_page_layout(300, 150, ExportSettings())
    rects = preview_rects(layout, 400, 400)

    assert rects is not None
    assert (rects.page.x0, rects.page.x1) == pytest.approx((0, 400))
    assert (rects.page.y0, rects.page.y1) == pytest.approx((100, 300))
    assert rects.content == rects.page
    assert rects.image == rects.page


def test_preview_rects_for_a4_with_margin_match_the_pdf_layout_scaled() -> None:
    settings = ExportSettings(page_size=PageSizeMode.A4, margin=MarginPreset.SMALL)
    layout = calculate_page_layout(1000, 500, settings)
    inset = 10
    rects = preview_rects(layout, 2 * A4_PORTRAIT.width + 2 * inset, 2 * A4_PORTRAIT.height + 2 * inset, inset=inset)

    margin = A4_PORTRAIT.width * 0.04
    image_width = A4_PORTRAIT.width - 2 * margin
    image_height = image_width / 2
    image_top = (A4_PORTRAIT.height - image_height) / 2

    assert rects is not None
    assert (rects.page.x0, rects.page.y0) == pytest.approx((inset, inset))
    assert (rects.page.width, rects.page.height) == pytest.approx((2 * A4_PORTRAIT.width, 2 * A4_PORTRAIT.height))
    assert (rects.content.x0, rects.content.y0) == pytest.approx((inset + 2 * margin, inset + 2 * margin))
    assert (rects.content.x1, rects.content.y1) == pytest.approx(
        (inset + 2 * (A4_PORTRAIT.width - margin), inset + 2 * (A4_PORTRAIT.height - margin))
    )
    assert (rects.image.x0, rects.image.y0) == pytest.approx((inset + 2 * margin, inset + 2 * image_top))
    assert (rects.image.width, rects.image.height) == pytest.approx((2 * image_width, 2 * image_height))


def test_preview_rects_need_room_to_draw() -> None:
    assert preview_rects(calculate_page_layout(10, 10), 20, 20, inset=10) is None
