from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QListWidget, QPushButton
from PIL import Image

from pdf_toolbox.core.output_location import OpenLocationResult
from pdf_toolbox.core.pdf_to_image import DpiPreset, JpgQuality, OutputFormat, PdfInfo
from pdf_toolbox.core.pdf_to_image_state import pdf_key
from pdf_toolbox.ui.components.file_list import FileRowWidget
from pdf_toolbox.ui.pdf_to_image_page import (
    OUTPUT_FOLDER_SETTING,
    SOURCE_KEY_ROLE,
    PdfToImagePage,
    ThumbnailWorker,
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


@pytest.fixture(autouse=True)
def cleanup_qt_widgets(app: QApplication):
    yield
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()


@pytest.fixture()
def isolated_settings(tmp_path: Path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path / "settings"))
    QCoreApplication.setOrganizationName("pdf-toolbox-tests")
    QCoreApplication.setApplicationName("pdf-toolbox-tests")
    QSettings().clear()
    yield
    QSettings().sync()
    QSettings().clear()


def combo_values(combo) -> list[str]:
    return [combo.itemText(index) for index in range(combo.count())]


def load_fake_pdf(page: PdfToImagePage, tmp_path: Path, page_count: int = 3) -> None:
    pdf_path = tmp_path / "document.pdf"
    pdf_path.write_bytes(b"%PDF fake for ui state")
    info = PdfInfo(pdf_path, pdf_path.name, page_count, pdf_path.stat().st_size)
    page.state.load_pdf(info)
    page._populate_rows()
    page._update_pdf_info()
    page._update_state()


def fake_info(path: Path, page_count: int) -> PdfInfo:
    path.write_bytes(b"%PDF fake for ui state")
    return PdfInfo(path, path.name, page_count, path.stat().st_size)


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (80, 120), (240, 245, 250)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_pdf_to_image_setting_defaults_are_populated(app: QApplication) -> None:
    page = PdfToImagePage()

    assert combo_values(page.format_combo) == [item.value for item in OutputFormat]
    assert combo_values(page.dpi_combo) == [item.value for item in DpiPreset]
    assert sorted(page.jpg_quality_combo.itemData(i) for i in range(page.jpg_quality_combo.count())) == sorted(
        item.value for item in JpgQuality
    )
    assert page.format_combo.currentText() == OutputFormat.JPG.value
    assert page.dpi_combo.currentText() == DpiPreset.HIGH.value
    assert page.jpg_quality_combo.currentData() == JpgQuality.MAXIMUM.value


def test_pdf_to_image_empty_state_and_primary_buttons(app: QApplication) -> None:
    page = PdfToImagePage()
    labels = [label.text() for label in page.empty_state.findChildren(type(page.pdf_info_label))]

    assert "Add PDF files to turn their pages into images" in labels
    assert page.add_button.text() == "Add PDFs"
    assert page.add_button.objectName() == "PrimaryButton"
    empty_buttons = page.empty_state.findChildren(QPushButton)
    assert any(button.text() == "Add PDFs" and button.objectName() == "PrimaryButton" for button in empty_buttons)
    assert page.convert_button.objectName() == "PrimaryButton"
    assert page.clear_button.objectName() != "PrimaryButton"


def test_png_disables_jpg_quality_but_keeps_value_readable(app: QApplication) -> None:
    page = PdfToImagePage()

    page.format_combo.setCurrentIndex(page.format_combo.findData(OutputFormat.PNG.value))
    page._on_format_changed()

    assert page.state.output_format == OutputFormat.PNG
    assert page.jpg_quality_container.isHidden()
    assert page.jpg_quality_combo.currentData() == JpgQuality.MAXIMUM.value

    page.format_combo.setCurrentIndex(page.format_combo.findData(OutputFormat.JPG.value))
    page._on_format_changed()

    assert page.state.output_format == OutputFormat.JPG
    assert not page.jpg_quality_container.isHidden()


