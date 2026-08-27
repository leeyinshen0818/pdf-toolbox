from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from pillow_heif import register_heif_opener

from pdf_toolbox.core.heic_to_jpg import (
    HeicCollection,
    HeicConversionCancelled,
    HeicConversionError,
    HeicImageEntry,
    HeicJpgSettings,
    HeicLoadError,
    HeicToJpgService,
)
from pdf_toolbox.core.pdf_to_image import JpgQuality


register_heif_opener()


def make_heic(path: Path, size: tuple[int, int] = (32, 24), color=(80, 120, 180)) -> Path:
    Image.new("RGB", size, color).save(path, format="HEIF")
    return path


def make_heif(path: Path, size: tuple[int, int] = (32, 24), color=(80, 120, 180)) -> Path:
    Image.new("RGB", size, color).save(path, format="HEIF")
    return path


def entries_for(paths: list[Path]) -> tuple[HeicImageEntry, ...]:
    service = HeicToJpgService()
    collection = HeicCollection()
    result = collection.add_paths(paths, service)
    assert not result.rejected
    return collection.entries


def test_valid_heic_accepted(tmp_path: Path) -> None:
    path = make_heic(tmp_path / "photo.heic", size=(40, 30))

    info = HeicToJpgService().load_image_info(path)

    assert info.filename == "photo.heic"
    assert (info.width, info.height) == (40, 30)


def test_valid_heif_accepted(tmp_path: Path) -> None:
    path = make_heif(tmp_path / "photo.heif", size=(30, 40))

    info = HeicToJpgService().load_image_info(path)

    assert info.filename == "photo.heif"
    assert (info.width, info.height) == (30, 40)


def test_missing_corrupted_and_masquerading_files_rejected(tmp_path: Path) -> None:
    service = HeicToJpgService()
    corrupted = tmp_path / "broken.heic"
    corrupted.write_bytes(b"not an image")
    masquerading = tmp_path / "fake.heic"
    Image.new("RGB", (10, 10)).save(masquerading, format="PNG")

    with pytest.raises(HeicLoadError, match="source file could not be found"):
        service.load_image_info(tmp_path / "missing.heic")
    with pytest.raises(HeicLoadError, match="could not be opened"):
        service.load_image_info(corrupted)
    with pytest.raises(HeicLoadError, match="not a supported"):
        service.load_image_info(masquerading)


def test_duplicate_file_rejected(tmp_path: Path) -> None:
    path = make_heic(tmp_path / "photo.heic")
    service = HeicToJpgService()
    collection = HeicCollection()

    first = collection.add_paths([path], service)
    second = collection.add_paths([path], service)

    assert len(first.added) == 1
    assert second.duplicates == (path,)
    assert len(collection.entries) == 1


def test_one_heic_converts_to_jpg_with_dimensions_and_rgb(tmp_path: Path) -> None:
    source = make_heic(tmp_path / "photo.heic", size=(64, 48), color=(200, 100, 50))

    outputs = HeicToJpgService().convert_entries(entries_for([source]), tmp_path, HeicJpgSettings())

    assert [path.name for path in outputs] == ["photo.jpg"]
    with Image.open(outputs[0]) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.size == (64, 48)


def test_multiple_heics_convert_in_order_and_source_unchanged(tmp_path: Path) -> None:
    first = make_heic(tmp_path / "first.heic", size=(20, 30))
    second = make_heif(tmp_path / "second.heif", size=(40, 25))
    before = first.read_bytes()

    outputs = HeicToJpgService().convert_entries(entries_for([first, second]), tmp_path, HeicJpgSettings())

    assert [path.name for path in outputs] == ["first.jpg", "second.jpg"]
    assert first.read_bytes() == before
    with Image.open(outputs[0]) as portrait, Image.open(outputs[1]) as landscape:
        assert portrait.height > portrait.width
        assert landscape.width > landscape.height


def test_maximum_quality_path_uses_jpg_output(tmp_path: Path) -> None:
    source = make_heic(tmp_path / "quality.heic")

    outputs = HeicToJpgService().convert_entries(
        entries_for([source]),
        tmp_path,
        HeicJpgSettings(jpg_quality=JpgQuality.MAXIMUM),
    )

    assert outputs[0].suffix == ".jpg"
    assert outputs[0].exists()


def test_collision_safe_naming_for_heic_outputs(tmp_path: Path) -> None:
    source = make_heic(tmp_path / "photo.heic")
    (tmp_path / "photo.jpg").write_bytes(b"existing")
    (tmp_path / "photo_1.jpg").write_bytes(b"existing")

    outputs = HeicToJpgService().convert_entries(entries_for([source]), tmp_path, HeicJpgSettings())

    assert outputs[0].name == "photo_2.jpg"


def test_same_base_filename_from_different_folders_uses_collision_safe_names(tmp_path: Path) -> None:
    first_dir = tmp_path / "one"
    second_dir = tmp_path / "two"
    first_dir.mkdir()
    second_dir.mkdir()
    first = make_heic(first_dir / "photo.heic")
    second = make_heic(second_dir / "photo.heic")

    outputs = HeicToJpgService().convert_entries(entries_for([first, second]), tmp_path, HeicJpgSettings())

    assert [path.name for path in outputs] == ["photo.jpg", "photo_1.jpg"]


def test_cancellation_stops_before_later_files_and_keeps_completed(tmp_path: Path) -> None:
    first = make_heic(tmp_path / "first.heic")
    second = make_heic(tmp_path / "second.heic")
    cancel = {"requested": False}

    def on_progress(current: int, total: int, source: Path, target: Path) -> None:
        cancel["requested"] = True

    with pytest.raises(HeicConversionCancelled) as exc_info:
        HeicToJpgService().convert_entries(
            entries_for([first, second]),
            tmp_path,
            HeicJpgSettings(),
            progress_callback=on_progress,
            cancel_callback=lambda: cancel["requested"],
        )

    assert len(exc_info.value.completed_paths) == 1
    assert exc_info.value.completed_paths[0].exists()
    assert not (tmp_path / "second.jpg").exists()


def test_failure_stops_batch_and_keeps_completed(tmp_path: Path) -> None:
    valid = make_heic(tmp_path / "valid.heic")
    broken = tmp_path / "broken.heic"
    broken.write_bytes(b"broken")
    entries = (
        entries_for([valid])[0],
        HeicImageEntry(broken, broken.name, 1, 1, broken.stat().st_size),
    )

    with pytest.raises(HeicConversionError, match="failed to convert broken.heic"):
        HeicToJpgService().convert_entries(entries, tmp_path, HeicJpgSettings())

    assert (tmp_path / "valid.jpg").exists()
    assert not (tmp_path / "broken.jpg").exists()
