from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from pdf_toolbox.core.image_collection import ImageCollection
from pdf_toolbox.core.image_validation import ImageValidationError, validate_image_file


def make_image(path: Path, mode: str = "RGB", color=(255, 0, 0)) -> Path:
    Image.new(mode, (12, 8), color).save(path)
    return path


@pytest.mark.parametrize(
    ("filename", "expected_format"),
    [
        ("photo.jpg", "JPEG"),
        ("photo.jpeg", "JPEG"),
        ("photo.png", "PNG"),
    ],
)
def test_supported_image_types_are_accepted(tmp_path: Path, filename: str, expected_format: str) -> None:
    path = make_image(tmp_path / filename)

    info = validate_image_file(path)

    assert info.filename == filename
    assert info.format == expected_format
    assert (info.width, info.height) == (12, 8)


def test_unsupported_files_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("not an image", encoding="utf-8")

    with pytest.raises(ImageValidationError, match="Unsupported file type"):
        validate_image_file(path)


def test_corrupted_image_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.png"
    path.write_bytes(b"this is not a real png")

    with pytest.raises(ImageValidationError, match="readable image"):
        validate_image_file(path)


def test_image_collection_preserves_explicit_order(tmp_path: Path) -> None:
    first = make_image(tmp_path / "first.jpg")
    second = make_image(tmp_path / "second.png")
    third = make_image(tmp_path / "third.jpeg")

    collection = ImageCollection()
    result = collection.add_paths([first, second, third])

    assert len(result.added) == 3
    assert [entry.path for entry in collection.entries] == [first, second, third]

    collection.reorder_by_paths([third, first, second])

    assert [entry.path for entry in collection.entries] == [third, first, second]


def test_duplicate_images_are_not_added(tmp_path: Path) -> None:
    path = make_image(tmp_path / "one.png")
    collection = ImageCollection()

    first = collection.add_paths([path])
    second = collection.add_paths([path])

    assert len(first.added) == 1
    assert len(second.added) == 0
    assert second.duplicates == (path,)
    assert len(collection.entries) == 1
