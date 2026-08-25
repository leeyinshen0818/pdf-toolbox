from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication, QLabel

from pdf_toolbox.ui.image_to_pdf_page import ImageToPdfPage


@pytest.fixture(scope="module")
def app() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def make_image(path: Path, size=(470, 311)) -> Path:
    Image.new("RGB", size, (80, 120, 180)).save(path)
    return path


def row_texts(page: ImageToPdfPage, row: int) -> list[str]:
    widget = page.image_list.itemWidget(page.image_list.item(row))
    assert widget is not None
    return [label.text() for label in widget.findChildren(QLabel)]


def test_imported_image_details_render_immediately(app: QApplication, tmp_path: Path) -> None:
    image = make_image(tmp_path / "photo.png")
    page = ImageToPdfPage()

    page._add_images([str(image)])
    app.processEvents()

    assert page.image_list.count() == 1
    texts = row_texts(page, 0)
    assert "photo.png" in texts
    assert "470 × 311 px" in texts


def test_batch_import_and_reorder_keep_row_details(app: QApplication, tmp_path: Path) -> None:
    first = make_image(tmp_path / "first.jpg", size=(100, 200))
    second = make_image(tmp_path / "second.png", size=(300, 150))
    page = ImageToPdfPage()

    page._add_images([str(first), str(second)])
    page.collection.reorder_by_paths([second, first])
    page._sync_list_from_collection()
    app.processEvents()

    assert page.image_list.count() == 2
    assert "second.png" in row_texts(page, 0)
    assert "300 × 150 px" in row_texts(page, 0)
    assert "first.jpg" in row_texts(page, 1)
    assert "100 × 200 px" in row_texts(page, 1)
