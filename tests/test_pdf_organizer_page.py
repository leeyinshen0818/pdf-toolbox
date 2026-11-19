from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from pdf_toolbox.core.output_location import OpenLocationResult
from pdf_toolbox.core.pdf_to_image import PdfInfo
from pdf_toolbox.core.pdf_organizer import pdf_key
from pdf_toolbox.ui.components.widgets import thumbnail_placeholder
from pdf_toolbox.ui.pdf_organizer_page import PAGE_ID_ROLE, THUMBNAIL_SIZE, PdfOrganizerPage


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


def fake_info(path: Path, page_count: int) -> PdfInfo:
    path.write_bytes(b"%PDF fake for organizer ui")
    return PdfInfo(path, path.name, page_count, path.stat().st_size)


def load_fake_workspace(page: PdfOrganizerPage, tmp_path: Path) -> None:
    first = fake_info(tmp_path / "first.pdf", 2)
    second = fake_info(tmp_path / "second.pdf", 1)
    page.workspace.add_pdf(first)
    page.workspace.add_pdf(second)
    page._rebuild_grid()
    page._update_info()
    page._update_state()


def test_organizer_empty_state_and_toolbar_defaults(app: QApplication) -> None:
    page = PdfOrganizerPage()
    labels = [label.text() for label in page.empty_state.findChildren(type(page.info_label))]

    assert "Add PDFs to start organizing pages" in labels
    assert page.add_button.text() == "Add PDFs"
    assert page.add_button.objectName() == "PrimaryButton"
    assert page.export_button.text() == "Export PDF"
    assert page.export_button.objectName() == "PrimaryButton"
    assert page.delete_button.objectName() != "PrimaryButton"
    assert not page.export_button.isEnabled()
    assert not page.delete_button.isEnabled()
    assert page.stack.currentWidget() == page.empty_state


def test_organizer_grid_shows_all_pages_with_source_metadata(app: QApplication, tmp_path: Path) -> None:
    page = PdfOrganizerPage()
    load_fake_workspace(page, tmp_path)

    assert page.page_grid.count() == 3
    assert page.stack.currentWidget() == page.page_grid
    assert page.info_label.text().startswith("2 PDFs loaded - 3 pages")
    assert page.page_grid.item(2).data(PAGE_ID_ROLE) == page.workspace.pages[2].page_id
    card = page.page_grid.itemWidget(page.page_grid.item(2))
    labels = [label.text() for label in card.findChildren(QLabel)]
    assert "Page 3" in labels
    assert "second.pdf \u00b7 page 1" in labels


def test_reorder_updates_workspace_order(app: QApplication, tmp_path: Path) -> None:
    page = PdfOrganizerPage()
    load_fake_workspace(page, tmp_path)
    before = page.workspace.page_ids()
    after = [before[2], before[0], before[1]]

    page._on_order_changed(before, after)

    assert page.workspace.page_ids() == after
    assert [(item.data(PAGE_ID_ROLE)) for item in [page.page_grid.item(i) for i in range(3)]] == after


def test_delete_duplicate_rotate_and_undo_redo_from_selection(app: QApplication, tmp_path: Path) -> None:
    page = PdfOrganizerPage()
    load_fake_workspace(page, tmp_path)
    first_id = page.workspace.pages[0].page_id
    page.page_grid.item(0).setSelected(True)

    page._duplicate_selected()
    assert len(page.workspace.pages) == 4
    duplicated_id = page.workspace.pages[1].page_id
    assert page.workspace.pages[1].duplicate_of == first_id

    page.page_grid.clearSelection()
    page.page_grid.item(1).setSelected(True)
    page._rotate_selected(90)
    assert page.workspace.pages[1].rotation == 90

    page._delete_selected()
    assert all(workspace_page.page_id != duplicated_id for workspace_page in page.workspace.pages)

    page._undo()
    assert any(workspace_page.page_id == duplicated_id for workspace_page in page.workspace.pages)
    page._undo()
    assert page.workspace.pages[1].rotation == 0
    page._redo()
    assert page.workspace.pages[1].rotation == 90


