from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageCms
from pillow_heif import register_heif_opener

from pdf_toolbox.core.image_to_jpg import (
    ImageToJpgService,
    JpgConversionCancelled,
    JpgConversionError,
    JpgSettings,
    PhotoCollection,
    PhotoEntry,
    PhotoLoadError,
)
from pdf_toolbox.core.image_validation import EXIF_ORIENTATION_TAG
from pdf_toolbox.core.pdf_to_image import JpgQuality
from pdf_toolbox.ui.image_to_jpg_page import ConvertToJpgPage


register_heif_opener()


def make_heic(path: Path, size: tuple[int, int] = (32, 24), color=(80, 120, 180)) -> Path:
    Image.new("RGB", size, color).save(path, format="HEIF")
    return path


def make_heif(path: Path, size: tuple[int, int] = (32, 24), color=(80, 120, 180)) -> Path:
    Image.new("RGB", size, color).save(path, format="HEIF")
    return path


def entries_for(paths: list[Path]) -> tuple[PhotoEntry, ...]:
    service = ImageToJpgService()
    collection = PhotoCollection()
    result = collection.add_paths(paths, service)
    assert not result.rejected
    return collection.entries


def test_valid_heic_accepted(tmp_path: Path) -> None:
    path = make_heic(tmp_path / "photo.heic", size=(40, 30))

    info = ImageToJpgService().load_image_info(path)

    assert info.filename == "photo.heic"
    assert (info.width, info.height) == (40, 30)


def test_valid_heif_accepted(tmp_path: Path) -> None:
    path = make_heif(tmp_path / "photo.heif", size=(30, 40))

    info = ImageToJpgService().load_image_info(path)

    assert info.filename == "photo.heif"
    assert (info.width, info.height) == (30, 40)


def test_missing_corrupted_and_masquerading_files_rejected(tmp_path: Path) -> None:
    service = ImageToJpgService()
    corrupted = tmp_path / "broken.heic"
    corrupted.write_bytes(b"not an image")
    masquerading = tmp_path / "fake.heic"
    Image.new("RGB", (10, 10)).save(masquerading, format="PNG")

    with pytest.raises(PhotoLoadError, match="source file could not be found"):
        service.load_image_info(tmp_path / "missing.heic")
    with pytest.raises(PhotoLoadError, match="could not be opened"):
        service.load_image_info(corrupted)
    with pytest.raises(PhotoLoadError, match="not a supported"):
        service.load_image_info(masquerading)


@pytest.mark.parametrize(("filename", "image_format"), [("photo.webp", "WEBP"), ("photo.png", "PNG")])
def test_webp_and_png_accepted(tmp_path: Path, filename: str, image_format: str) -> None:
    path = tmp_path / filename
    Image.new("RGB", (20, 10), (10, 20, 30)).save(path, format=image_format)

    info = ImageToJpgService().load_image_info(path)

    assert (info.width, info.height) == (20, 10)


def test_jpg_is_not_accepted(tmp_path: Path) -> None:
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (10, 10)).save(path, format="JPEG")

    assert ".jpg" not in ConvertToJpgPage.ACCEPTED_EXTENSIONS
    assert ".jpeg" not in ConvertToJpgPage.ACCEPTED_EXTENSIONS
    with pytest.raises(PhotoLoadError, match="Unsupported file type"):
        ImageToJpgService().load_image_info(path)


@pytest.mark.parametrize(("filename", "image_format"), [("rotated.png", "PNG"), ("rotated.webp", "WEBP")])
def test_exif_orientation_is_applied_once_and_other_exif_survives(
    tmp_path: Path, filename: str, image_format: str
) -> None:
    # 4x2: red left half, blue right half. Orientation 6 means "rotate 90 degrees clockwise to view".
    source = tmp_path / filename
    image = Image.new("RGB", (4, 2), (255, 0, 0))
    image.paste((0, 0, 255), (2, 0, 4, 2))
    exif = Image.Exif()
    exif[EXIF_ORIENTATION_TAG] = 6
    exif[0x010F] = "TestCam"  # Make
    save_kwargs = {"lossless": True} if image_format == "WEBP" else {}
    image.save(source, format=image_format, exif=exif.tobytes(), **save_kwargs)

    (output,) = ImageToJpgService().convert_entries(entries_for([source]), tmp_path, JpgSettings())

    with Image.open(output) as converted:
        assert converted.size == (2, 4)
        top, bottom = converted.getpixel((1, 0)), converted.getpixel((1, 3))
        assert top[0] > 200 and top[2] < 60  # red now on top
        assert bottom[2] > 200 and bottom[0] < 60
        out_exif = converted.getexif()
        assert out_exif.get(EXIF_ORIENTATION_TAG, 1) == 1
        assert out_exif.get(0x010F) == "TestCam"


