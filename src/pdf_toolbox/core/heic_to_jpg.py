from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import tempfile
from typing import Callable, Iterable

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from pdf_toolbox.core.image_validation import oriented_size
from pdf_toolbox.core.pdf_to_image import JpgQuality, collision_safe_path, safe_filename_stem
from pdf_toolbox.core.path_keys import path_key as heic_key


SUPPORTED_HEIC_EXTENSIONS = {".heic", ".heif"}


class HeicLoadError(Exception):
    """Raised when a HEIC/HEIF file cannot be loaded."""


class HeicConversionError(Exception):
    """Raised when HEIC/HEIF conversion cannot complete; `filename` names the photo at fault, when known."""

    def __init__(self, message: str = "", filename: str | None = None) -> None:
        super().__init__(message)
        self.filename = filename


class HeicConversionCancelled(Exception):
    def __init__(self, completed_paths: tuple[Path, ...]) -> None:
        super().__init__("Conversion cancelled.")
        self.completed_paths = completed_paths


@dataclass(frozen=True)
class HeicImageInfo:
    path: Path
    filename: str
    width: int
    height: int
    file_size_bytes: int


@dataclass(frozen=True)
class HeicImageEntry:
    path: Path
    filename: str
    width: int
    height: int
    file_size_bytes: int

    @classmethod
    def from_info(cls, info: HeicImageInfo) -> "HeicImageEntry":
        return cls(
            path=info.path,
            filename=info.filename,
            width=info.width,
            height=info.height,
            file_size_bytes=info.file_size_bytes,
        )


@dataclass(frozen=True)
class RejectedHeic:
    path: Path
    reason: str


@dataclass(frozen=True)
class AddHeicResult:
    added: tuple[HeicImageEntry, ...]
    rejected: tuple[RejectedHeic, ...]
    duplicates: tuple[Path, ...]


@dataclass(frozen=True)
class DecodedHeic:
    """One full decode of a photo: its upright size and a downscaled copy for display."""

    image: Image.Image
    width: int
    height: int


@dataclass(frozen=True)
class HeicJpgSettings:
    jpg_quality: JpgQuality = JpgQuality.MAXIMUM


ProgressCallback = Callable[[int, int, Path, Path], None]
CancelCallback = Callable[[], bool]


def register_heic_support() -> None:
    register_heif_opener()


class HeicCollection:
    def __init__(self) -> None:
        self._entries: list[HeicImageEntry] = []
        self._keys: set[str] = set()

    @property
    def entries(self) -> tuple[HeicImageEntry, ...]:
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def add_paths(self, paths: Iterable[str | Path], service: "HeicToJpgService") -> AddHeicResult:
        added: list[HeicImageEntry] = []
        rejected: list[RejectedHeic] = []
        duplicates: list[Path] = []

        for raw_path in paths:
            path = Path(raw_path)
            key = heic_key(path)
            if key in self._keys:
                duplicates.append(path)
                continue

            try:
                info = service.load_image_info(path)
            except HeicLoadError as exc:
                rejected.append(RejectedHeic(path=path, reason=str(exc)))
                continue

            entry = HeicImageEntry.from_info(info)
            self._entries.append(entry)
            self._keys.add(key)
            added.append(entry)

        return AddHeicResult(tuple(added), tuple(rejected), tuple(duplicates))

    def remove_path(self, path: str | Path) -> None:
        key = heic_key(path)
        self._entries = [entry for entry in self._entries if heic_key(entry.path) != key]
        self._keys = {heic_key(entry.path) for entry in self._entries}

    def clear(self) -> None:
        self._entries.clear()
        self._keys.clear()


