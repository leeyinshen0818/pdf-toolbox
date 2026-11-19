"""Image → PDF export choices remembered between launches (page size, orientation, margin).

Values are stored by enum *name* so renaming a label never breaks a saved setting. Anything
missing or unrecognised falls back to the default. Corrections are deliberately not stored.
"""
from __future__ import annotations

from typing import Mapping

from pdf_toolbox.core.pdf_geometry import ExportSettings, MarginPreset, PageOrientation, PageSizeMode
from pdf_toolbox.core.stored_enums import enum_or_default


PAGE_SIZE_KEY = "image_to_pdf/page_size"
ORIENTATION_KEY = "image_to_pdf/orientation"
MARGIN_KEY = "image_to_pdf/margin"
OUTPUT_FOLDER_KEY = "image_to_pdf/output_folder"
EXPORT_SETTING_KEYS = (PAGE_SIZE_KEY, ORIENTATION_KEY, MARGIN_KEY)


def export_settings_to_values(settings: ExportSettings) -> dict[str, str]:
    return {
        PAGE_SIZE_KEY: PageSizeMode(settings.page_size).name,
        ORIENTATION_KEY: PageOrientation(settings.orientation).name,
        MARGIN_KEY: MarginPreset(settings.margin).name,
    }


def export_settings_from_values(values: Mapping[str, object]) -> ExportSettings:
    defaults = ExportSettings()
    return ExportSettings(
        page_size=enum_or_default(PageSizeMode, values.get(PAGE_SIZE_KEY), defaults.page_size),
        orientation=enum_or_default(PageOrientation, values.get(ORIENTATION_KEY), defaults.orientation),
        margin=enum_or_default(MarginPreset, values.get(MARGIN_KEY), defaults.margin),
    )
