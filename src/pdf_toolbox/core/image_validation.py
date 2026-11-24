from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError


# Accepted extension -> the Pillow format the file's contents must actually be.
IMAGE_FORMATS_BY_EXTENSION = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
SUPPORTED_EXTENSIONS = set(IMAGE_FORMATS_BY_EXTENSION)
EXIF_ORIENTATION_TAG = 0x0112
# EXIF orientations 5-8 rotate the image by 90 or 270 degrees, swapping width and height.
TRANSPOSING_ORIENTATIONS = {5, 6, 7, 8}


def exif_orientation(image: Image.Image) -> int:
    try:
        return int(image.getexif().get(EXIF_ORIENTATION_TAG, 1))
    except Exception:
        return 1


def oriented_size(image: Image.Image) -> tuple[int, int]:
    """Size after EXIF orientation is applied, read from the header without decoding pixels."""
    width, height = image.size
    if exif_orientation(image) in TRANSPOSING_ORIENTATIONS:
        return height, width
    return width, height


class ImageValidationError(Exception):
    """Raised when an imported image cannot be used safely."""


@dataclass(frozen=True)
class ImageInfo:
    path: Path
    filename: str
    width: int
    height: int
    format: str


def validate_image_file(path: str | Path) -> ImageInfo:
    image_path = Path(path)

    if not image_path.exists():
        raise ImageValidationError("The source file could not be found.")
    if not image_path.is_file():
        raise ImageValidationError("Path is not a file.")

    extension = image_path.suffix.lower()
    expected_format = IMAGE_FORMATS_BY_EXTENSION.get(extension)
    if expected_format is None:
        raise ImageValidationError("Unsupported file type. Use JPG, JPEG, PNG or WebP.")

    # Header + EXIF only: no pixel data is decoded here. Damaged pixel data surfaces later,
    # when the thumbnail, preview, or export decodes the file.
    try:
        with Image.open(image_path) as image:
            width, height = oriented_size(image)
            image_format = (image.format or extension.lstrip(".")).upper()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ImageValidationError("This image could not be opened.") from exc

    if width <= 0 or height <= 0:
        raise ImageValidationError("Image has invalid dimensions.")

    if image_format != expected_format:
        raise ImageValidationError("This file is not a supported JPG, JPEG, PNG or WebP image.")

    return ImageInfo(
        path=image_path,
        filename=image_path.name,
        width=width,
        height=height,
        format=image_format,
    )
