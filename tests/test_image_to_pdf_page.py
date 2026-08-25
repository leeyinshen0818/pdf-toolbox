from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from pdf_toolbox.core.image_corrections import CorrectionSettings, SharpnessPreset, TonePreset
from pdf_toolbox.core.pdf_geometry import MarginPreset, PageOrientation, PageSizeMode
from pdf_toolbox.ui.image_to_pdf_page import ImageToPdfPage


@pytest.fixture(scope="module")
def app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def make_image(path: Path, size=(470, 311)) -> Path:
    Image.new("RGB", size, (80, 120, 180)).save(path)
    return path


def row_widget(page: ImageToPdfPage, row: int):
    widget = page.image_list.itemWidget(page.image_list.item(row))
    assert widget is not None
    return widget


def row_texts(page: ImageToPdfPage, row: int) -> list[str]:
    return [label.text() for label in row_widget(page, row).findChildren(QLabel)]


def row_delete_button(page: ImageToPdfPage, row: int) -> QPushButton:
    buttons = row_widget(page, row).findChildren(QPushButton, "IconButton")
    assert len(buttons) == 1
    return buttons[0]


def combo_values(combo) -> list[str]:
    return [combo.itemText(index) for index in range(combo.count())]


def test_imported_image_details_render_immediately(app: QApplication, tmp_path: Path) -> None:
    image = make_image(tmp_path / "photo.png")
    page = ImageToPdfPage()

    page._add_images([str(image)])
    app.processEvents()

    assert page.image_list.count() == 1
    texts = row_texts(page, 0)
    assert "photo.png" in texts
    assert "470 x 311 px" in texts


def test_top_toolbar_has_add_and_clear_without_remove_selected(app: QApplication) -> None:
    page = ImageToPdfPage()

    assert page.add_button.text() == "Add Images"
    assert page.add_button.objectName() == "PrimaryButton"
    assert page.clear_button.text() == "Clear"
    assert not hasattr(page, "remove_button")


def test_each_imported_image_has_own_removal_action(app: QApplication, tmp_path: Path) -> None:
    first = make_image(tmp_path / "first.jpg", size=(100, 200))
    second = make_image(tmp_path / "second.png", size=(300, 150))
    page = ImageToPdfPage()

    page._add_images([str(first), str(second)])
    row_delete_button(page, 0).click()
    app.processEvents()

    assert [entry.path for entry in page.collection.entries] == [second]
    assert page.image_list.count() == 1
    assert "second.png" in row_texts(page, 0)


def test_removing_current_image_updates_preview_state_safely(app: QApplication, tmp_path: Path) -> None:
    first = make_image(tmp_path / "first.jpg")
    second = make_image(tmp_path / "second.png")
    page = ImageToPdfPage()

    page._add_images([str(first), str(second)])
    page._select_path(first)
    row_delete_button(page, 0).click()
    app.processEvents()

    assert page._current_entry() is not None
    assert page._current_entry().path == second


def test_clear_removes_all_images(app: QApplication, tmp_path: Path) -> None:
    image = make_image(tmp_path / "photo.png")
    page = ImageToPdfPage()

    page._add_images([str(image)])
    page._clear_images()

    assert len(page.collection.entries) == 0
    assert page.image_list.count() == 0
    assert not page.clear_button.isEnabled()


def test_batch_import_and_reorder_keep_row_details(app: QApplication, tmp_path: Path) -> None:
    first = make_image(tmp_path / "first.jpg", size=(100, 200))
    second = make_image(tmp_path / "second.png", size=(300, 150))
    page = ImageToPdfPage()

    page._add_images([str(first), str(second)])
    page.collection.reorder_by_paths([second, first])
    page._sync_list_from_collection()
    app.processEvents()

    assert page.image_list.count() == 2
    assert "second.png" in row_texts(page, 0)
    assert "300 x 150 px" in row_texts(page, 0)
    assert "first.jpg" in row_texts(page, 1)
    assert "100 x 200 px" in row_texts(page, 1)


def test_corrections_are_collapsed_by_default_and_use_preset_buttons(app: QApplication) -> None:
    page = ImageToPdfPage()

    assert not page.corrections_panel.isVisible()
    assert page.corrections_toggle.text() == "Corrections v"
    assert set(page.sharpness_buttons) == set(SharpnessPreset)
    assert set(page.tone_buttons) == set(TonePreset)
    for button in [*page.sharpness_buttons.values(), *page.tone_buttons.values()]:
        assert button.minimumHeight() >= 34


def test_settings_panel_has_room_for_controls(app: QApplication) -> None:
    page = ImageToPdfPage()

    assert page.page_size_combo.minimumWidth() >= 300
    assert page.page_size_combo.view().minimumWidth() >= 320
    assert page.corrections_panel.parentWidget().minimumWidth() >= 350


def test_corrections_remain_per_image(app: QApplication, tmp_path: Path) -> None:
    first = make_image(tmp_path / "first.jpg")
    second = make_image(tmp_path / "second.png")
    page = ImageToPdfPage()

    page._add_images([str(first), str(second)])
    page._select_path(first)
    page._set_sharpness(SharpnessPreset.SHARPER)
    page._select_path(second)
    page._set_tone(TonePreset.BRIGHT_20)

    entries = {entry.path.name: entry.corrections for entry in page.collection.entries}
    assert entries["first.jpg"] == CorrectionSettings(sharpness=SharpnessPreset.SHARPER)
    assert entries["second.png"] == CorrectionSettings(tone=TonePreset.BRIGHT_20)


def test_conversion_setting_values_are_populated_and_readable(app: QApplication) -> None:
    page = ImageToPdfPage()

    assert combo_values(page.page_size_combo) == [mode.value for mode in PageSizeMode]
    assert combo_values(page.orientation_combo) == [mode.value for mode in PageOrientation]
    assert combo_values(page.margin_combo) == [mode.value for mode in MarginPreset]
    assert page.page_size_combo.currentText() == PageSizeMode.FIT.value
    assert page.orientation_combo.currentText() == PageOrientation.PORTRAIT.value
    assert page.margin_combo.currentText() == MarginPreset.NO_MARGIN.value
    assert page.page_size_combo.view().model().rowCount() == 3
    assert page.orientation_combo.view().model().rowCount() == 2
    assert page.margin_combo.view().model().rowCount() == 3
