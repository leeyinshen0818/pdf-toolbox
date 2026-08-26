from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from pdf_toolbox.core.pdf_to_image import DpiPreset, JpgQuality, OutputFormat, PdfInfo
from pdf_toolbox.ui.pdf_to_image_page import PdfToImagePage


@pytest.fixture(scope="module")
def app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def combo_values(combo) -> list[str]:
    return [combo.itemText(index) for index in range(combo.count())]


def load_fake_pdf(page: PdfToImagePage, tmp_path: Path, page_count: int = 3) -> None:
    pdf_path = tmp_path / "document.pdf"
    pdf_path.write_bytes(b"%PDF fake for ui state")
    info = PdfInfo(pdf_path, pdf_path.name, page_count, pdf_path.stat().st_size)
    page.state.load_pdf(info)
    page._populate_page_items(page_count)
    page._update_pdf_info()
    page._update_state()


def test_pdf_to_image_setting_defaults_are_populated(app: QApplication) -> None:
    page = PdfToImagePage()

    assert combo_values(page.format_combo) == [item.value for item in OutputFormat]
    assert combo_values(page.dpi_combo) == [item.value for item in DpiPreset]
    assert combo_values(page.jpg_quality_combo) == [item.value for item in JpgQuality]
    assert page.format_combo.currentText() == OutputFormat.JPG.value
    assert page.dpi_combo.currentText() == DpiPreset.HIGH.value
    assert page.jpg_quality_combo.currentText() == JpgQuality.HIGH.value


def test_all_pages_are_selected_by_default_in_thumbnail_grid(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    load_fake_pdf(page, tmp_path, page_count=4)

    assert page.thumbnail_list.count() == 4
    assert len(page.thumbnail_list.selectedItems()) == 4
    assert page.state.ordered_selected_pages() == (0, 1, 2, 3)


def test_select_all_and_clear_selection_buttons(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    load_fake_pdf(page, tmp_path, page_count=2)

    page._clear_page_selection()
    assert page.state.ordered_selected_pages() == ()

    page._select_all_pages()
    assert page.state.ordered_selected_pages() == (0, 1)


def test_png_disables_jpg_quality_but_keeps_value_readable(app: QApplication) -> None:
    page = PdfToImagePage()

    page.format_combo.setCurrentIndex(page.format_combo.findData(OutputFormat.PNG.value))
    page._on_format_changed()

    assert not page.jpg_quality_combo.isEnabled()
    assert page.jpg_quality_combo.currentText() == JpgQuality.HIGH.value
