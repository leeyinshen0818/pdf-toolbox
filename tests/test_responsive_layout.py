from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea

from pdf_toolbox.app import ensure_window_starts_maximized
from pdf_toolbox.ui.heic_to_jpg_page import HeicToJpgPage
from pdf_toolbox.ui.image_to_pdf_page import ImageToPdfPage
from pdf_toolbox.ui.main_window import MainWindow
from pdf_toolbox.ui.pdf_to_image_page import PdfToImagePage
from pdf_toolbox.ui.responsive import ResponsiveMode


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
    assert all(scroll.maximumWidth() <= 400 or scroll.maximumWidth() >= 16777215 for scroll in settings_scrolls)
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


@pytest.mark.parametrize(
    ("width", "expected"),
    [
        (1500, ResponsiveMode.WIDE),
        (1100, ResponsiveMode.MEDIUM),
        (760, ResponsiveMode.COMPACT),
    ],
)
def test_three_panel_pages_change_layout_modes_without_losing_controls(
    app: QApplication,
    width: int,
    expected: ResponsiveMode,
) -> None:
    image_page = ImageToPdfPage()
    image_page.resize(width, 640)
    image_page.show()
    image_page._apply_responsive_layout(force=True)
    app.processEvents()

    assert image_page._layout_mode == expected
    assert image_page.add_button.isVisible()
    assert image_page.page_size_combo.isVisible()
    assert image_page.export_button.isVisible()

    heic_page = HeicToJpgPage()
    heic_page.resize(width, 640)
    heic_page.show()
    heic_page._apply_responsive_layout(force=True)
    app.processEvents()

    assert heic_page._layout_mode == expected
    assert heic_page.add_button.isVisible()
    assert heic_page.jpg_quality_combo.isVisible()
    assert heic_page.browse_output_folder_button.isVisible()
    assert heic_page.set_default_folder_button.isVisible()
    assert heic_page.convert_button.isVisible()


@pytest.mark.parametrize(
    ("width", "expected"),
    [
        (1500, ResponsiveMode.WIDE),
        (820, ResponsiveMode.COMPACT),
    ],
)
def test_pdf_to_image_stacks_settings_when_width_is_tight(
    app: QApplication,
    width: int,
    expected: ResponsiveMode,
) -> None:
    page = PdfToImagePage()
    page.resize(width, 640)
    page.show()
    page._apply_responsive_layout(force=True)
    app.processEvents()

    assert page._layout_mode == expected
    assert page.format_combo.isVisible()
    assert page.dpi_combo.isVisible()
    assert page.output_folder_edit.minimumWidth() == 0
    assert page.browse_output_folder_button.isVisible()
    assert page.set_default_folder_button.isVisible()
    assert page.convert_button.isVisible()


def test_pdf_organizer_toolbar_wraps_instead_of_clipping(app: QApplication) -> None:
    window = MainWindow()
    window.stack.setCurrentIndex(2)
    window.show()
    page = window.stack.widget(2)
    app.processEvents()

    assert page.layout().itemAt(2).layout().hasHeightForWidth()
    assert page.add_button.isVisible()
    assert page.rotate_right_button.isVisible()
    assert page.delete_button.isVisible()
    assert page.export_button.isVisible()


def test_pdf_organizer_navigation_is_enabled(app: QApplication) -> None:
    window = MainWindow()
    buttons = {button.text(): button for button in window.findChildren(QPushButton)}

    assert buttons["PDF Organizer"].isEnabled()
    buttons["PDF Organizer"].click()
    assert window.stack.currentIndex() == 2
    assert buttons["HEIC -> JPG"].isEnabled()
    buttons["HEIC -> JPG"].click()
    assert window.stack.currentIndex() == 3
