"""Image → PDF export choices remembered between launches (page size, orientation, margin).

Values are stored by enum *name* so renaming a label never breaks a saved setting. Anything
missing or unrecognised falls back to the default. Corrections are deliberately not stored.
"""
from __future__ import annotations

from enum import Enum
from typing import Mapping, TypeVar

from pdf_toolbox.core.pdf_geometry import ExportSettings, MarginPreset, PageOrientation, PageSizeMode


PAGE_SIZE_KEY = "image_to_pdf/page_size"
ORIENTATION_KEY = "image_to_pdf/orientation"
MARGIN_KEY = "image_to_pdf/margin"
OUTPUT_FOLDER_KEY = "image_to_pdf/output_folder"
EXPORT_SETTING_KEYS = (PAGE_SIZE_KEY, ORIENTATION_KEY, MARGIN_KEY)

_E = TypeVar("_E", bound=Enum)


def export_settings_to_values(settings: ExportSettings) -> dict[str, str]:
    return {
        PAGE_SIZE_KEY: PageSizeMode(settings.page_size).name,
        ORIENTATION_KEY: PageOrientation(settings.orientation).name,
        MARGIN_KEY: MarginPreset(settings.margin).name,
    }


def export_settings_from_values(values: Mapping[str, object]) -> ExportSettings:
    defaults = ExportSettings()
    return ExportSettings(
        page_size=_enum_or_default(PageSizeMode, values.get(PAGE_SIZE_KEY), defaults.page_size),
        orientation=_enum_or_default(PageOrientation, values.get(ORIENTATION_KEY), defaults.orientation),
        margin=_enum_or_default(MarginPreset, values.get(MARGIN_KEY), defaults.margin),
    )


def _enum_or_default(enum_type: type[_E], raw: object, default: _E) -> _E:
    if not isinstance(raw, str):
        return default
    try:
        return enum_type[raw]
    except KeyError:
        return default
