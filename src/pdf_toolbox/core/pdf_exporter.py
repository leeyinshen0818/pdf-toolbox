from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Callable, Iterable

import pymupdf
from PIL import Image

from pdf_toolbox.core.image_corrections import CorrectionSettings, apply_corrections, flatten_to_white
from pdf_toolbox.core.image_collection import ImageEntry
from pdf_toolbox.core.image_validation import ImageValidationError, validate_image_file
from pdf_toolbox.core.pdf_geometry import ExportSettings, calculate_page_layout


class PdfExportError(Exception):
    """Raised when PDF export cannot complete.

    `filename` names the image that caused the failure, when one did.
    """

    def __init__(self, message: str, filename: str | None = None) -> None:
        super().__init__(message)
        self.filename = filename


class PdfExportCancelled(Exception):
    """Raised when the user cancels an export; no output is written and any existing target is untouched."""

    def __init__(self) -> None:
        super().__init__("Export cancelled.")


@dataclass(frozen=True)
class ExportValidationIssue:
    path: Path
    reason: str


ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]


class PdfExporter:
    def validate_entries(self, entries: Iterable[ImageEntry]) -> tuple[ExportValidationIssue, ...]:
        issues: list[ExportValidationIssue] = []
        for entry in entries:
            try:
                info = validate_image_file(entry.path)
            except ImageValidationError as exc:
                issues.append(ExportValidationIssue(entry.path, str(exc)))
                continue

            if info.width <= 0 or info.height <= 0:
                issues.append(ExportValidationIssue(entry.path, "Image has invalid dimensions."))

        return tuple(issues)

    def export(
        self,
        entries: Iterable[ImageEntry],
        output_path: str | Path,
        *,
        settings: ExportSettings | None = None,
        overwrite: bool = False,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
    ) -> Path:
        ordered_entries = tuple(entries)
        if not ordered_entries:
            raise PdfExportError("Add at least one image before exporting.")

        destination = Path(output_path)
        if destination.suffix.lower() != ".pdf":
            destination = destination.with_suffix(".pdf")

        parent = destination.parent
        if not parent.exists():
            raise PdfExportError("Output folder does not exist.")
        if destination.exists() and not overwrite:
            raise PdfExportError("Output file already exists.")

        issues = self.validate_entries(ordered_entries)
        if issues:
            details = "\n".join(f"{issue.path.name}: {issue.reason}" for issue in issues)
            raise PdfExportError(f"Some images cannot be exported:\n{details}", filename=issues[0].path.name)

        temp_path: Path | None = None
        document = pymupdf.open()
        export_settings = settings or ExportSettings()

        try:
            for index, entry in enumerate(ordered_entries, start=1):
                if cancel_callback is not None and cancel_callback():
                    raise PdfExportCancelled()
                prepared = self._prepare_image(entry.path, entry.corrections)
                layout = calculate_page_layout(prepared.width, prepared.height, export_settings)
                page = document.new_page(width=layout.page_size.width, height=layout.page_size.height)
                target = layout.image_rect
                target_rect = pymupdf.Rect(target.x0, target.y0, target.x1, target.y1)
                page.draw_rect(page.rect, color=None, fill=(1, 1, 1), overlay=False)
                if prepared.jpeg_bytes is not None:
                    page.insert_image(target_rect, stream=prepared.jpeg_bytes)
                else:
                    page.insert_image(target_rect, pixmap=prepared.pixmap)

                if progress_callback is not None:
                    progress_callback(index, len(ordered_entries))

            if cancel_callback is not None and cancel_callback():
                raise PdfExportCancelled()

            with tempfile.NamedTemporaryFile(
                suffix=".pdf",
                dir=parent,
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)

            document.save(temp_path)
            document.close()
            # os.replace overwrites an existing target in one step, so a failure here never
            # leaves the user without their previous file.
            temp_path.replace(destination)
            return destination
        except PdfExportCancelled:
            raise
        except OSError as exc:
            raise PdfExportError("Could not write the PDF to the selected location.") from exc
        except Exception as exc:
            if isinstance(exc, PdfExportError):
                raise
            raise PdfExportError("Export failed. The PDF could not be created.") from exc
        finally:
            if not document.is_closed:
                document.close()
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def _prepare_image(self, path: Path, corrections: CorrectionSettings | None = None) -> PreparedImage:
        """Decode, correct and flatten one image for embedding.

        Unchanged baseline-friendly JPEGs are embedded byte-for-byte (no re-encode, so no quality
        change); they are still fully decoded first so a damaged file fails here, naming the file.
        Everything else is handed to MuPDF as raw RGB pixels, which it stores losslessly; this
        skips the slow PNG round-trip the exporter used to make for every page.
        """
        settings = (corrections or CorrectionSettings()).normalized()
        try:
            with Image.open(path) as image:
                image.load()
                if _can_embed_jpeg_unchanged(image, settings):
                    width, height = image.size
                    if width <= 0 or height <= 0:
                        raise PdfExportError(f"{path.name} has invalid dimensions.", filename=path.name)
                    return PreparedImage(width, height, jpeg_bytes=path.read_bytes())

                corrected = apply_corrections(image, settings)
                rgb_image = flatten_to_white(corrected)
                width, height = rgb_image.size

                if width <= 0 or height <= 0:
                    raise PdfExportError(f"{path.name} has invalid dimensions.", filename=path.name)

                pixmap = pymupdf.Pixmap(pymupdf.csRGB, width, height, rgb_image.tobytes("raw", "RGB"), 0)
                return PreparedImage(width, height, pixmap=pixmap)
        except PdfExportError:
            raise
        except Exception as exc:
            raise PdfExportError(f"This image could not be opened: {path.name}", filename=path.name) from exc


@dataclass(frozen=True)
class PreparedImage:
    width: int
    height: int
    jpeg_bytes: bytes | None = None
    pixmap: pymupdf.Pixmap | None = None


_EXIF_ORIENTATION_TAG = 0x0112


def _can_embed_jpeg_unchanged(image: Image.Image, corrections: CorrectionSettings) -> bool:
    """True when embedding the original JPEG gives the same picture as decoding and re-encoding it."""
    if image.format != "JPEG" or image.mode not in {"RGB", "L"}:
        return False  # CMYK/YCCK JPEGs render inconsistently across PDF viewers
    if corrections != CorrectionSettings():
        return False
    orientation = image.getexif().get(_EXIF_ORIENTATION_TAG, 1)
    return orientation in (None, 1)
