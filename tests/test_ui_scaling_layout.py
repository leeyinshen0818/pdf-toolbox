from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QScrollArea

from pdf_toolbox.app import ensure_window_starts_maximized
from pdf_toolbox.ui.components.drop_area import EmptyState
from pdf_toolbox.ui.image_to_jpg_page import FORMAT_BADGES, ConvertToJpgPage
from pdf_toolbox.ui.image_to_pdf_page import ImageToPdfPage
from pdf_toolbox.ui import main_window as main_window_module
from pdf_toolbox.ui.main_window import MainWindow, effective_minimum_size
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
    assert organizer_page.export_button.isVisible()

    window.stack.setCurrentIndex(3)
    app.processEvents()
    jpg_page = window.stack.widget(3)
    assert jpg_page.convert_button.text() == "Convert"
    assert jpg_page.browse_output_folder_button.isVisible()


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

    jpg_page = ConvertToJpgPage()
    assert isinstance(jpg_page.content_layout, QHBoxLayout)
    assert jpg_page.content_layout.count() == 3
    assert jpg_page.content_layout.itemAt(0).widget() is jpg_page.list_section
    assert jpg_page.content_layout.itemAt(1).widget() is jpg_page.preview_section
    assert jpg_page.content_layout.itemAt(2).widget() is jpg_page.settings_panel
    assert not hasattr(jpg_page, "_apply_responsive_layout")
    assert not hasattr(jpg_page, "_layout_mode")


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
    page = ConvertToJpgPage()
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


def test_pdf_organizer_toolbar_is_one_row_and_export_is_in_the_footer(app: QApplication) -> None:
    window = MainWindow()
    window.resize(1366, 768)
    window.stack.setCurrentIndex(2)
    window.show()
    app.processEvents()
    page = window.stack.widget(2)
    toolbar = page.layout().itemAt(2).layout()

    assert isinstance(toolbar, QHBoxLayout)
    assert not toolbar.hasHeightForWidth()
    buttons = [
        page.add_button,
        page.rotate_left_button,
        page.rotate_right_button,
        page.duplicate_button,
        page.delete_button,
        page.undo_button,
        page.redo_button,
        page.clear_button,
    ]
    assert all(button.isVisible() for button in buttons)
    assert all(toolbar.indexOf(button) >= 0 for button in buttons)
    assert toolbar.indexOf(page.export_button) == -1
    assert page.export_button.isVisible()
    assert page_y(page, page.export_button) > page_y(page, page.page_grid.parentWidget())


def test_pdf_organizer_navigation_is_enabled(app: QApplication) -> None:
    window = MainWindow()
    buttons = {button.text(): button for button in window.findChildren(QPushButton)}

    assert buttons["PDF Organizer"].isEnabled()
    buttons["PDF Organizer"].click()
    assert window.stack.currentIndex() == 2
    assert buttons["Convert to JPG"].isEnabled()
    buttons["Convert to JPG"].click()
    assert window.stack.currentIndex() == 3


@pytest.mark.parametrize("page_type", [ImageToPdfPage, PdfToImagePage, PdfOrganizerPage, ConvertToJpgPage])
def test_every_page_fits_a_600px_tall_work_area(app: QApplication, page_type) -> None:
    page = page_type()

    assert page.minimumSizeHint().height() <= 600

def assert_empty_state_fits(state) -> None:
    """Visible parts lie inside the empty state at full height, top to bottom in this order, apart:
    heading, hint, badges, button, caption."""
    parts = [state.headline, state.hint, state.format_badges, state.button, state.caption]
    visible = [part for part in parts if part is not None and part.isVisible()]
    previous_bottom = None
    for part in visible:
        geometry = QRect(part.mapTo(state, QPoint(0, 0)), part.size())
        assert state.rect().contains(geometry), part.objectName()
        needed = part.heightForWidth(geometry.width()) if part.hasHeightForWidth() else part.sizeHint().height()
        assert geometry.height() >= needed, part.objectName()
        if previous_bottom is not None:
            assert geometry.top() > previous_bottom, part.objectName()
        previous_bottom = geometry.bottom()
    assert state.button.width() >= state.button.sizeHint().width()
    if state.format_badges is not None and state.format_badges.isVisible():
        assert_badges_fit(state.format_badges)


