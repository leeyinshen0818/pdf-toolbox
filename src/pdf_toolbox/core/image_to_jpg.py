from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import tempfile
from typing import Callable, Iterable

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from pdf_toolbox.core.image_corrections import flatten_to_white
from pdf_toolbox.core.image_validation import EXIF_ORIENTATION_TAG, oriented_size
from pdf_toolbox.core.pdf_to_image import JpgQuality, collision_safe_path, safe_filename_stem
from pdf_toolbox.core.path_keys import path_key as photo_key


# Accepted extension -> the Pillow format the file's contents must actually be.
PHOTO_FORMATS_BY_EXTENSION = {".heic": "HEIF", ".heif": "HEIF", ".webp": "WEBP", ".png": "PNG"}
# Only these can hold several frames whose first frame is what gets converted (animated WebP, APNG).
# HEIF is left out: the opener shows the primary image, which is not necessarily the first.
MULTI_FRAME_FORMATS = {"WEBP", "PNG"}


class PhotoLoadError(Exception):
    """Raised when a photo cannot be loaded."""


class JpgConversionError(Exception):
    """Raised when JPG conversion cannot complete; `filename` names the photo at fault, when known."""

    def __init__(self, message: str = "", filename: str | None = None) -> None:
        super().__init__(message)
        self.filename = filename


class JpgConversionCancelled(Exception):
    def __init__(self, completed_paths: tuple[Path, ...]) -> None:
        super().__init__("Conversion cancelled.")
        self.completed_paths = completed_paths


@dataclass(frozen=True)
class PhotoInfo:
    path: Path
    filename: str
    width: int
    height: int
    file_size_bytes: int
    n_frames: int = 1


@dataclass(frozen=True)
class PhotoEntry:
    path: Path
    filename: str
    width: int
    height: int
    file_size_bytes: int
    n_frames: int = 1

    @classmethod
    def from_info(cls, info: PhotoInfo) -> "PhotoEntry":
        return cls(
            path=info.path,
            filename=info.filename,
            width=info.width,
            height=info.height,
            file_size_bytes=info.file_size_bytes,
            n_frames=info.n_frames,
        )


@dataclass(frozen=True)
class RejectedPhoto:
    path: Path
    reason: str


@dataclass(frozen=True)
class AddPhotoResult:
    added: tuple[PhotoEntry, ...]
    rejected: tuple[RejectedPhoto, ...]
    duplicates: tuple[Path, ...]


@dataclass(frozen=True)
class DecodedPhoto:
    """One full decode of a photo: its upright size and a downscaled copy for display."""

    image: Image.Image
    width: int
    height: int


@dataclass(frozen=True)
class JpgSettings:
    jpg_quality: JpgQuality = JpgQuality.MAXIMUM


ProgressCallback = Callable[[int, int, Path, Path], None]
CancelCallback = Callable[[], bool]


def register_heic_support() -> None:
    register_heif_opener()


class PhotoCollection:
    def __init__(self) -> None:
        self._entries: list[PhotoEntry] = []
        self._keys: set[str] = set()

    @property
    def entries(self) -> tuple[PhotoEntry, ...]:
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def add_paths(self, paths: Iterable[str | Path], service: "ImageToJpgService") -> AddPhotoResult:
        added: list[PhotoEntry] = []
        rejected: list[RejectedPhoto] = []
        duplicates: list[Path] = []

        for raw_path in paths:
            path = Path(raw_path)
            key = photo_key(path)
            if key in self._keys:
                duplicates.append(path)
                continue

            try:
                info = service.load_image_info(path)
            except PhotoLoadError as exc:
                rejected.append(RejectedPhoto(path=path, reason=str(exc)))
                continue

            entry = PhotoEntry.from_info(info)
            self._entries.append(entry)
            self._keys.add(key)
            added.append(entry)

        return AddPhotoResult(tuple(added), tuple(rejected), tuple(duplicates))

    def remove_path(self, path: str | Path) -> None:
        key = photo_key(path)
        self._entries = [entry for entry in self._entries if photo_key(entry.path) != key]
        self._keys = {photo_key(entry.path) for entry in self._entries}

    def clear(self) -> None:
        self._entries.clear()
        self._keys.clear()


