from __future__ import annotations

import pytest

from pdf_toolbox.core.conversion_preferences import (
    HEIC_JPG_QUALITY_KEY,
    PDF_TO_IMAGE_FORMAT_KEY,
    PDF_TO_IMAGE_JPG_QUALITY_KEY,
    PDF_TO_IMAGE_RESOLUTION_KEY,
    HeicPreferences,
    PdfToImagePreferences,
    heic_preferences_from_values,
    heic_preferences_to_values,
    pdf_to_image_preferences_from_values,
    pdf_to_image_preferences_to_values,
)
from pdf_toolbox.core.pdf_to_image import DpiPreset, JpgQuality, OutputFormat


@pytest.mark.parametrize(
    "preferences",
    [
        PdfToImagePreferences(),
        PdfToImagePreferences(OutputFormat.PNG, DpiPreset.STANDARD, JpgQuality.STANDARD),
        PdfToImagePreferences(OutputFormat.JPG, DpiPreset.HIGH, JpgQuality.HIGH),
    ],
)
def test_pdf_to_image_preferences_round_trip(preferences: PdfToImagePreferences) -> None:
    assert pdf_to_image_preferences_from_values(pdf_to_image_preferences_to_values(preferences)) == preferences


@pytest.mark.parametrize("quality", list(JpgQuality))
def test_heic_preferences_round_trip(quality: JpgQuality) -> None:
    preferences = HeicPreferences(quality)
    assert heic_preferences_from_values(heic_preferences_to_values(preferences)) == preferences


@pytest.mark.parametrize(
    "values",
    [
        {},
        {PDF_TO_IMAGE_FORMAT_KEY: None, PDF_TO_IMAGE_RESOLUTION_KEY: None, PDF_TO_IMAGE_JPG_QUALITY_KEY: None},
        {PDF_TO_IMAGE_FORMAT_KEY: "TIFF", PDF_TO_IMAGE_RESOLUTION_KEY: "ULTRA", PDF_TO_IMAGE_JPG_QUALITY_KEY: "Best"},
        {PDF_TO_IMAGE_FORMAT_KEY: 1, PDF_TO_IMAGE_RESOLUTION_KEY: ["HIGH"], PDF_TO_IMAGE_JPG_QUALITY_KEY: "maximum"},
        # Labels are not valid stored values (names are stored).
        {PDF_TO_IMAGE_FORMAT_KEY: "PNG ", PDF_TO_IMAGE_RESOLUTION_KEY: "Standard - 150 DPI", PDF_TO_IMAGE_JPG_QUALITY_KEY: "Standard"},
    ],
)
def test_invalid_pdf_to_image_values_fall_back_to_defaults(values: dict) -> None:
    assert pdf_to_image_preferences_from_values(values) == PdfToImagePreferences()


def test_each_invalid_pdf_to_image_value_falls_back_on_its_own() -> None:
    restored = pdf_to_image_preferences_from_values(
        {PDF_TO_IMAGE_FORMAT_KEY: "PNG", PDF_TO_IMAGE_RESOLUTION_KEY: "nonsense", PDF_TO_IMAGE_JPG_QUALITY_KEY: "STANDARD"}
    )

    assert restored == PdfToImagePreferences(OutputFormat.PNG, DpiPreset.HIGH, JpgQuality.STANDARD)


@pytest.mark.parametrize("raw", [None, "", "Best quality", "maximum", 85, ["HIGH"]])
def test_invalid_heic_quality_falls_back_to_default(raw: object) -> None:
    assert heic_preferences_from_values({HEIC_JPG_QUALITY_KEY: raw}) == HeicPreferences()
