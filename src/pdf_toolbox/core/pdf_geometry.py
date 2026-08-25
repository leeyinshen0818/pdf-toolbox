from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


POINTS_PER_INCH = 72
MM_PER_INCH = 25.4
A4_WIDTH_MM = 210
A4_HEIGHT_MM = 297
A4_WIDTH_POINTS = A4_WIDTH_MM / MM_PER_INCH * POINTS_PER_INCH
A4_HEIGHT_POINTS = A4_HEIGHT_MM / MM_PER_INCH * POINTS_PER_INCH
LETTER_WIDTH_POINTS = 8.5 * POINTS_PER_INCH
LETTER_HEIGHT_POINTS = 11 * POINTS_PER_INCH
DEFAULT_FIT_DPI = 150


class PageSizeMode(str, Enum):
    FIT = "Fit - Same page size as image"
    A4 = "A4"
    LETTER = "US Letter"


class PageOrientation(str, Enum):
    PORTRAIT = "Portrait"
    LANDSCAPE = "Landscape"


class MarginPreset(str, Enum):
    NO_MARGIN = "No Margin"
    SMALL = "Small"
    BIG = "Big"


MARGIN_FACTORS = {
    MarginPreset.NO_MARGIN: 0.0,
    MarginPreset.SMALL: 0.04,
    MarginPreset.BIG: 0.10,
}


@dataclass(frozen=True)
class PageSize:
    width: float
    height: float


@dataclass(frozen=True)
class FitRect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass(frozen=True)
class ExportSettings:
    page_size: PageSizeMode = PageSizeMode.FIT
    orientation: PageOrientation = PageOrientation.PORTRAIT
    margin: MarginPreset = MarginPreset.NO_MARGIN


@dataclass(frozen=True)
class PageLayout:
    page_size: PageSize
    image_rect: FitRect


A4_PORTRAIT = PageSize(width=A4_WIDTH_POINTS, height=A4_HEIGHT_POINTS)
LETTER_PORTRAIT = PageSize(width=LETTER_WIDTH_POINTS, height=LETTER_HEIGHT_POINTS)


def fit_rect_to_page(
    source_width: int | float,
    source_height: int | float,
    page_width: int | float = A4_PORTRAIT.width,
    page_height: int | float = A4_PORTRAIT.height,
) -> FitRect:
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Source dimensions must be greater than zero.")
    if page_width <= 0 or page_height <= 0:
        raise ValueError("Page dimensions must be greater than zero.")

    scale = min(page_width / source_width, page_height / source_height)
    fitted_width = source_width * scale
    fitted_height = source_height * scale
    x0 = (page_width - fitted_width) / 2
    y0 = (page_height - fitted_height) / 2

    return FitRect(
        x0=x0,
        y0=y0,
        x1=x0 + fitted_width,
        y1=y0 + fitted_height,
    )


def page_size_for_settings(
    source_width: int | float,
    source_height: int | float,
    settings: ExportSettings,
) -> PageSize:
    page_mode = PageSizeMode(settings.page_size)
    orientation = PageOrientation(settings.orientation)

    if page_mode == PageSizeMode.FIT:
        return _fit_page_size(source_width, source_height, MarginPreset(settings.margin))

    if page_mode == PageSizeMode.A4:
        base = A4_PORTRAIT
    elif page_mode == PageSizeMode.LETTER:
        base = LETTER_PORTRAIT
    else:
        raise ValueError(f"Unsupported page size: {settings.page_size}")

    if orientation == PageOrientation.LANDSCAPE:
        return PageSize(width=base.height, height=base.width)

    return base


def calculate_page_layout(
    source_width: int | float,
    source_height: int | float,
    settings: ExportSettings | None = None,
) -> PageLayout:
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Source dimensions must be greater than zero.")

    export_settings = settings or ExportSettings()
    page_mode = PageSizeMode(export_settings.page_size)
    margin_preset = MarginPreset(export_settings.margin)
    page_size = page_size_for_settings(source_width, source_height, export_settings)

    if page_mode == PageSizeMode.FIT:
        margin = _fit_margin_points(source_width, source_height, margin_preset)
    else:
        margin = min(page_size.width, page_size.height) * MARGIN_FACTORS[margin_preset]

    content_width = page_size.width - (2 * margin)
    content_height = page_size.height - (2 * margin)
    if content_width <= 0 or content_height <= 0:
        raise ValueError("Margin leaves no usable page area.")

    fitted = fit_rect_to_page(source_width, source_height, content_width, content_height)
    return PageLayout(
        page_size=page_size,
        image_rect=FitRect(
            x0=fitted.x0 + margin,
            y0=fitted.y0 + margin,
            x1=fitted.x1 + margin,
            y1=fitted.y1 + margin,
        ),
    )


def _fit_page_size(
    source_width: int | float,
    source_height: int | float,
    margin_preset: MarginPreset,
) -> PageSize:
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Source dimensions must be greater than zero.")

    image_width = source_width / DEFAULT_FIT_DPI * POINTS_PER_INCH
    image_height = source_height / DEFAULT_FIT_DPI * POINTS_PER_INCH
    margin = _fit_margin_points(source_width, source_height, margin_preset)

    return PageSize(
        width=image_width + (2 * margin),
        height=image_height + (2 * margin),
    )


def _fit_margin_points(
    source_width: int | float,
    source_height: int | float,
    margin_preset: MarginPreset,
) -> float:
    if margin_preset == MarginPreset.NO_MARGIN:
        return 0.0

    image_width = source_width / DEFAULT_FIT_DPI * POINTS_PER_INCH
    image_height = source_height / DEFAULT_FIT_DPI * POINTS_PER_INCH
    return min(image_width, image_height) * MARGIN_FACTORS[margin_preset]
