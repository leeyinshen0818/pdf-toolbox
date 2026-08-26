from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pdf_toolbox.core.pdf_to_image import DpiPreset, JpgQuality, OutputFormat, PdfInfo


@dataclass
class PdfToImageState:
    pdf_info: PdfInfo | None = None
    selected_pages: set[int] = field(default_factory=set)
    active_page_index: int | None = None
    output_format: OutputFormat = OutputFormat.JPG
    dpi: DpiPreset = DpiPreset.HIGH
    jpg_quality: JpgQuality = JpgQuality.HIGH
    output_folder: Path | None = None

    def load_pdf(self, info: PdfInfo) -> None:
        self.pdf_info = info
        self.selected_pages = set(range(info.page_count))
        self.active_page_index = 0

    def clear_pdf(self) -> None:
        self.pdf_info = None
        self.selected_pages.clear()
        self.active_page_index = None

    def toggle_page(self, page_index: int) -> None:
        self._require_valid_page(page_index)
        if page_index in self.selected_pages:
            self.selected_pages.remove(page_index)
        else:
            self.selected_pages.add(page_index)
        self.active_page_index = page_index

    def set_active_page(self, page_index: int) -> None:
        self._require_valid_page(page_index)
        self.active_page_index = page_index

    def select_all(self) -> None:
        if self.pdf_info is None:
            return
        self.selected_pages = set(range(self.pdf_info.page_count))

    def clear_selection(self) -> None:
        self.selected_pages.clear()

    def ordered_selected_pages(self) -> tuple[int, ...]:
        return tuple(sorted(self.selected_pages))

    def _require_valid_page(self, page_index: int) -> None:
        if self.pdf_info is None:
            raise ValueError("No PDF is loaded.")
        if page_index < 0 or page_index >= self.pdf_info.page_count:
            raise ValueError("Page index is outside the PDF page range.")