@pytest.mark.parametrize(("filename", "image_format"), [("profiled.png", "PNG"), ("profiled.webp", "WEBP")])
def test_icc_profile_is_preserved(tmp_path: Path, filename: str, image_format: str) -> None:
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    source = tmp_path / filename
    Image.new("RGB", (8, 8), (10, 120, 200)).save(source, format=image_format, icc_profile=profile)

    (output,) = ImageToJpgService().convert_entries(entries_for([source]), tmp_path, JpgSettings())

    with Image.open(output) as converted:
        assert converted.info.get("icc_profile") == profile


def test_same_stem_png_and_webp_in_one_batch_get_distinct_names(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    png = sources / "photo.png"
    webp = sources / "photo.webp"
    Image.new("RGB", (8, 8)).save(png, format="PNG")
    Image.new("RGB", (8, 8)).save(webp, format="WEBP")

    outputs = ImageToJpgService().convert_entries(entries_for([png, webp]), tmp_path, JpgSettings())

    assert [path.name for path in outputs] == ["photo.jpg", "photo_1.jpg"]


def test_duplicate_file_rejected(tmp_path: Path) -> None:
    path = make_heic(tmp_path / "photo.heic")
    service = ImageToJpgService()
    collection = PhotoCollection()

    first = collection.add_paths([path], service)
    second = collection.add_paths([path], service)

    assert len(first.added) == 1
    assert second.duplicates == (path,)
    assert len(collection.entries) == 1


def test_one_heic_converts_to_jpg_with_dimensions_and_rgb(tmp_path: Path) -> None:
    source = make_heic(tmp_path / "photo.heic", size=(64, 48), color=(200, 100, 50))

    outputs = ImageToJpgService().convert_entries(entries_for([source]), tmp_path, JpgSettings())

    assert [path.name for path in outputs] == ["photo.jpg"]
    with Image.open(outputs[0]) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.size == (64, 48)


def test_multiple_heics_convert_in_order_and_source_unchanged(tmp_path: Path) -> None:
    first = make_heic(tmp_path / "first.heic", size=(20, 30))
    second = make_heif(tmp_path / "second.heif", size=(40, 25))
    before = first.read_bytes()

    outputs = ImageToJpgService().convert_entries(entries_for([first, second]), tmp_path, JpgSettings())

    assert [path.name for path in outputs] == ["first.jpg", "second.jpg"]
    assert first.read_bytes() == before
    with Image.open(outputs[0]) as portrait, Image.open(outputs[1]) as landscape:
        assert portrait.height > portrait.width
        assert landscape.width > landscape.height


def test_maximum_quality_path_uses_jpg_output(tmp_path: Path) -> None:
    source = make_heic(tmp_path / "quality.heic")

    outputs = ImageToJpgService().convert_entries(
        entries_for([source]),
        tmp_path,
        JpgSettings(jpg_quality=JpgQuality.MAXIMUM),
    )

    assert outputs[0].suffix == ".jpg"
    assert outputs[0].exists()


def test_collision_safe_naming_for_heic_outputs(tmp_path: Path) -> None:
    source = make_heic(tmp_path / "photo.heic")
    (tmp_path / "photo.jpg").write_bytes(b"existing")
    (tmp_path / "photo_1.jpg").write_bytes(b"existing")

    outputs = ImageToJpgService().convert_entries(entries_for([source]), tmp_path, JpgSettings())

    assert outputs[0].name == "photo_2.jpg"


def test_same_base_filename_from_different_folders_uses_collision_safe_names(tmp_path: Path) -> None:
    first_dir = tmp_path / "one"
    second_dir = tmp_path / "two"
    first_dir.mkdir()
    second_dir.mkdir()
    first = make_heic(first_dir / "photo.heic")
    second = make_heic(second_dir / "photo.heic")

    outputs = ImageToJpgService().convert_entries(entries_for([first, second]), tmp_path, JpgSettings())

    assert [path.name for path in outputs] == ["photo.jpg", "photo_1.jpg"]


def test_cancellation_stops_before_later_files_and_keeps_completed(tmp_path: Path) -> None:
    first = make_heic(tmp_path / "first.heic")
    second = make_heic(tmp_path / "second.heic")
    cancel = {"requested": False}

    def on_progress(current: int, total: int, source: Path, target: Path) -> None:
        cancel["requested"] = True

    with pytest.raises(JpgConversionCancelled) as exc_info:
        ImageToJpgService().convert_entries(
            entries_for([first, second]),
            tmp_path,
            JpgSettings(),
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
        PhotoEntry(broken, broken.name, 1, 1, broken.stat().st_size),
    )

    with pytest.raises(JpgConversionError, match="failed to convert broken.heic"):
        ImageToJpgService().convert_entries(entries, tmp_path, JpgSettings())

    assert (tmp_path / "valid.jpg").exists()
    assert not (tmp_path / "broken.jpg").exists()
