from __future__ import annotations

from pathlib import Path
from typing import Callable

import pymupdf

from pdf_toolbox.core.pdf_organizer import OrganizerPage


class PdfOrganizerExportError(Exception):
    """Raised when the organizer cannot export the arranged PDF."""


ProgressCallback = Callable[[int, int], None]


class PdfOrganizerExporter:
    def export(
        self,
        pages: tuple[OrganizerPage, ...],
        output_path: str | Path,
        *,
        overwrite: bool = False,
        progress_callback: ProgressCallback | None = None,
    ) -> Path:
        if not pages:
            raise PdfOrganizerExportError("No pages to export.")

        target = Path(output_path)
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")
        if not target.parent.exists():
            raise PdfOrganizerExportError("The selected output folder is no longer available.")
        target_key = resolved_key(target)
        if any(resolved_key(page.source_path) == target_key for page in pages):
            raise PdfOrganizerExportError("Export path cannot be one of the source PDFs.")
        if target.exists() and not overwrite:
            raise PdfOrganizerExportError("Output PDF already exists.")
        if target.exists() and overwrite:
            try:
                target.unlink()
            except OSError as exc:
                raise PdfOrganizerExportError("Could not replace the existing output PDF.") from exc

        sources: dict[Path, pymupdf.Document] = {}
        output = pymupdf.open()
        try:
            for done, page in enumerate(pages, start=1):
                source_path = Path(page.source_path)
                if not source_path.exists():
                    raise PdfOrganizerExportError(f"The source file could not be found: {source_path.name}")
                document = sources.get(source_path)
                if document is None:
                    try:
                        document = pymupdf.open(source_path)
                    except Exception as exc:
                        raise PdfOrganizerExportError(f"The PDF appears to be corrupted: {source_path.name}") from exc
                    if document.needs_pass:
                        raise PdfOrganizerExportError(f"This PDF is password protected and cannot be opened: {source_path.name}")
                    sources[source_path] = document

                if page.source_page_index < 0 or page.source_page_index >= document.page_count:
                    raise PdfOrganizerExportError(
                        f"Source page is unavailable: {page.source_filename} page {page.source_page_index + 1}"
                    )

                output.insert_pdf(document, from_page=page.source_page_index, to_page=page.source_page_index)
                exported_page = output[-1]
                rotation = (exported_page.rotation + page.rotation) % 360
                exported_page.set_rotation(rotation)
                if progress_callback is not None:
                    progress_callback(done, len(pages))

            output.save(target)
        except Exception:
            if target.exists():
                try:
                    target.unlink()
                except OSError:
                    pass
            raise
        finally:
            output.close()
            for document in sources.values():
                document.close()

        return target


def resolved_key(path: str | Path) -> str:
    return str(Path(path).resolve(strict=False)).casefold()
