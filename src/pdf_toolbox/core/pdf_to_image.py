from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
import tempfile
from typing import Callable, Iterable

import pymupdf
from PIL import Image


class PdfLoadError(Exception):
    """Raised when a PDF cannot be loaded for conversion."""


class PdfRenderError(Exception):
    """Raised when a PDF page cannot be rendered."""


class ConversionCancelled(Exception):
    def __init__(self, completed_paths: tuple[Path, ...]) -> None:
        super().__init__("Conversion cancelled.")
        self.completed_paths = completed_paths


class OutputFormat(str, Enum):
    JPG = "JPG"
    PNG = "PNG"

    @property
    def extension(self) -> str:
        return ".jpg" if self == OutputFormat.JPG else ".png"


class DpiPreset(str, Enum):
    STANDARD = "Standard - 150 DPI"
    HIGH = "High - 300 DPI"

    @property
    def dpi(self) -> int:
        return 150 if self == DpiPreset.STANDARD else 300


class JpgQuality(str, Enum):
    STANDARD = "Standard"
    HIGH = "High"
    MAXIMUM = "Maximum"

    @property
    def quality(self) -> int:
        return {
            JpgQuality.STANDARD: 85,
            JpgQuality.HIGH: 95,
            JpgQuality.MAXIMUM: 100,
        }[self]


@dataclass(frozen=True)
class PdfInfo:
    path: Path
    filename: str
    page_count: int
    file_size_bytes: int


@dataclass(frozen=True)
class PdfImageExportSettings:
    output_format: OutputFormat = OutputFormat.JPG
    dpi: DpiPreset = DpiPreset.HIGH
    jpg_quality: JpgQuality = JpgQuality.HIGH


ProgressCallback = Callable[[int, int, int, Path], None]
CancelCallback = Callable[[], bool]


class PdfToImageService:
    def load_pdf_info(self, path: str | Path) -> PdfInfo:
        pdf_path = Path(path)
        if not pdf_path.exists():
            raise PdfLoadError("PDF file no longer exists.")
        if not pdf_path.is_file():
            raise PdfLoadError("Path is not a file.")
        if pdf_path.suffix.lower() != ".pdf":
            raise PdfLoadError("Unsupported file type. Use a PDF file.")

        try:
            with pymupdf.open(pdf_path) as document:
                if document.needs_pass:
                    raise PdfLoadError("This PDF is password-protected and cannot be opened without a password.")
                page_count = document.page_count
        except PdfLoadError:
            raise
        except Exception as exc:
            raise PdfLoadError("File is not a readable PDF.") from exc

        if page_count <= 0:
            raise PdfLoadError("PDF has no pages.")

        return PdfInfo(
            path=pdf_path,
            filename=pdf_path.name,
            page_count=page_count,
            file_size_bytes=pdf_path.stat().st_size,
        )

    def render_page_png_bytes(self, path: str | Path, page_index: int, dpi: int) -> bytes:
        try:
            pixmap = self._render_page_pixmap(Path(path), page_index, dpi)
            return pixmap.tobytes("png")
        except PdfRenderError:
            raise
        except Exception as exc:
            raise PdfRenderError(f"Failed to render page {page_index + 1}.") from exc

    def export_pages(
        self,
        path: str | Path,
        page_indices: Iterable[int],
        output_folder: str | Path,
        settings: PdfImageExportSettings,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
    ) -> tuple[Path, ...]:
        pdf_path = Path(path)
        output_dir = Path(output_folder)
        if not output_dir.exists():
            raise PdfRenderError("Output folder does not exist.")
        if not output_dir.is_dir():
            raise PdfRenderError("Output path is not a folder.")

        info = self.load_pdf_info(pdf_path)
        pages = tuple(page_indices)
        if not pages:
            raise PdfRenderError("Select at least one page before converting.")

        for index in pages:
            if index < 0 or index >= info.page_count:
                raise PdfRenderError(f"Page {index + 1} is outside the PDF page range.")

        completed: list[Path] = []
        total = len(pages)
        stem = safe_filename_stem(pdf_path.stem)
        output_format = OutputFormat(settings.output_format)

        for done, page_index in enumerate(pages, start=1):
            if cancel_callback is not None and cancel_callback():
                raise ConversionCancelled(tuple(completed))

            target = collision_safe_path(
                output_dir,
                page_output_name(stem, page_index, info.page_count, output_format),
            )

            try:
                pixmap = self._render_page_pixmap(pdf_path, page_index, DpiPreset(settings.dpi).dpi)
                self._save_pixmap_atomic(pixmap, target, settings)
            except Exception as exc:
                if target.exists():
                    try:
                        target.unlink()
                    except OSError:
                        pass
                raise PdfRenderError(f"Failed to render page {page_index + 1}.") from exc

            completed.append(target)
            if progress_callback is not None:
                progress_callback(done, total, page_index, target)

        return tuple(completed)

    def _render_page_pixmap(self, path: Path, page_index: int, dpi: int) -> pymupdf.Pixmap:
        try:
            with pymupdf.open(path) as document:
                if document.needs_pass:
                    raise PdfRenderError("This PDF is password-protected and cannot be opened without a password.")
                if page_index < 0 or page_index >= document.page_count:
                    raise PdfRenderError(f"Page {page_index + 1} is outside the PDF page range.")

                page = document.load_page(page_index)
                scale = dpi / 72
                matrix = pymupdf.Matrix(scale, scale)
                return page.get_pixmap(matrix=matrix, alpha=False)
        except PdfRenderError:
            raise
        except Exception as exc:
            raise PdfRenderError(f"Failed to render page {page_index + 1}.") from exc

    def _save_pixmap_atomic(
        self,
        pixmap: pymupdf.Pixmap,
        target: Path,
        settings: PdfImageExportSettings,
    ) -> None:
        output_format = OutputFormat(settings.output_format)
        with tempfile.NamedTemporaryFile(suffix=target.suffix, dir=target.parent, delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            if output_format == OutputFormat.JPG:
                image.save(temp_path, format="JPEG", quality=JpgQuality(settings.jpg_quality).quality, optimize=True)
            else:
                image.save(temp_path, format="PNG")
            temp_path.replace(target)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass


def page_output_name(stem: str, page_index: int, total_pages: int, output_format: OutputFormat) -> str:
    width = max(3, len(str(total_pages)))
    return f"{stem}_page_{page_index + 1:0{width}d}{OutputFormat(output_format).extension}"


def collision_safe_path(output_dir: Path, filename: str) -> Path:
    candidate = output_dir / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        next_candidate = output_dir / f"{stem}_{counter}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        counter += 1


def safe_filename_stem(stem: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem).strip(" ._")
    return cleaned or "document"
