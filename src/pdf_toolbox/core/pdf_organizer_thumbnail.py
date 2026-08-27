from __future__ import annotations

from pathlib import Path

import pymupdf


class PdfOrganizerThumbnailError(Exception):
    """Raised when a page thumbnail cannot be rendered."""


class PdfOrganizerThumbnailService:
    def render_page_png_bytes(self, path: str | Path, page_index: int, rotation: int, dpi: int = 54) -> bytes:
        try:
            with pymupdf.open(Path(path)) as document:
                if document.needs_pass:
                    raise PdfOrganizerThumbnailError("This PDF is password protected and cannot be opened.")
                if page_index < 0 or page_index >= document.page_count:
                    raise PdfOrganizerThumbnailError("Page is outside the PDF page range.")
                page = document.load_page(page_index)
                matrix = pymupdf.Matrix(dpi / 72, dpi / 72).prerotate(rotation)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                return pixmap.tobytes("png")
        except PdfOrganizerThumbnailError:
            raise
        except Exception as exc:
            raise PdfOrganizerThumbnailError("Preview unavailable for this page.") from exc
