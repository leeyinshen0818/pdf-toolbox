from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import pymupdf
from PIL import Image
from PySide6.QtWidgets import QAbstractItemView, QApplication, QLabel, QPushButton

from pdf_toolbox.core.output_location import OpenLocationResult
from pdf_toolbox.core.image_corrections import CorrectionSettings, SharpnessPreset, TonePreset
from pdf_toolbox.core.pdf_exporter import PdfExporter
from pdf_toolbox.core.pdf_geometry import A4_PORTRAIT, LETTER_PORTRAIT, MarginPreset, PageOrientation, PageSizeMode
from pdf_toolbox.ui.image_to_pdf_page import AUTO_ORIENTATION_LABEL, ImageToPdfPage


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


def row_number(page: ImageToPdfPage, row: int) -> str:
    labels = row_widget(page, row).findChildren(QLabel, "ImageOrderNumber")
    assert len(labels) == 1
    return labels[0].text()


def combo_values(combo) -> list[str]:
    return [combo.itemText(index) for index in range(combo.count())]


def test_imported_image_details_render_immediately(app: QApplication, tmp_path: Path) -> None:
    image = make_image(tmp_path / "photo.png")
    page = ImageToPdfPage()

    page._add_images([str(image)])
    app.processEvents()

    assert page.image_list.count() == 1
    texts = row_texts(page, 0)
    assert row_number(page, 0) == "1"
    assert "photo.png" in texts
    assert "470 x 311 px" in texts


def test_top_toolbar_has_add_and_clear_without_remove_selected(app: QApplication) -> None:
    page = ImageToPdfPage()
    labels = [label.text() for label in page.empty_state.findChildren(QLabel)]

    assert "Add images to create a PDF" in labels
    assert page.add_button.text() == "Add Images"
    assert page.add_button.objectName() == "PrimaryButton"
    assert page.export_button.objectName() == "PrimaryButton"
    empty_buttons = page.empty_state.findChildren(QPushButton)
    assert any(button.text() == "Add Images" and button.objectName() == "PrimaryButton" for button in empty_buttons)
    assert page.clear_button.text() == "Clear"
    assert page.clear_button.objectName() != "PrimaryButton"
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
    assert row_number(page, 0) == "1"


def test_deleting_selected_last_image_selects_previous(app: QApplication, tmp_path: Path) -> None:
    first = make_image(tmp_path / "first.jpg")
    second = make_image(tmp_path / "second.png")
    page = ImageToPdfPage()

    page._add_images([str(first), str(second)])
    page._select_path(second)
    row_delete_button(page, 1).click()
    app.processEvents()

    assert page._current_entry() is not None
    assert page._current_entry().path == first
    assert row_number(page, 0) == "1"


def test_deleting_final_image_clears_preview_safely(app: QApplication, tmp_path: Path) -> None:
    image = make_image(tmp_path / "only.png")
    page = ImageToPdfPage()

    page._add_images([str(image)])
    row_delete_button(page, 0).click()
    app.processEvents()

    assert page.image_list.count() == 0
    assert page._current_entry() is None
    assert page.preview.current_layout() is None


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
    page._sync_order_from_list([str(second), str(first)])
    app.processEvents()

    assert page.image_list.count() == 2
    assert row_number(page, 0) == "1"
    assert row_number(page, 1) == "2"
    assert "second.png" in row_texts(page, 0)
    assert "300 x 150 px" in row_texts(page, 0)
    assert "first.jpg" in row_texts(page, 1)
    assert "100 x 200 px" in row_texts(page, 1)


def test_append_additional_images_updates_order_numbers(app: QApplication, tmp_path: Path) -> None:
    first = make_image(tmp_path / "first.jpg")
    second = make_image(tmp_path / "second.png")
    third = make_image(tmp_path / "third.jpeg")
    page = ImageToPdfPage()

    page._add_images([str(first), str(second)])
    page._add_images([str(third)])

    assert [row_number(page, index) for index in range(3)] == ["1", "2", "3"]
    assert [entry.path for entry in page.collection.entries] == [first, second, third]


def test_large_batch_keeps_compact_numbered_rows_and_bounded_preview_cache(
    app: QApplication,
    tmp_path: Path,
) -> None:
    images = [make_image(tmp_path / f"image_{index:03d}.png", size=(32, 24)) for index in range(100)]
    page = ImageToPdfPage()

    page._add_images([str(path) for path in images])

    assert page.image_list.count() == 100
    assert row_number(page, 0) == "1"
    assert row_number(page, 49) == "50"
    assert row_number(page, 99) == "100"
    assert page.image_list.item(0).sizeHint().height() <= 90
    assert len(page.preview_cache) <= 1
    assert len(page.thumbnail_cache) == 100


def test_first_import_auto_selects_only_when_no_selection(app: QApplication, tmp_path: Path) -> None:
    first = make_image(tmp_path / "first.jpg")
    second = make_image(tmp_path / "second.png")
    third = make_image(tmp_path / "third.jpeg")
    page = ImageToPdfPage()

    page._add_images([str(first), str(second)])
    assert page._current_entry() is not None
    assert page._current_entry().path == first

    page._select_path(second)
    page._add_images([str(third)])

    assert page._current_entry() is not None
    assert page._current_entry().path == second


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

    assert page.page_size_combo.minimumWidth() >= 260
    assert page.page_size_combo.view().minimumWidth() >= 300
    assert page.corrections_panel.parentWidget().minimumWidth() >= 300


