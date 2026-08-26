from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from pdf_toolbox.core.pdf_to_image import DpiPreset, JpgQuality, OutputFormat, PdfInfo, PdfPageRef


@dataclass(frozen=True)
class LoadedPdf:
    info: PdfInfo
    source_key: str


@dataclass
class PdfToImageState:
    loaded_pdfs: list[LoadedPdf] = field(default_factory=list)
    output_format: OutputFormat = OutputFormat.JPG
    dpi: DpiPreset = DpiPreset.HIGH
    jpg_quality: JpgQuality = JpgQuality.MAXIMUM
    output_folder: Path | None = None

    @property
    def pdf_info(self) -> PdfInfo | None:
        return self.loaded_pdfs[0].info if self.loaded_pdfs else None

    def load_pdf(self, info: PdfInfo) -> bool:
        return self.add_pdf(info)

    def add_pdf(self, info: PdfInfo) -> bool:
        key = pdf_key(info.path)
        if any(document.source_key == key for document in self.loaded_pdfs):
            return False

        self.loaded_pdfs.append(LoadedPdf(info=info, source_key=key))
        return True

    def clear_pdf(self) -> None:
        self.clear_all()

    def clear_all(self) -> None:
        self.loaded_pdfs.clear()

    def remove_pdf(self, source_key: str) -> None:
        self.loaded_pdfs = [document for document in self.loaded_pdfs if document.source_key != source_key]

    def all_page_refs(self) -> tuple[PdfPageRef, ...]:
        return tuple(
            self.page_ref(document.source_key, page_index)
            for document in self.loaded_pdfs
            for page_index in range(document.info.page_count)
        )

    @property
    def page_count(self) -> int:
        return sum(document.info.page_count for document in self.loaded_pdfs)

    def page_ref(self, source_key: str, page_index: int) -> PdfPageRef:
        document = self.document_for_key(source_key)
        if document is None:
            raise ValueError("PDF source is not loaded.")
        if page_index < 0 or page_index >= document.info.page_count:
            raise ValueError("Page index is outside the PDF page range.")
        return PdfPageRef(
            source_path=document.info.path,
            source_filename=document.info.filename,
            page_index=page_index,
            page_count=document.info.page_count,
        )

    def document_for_key(self, source_key: str) -> LoadedPdf | None:
        for document in self.loaded_pdfs:
            if document.source_key == source_key:
                return document
        return None

    def first_page_key(self) -> tuple[str, int] | None:
        if not self.loaded_pdfs:
            return None
        return (self.loaded_pdfs[0].source_key, 0)


def pdf_key(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).resolve(strict=False)))
