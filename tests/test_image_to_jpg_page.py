from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QCoreApplication, QDeadlineTimer, QSettings
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton
from pillow_heif import register_heif_opener

from pdf_toolbox.core.output_location import OpenLocationResult
from pdf_toolbox.core.pdf_to_image import JpgQuality
from pdf_toolbox.core.path_keys import path_key as photo_key
from pdf_toolbox.ui.image_to_jpg_page import CONVERT_TO_JPG_OUTPUT_FOLDER_SETTING, PhotoPreviewWidget, ConvertToJpgPage


register_heif_opener()


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
    QCoreApplication.setOrganizationName("pdf-toolbox-heic-tests")
    QCoreApplication.setApplicationName("pdf-toolbox-heic-tests")
    QSettings().clear()
    yield
    QSettings().sync()
    QSettings().clear()


def wait_for_decodes(page: ConvertToJpgPage, timeout_ms: int = 20_000) -> None:
    deadline = QDeadlineTimer(timeout_ms)
    while page.has_pending_decodes() or page.has_background_work():
        assert not deadline.hasExpired(), "background decoding did not finish"
        QTest.qWait(10)


def make_heic(path: Path, size: tuple[int, int] = (48, 36)) -> Path:
    Image.new("RGB", size, (80, 120, 180)).save(path, format="HEIF")
    return path


def combo_values(combo) -> list[str]:
    return [combo.itemText(index) for index in range(combo.count())]


def test_heic_to_jpg_defaults_and_empty_state(app: QApplication) -> None:
    page = ConvertToJpgPage()
    labels = [label.text() for label in page.empty_state.findChildren(type(page.info_label))]
    buttons = page.empty_state.findChildren(QPushButton)

    assert "Add photos to convert into JPG" in labels
    assert any(button.text() == "Add Photos" and button.objectName() == "PrimaryButton" for button in buttons)
    assert sorted(page.jpg_quality_combo.itemData(i) for i in range(page.jpg_quality_combo.count())) == sorted(
        quality.value for quality in JpgQuality
    )
    assert page.jpg_quality_combo.currentData() == JpgQuality.MAXIMUM.value
    assert page.convert_button.objectName() == "PrimaryButton"
    assert not page.convert_button.isEnabled()


def test_heic_files_import_render_and_remove(app: QApplication, tmp_path: Path) -> None:
    first = make_heic(tmp_path / "first.heic", size=(40, 30))
    second = make_heic(tmp_path / "second.heif", size=(30, 40))
    page = ConvertToJpgPage()

    page._add_photo_paths([str(first), str(second)])
    wait_for_decodes(page)

    assert page.file_list.count() == 2
    assert page.info_label.text() == "2 photos loaded"
    assert page._current_entry() is not None
    assert page._current_entry().path == first
    assert page.preview._pixmap is not None

    row = page.file_list.itemWidget(page.file_list.item(0))
    assert row is not None
    row.findChildren(QPushButton, "IconButton")[0].click()
    app.processEvents()

    assert page.file_list.count() == 1
    assert page._current_entry() is not None
    assert page._current_entry().path == second


def test_duplicate_and_invalid_heic_import_handled(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = make_heic(tmp_path / "valid.heic")
    invalid = tmp_path / "invalid.heic"
    invalid.write_bytes(b"bad")
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, _title, message: warnings.append(message) or QMessageBox.Ok)
    page = ConvertToJpgPage()

    page._add_photo_paths([str(valid), str(valid), str(invalid)])

    assert page.file_list.count() == 1
    assert "Skipped 1 duplicate" in page.status_label.text()
    assert "Rejected 1" in page.status_label.text()
    assert warnings



def test_success_failure_and_cancel_output_opening(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    page = ConvertToJpgPage()
    output = tmp_path / "exports"
    output.mkdir()
    saved = output / "photo.jpg"
    saved.write_bytes(b"jpg")
    calls: list[Path] = []
    page.open_output_location = lambda path: calls.append(Path(path)) or OpenLocationResult(True)
    page._set_output_folder(output)

    page._on_conversion_finished((saved,))
    page._on_conversion_cancelled((saved,))
    monkeypatch.setattr(QMessageBox, "critical", lambda *_args: QMessageBox.Ok)
    page._on_conversion_failed("failed")

    assert calls == [output]


def test_preview_widget_paints_loaded_pixmap(app: QApplication) -> None:
    widget = PhotoPreviewWidget()
    widget.resize(400, 400)
    source = QPixmap(120, 80)
    source.fill(QColor(255, 0, 0))
    widget.set_preview(source)

    canvas = QPixmap(widget.size())
    canvas.fill(QColor(0, 0, 0))
    widget.render(canvas)

    center = canvas.toImage().pixelColor(200, 200)
    assert (center.red(), center.green(), center.blue()) == (255, 0, 0)


def test_output_folder_is_remembered_after_browse_and_after_a_successful_job(
    app: QApplication,
    isolated_settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    chosen = tmp_path / "chosen"
    after_job = tmp_path / "after_job"
    chosen.mkdir()
    after_job.mkdir()
    page = ConvertToJpgPage()
    page.open_output_location = lambda _path: OpenLocationResult(True)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_args: str(chosen))

    page._choose_output_folder()

    assert QSettings().value(CONVERT_TO_JPG_OUTPUT_FOLDER_SETTING, "", str) == str(chosen)
    assert ConvertToJpgPage().output_folder == chosen

    page._set_output_folder(after_job)
    page._on_conversion_finished((after_job / "photo.jpg",))

    assert QSettings().value(CONVERT_TO_JPG_OUTPUT_FOLDER_SETTING, "", str) == str(after_job)
    assert ConvertToJpgPage().output_folder == after_job


def test_photos_decode_in_the_background_into_thumbnail_preview_and_size(app: QApplication, tmp_path: Path) -> None:
    photo = make_heic(tmp_path / "photo.heic", size=(64, 40))
    page = ConvertToJpgPage()

    page._add_photo_paths([str(photo)])

    # The row exists at once, before the photo has been decoded.
    assert page.file_list.count() == 1
    wait_for_decodes(page)

    cache_key = page._cache_key(photo)
    assert page.thumbnail_cache.get(cache_key) is not None
    assert page.preview_cache.get(cache_key) is not None
    assert page.preview._pixmap is not None
    assert page._decoded_sizes[photo_key(photo)] == (64, 40)
    row = page.file_list.itemWidget(page.file_list.item(0))
    assert row.thumbnail_label.pixmap().cacheKey() == page.thumbnail_cache.get(cache_key).cacheKey()


def test_clearing_mid_load_drops_results_still_being_decoded(app: QApplication, tmp_path: Path) -> None:
    photos = [make_heic(tmp_path / f"photo_{index}.heic", size=(400, 300)) for index in range(4)]
    page = ConvertToJpgPage()

    page._add_photo_paths([str(path) for path in photos])
    assert page.has_pending_decodes()
    page._clear_files()
    wait_for_decodes(page)  # in-flight results arrive after the clear and must be ignored

    assert page.file_list.count() == 0
    assert len(page.collection) == 0
    assert not page._decode_status and not page._decoded_sizes
    assert all(page.thumbnail_cache.get(page._cache_key(path)) is None for path in photos)
    assert all(page.preview_cache.get(page._cache_key(path)) is None for path in photos)
    assert page.preview._pixmap is None

    # The page still works after a mid-load clear.
    page._add_photo_paths([str(photos[0])])
    wait_for_decodes(page)
    assert page.preview._pixmap is not None
