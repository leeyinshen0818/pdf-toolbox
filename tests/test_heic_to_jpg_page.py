from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton
from pillow_heif import register_heif_opener

from pdf_toolbox.core.output_location import OpenLocationResult
from pdf_toolbox.core.pdf_to_image import JpgQuality
from pdf_toolbox.ui.heic_to_jpg_page import HEIC_OUTPUT_FOLDER_SETTING, HeicToJpgPage


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


def make_heic(path: Path, size: tuple[int, int] = (48, 36)) -> Path:
    Image.new("RGB", size, (80, 120, 180)).save(path, format="HEIF")
    return path


def combo_values(combo) -> list[str]:
    return [combo.itemText(index) for index in range(combo.count())]


def test_heic_to_jpg_defaults_and_empty_state(app: QApplication) -> None:
    page = HeicToJpgPage()
    labels = [label.text() for label in page.empty_state.findChildren(type(page.info_label))]
    buttons = page.empty_state.findChildren(QPushButton)

    assert "Add HEIC files to convert into JPG" in labels
    assert any(button.text() == "Add HEICs" and button.objectName() == "PrimaryButton" for button in buttons)
    assert combo_values(page.jpg_quality_combo) == [quality.value for quality in JpgQuality]
    assert page.jpg_quality_combo.currentText() == JpgQuality.MAXIMUM.value
    assert page.convert_button.objectName() == "PrimaryButton"
    assert not page.convert_button.isEnabled()


def test_heic_files_import_render_and_remove(app: QApplication, tmp_path: Path) -> None:
    first = make_heic(tmp_path / "first.heic", size=(40, 30))
    second = make_heic(tmp_path / "second.heif", size=(30, 40))
    page = HeicToJpgPage()

    page._add_heic_paths([str(first), str(second)])
    app.processEvents()

    assert page.file_list.count() == 2
    assert page.info_label.text() == "2 HEIC files loaded"
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
    page = HeicToJpgPage()

    page._add_heic_paths([str(valid), str(valid), str(invalid)])

    assert page.file_list.count() == 1
    assert "Skipped 1 duplicate" in page.status_label.text()
    assert "Rejected 1" in page.status_label.text()
    assert warnings


def test_output_folder_browse_and_default_persistence(
    app: QApplication,
    isolated_settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    saved = tmp_path / "saved"
    chosen = tmp_path / "chosen"
    saved.mkdir()
    chosen.mkdir()
    QSettings().setValue(HEIC_OUTPUT_FOLDER_SETTING, str(saved))
    page = HeicToJpgPage()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_args: str(chosen))

    page._choose_output_folder()

    assert page.output_folder == chosen
    assert QSettings().value(HEIC_OUTPUT_FOLDER_SETTING, "", str) == str(saved)

    page._set_default_output_folder()
    restored = HeicToJpgPage()

    assert QSettings().value(HEIC_OUTPUT_FOLDER_SETTING, "", str) == str(chosen)
    assert restored.output_folder == chosen


def test_success_failure_and_cancel_output_opening(
    app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    page = HeicToJpgPage()
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
