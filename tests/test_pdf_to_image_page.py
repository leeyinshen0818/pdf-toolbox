from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QListWidget
from PIL import Image

from pdf_toolbox.core.output_location import OpenLocationResult
from pdf_toolbox.core.pdf_to_image import DpiPreset, JpgQuality, OutputFormat, PdfInfo
from pdf_toolbox.core.pdf_to_image_state import pdf_key
from pdf_toolbox.ui.pdf_to_image_page import (
    OUTPUT_FOLDER_SETTING,
    PAGE_INDEX_ROLE,
    SOURCE_KEY_ROLE,
    THUMBNAIL_ICON_SIZE,
    PdfToImagePage,
    ThumbnailWorker,
    thumbnail_from_png_bytes,
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
    page._populate_page_items()
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
    assert combo_values(page.jpg_quality_combo) == [item.value for item in JpgQuality]
    assert page.format_combo.currentText() == OutputFormat.JPG.value
    assert page.dpi_combo.currentText() == DpiPreset.HIGH.value
    assert page.jpg_quality_combo.currentText() == JpgQuality.MAXIMUM.value


def test_all_pages_are_displayed_by_default_in_thumbnail_grid(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    load_fake_pdf(page, tmp_path, page_count=4)

    assert page.thumbnail_list.count() == 4
    assert len(page.thumbnail_list.selectedItems()) == 0
    assert [ref.page_index for ref in page.state.all_page_refs()] == [0, 1, 2, 3]


def test_thumbnail_grid_is_display_only_for_conversion(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    load_fake_pdf(page, tmp_path, page_count=2)

    assert page.thumbnail_list.selectionMode() == QListWidget.NoSelection
    assert [ref.page_index for ref in page._page_refs_for_conversion()] == [0, 1]


def test_png_disables_jpg_quality_but_keeps_value_readable(app: QApplication) -> None:
    page = PdfToImagePage()

    page.format_combo.setCurrentIndex(page.format_combo.findData(OutputFormat.PNG.value))
    page._on_format_changed()

    assert page.state.output_format == OutputFormat.PNG
    assert page.jpg_quality_container.isHidden()
    assert page.jpg_quality_combo.currentText() == JpgQuality.MAXIMUM.value

    page.format_combo.setCurrentIndex(page.format_combo.findData(OutputFormat.JPG.value))
    page._on_format_changed()

    assert page.state.output_format == OutputFormat.JPG
    assert not page.jpg_quality_container.isHidden()


def test_multiple_pdf_pages_show_source_and_keep_source_data(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    first = fake_info(tmp_path / "first.pdf", 2)
    second = fake_info(tmp_path / "second.pdf", 1)

    page.state.add_pdf(first)
    page.state.add_pdf(second)
    page._populate_page_items()

    assert page.thumbnail_list.count() == 3
    assert page.thumbnail_list.item(0).text() == "first.pdf\nPage 1"
    assert page.thumbnail_list.item(2).text() == "second.pdf\nPage 1"
    assert page.thumbnail_list.item(2).data(SOURCE_KEY_ROLE) == pdf_key(second.path)
    assert page.thumbnail_list.item(2).data(PAGE_INDEX_ROLE) == 0


def test_conversion_uses_all_pages_from_all_loaded_pdfs(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    first = fake_info(tmp_path / "first.pdf", 2)
    second = fake_info(tmp_path / "second.pdf", 3)
    page.state.add_pdf(first)
    page.state.add_pdf(second)
    page._populate_page_items()

    refs = page._page_refs_for_conversion()

    assert page.thumbnail_list.count() == 5
    assert [(ref.source_filename, ref.page_index) for ref in refs] == [
        ("first.pdf", 0),
        ("first.pdf", 1),
        ("second.pdf", 0),
        ("second.pdf", 1),
        ("second.pdf", 2),
    ]


def test_thumbnail_requests_include_missing_pages_from_previous_uploads(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    first = fake_info(tmp_path / "first.pdf", 2)
    second = fake_info(tmp_path / "second.pdf", 1)
    first_key = pdf_key(first.path)
    second_key = pdf_key(second.path)
    page.state.add_pdf(first)
    page.thumbnail_cache[(first_key, 0)] = thumbnail_from_png_bytes(png_bytes())
    page.state.add_pdf(second)

    requests = page._thumbnail_requests()

    assert requests == (
        (first_key, first.path, 1),
        (second_key, second.path, 0),
    )


def test_populated_thumbnail_grid_preserves_cached_previews(app: QApplication, tmp_path: Path) -> None:
    page = PdfToImagePage()
    first = fake_info(tmp_path / "first.pdf", 1)
    second = fake_info(tmp_path / "second.pdf", 1)
    first_key = pdf_key(first.path)
    cached = thumbnail_from_png_bytes(png_bytes())
    page.state.add_pdf(first)
    page.thumbnail_cache[(first_key, 0)] = cached
    page.state.add_pdf(second)

    page._populate_page_items()

    restored = page.thumbnail_list.item(0).icon().pixmap(THUMBNAIL_ICON_SIZE)
    assert restored.cacheKey() == cached.cacheKey()


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


def test_thumbnail_pixmap_has_stable_canvas_size(app: QApplication) -> None:
    pixmap = thumbnail_from_png_bytes(png_bytes())

    assert not pixmap.isNull()
    assert pixmap.size() == THUMBNAIL_ICON_SIZE


def test_set_as_default_folder_is_visible_and_readable(app: QApplication) -> None:
    page = PdfToImagePage()

    assert page.set_default_folder_button.text() == "Set as Default Folder"
    assert page.set_default_folder_button.objectName() == "SecondaryActionButton"
    assert page.set_default_folder_button.isVisible() or not page.isVisible()


def test_browse_folder_changes_current_folder_without_saving_default(
    app: QApplication,
    isolated_settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    saved = tmp_path / "saved"
    chosen = tmp_path / "chosen"
    saved.mkdir()
    chosen.mkdir()
    QSettings().setValue(OUTPUT_FOLDER_SETTING, str(saved))
    page = PdfToImagePage()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_args: str(chosen))

    page._choose_output_folder()

    assert page.state.output_folder == chosen
    assert page.output_folder_edit.text() == str(chosen)
    assert QSettings().value(OUTPUT_FOLDER_SETTING, "", str) == str(saved)


def test_output_folder_is_stored_only_when_set_as_default(app: QApplication, isolated_settings, tmp_path: Path) -> None:
    output = tmp_path / "exports"
    output.mkdir()
    page = PdfToImagePage()

    page._set_output_folder(output)
    page._set_default_output_folder()
    restored = PdfToImagePage()

    assert QSettings().value(OUTPUT_FOLDER_SETTING, "", str) == str(output)
    assert restored.state.output_folder == output
    assert restored.output_folder_edit.text() == str(output)
    assert page.status_label.text() == "Default output folder saved."


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
