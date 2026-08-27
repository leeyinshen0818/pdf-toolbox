from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea

from pdf_toolbox.app import ensure_window_starts_maximized
from pdf_toolbox.ui.main_window import MainWindow


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


@pytest.mark.parametrize("width,height", [(1280, 720), (1366, 768), (1920, 1080), (2560, 1440)])
def test_main_pages_keep_key_controls_accessible_at_common_desktop_sizes(
    app: QApplication,
    width: int,
    height: int,
) -> None:
    window = MainWindow()
    window.resize(width, height)
    window.show()
    app.processEvents()

    window.stack.setCurrentIndex(0)
    app.processEvents()
    image_page = window.stack.widget(0)
    assert image_page.export_button.isVisible()

    window.stack.setCurrentIndex(1)
    app.processEvents()
    pdf_page = window.stack.widget(1)
    settings_scrolls = window.findChildren(QScrollArea, "SettingsScroll")
    assert pdf_page.convert_button.isVisible()
    assert pdf_page.set_default_folder_button.text() == "Set as Default Folder"
    assert pdf_page.thumbnail_list.isWrapping()
    assert all(scroll.maximumWidth() <= 430 for scroll in settings_scrolls)
    assert all(scroll.minimumWidth() <= scroll.maximumWidth() for scroll in settings_scrolls)

    window.stack.setCurrentIndex(2)
    app.processEvents()
    organizer_page = window.stack.widget(2)
    assert organizer_page.export_button.text() == "Export PDF"
    assert organizer_page.page_grid.isWrapping()

    window.stack.setCurrentIndex(3)
    app.processEvents()
    heic_page = window.stack.widget(3)
    assert heic_page.convert_button.text() == "Convert"
    assert heic_page.set_default_folder_button.text() == "Set as Default Folder"


def test_startup_helper_requests_maximized_window(app: QApplication) -> None:
    window = MainWindow()

    ensure_window_starts_maximized(window, app)
    app.processEvents()

    assert bool(window.windowState() & Qt.WindowMaximized)


def test_restored_window_has_sensible_minimum_size(app: QApplication) -> None:
    window = MainWindow()

    assert window.minimumWidth() >= 960
    assert window.minimumHeight() >= 640


def test_pdf_organizer_navigation_is_enabled(app: QApplication) -> None:
    window = MainWindow()
    buttons = {button.text(): button for button in window.findChildren(QPushButton)}

    assert buttons["PDF Organizer"].isEnabled()
    buttons["PDF Organizer"].click()
    assert window.stack.currentIndex() == 2
    assert buttons["HEIC -> JPG"].isEnabled()
    buttons["HEIC -> JPG"].click()
    assert window.stack.currentIndex() == 3
