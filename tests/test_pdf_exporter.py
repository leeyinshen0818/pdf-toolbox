from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from pdf_toolbox.core.image_collection import ImageCollection
from pdf_toolbox.core.pdf_exporter import PdfExportError, PdfExporter


def make_rgb(path: Path, size=(20, 12), color=(255, 0, 0)) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def make_transparent_png(path: Path) -> Path:
    image = Image.new("RGBA", (10, 10), (255, 255, 255, 0))
    for x in range(5):
        for y in range(10):
            image.putpixel((x, y), (255, 0, 0, 255))
    image.save(path)
    return path


def entries_for(paths: list[Path]):
    collection = ImageCollection()
    result = collection.add_paths(paths)
    assert not result.rejected
    return collection.entries


def page_center_color(document: pymupdf.Document, page_index: int) -> tuple[int, int, int]:
    page = document[page_index]
    pixmap = page.get_pixmap(alpha=False)
    return pixmap.pixel(pixmap.width // 2, pixmap.height // 2)[:3]


def assert_close_color(actual: tuple[int, int, int], expected: tuple[int, int, int], tolerance: int = 3) -> None:
    assert all(abs(channel - target) <= tolerance for channel, target in zip(actual, expected))


def test_pdf_output_created_successfully(tmp_path: Path) -> None:
    image = make_rgb(tmp_path / "image.jpg")
    output = tmp_path / "output.pdf"

    result = PdfExporter().export(entries_for([image]), output)

    assert result == output
    assert output.exists()
    with pymupdf.open(output) as document:
        assert document.page_count == 1


def test_multiple_images_exported_in_correct_order(tmp_path: Path) -> None:
    red = make_rgb(tmp_path / "red.png", color=(255, 0, 0))
    green = make_rgb(tmp_path / "green.jpg", color=(0, 255, 0))
    blue = make_rgb(tmp_path / "blue.jpeg", color=(0, 0, 255))
    output = tmp_path / "ordered.pdf"

    PdfExporter().export(entries_for([red, green, blue]), output)

    with pymupdf.open(output) as document:
        assert document.page_count == 3
        assert_close_color(page_center_color(document, 0), (255, 0, 0))
        assert_close_color(page_center_color(document, 1), (0, 255, 0))
        assert_close_color(page_center_color(document, 2), (0, 0, 255))


def test_export_uses_image_dimensions_as_page_size(tmp_path: Path) -> None:
    image = make_rgb(tmp_path / "wide.png", size=(31, 17), color=(20, 40, 60))
    output = tmp_path / "sized.pdf"

    PdfExporter().export(entries_for([image]), output)

    with pymupdf.open(output) as document:
        rect = document[0].rect
        assert rect.width == pytest.approx(31)
        assert rect.height == pytest.approx(17)


def test_transparent_png_is_flattened_onto_white(tmp_path: Path) -> None:
    transparent = make_transparent_png(tmp_path / "transparent.png")
    output = tmp_path / "transparent.pdf"

    PdfExporter().export(entries_for([transparent]), output)

    with pymupdf.open(output) as document:
        pixmap = document[0].get_pixmap(alpha=False)
        assert pixmap.pixel(2, 5)[:3] == (255, 0, 0)
        assert pixmap.pixel(8, 5)[:3] == (255, 255, 255)


def test_missing_source_image_is_handled(tmp_path: Path) -> None:
    image = make_rgb(tmp_path / "image.png")
    entries = entries_for([image])
    image.unlink()

    with pytest.raises(PdfExportError, match="File no longer exists"):
        PdfExporter().export(entries, tmp_path / "missing.pdf")


def test_output_file_already_exists_is_handled(tmp_path: Path) -> None:
    image = make_rgb(tmp_path / "image.png")
    output = tmp_path / "exists.pdf"
    output.write_bytes(b"existing")

    with pytest.raises(PdfExportError, match="already exists"):
        PdfExporter().export(entries_for([image]), output)


def test_empty_export_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(PdfExportError, match="at least one image"):
        PdfExporter().export([], tmp_path / "empty.pdf")
