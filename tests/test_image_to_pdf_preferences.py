from __future__ import annotations

import pytest

from pdf_toolbox.core.image_to_pdf_preferences import (
    MARGIN_KEY,
    ORIENTATION_KEY,
    PAGE_SIZE_KEY,
    export_settings_from_values,
    export_settings_to_values,
)
from pdf_toolbox.core.pdf_geometry import ExportSettings, MarginPreset, PageOrientation, PageSizeMode


@pytest.mark.parametrize(
    "settings",
    [
        ExportSettings(),
        ExportSettings(PageSizeMode.A4, PageOrientation.LANDSCAPE, MarginPreset.SMALL),
        ExportSettings(PageSizeMode.LETTER, PageOrientation.PORTRAIT, MarginPreset.BIG),
    ],
)
def test_export_settings_round_trip(settings: ExportSettings) -> None:
    assert export_settings_from_values(export_settings_to_values(settings)) == settings


@pytest.mark.parametrize(
    "values",
    [
        {},
        {PAGE_SIZE_KEY: None, ORIENTATION_KEY: None, MARGIN_KEY: None},
        {PAGE_SIZE_KEY: "A5", ORIENTATION_KEY: "Sideways", MARGIN_KEY: "Huge"},
        {PAGE_SIZE_KEY: "A4 ", ORIENTATION_KEY: 3, MARGIN_KEY: ["SMALL"]},
        # Display labels are not valid stored values (names are stored, not labels).
        {PAGE_SIZE_KEY: "US Letter", ORIENTATION_KEY: "Landscape", MARGIN_KEY: "Small"},
    ],
)
def test_invalid_stored_values_fall_back_to_defaults(values: dict) -> None:
    assert export_settings_from_values(values) == ExportSettings()


def test_each_invalid_value_falls_back_on_its_own() -> None:
    restored = export_settings_from_values({PAGE_SIZE_KEY: "A4", ORIENTATION_KEY: "bogus", MARGIN_KEY: "BIG"})

    assert restored == ExportSettings(PageSizeMode.A4, PageOrientation.PORTRAIT, MarginPreset.BIG)