def test_redesigned_workspace_uses_independent_scrollable_image_list(app: QApplication) -> None:
    page = ImageToPdfPage()

    assert page.stack.minimumWidth() >= 260
    assert page.stack.maximumHeight() > 100000
    assert page.image_list.verticalScrollMode() == QAbstractItemView.ScrollPerPixel
    assert page.image_list.autoScrollMargin() >= 48
    assert page.preview.minimumWidth() >= 280
    assert page.export_button.isVisible() or not page.isVisible()


@pytest.mark.parametrize("width,height", [(1366, 768), (1920, 1080)])
def test_image_to_pdf_layout_keeps_three_work_areas_accessible(
    app: QApplication,
    width: int,
    height: int,
) -> None:
    page = ImageToPdfPage()

    page.resize(width, height)
    page.show()
    app.processEvents()

    assert page.stack.isVisible()
    assert page.preview.isVisible()
    assert page.export_button.isVisible()
    assert page.stack.width() > 0
    assert page.preview.width() > 0


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
    assert combo_values(page.orientation_combo) == [AUTO_ORIENTATION_LABEL]
    assert combo_values(page.margin_combo) == [mode.value for mode in MarginPreset]
    assert page.page_size_combo.currentText() == PageSizeMode.FIT.value
    assert page.orientation_combo.currentText() == AUTO_ORIENTATION_LABEL
    assert not page.orientation_combo.isEnabled()
    assert page.margin_combo.currentText() == MarginPreset.NO_MARGIN.value
    assert page.page_size_combo.view().model().rowCount() == 3
    assert page.orientation_combo.view().model().rowCount() == 1
    assert page.margin_combo.view().model().rowCount() == 3


def test_fixed_page_size_enables_manual_orientation(app: QApplication) -> None:
    page = ImageToPdfPage()

    page.page_size_combo.setCurrentIndex(page.page_size_combo.findData(PageSizeMode.A4.value))
    app.processEvents()

    assert page.orientation_combo.isEnabled()
    assert combo_values(page.orientation_combo) == [mode.value for mode in PageOrientation]
    assert page.orientation_combo.currentText() == PageOrientation.PORTRAIT.value

    page.orientation_combo.setCurrentIndex(page.orientation_combo.findData(PageOrientation.LANDSCAPE.value))
    page.page_size_combo.setCurrentIndex(page.page_size_combo.findData(PageSizeMode.FIT.value))
    page.page_size_combo.setCurrentIndex(page.page_size_combo.findData(PageSizeMode.LETTER.value))
    app.processEvents()

    assert page.orientation_combo.isEnabled()
    assert page.orientation_combo.currentText() == PageOrientation.LANDSCAPE.value


@pytest.mark.parametrize(
    ("page_size", "orientation", "expected"),
    [
        (PageSizeMode.A4, PageOrientation.PORTRAIT, (A4_PORTRAIT.width, A4_PORTRAIT.height)),
        (PageSizeMode.A4, PageOrientation.LANDSCAPE, (A4_PORTRAIT.height, A4_PORTRAIT.width)),
        (PageSizeMode.LETTER, PageOrientation.PORTRAIT, (LETTER_PORTRAIT.width, LETTER_PORTRAIT.height)),
        (PageSizeMode.LETTER, PageOrientation.LANDSCAPE, (LETTER_PORTRAIT.height, LETTER_PORTRAIT.width)),
    ],
)
def test_preview_geometry_matches_export_geometry(
    app: QApplication,
    tmp_path: Path,
    page_size: PageSizeMode,
    orientation: PageOrientation,
    expected: tuple[float, float],
) -> None:
    image = make_image(tmp_path / "document.png", size=(1200, 800))
    page = ImageToPdfPage()
    page._add_images([str(image)])
    page.page_size_combo.setCurrentIndex(page.page_size_combo.findData(page_size.value))
    page.orientation_combo.setCurrentIndex(page.orientation_combo.findData(orientation.value))
    page._update_preview()
    layout = page.preview.current_layout()
    output = tmp_path / "preview-match.pdf"

    assert layout is not None
    assert layout.page_size.width == pytest.approx(expected[0])
    assert layout.page_size.height == pytest.approx(expected[1])

    PdfExporter().export(page.collection.entries, output, settings=page._export_settings())

    with pymupdf.open(output) as document:
        assert document[0].rect.width == pytest.approx(layout.page_size.width, abs=0.01)
        assert document[0].rect.height == pytest.approx(layout.page_size.height, abs=0.01)


def test_successful_pdf_export_reveals_output_file(app: QApplication, tmp_path: Path) -> None:
    page = ImageToPdfPage()
    output = tmp_path / "result.pdf"
    output.write_bytes(b"%PDF")
    calls: list[tuple[Path, bool]] = []
    page.open_output_location = lambda path, reveal=False: calls.append((Path(path), reveal)) or OpenLocationResult(True)

    page._on_export_finished(str(output))

    assert calls == [(output, True)]
    assert page.status_label.text() == "PDF exported successfully."


def test_pdf_export_open_failure_does_not_invalidate_export(app: QApplication, tmp_path: Path) -> None:
    page = ImageToPdfPage()
    output = tmp_path / "result.pdf"
    output.write_bytes(b"%PDF")
    page.open_output_location = lambda _path, reveal=False: OpenLocationResult(False, "blocked")

    page._on_export_finished(str(output))

    assert page.status_label.text() == "PDF exported successfully, but the output folder could not be opened."