def test_conversion_uses_all_pages_from_all_loaded_pdfs(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    first = fake_info(tmp_path / "first.pdf", 2)
    second = fake_info(tmp_path / "second.pdf", 3)
    page.state.add_pdf(first)
    page.state.add_pdf(second)
    page._populate_rows()

    refs = page._page_refs_for_conversion()

    assert page.file_list.count() == 2
    assert [(ref.source_filename, ref.page_index) for ref in refs] == [
        ("first.pdf", 0),
        ("first.pdf", 1),
        ("second.pdf", 0),
        ("second.pdf", 1),
        ("second.pdf", 2),
    ]


def test_thumbnail_worker_continues_after_one_preview_failure(app: QApplication, tmp_path: Path) -> None:
    class FakeService:
        def render_page_png_bytes(self, path: Path, page_index: int, dpi: int) -> bytes:
            if page_index == 0:
                raise RuntimeError("bad preview")
            return png_bytes()

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF fake")
    worker = ThumbnailWorker((("source", pdf, 0), ("source", pdf, 1)))
    worker.service = FakeService()
    ready: list[tuple[str, int]] = []
    failed: list[tuple[str, int, str]] = []
    worker.thumbnail_ready.connect(lambda source, page, _data: ready.append((source, page)))
    worker.thumbnail_failed.connect(lambda source, page, message: failed.append((source, page, message)))

    worker.run()

    assert ready == [("source", 1)]
    assert failed == [("source", 0, "bad preview")]


def test_missing_saved_output_folder_falls_back_safely(app: QApplication, isolated_settings, tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    QSettings().setValue(OUTPUT_FOLDER_SETTING, str(missing))

    page = PdfToImagePage()

    assert page.state.output_folder is not None
    assert page.state.output_folder.exists()
    assert page.state.output_folder != missing


def test_successful_conversion_opens_output_folder_once(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    output = tmp_path / "exports"
    output.mkdir()
    saved = output / "page-1.jpg"
    saved.write_bytes(b"image")
    calls: list[Path] = []
    page.open_output_location = lambda path: calls.append(Path(path)) or OpenLocationResult(True)
    page._set_output_folder(output)

    page._on_conversion_finished((saved,))

    assert calls == [output]
    assert page.status_label.text() == "Conversion complete - 1 image(s) saved."


def test_cancelled_conversion_does_not_open_output_folder(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    output = tmp_path / "exports"
    output.mkdir()
    calls: list[Path] = []
    page.open_output_location = lambda path: calls.append(Path(path)) or OpenLocationResult(True)
    page._set_output_folder(output)

    page._on_conversion_cancelled((output / "partial.jpg",))

    assert calls == []


def test_failed_conversion_does_not_open_output_folder(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    page = PdfToImagePage()
    output = tmp_path / "exports"
    output.mkdir()
    calls: list[Path] = []
    page.open_output_location = lambda path: calls.append(Path(path)) or OpenLocationResult(True)
    monkeypatch.setattr(QMessageBox, "critical", lambda *_args: QMessageBox.Ok)
    page._set_output_folder(output)

    page._on_conversion_failed("boom")

    assert calls == []


def test_output_folder_open_failure_keeps_conversion_success(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    output = tmp_path / "exports"
    output.mkdir()
    saved = output / "page-1.jpg"
    saved.write_bytes(b"image")
    page.open_output_location = lambda _path: OpenLocationResult(False, "blocked")
    page._set_output_folder(output)

    page._on_conversion_finished((saved,))

    assert page.status_label.text() == "Conversion complete, but the output folder could not be opened."


def row_for(page: PdfToImagePage, index: int) -> FileRowWidget:
    widget = page.file_list.itemWidget(page.file_list.item(index))
    assert isinstance(widget, FileRowWidget)
    return widget


def test_one_row_per_pdf_and_every_page_is_converted(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    first = fake_info(tmp_path / "first.pdf", 4)
    second = fake_info(tmp_path / "second.pdf", 1)
    page.state.add_pdf(first)
    page.state.add_pdf(second)
    page._populate_rows()

    assert page.file_list.count() == 2
    assert page.file_list.selectionMode() == QListWidget.NoSelection
    assert page.file_list.item(1).data(SOURCE_KEY_ROLE) == pdf_key(second.path)
    assert len(page._page_refs_for_conversion()) == 5


def test_only_the_first_page_thumbnail_is_requested_per_pdf(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    first = fake_info(tmp_path / "first.pdf", 100)
    second = fake_info(tmp_path / "second.pdf", 3)
    page.state.add_pdf(first)
    page.thumbnail_cache[pdf_key(first.path)] = QPixmap(10, 10)
    page.state.add_pdf(second)

    assert page._thumbnail_requests() == ((pdf_key(second.path), second.path, 0),)


def test_rows_reuse_cached_first_page_thumbnails(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    first = fake_info(tmp_path / "first.pdf", 1)
    cached = QPixmap(20, 30)
    page.state.add_pdf(first)
    page.thumbnail_cache[pdf_key(first.path)] = cached

    page._populate_rows()

    assert row_for(page, 0).thumbnail_label.pixmap().cacheKey() == cached.cacheKey()


def test_removing_one_pdf_removes_only_that_pdf(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    infos = [fake_info(tmp_path / f"{name}.pdf", count) for name, count in (("a", 2), ("b", 3), ("c", 1))]
    for info in infos:
        page.state.add_pdf(info)
    page._populate_rows()

    row_for(page, 1).delete_button.click()

    assert [document.info.path for document in page.state.loaded_pdfs] == [infos[0].path, infos[2].path]
    assert [ref.source_filename for ref in page._page_refs_for_conversion()] == ["a.pdf", "a.pdf", "c.pdf"]
    assert page.file_list.count() == 2
    assert [page.file_list.item(i).data(SOURCE_KEY_ROLE) for i in range(2)] == [
        pdf_key(infos[0].path),
        pdf_key(infos[2].path),
    ]


def test_output_folder_is_remembered_after_browse(
    app: QApplication,
    isolated_settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    chosen = tmp_path / "chosen"
    chosen.mkdir()
    page = PdfToImagePage()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_args: str(chosen))

    page._choose_output_folder()

    assert QSettings().value(OUTPUT_FOLDER_SETTING, "", str) == str(chosen)
    assert PdfToImagePage().state.output_folder == chosen


def test_output_folder_is_remembered_after_a_successful_job(
    app: QApplication, isolated_settings, tmp_path: Path
) -> None:
    output = tmp_path / "exports"
    output.mkdir()
    page = PdfToImagePage()
    page.open_output_location = lambda _path: OpenLocationResult(True)
    page._set_output_folder(output)

    assert QSettings().value(OUTPUT_FOLDER_SETTING, "", str) != str(output)

    page._on_conversion_finished((output / "page-1.jpg",))

    assert QSettings().value(OUTPUT_FOLDER_SETTING, "", str) == str(output)
    assert PdfToImagePage().state.output_folder == output