def assert_badges_fit(container) -> None:
    """Badges are equal-size, fully inside their container, large enough for their label, and apart."""
    rects = [badge.geometry() for badge in container.badges]
    assert len({(rect.width(), rect.height()) for rect in rects}) == 1
    for badge, rect in zip(container.badges, rects):
        assert container.rect().contains(rect), badge.label
        natural = badge.natural_size()
        assert rect.width() >= natural.width() and rect.height() >= natural.height(), badge.label
    for first in range(len(rects)):
        for second in range(first + 1, len(rects)):
            assert not rects[first].intersects(rects[second])


# The minimum window plus the desktop sizes used above; the screen-relative UI scale keeps the
# logical window at or above these sizes at 100%/125%/150% Windows scaling.
@pytest.mark.parametrize("width,height", [(960, 640), (1280, 720), (1366, 768), (1920, 1080), (2560, 1440)])
def test_convert_to_jpg_empty_state_fits_without_clipping(app: QApplication, width: int, height: int) -> None:
    window = MainWindow()
    window.resize(width, height)
    window.stack.setCurrentIndex(3)
    window.show()
    app.processEvents()
    state = window.stack.widget(3).empty_state.findChild(EmptyState)

    assert_empty_state_fits(state)
    if height >= 720:
        assert state.format_badges.isVisible() and state.caption.isVisible()


@pytest.mark.parametrize("extra_width,stacked", [(-1, True), (0, False)])
def test_convert_to_jpg_badges_stack_only_when_the_row_does_not_fit(
    app: QApplication, extra_width: int, stacked: bool
) -> None:
    state = EmptyState("Heading", None, "Add", format_badges=FORMAT_BADGES, caption="Caption")
    badges = state.format_badges
    margins = state.layout().contentsMargins()
    state.resize(badges.row_width() + extra_width + margins.left() + margins.right(), 1000)
    state.show()
    app.processEvents()

    assert badges.is_stacked() is stacked
    tops = {badge.geometry().top() for badge in badges.badges}
    assert len(tops) == (len(badges.badges) if stacked else 1)
    assert_empty_state_fits(state)


def test_convert_to_jpg_empty_state_fits_at_page_minimum_size(app: QApplication) -> None:
    page = ConvertToJpgPage()
    page.resize(page.minimumSizeHint())
    page.show()
    app.processEvents()

    assert_empty_state_fits(page.empty_state.findChild(EmptyState))


def test_window_minimum_fits_every_page_without_overlapping_panels(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The offscreen test screen is 800x800; give the window a 4K work area so the clamp stays out of the way.
    monkeypatch.setattr(main_window_module, "available_screen_size", lambda _window: QSize(3840, 2160))
    window = MainWindow()
    window.show()
    app.processEvents()

    for index, page in enumerate(window._pages()):
        window.stack.setCurrentIndex(index)
        app.processEvents()
        window.resize(window.minimumSize())
        app.processEvents()

        sidebar = effective_minimum_size(window.sidebar)
        page_minimum = effective_minimum_size(page)
        assert window.minimumWidth() >= sidebar.width() + page_minimum.width()
        assert window.minimumHeight() >= max(sidebar.height(), page_minimum.height())
        assert page.width() >= page_minimum.width() and page.height() >= page_minimum.height()

        layout = page.content_layout
        panels = [layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget() is not None]
        rects = [QRect(panel.mapTo(page, QPoint(0, 0)), panel.size()) for panel in panels if panel.isVisible()]
        for panel, rect in zip(panels, rects):
            assert page.rect().contains(rect), type(page).__name__
            assert panel.width() >= effective_minimum_size(panel).width(), type(page).__name__
        for first in range(len(rects)):
            for second in range(first + 1, len(rects)):
                assert not rects[first].intersects(rects[second]), type(page).__name__
        if isinstance(page, ConvertToJpgPage):
            assert_empty_state_fits(page.empty_state.findChild(EmptyState))