class ImageToJpgService:
    def __init__(self) -> None:
        register_heic_support()

    def load_image_info(self, path: str | Path) -> PhotoInfo:
        image_path = Path(path)
        if not image_path.exists():
            raise PhotoLoadError("The source file could not be found.")
        if not image_path.is_file():
            raise PhotoLoadError("Path is not a file.")
        extension = image_path.suffix.lower()
        expected_format = PHOTO_FORMATS_BY_EXTENSION.get(extension)
        if expected_format is None:
            raise PhotoLoadError("Unsupported file type. Use HEIC, HEIF, WebP or PNG files.")

        # Header only: the pixels are decoded once later, by decode_preview_image.
        try:
            with Image.open(image_path) as image:
                if image.format != expected_format:
                    raise PhotoLoadError(
                        f"This file is not a supported image: its contents do not match the {extension} extension."
                    )
                width, height = oriented_size(image)
                n_frames = getattr(image, "n_frames", 1) if expected_format in MULTI_FRAME_FORMATS else 1
        except PhotoLoadError:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise PhotoLoadError("This image could not be opened.") from exc

        if width <= 0 or height <= 0:
            raise PhotoLoadError("Image has invalid dimensions.")

        return PhotoInfo(
            path=image_path,
            filename=image_path.name,
            width=width,
            height=height,
            file_size_bytes=image_path.stat().st_size,
            n_frames=n_frames,
        )

    def decode_preview_image(self, path: str | Path, max_size: tuple[int, int] = (1000, 1000)) -> Image.Image:
        """Decode the file once and return an oriented RGB image no larger than max_size."""
        return self.decode_for_display(path, max_size).image

    def decode_for_display(self, path: str | Path, max_size: tuple[int, int] = (1000, 1000)) -> DecodedPhoto:
        """Decode the file once: the upright full size plus an RGB copy no larger than max_size."""
        try:
            with Image.open(Path(path)) as image:
                prepared = prepare_jpg_image(image)
            width, height = prepared.size
            prepared.thumbnail(max_size, Image.Resampling.LANCZOS)
            return DecodedPhoto(prepared, width, height)
        except Exception as exc:
            raise PhotoLoadError("Preview unavailable for this image.") from exc

    def render_preview_png_bytes(self, path: str | Path, max_size: tuple[int, int] = (1000, 1000)) -> bytes:
        prepared = self.decode_preview_image(path, max_size)
        try:
            buffer = BytesIO()
            prepared.save(buffer, format="PNG")
            return buffer.getvalue()
        except Exception as exc:
            raise PhotoLoadError("Preview unavailable for this image.") from exc

    def convert_entries(
        self,
        entries: Iterable[PhotoEntry],
        output_folder: str | Path,
        settings: JpgSettings,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
    ) -> tuple[Path, ...]:
        output_dir = Path(output_folder)
        if not output_dir.exists():
            raise JpgConversionError("The selected output folder is no longer available.")
        if not output_dir.is_dir():
            raise JpgConversionError("Output path is not a folder.")

        ordered_entries = tuple(entries)
        if not ordered_entries:
            raise JpgConversionError("No photos available to convert.")

        completed: list[Path] = []
        total = len(ordered_entries)
        for done, entry in enumerate(ordered_entries, start=1):
            if cancel_callback is not None and cancel_callback():
                raise JpgConversionCancelled(tuple(completed))

            target = collision_safe_path(output_dir, f"{safe_filename_stem(entry.path.stem)}.jpg")
            try:
                self._convert_one_atomic(entry.path, target, settings)
            except Exception as exc:
                if target.exists():
                    try:
                        target.unlink()
                    except OSError:
                        pass
                raise JpgConversionError(
                    f"Conversion stopped - failed to convert {entry.filename}.", filename=entry.filename
                ) from exc

            completed.append(target)
            if progress_callback is not None:
                progress_callback(done, total, entry.path, target)

        return tuple(completed)

    def _convert_one_atomic(self, source: Path, target: Path, settings: JpgSettings) -> None:
        if not source.exists():
            raise JpgConversionError(f"The source file could not be found: {source.name}")

        with tempfile.NamedTemporaryFile(suffix=".jpg", dir=target.parent, delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            with Image.open(source) as image:
                converted = prepare_jpg_image(image)
                exif = output_exif_bytes(image)
                icc_profile = image.info.get("icc_profile")
                save_kwargs = {
                    "format": "JPEG",
                    "quality": JpgQuality(settings.jpg_quality).quality,
                    "optimize": True,
                }
                if JpgQuality(settings.jpg_quality) == JpgQuality.MAXIMUM:
                    save_kwargs["subsampling"] = 0
                if icc_profile:
                    save_kwargs["icc_profile"] = icc_profile
                if exif:
                    save_kwargs["exif"] = exif
                try:
                    converted.save(temp_path, **save_kwargs)
                except Exception:
                    if "exif" not in save_kwargs:
                        raise
                    save_kwargs.pop("exif", None)
                    converted.save(temp_path, **save_kwargs)
            temp_path.replace(target)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass


def prepare_jpg_image(image: Image.Image) -> Image.Image:
    oriented = ImageOps.exif_transpose(image)
    oriented.load()
    return flatten_to_white(oriented)


def output_exif_bytes(image: Image.Image) -> bytes | None:
    """The source EXIF for the JPG, minus Orientation: prepare_jpg_image already applied it.

    Rebuilt from getexif() rather than copying info["exif"], whose raw bytes lack the
    "Exif" header for WebP and would still carry the orientation for JPG/PNG/WebP sources.
    """
    try:
        exif = image.getexif()
        exif.pop(EXIF_ORIENTATION_TAG, None)
        return exif.tobytes() if len(exif) else None
    except Exception:
        return None