class HeicToJpgService:
    def __init__(self) -> None:
        register_heic_support()

    def load_image_info(self, path: str | Path) -> HeicImageInfo:
        image_path = Path(path)
        if not image_path.exists():
            raise HeicLoadError("The source file could not be found.")
        if not image_path.is_file():
            raise HeicLoadError("Path is not a file.")
        if image_path.suffix.lower() not in SUPPORTED_HEIC_EXTENSIONS:
            raise HeicLoadError("Unsupported file type. Use HEIC or HEIF files.")

        # Header only: the pixels are decoded once later, by decode_preview_image.
        try:
            with Image.open(image_path) as image:
                if image.format != "HEIF":
                    raise HeicLoadError("This file is not a supported HEIC or HEIF image.")
                width, height = oriented_size(image)
        except HeicLoadError:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise HeicLoadError("This HEIC image could not be opened.") from exc

        if width <= 0 or height <= 0:
            raise HeicLoadError("Image has invalid dimensions.")

        return HeicImageInfo(
            path=image_path,
            filename=image_path.name,
            width=width,
            height=height,
            file_size_bytes=image_path.stat().st_size,
        )

    def decode_preview_image(self, path: str | Path, max_size: tuple[int, int] = (1000, 1000)) -> Image.Image:
        """Decode the file once and return an oriented RGB image no larger than max_size."""
        return self.decode_for_display(path, max_size).image

    def decode_for_display(self, path: str | Path, max_size: tuple[int, int] = (1000, 1000)) -> DecodedHeic:
        """Decode the file once: the upright full size plus an RGB copy no larger than max_size."""
        try:
            with Image.open(Path(path)) as image:
                prepared = prepare_jpg_image(image)
            width, height = prepared.size
            prepared.thumbnail(max_size, Image.Resampling.LANCZOS)
            return DecodedHeic(prepared, width, height)
        except Exception as exc:
            raise HeicLoadError("Preview unavailable for this image.") from exc

    def render_preview_png_bytes(self, path: str | Path, max_size: tuple[int, int] = (1000, 1000)) -> bytes:
        prepared = self.decode_preview_image(path, max_size)
        try:
            buffer = BytesIO()
            prepared.save(buffer, format="PNG")
            return buffer.getvalue()
        except Exception as exc:
            raise HeicLoadError("Preview unavailable for this image.") from exc

    def convert_entries(
        self,
        entries: Iterable[HeicImageEntry],
        output_folder: str | Path,
        settings: HeicJpgSettings,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
    ) -> tuple[Path, ...]:
        output_dir = Path(output_folder)
        if not output_dir.exists():
            raise HeicConversionError("The selected output folder is no longer available.")
        if not output_dir.is_dir():
            raise HeicConversionError("Output path is not a folder.")

        ordered_entries = tuple(entries)
        if not ordered_entries:
            raise HeicConversionError("No HEIC files available to convert.")

        completed: list[Path] = []
        total = len(ordered_entries)
        for done, entry in enumerate(ordered_entries, start=1):
            if cancel_callback is not None and cancel_callback():
                raise HeicConversionCancelled(tuple(completed))

            target = collision_safe_path(output_dir, f"{safe_filename_stem(entry.path.stem)}.jpg")
            try:
                self._convert_one_atomic(entry.path, target, settings)
            except Exception as exc:
                if target.exists():
                    try:
                        target.unlink()
                    except OSError:
                        pass
                raise HeicConversionError(
                    f"Conversion stopped - failed to convert {entry.filename}.", filename=entry.filename
                ) from exc

            completed.append(target)
            if progress_callback is not None:
                progress_callback(done, total, entry.path, target)

        return tuple(completed)

    def _convert_one_atomic(self, source: Path, target: Path, settings: HeicJpgSettings) -> None:
        if not source.exists():
            raise HeicConversionError(f"The source file could not be found: {source.name}")

        with tempfile.NamedTemporaryFile(suffix=".jpg", dir=target.parent, delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            with Image.open(source) as image:
                converted = prepare_jpg_image(image)
                exif = image.info.get("exif")
                save_kwargs = {
                    "format": "JPEG",
                    "quality": JpgQuality(settings.jpg_quality).quality,
                    "optimize": True,
                }
                if JpgQuality(settings.jpg_quality) == JpgQuality.MAXIMUM:
                    save_kwargs["subsampling"] = 0
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
    if oriented.mode in {"RGBA", "LA"} or ("transparency" in oriented.info):
        background = Image.new("RGB", oriented.size, (255, 255, 255))
        alpha_source = oriented.convert("RGBA")
        background.paste(alpha_source, mask=alpha_source.getchannel("A"))
        return background
    if oriented.mode != "RGB":
        return oriented.convert("RGB")
    return oriented.copy()
