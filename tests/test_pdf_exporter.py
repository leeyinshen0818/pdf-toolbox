from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from pdf_toolbox.core.image_collection import ImageCollection
from pdf_toolbox.core.image_corrections import CorrectionSettings, SharpnessPreset, TonePreset
from pdf_toolbox.core.pdf_exporter import PdfExportError, PdfExporter
from pdf_toolbox.core.pdf_geometry import (
    A4_PORTRAIT,
    LETTER_PORTRAIT,
    ExportSettings,
    MarginPreset,
    PageOrientation,
    PageSizeMode,
    calculate_page_layout,
)


def make_rgb(path: Path, size=(120, 80), color=(255, 0, 0)) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def make_split_image(path: Path, size=(300, 100)) -> Path:
    image = Image.new("RGB", size)
    for x in range(size[0]):
        color = (255, 0, 0) if x < size[0] // 2 else (0, 0, 255)
        for y in range(size[1]):
            image.putpixel((x, y), color)
    image.save(path)
    return path


def make_transparent_png(path: Path, size=(200, 200)) -> Path:
    image = Image.new("RGBA", size, (255, 255, 255, 0))
    for x in range(size[0] // 2):
        for y in range(size[1]):
            image.putpixel((x, y), (255, 0, 0, 255))
    image.save(path)
    return path


def collection_for(paths: list[Path]) -> ImageCollection:
    collection = ImageCollection()
    result = collection.add_paths(paths)
    assert not result.rejected
    return collection


def entries_for(paths: list[Path]):
    return collection_for(paths).entries


def assert_close_color(actual: tuple[int, int, int], expected: tuple[int, int, int], tolerance: int = 3) -> None:
    assert all(abs(channel - target) <= tolerance for channel, target in zip(actual, expected))


def assert_page_size(page: pymupdf.Page, width: float, height: float) -> None:
    assert page.rect.width == pytest.approx(width, abs=0.01)
    assert page.rect.height == pytest.approx(height, abs=0.01)


def assert_rect_close(actual: pymupdf.Rect, expected: pymupdf.Rect) -> None:
    assert actual.x0 == pytest.approx(expected.x0, abs=0.01)
    assert actual.y0 == pytest.approx(expected.y0, abs=0.01)
    assert actual.x1 == pytest.approx(expected.x1, abs=0.01)
    assert actual.y1 == pytest.approx(expected.y1, abs=0.01)


def placed_image_rect(page: pymupdf.Page) -> pymupdf.Rect:
    images = page.get_images()
    assert len(images) == 1
    rects = page.get_image_rects(images[0][0])
    assert len(rects) == 1
    return rects[0]


def embedded_image_size(page: pymupdf.Page) -> tuple[int, int]:
    image = page.get_images()[0]
    return image[2], image[3]


def sample_page(page: pymupdf.Page, x_fraction: float, y_fraction: float = 0.5) -> tuple[int, int, int]:
    pixmap = page.get_pixmap(alpha=False)
    x = min(pixmap.width - 1, max(0, int(pixmap.width * x_fraction)))
    y = min(pixmap.height - 1, max(0, int(pixmap.height * y_fraction)))
    return pixmap.pixel(x, y)[:3]


def test_pdf_output_created_successfully_with_default_fit(tmp_path: Path) -> None:
    image = make_rgb(tmp_path / "image.jpg")
    output = tmp_path / "output.pdf"

    result = PdfExporter().export(entries_for([image]), output)

    assert result == output
    assert output.exists()
    with pymupdf.open(output) as document:
        assert document.page_count == 1
        expected = calculate_page_layout(120, 80)
        assert_page_size(document[0], expected.page_size.width, expected.page_size.height)
        assert_rect_close(placed_image_rect(document[0]), document[0].rect)


def test_fit_no_margin_embeds_original_pixel_dimensions(tmp_path: Path) -> None:
    image = make_rgb(tmp_path / "image.png", size=(321, 123), color=(10, 20, 30))
    output = tmp_path / "fit.pdf"

    PdfExporter().export(entries_for([image]), output)

    with pymupdf.open(output) as document:
        assert embedded_image_size(document[0]) == (321, 123)
        assert_rect_close(placed_image_rect(document[0]), document[0].rect)


def test_multiple_images_exported_in_correct_order(tmp_path: Path) -> None:
    red = make_rgb(tmp_path / "red.png", color=(255, 0, 0))
    green = make_rgb(tmp_path / "green.jpg", color=(0, 255, 0))
    blue = make_rgb(tmp_path / "blue.jpeg", color=(0, 0, 255))
    output = tmp_path / "ordered.pdf"

    PdfExporter().export(entries_for([red, green, blue]), output)

    with pymupdf.open(output) as document:
        assert document.page_count == 3
        assert_close_color(sample_page(document[0], 0.5), (255, 0, 0))
        assert_close_color(sample_page(document[1], 0.5), (0, 255, 0))
        assert_close_color(sample_page(document[2], 0.5), (0, 0, 255))


def test_fit_pages_may_have_different_dimensions(tmp_path: Path) -> None:
    wide = make_rgb(tmp_path / "wide.png", size=(400, 100), color=(255, 0, 0))
    tall = make_rgb(tmp_path / "tall.png", size=(100, 400), color=(0, 255, 0))
    output = tmp_path / "fit-different.pdf"

    PdfExporter().export(entries_for([wide, tall]), output)

    with pymupdf.open(output) as document:
        assert document[0].rect.width > document[0].rect.height
        assert document[1].rect.height > document[1].rect.width
        assert document[0].rect != document[1].rect


@pytest.mark.parametrize(
    ("filename", "size"),
    [
        ("portrait.png", (800, 1200)),
        ("landscape.png", (1200, 800)),
        ("square.png", (900, 900)),
    ],
)
def test_fit_export_preserves_portrait_landscape_and_square_geometry(
    tmp_path: Path,
    filename: str,
    size: tuple[int, int],
) -> None:
    image = make_rgb(tmp_path / filename, size=size)
    output = tmp_path / f"{Path(filename).stem}.pdf"

    PdfExporter().export(
        entries_for([image]),
        output,
        settings=ExportSettings(page_size=PageSizeMode.FIT, orientation=PageOrientation.LANDSCAPE),
    )

    with pymupdf.open(output) as document:
        page = document[0]
        assert page.rect.width / page.rect.height == pytest.approx(size[0] / size[1])
        assert_rect_close(placed_image_rect(page), page.rect)


def test_a4_pages_remain_consistent_when_selected(tmp_path: Path) -> None:
    small = make_rgb(tmp_path / "small.png", size=(40, 20), color=(255, 0, 0))
    tall = make_rgb(tmp_path / "tall.jpg", size=(200, 900), color=(0, 255, 0))
    output = tmp_path / "a4.pdf"

    PdfExporter().export(
        entries_for([small, tall]),
        output,
        settings=ExportSettings(page_size=PageSizeMode.A4),
    )

    with pymupdf.open(output) as document:
        for page in document:
            assert_page_size(page, A4_PORTRAIT.width, A4_PORTRAIT.height)


def test_letter_pages_remain_consistent_when_selected(tmp_path: Path) -> None:
    small = make_rgb(tmp_path / "small.png", size=(40, 20), color=(255, 0, 0))
    wide = make_rgb(tmp_path / "wide.jpeg", size=(1200, 300), color=(0, 0, 255))
    output = tmp_path / "letter.pdf"

    PdfExporter().export(
        entries_for([small, wide]),
        output,
        settings=ExportSettings(page_size=PageSizeMode.LETTER),
    )

    with pymupdf.open(output) as document:
        for page in document:
            assert_page_size(page, LETTER_PORTRAIT.width, LETTER_PORTRAIT.height)


def test_landscape_orientation_for_fixed_page_size(tmp_path: Path) -> None:
    image = make_rgb(tmp_path / "image.png")
    output = tmp_path / "landscape.pdf"

    PdfExporter().export(
        entries_for([image]),
        output,
        settings=ExportSettings(page_size=PageSizeMode.A4, orientation=PageOrientation.LANDSCAPE),
    )

    with pymupdf.open(output) as document:
        assert_page_size(document[0], A4_PORTRAIT.height, A4_PORTRAIT.width)


def test_letter_landscape_orientation_for_fixed_page_size(tmp_path: Path) -> None:
    image = make_rgb(tmp_path / "image.png")
    output = tmp_path / "letter-landscape.pdf"

    PdfExporter().export(
        entries_for([image]),
        output,
        settings=ExportSettings(page_size=PageSizeMode.LETTER, orientation=PageOrientation.LANDSCAPE),
    )

    with pymupdf.open(output) as document:
        assert_page_size(document[0], LETTER_PORTRAIT.height, LETTER_PORTRAIT.width)


def test_margins_keep_image_uncropped_inside_page(tmp_path: Path) -> None:
    image = make_rgb(tmp_path / "image.png", size=(300, 300))
    output = tmp_path / "margin.pdf"

    PdfExporter().export(
        entries_for([image]),
        output,
        settings=ExportSettings(page_size=PageSizeMode.A4, margin=MarginPreset.BIG),
    )

    with pymupdf.open(output) as document:
        rect = placed_image_rect(document[0])
        assert rect.x0 > 0
        assert rect.y0 > 0
        assert rect.x1 < document[0].rect.width
        assert rect.y1 < document[0].rect.height


def test_transparent_png_is_flattened_onto_white(tmp_path: Path) -> None:
    transparent = make_transparent_png(tmp_path / "transparent.png")
    output = tmp_path / "transparent.pdf"

    PdfExporter().export(entries_for([transparent]), output)

    with pymupdf.open(output) as document:
        assert_close_color(sample_page(document[0], 0.25), (255, 0, 0))
        assert_close_color(sample_page(document[0], 0.75), (255, 255, 255))


def test_tone_correction_is_applied_to_export(tmp_path: Path) -> None:
    image = make_rgb(tmp_path / "dim.png", size=(100, 100), color=(90, 90, 90))
    output = tmp_path / "bright.pdf"
    collection = collection_for([image])
    collection.update_corrections(image, CorrectionSettings(tone=TonePreset.BRIGHT_20))

    PdfExporter().export(collection.entries, output)

    with pymupdf.open(output) as document:
        assert sample_page(document[0], 0.5)[0] > 90


def test_original_source_file_is_not_modified_by_corrections(tmp_path: Path) -> None:
    image = make_split_image(tmp_path / "source.png")
    original_bytes = image.read_bytes()
    output = tmp_path / "corrected.pdf"
    collection = collection_for([image])
    collection.update_corrections(
        image,
        CorrectionSettings(
            sharpness=SharpnessPreset.SHARPER,
            tone=TonePreset.STRONG,
        ),
    )

    PdfExporter().export(collection.entries, output)

    assert image.read_bytes() == original_bytes


def test_missing_source_image_is_handled(tmp_path: Path) -> None:
    image = make_rgb(tmp_path / "image.png")
    entries = entries_for([image])
    image.unlink()

    with pytest.raises(PdfExportError, match="source file could not be found"):
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