def test_thumbnail_requests_skip_cached_duplicate_pages(app: QApplication, tmp_path: Path) -> None:
    page = PdfOrganizerPage()
    source = fake_info(tmp_path / "source.pdf", 1)
    page.workspace.add_pdf(source)
    original = page.workspace.pages[0]
    page.thumbnail_cache[original.thumbnail_key] = thumbnail_placeholder("Cached", THUMBNAIL_SIZE)
    page.workspace.duplicate_pages({original.page_id})

    assert page._selected_page_ids() == set()
    requests = tuple(
        workspace_page.thumbnail_key
        for workspace_page in page.workspace.pages
        if workspace_page.thumbnail_key not in page.thumbnail_cache
    )
    assert requests == ()


def test_export_success_opens_output_location(app: QApplication, tmp_path: Path) -> None:
    page = PdfOrganizerPage()
    output = tmp_path / "organized.pdf"
    output.write_bytes(b"%PDF")
    calls: list[tuple[Path, bool]] = []
    page.open_output_location = lambda path, reveal=False: calls.append((Path(path), reveal)) or OpenLocationResult(True)

    page._on_export_finished(str(output))

    assert calls == [(output, True)]
    assert page.status_label.text() == "Organized PDF exported successfully."


def test_loading_duplicate_source_does_not_add_pages(app: QApplication, tmp_path: Path) -> None:
    page = PdfOrganizerPage()
    info = fake_info(tmp_path / "source.pdf", 1)

    page.workspace.add_pdf(info)
    duplicate = page.workspace.add_pdf(info)

    assert duplicate == []
    assert len(page.workspace.loaded_sources) == 1
    assert pdf_key(info.path) in page.workspace.loaded_sources


def selected_ids(page: PdfOrganizerPage) -> set[str]:
    return {item.data(PAGE_ID_ROLE) for item in page.page_grid.selectedItems()}


def load_pages(page: PdfOrganizerPage, tmp_path: Path, count: int) -> list[str]:
    page.workspace.add_pdf(fake_info(tmp_path / "pages.pdf", count))
    page._rebuild_grid()
    page._update_info()
    page._update_state()
    return page.workspace.page_ids()


def test_alt_left_and_right_move_selected_pages_and_keep_them_selected(app: QApplication, tmp_path: Path) -> None:
    page = PdfOrganizerPage()
    ids = load_pages(page, tmp_path, 5)
    page.page_grid.item(1).setSelected(True)
    page.page_grid.item(2).setSelected(True)

    QTest.keyClick(page.page_grid, Qt.Key_Right, Qt.AltModifier)

    assert page.workspace.page_ids() == [ids[0], ids[3], ids[1], ids[2], ids[4]]
    assert page.page_grid.page_ids() == page.workspace.page_ids()
    assert selected_ids(page) == {ids[1], ids[2]}

    QTest.keyClick(page.page_grid, Qt.Key_Left, Qt.AltModifier)
    QTest.keyClick(page.page_grid, Qt.Key_Left, Qt.AltModifier)

    assert page.workspace.page_ids() == [ids[1], ids[2], ids[0], ids[3], ids[4]]
    assert selected_ids(page) == {ids[1], ids[2]}

    QTest.keyClick(page.page_grid, Qt.Key_Left, Qt.AltModifier)  # already first: nothing changes
    assert page.workspace.page_ids() == [ids[1], ids[2], ids[0], ids[3], ids[4]]

    page._undo()  # each move is its own undo step
    assert page.workspace.page_ids() == ids


def test_escape_during_a_card_drag_leaves_the_order_unchanged(app: QApplication, tmp_path: Path) -> None:
    page = PdfOrganizerPage()
    page.resize(1200, 800)
    page.show()
    ids = load_pages(page, tmp_path, 6)
    app.processEvents()
    grid = page.page_grid
    changes: list[tuple[list, list]] = []
    grid.order_changed.connect(lambda before, after: changes.append((before, after)))
    last = grid.card_rects()[-1]
    end_of_grid = QPoint(int(last[2]) + 4, int((last[1] + last[3]) / 2))

    grid.start_card_drag(grid.item(0), QPoint(10, 10))
    grid.update_card_drag(end_of_grid)
    assert grid.is_dragging()
    QTest.keyClick(grid, Qt.Key_Escape)
    grid.finish_card_drag(end_of_grid)  # the release that follows Esc must not drop

    assert not grid.is_dragging()
    assert changes == []
    assert page.workspace.page_ids() == ids

    # Without Esc the same drag does move the page to the end.
    grid.start_card_drag(grid.item(0), QPoint(10, 10))
    grid.finish_card_drag(end_of_grid)
    assert page.workspace.page_ids() == ids[1:] + ids[:1]
