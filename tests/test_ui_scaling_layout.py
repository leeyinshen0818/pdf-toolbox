from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QScrollArea

from pdf_toolbox.app import ensure_window_starts_maximized
from pdf_toolbox.ui.heic_to_jpg_page import HeicToJpgPage
from pdf_toolbox.ui.image_to_pdf_page import ImageToPdfPage
from pdf_toolbox.ui.main_window import MainWindow
from pdf_toolbox.ui.pdf_organizer_page import PdfOrganizerPage
from pdf_toolbox.ui.pdf_to_image_page import PdfToImagePage


def page_y(page, widget) -> int:
    return widget.mapTo(page, QPoint(0, 0)).y()


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
    assert pdf_page.browse_output_folder_button.isVisible()
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
    assert heic_page.browse_output_folder_button.isVisible()


def test_startup_helper_requests_maximized_window(app: QApplication) -> None:
    window = MainWindow()

    ensure_window_starts_maximized(window, app)
    app.processEvents()

    assert bool(window.windowState() & Qt.WindowMaximized)


def test_restored_window_minimum_size_fits_a_1366x768_work_area(app: QApplication) -> None:
    window = MainWindow()

    # 1366x768 at 100% leaves roughly 1366x728 above the taskbar.
    assert window.minimumWidth() <= 1366
    assert window.minimumHeight() <= 728


def test_three_panel_pages_keep_same_panel_order(app: QApplication) -> None:

    image_page = ImageToPdfPage()
    assert isinstance(image_page.content_layout, QHBoxLayout)
    assert image_page.content_layout.count() == 3
    assert image_page.content_layout.itemAt(0).widget() is image_page.list_section
    assert image_page.content_layout.itemAt(1).widget() is image_page.preview_section
    assert image_page.content_layout.itemAt(2).widget() is image_page.settings_panel
    assert not hasattr(image_page, "_apply_responsive_layout")
    assert not hasattr(image_page, "_layout_mode")

    heic_page = HeicToJpgPage()
    assert isinstance(heic_page.content_layout, QHBoxLayout)
    assert heic_page.content_layout.count() == 3
    assert heic_page.content_layout.itemAt(0).widget() is heic_page.list_section
    assert heic_page.content_layout.itemAt(1).widget() is heic_page.preview_section
    assert heic_page.content_layout.itemAt(2).widget() is heic_page.settings_panel
    assert not hasattr(heic_page, "_apply_responsive_layout")
    assert not hasattr(heic_page, "_layout_mode")


def test_image_to_pdf_settings_controls_do_not_spread_vertically(app: QApplication) -> None:
    page = ImageToPdfPage()
    page.resize(1536, 816)
    page.show()
    app.processEvents()

    assert page.orientation_combo.y() - page.page_size_combo.y() <= 80
    assert page.margin_combo.y() - page.orientation_combo.y() <= 80
    assert page.corrections_toggle.y() - page.margin_combo.y() <= 80
    assert page_y(page, page.export_button) > page_y(page, page.corrections_toggle)


def test_heic_to_jpg_settings_controls_do_not_spread_vertically(app: QApplication) -> None:
    page = HeicToJpgPage()
    page.resize(1536, 816)
    page.show()
    app.processEvents()

    assert page.output_folder_edit.y() - page.jpg_quality_combo.y() <= 90
    assert not page.progress_bar.isVisible()  # progress only shows while a conversion runs
    assert page_y(page, page.convert_button) > page_y(page, page.output_folder_edit)


def test_pdf_to_image_keeps_settings_to_the_right(app: QApplication) -> None:
    page = PdfToImagePage()
    page.show()
    app.processEvents()

    assert isinstance(page.content_layout, QHBoxLayout)
    assert page.content_layout.count() == 2
    assert page.content_layout.itemAt(0).widget() is page.main_section
    assert page.content_layout.itemAt(1).widget() is page.settings_panel
    assert page.format_combo.isVisible()
    assert page.browse_output_folder_button.isVisible()
    assert page.convert_button.isVisible()
    assert not hasattr(page, "_apply_responsive_layout")
    assert not hasattr(page, "_layout_mode")


def test_pdf_organizer_toolbar_keeps_original_single_row_layout(app: QApplication) -> None:
    window = MainWindow()
    window.stack.setCurrentIndex(2)
    window.show()
    app.processEvents()
    page = window.stack.widget(2)
    toolbar = page.layout().itemAt(2).layout()

    assert isinstance(toolbar, QHBoxLayout)
    assert not toolbar.hasHeightForWidth()
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
    assert buttons["HEIC → JPG"].isEnabled()
    buttons["HEIC → JPG"].click()
    assert window.stack.currentIndex() == 3


@pytest.mark.parametrize("page_type", [ImageToPdfPage, PdfToImagePage, PdfOrganizerPage, HeicToJpgPage])
def test_every_page_fits_a_600px_tall_work_area(app: QApplication, page_type) -> None:
    page = page_type()

    assert page.minimumSizeHint().height() <= 600
