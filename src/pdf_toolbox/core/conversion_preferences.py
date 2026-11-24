"""PDF → Image and Convert to JPG choices remembered between launches.

Same pattern as image_to_pdf_preferences: enum names are stored, and anything missing or
unrecognised falls back to the default. Output folders use their own keys (see the pages).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from pdf_toolbox.core.pdf_to_image import DpiPreset, JpgQuality, OutputFormat
from pdf_toolbox.core.stored_enums import enum_or_default


PDF_TO_IMAGE_FORMAT_KEY = "pdf_to_image/format"
PDF_TO_IMAGE_RESOLUTION_KEY = "pdf_to_image/resolution"
PDF_TO_IMAGE_JPG_QUALITY_KEY = "pdf_to_image/jpg_quality"
PDF_TO_IMAGE_SETTING_KEYS = (PDF_TO_IMAGE_FORMAT_KEY, PDF_TO_IMAGE_RESOLUTION_KEY, PDF_TO_IMAGE_JPG_QUALITY_KEY)

# Key keeps its pre-rename "heic_to_jpg/" prefix so existing users keep their saved quality.
CONVERT_TO_JPG_QUALITY_KEY = "heic_to_jpg/jpg_quality"
CONVERT_TO_JPG_SETTING_KEYS = (CONVERT_TO_JPG_QUALITY_KEY,)


@dataclass(frozen=True)
class PdfToImagePreferences:
    output_format: OutputFormat = OutputFormat.JPG
    dpi: DpiPreset = DpiPreset.HIGH
    jpg_quality: JpgQuality = JpgQuality.MAXIMUM


@dataclass(frozen=True)
class ConvertToJpgPreferences:
    jpg_quality: JpgQuality = JpgQuality.MAXIMUM


def pdf_to_image_preferences_to_values(preferences: PdfToImagePreferences) -> dict[str, str]:
    return {
        PDF_TO_IMAGE_FORMAT_KEY: OutputFormat(preferences.output_format).name,
        PDF_TO_IMAGE_RESOLUTION_KEY: DpiPreset(preferences.dpi).name,
        PDF_TO_IMAGE_JPG_QUALITY_KEY: JpgQuality(preferences.jpg_quality).name,
    }


def pdf_to_image_preferences_from_values(values: Mapping[str, object]) -> PdfToImagePreferences:
    defaults = PdfToImagePreferences()
    return PdfToImagePreferences(
        output_format=enum_or_default(OutputFormat, values.get(PDF_TO_IMAGE_FORMAT_KEY), defaults.output_format),
        dpi=enum_or_default(DpiPreset, values.get(PDF_TO_IMAGE_RESOLUTION_KEY), defaults.dpi),
        jpg_quality=enum_or_default(JpgQuality, values.get(PDF_TO_IMAGE_JPG_QUALITY_KEY), defaults.jpg_quality),
    )


def convert_to_jpg_preferences_to_values(preferences: ConvertToJpgPreferences) -> dict[str, str]:
    return {CONVERT_TO_JPG_QUALITY_KEY: JpgQuality(preferences.jpg_quality).name}


def convert_to_jpg_preferences_from_values(values: Mapping[str, object]) -> ConvertToJpgPreferences:
    defaults = ConvertToJpgPreferences()
    return ConvertToJpgPreferences(
        jpg_quality=enum_or_default(JpgQuality, values.get(CONVERT_TO_JPG_QUALITY_KEY), defaults.jpg_quality),
    )
