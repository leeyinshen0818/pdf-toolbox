from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


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
        raise ImageValidationError("File no longer exists.")
    if not image_path.is_file():
        raise ImageValidationError("Path is not a file.")

    extension = image_path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ImageValidationError("Unsupported file type. Use JPG, JPEG, or PNG.")

    try:
        with Image.open(image_path) as image:
            image.verify()

        with Image.open(image_path) as image:
            oriented = ImageOps.exif_transpose(image)
            width, height = oriented.size
            image_format = (image.format or extension.lstrip(".")).upper()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageValidationError("File is not a readable image.") from exc

    if width <= 0 or height <= 0:
        raise ImageValidationError("Image has invalid dimensions.")

    expected_format = "JPEG" if extension in {".jpg", ".jpeg"} else "PNG"
    if image_format != expected_format:
        raise ImageValidationError("File extension does not match a supported image format.")

    return ImageInfo(
        path=image_path,
        filename=image_path.name,
        width=width,
        height=height,
        format=image_format,
    )
