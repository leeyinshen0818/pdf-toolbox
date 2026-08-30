from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QScrollArea

from pdf_toolbox.app import ensure_window_starts_maximized
from pdf_toolbox.ui.heic_to_jpg_page import HeicToJpgPage
from pdf_toolbox.ui.image_to_pdf_page import ImageToPdfPage
from pdf_toolbox.ui.main_window import MainWindow
from pdf_toolbox.ui.pdf_to_image_page import PdfToImagePage
from pdf_toolbox.ui.scale import calculate_ui_scale, set_ui_scale


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
    set_ui_scale(1.0)
    app.processEvents()


@pytest.mark.parametrize(
    ("available_size", "expected"),
    [
        (QSize(1920, 1080), 1.0),
        (QSize(2560, 1440), 1.0),
        (QSize(1366, 768), 1366 / 1920),
        (QSize(1280, 720), 0.68),
        (QSize(1024, 600), 0.68),
    ],
)
def test_ui_scale_uses_logical_available_geometry_with_bounds(
    available_size: QSize,
    expected: float,
) -> None:
    assert calculate_ui_scale(available_size) == pytest.approx(expected, abs=0.005)


@pytest.mark.parametrize("width,height", [(1280, 720), (1366, 768), (1920, 1080), (2560, 1440)])
def test_main_pages_keep_key_controls_accessible_at_common_desktop_sizes(
    app: QApplication,
    width: int,
    height: int,
) -> None:
    set_ui_scale(calculate_ui_scale(QSize(width, height)))
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


def test_restored_window_minimum_size_scales_down_for_smaller_work_areas(app: QApplication) -> None:
    set_ui_scale(calculate_ui_scale(QSize(1366, 768)))
    window = MainWindow()

    assert 650 <= window.minimumWidth() < 960
    assert 430 <= window.minimumHeight() < 640


def test_three_panel_pages_keep_same_panel_order_when_scaled(app: QApplication) -> None:
    set_ui_scale(calculate_ui_scale(QSize(1366, 768)))

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
    assert page.export_button.y() > page.corrections_toggle.y()


def test_heic_to_jpg_settings_controls_do_not_spread_vertically(app: QApplication) -> None:
    page = HeicToJpgPage()
    page.resize(1536, 816)
    page.show()
    app.processEvents()

    assert page.output_folder_edit.y() - page.jpg_quality_combo.y() <= 90
    assert page.set_default_folder_button.y() - page.output_folder_edit.y() <= 60
    assert page.progress_bar.y() > page.set_default_folder_button.y()
    assert page.convert_button.y() > page.progress_bar.y()


def test_pdf_to_image_keeps_settings_to_the_right_when_scaled(app: QApplication) -> None:
    set_ui_scale(calculate_ui_scale(QSize(1366, 768)))
    page = PdfToImagePage()
    page.show()
    app.processEvents()

    assert isinstance(page.content_layout, QHBoxLayout)
    assert page.content_layout.count() == 2
    assert page.content_layout.itemAt(0).widget() is page.main_section
    assert page.content_layout.itemAt(1).widget() is page.settings_panel
    assert page.format_combo.isVisible()
    assert page.browse_output_folder_button.isVisible()
    assert page.set_default_folder_button.isVisible()
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
    assert buttons["HEIC -> JPG"].isEnabled()
    buttons["HEIC -> JPG"].click()
    assert window.stack.currentIndex() == 3
