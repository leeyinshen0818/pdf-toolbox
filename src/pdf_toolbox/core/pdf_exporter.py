from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
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
    """Raised when PDF export cannot complete."""


@dataclass(frozen=True)
class ExportValidationIssue:
    path: Path
    reason: str


ProgressCallback = Callable[[int, int], None]


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
            raise PdfExportError(f"Some images cannot be exported:\n{details}")

        temp_path: Path | None = None
        document = pymupdf.open()
        export_settings = settings or ExportSettings()

        try:
            for index, entry in enumerate(ordered_entries, start=1):
                image_bytes, width, height = self._prepare_image(entry.path, entry.corrections)
                layout = calculate_page_layout(width, height, export_settings)
                page = document.new_page(width=layout.page_size.width, height=layout.page_size.height)
                target = layout.image_rect
                target_rect = pymupdf.Rect(target.x0, target.y0, target.x1, target.y1)
                page.draw_rect(page.rect, color=None, fill=(1, 1, 1), overlay=False)
                page.insert_image(target_rect, stream=image_bytes)

                if progress_callback is not None:
                    progress_callback(index, len(ordered_entries))

            with tempfile.NamedTemporaryFile(
                suffix=".pdf",
                dir=parent,
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)

            document.save(temp_path)
            document.close()
            destination.unlink(missing_ok=True)
            temp_path.replace(destination)
            return destination
        except OSError as exc:
            raise PdfExportError("Could not write the PDF to the selected location.") from exc
        except Exception as exc:
            if isinstance(exc, PdfExportError):
                raise
            raise PdfExportError(f"Export failed: {exc}") from exc
        finally:
            if not document.is_closed:
                document.close()
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def _prepare_image(self, path: Path, corrections: CorrectionSettings | None = None) -> tuple[bytes, int, int]:
        try:
            with Image.open(path) as image:
                corrected = apply_corrections(image, corrections or CorrectionSettings())
                rgb_image = flatten_to_white(corrected)
                width, height = rgb_image.size

                if width <= 0 or height <= 0:
                    raise PdfExportError(f"{path.name} has invalid dimensions.")

                buffer = BytesIO()
                rgb_image.save(buffer, format="PNG")
                return buffer.getvalue(), width, height
        except PdfExportError:
            raise
        except Exception as exc:
            raise PdfExportError(f"Could not prepare {path.name} for export.") from exc
