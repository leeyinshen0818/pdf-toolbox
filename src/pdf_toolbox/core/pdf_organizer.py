from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from pdf_toolbox.core.pdf_to_image import PdfInfo


@dataclass(frozen=True)
class OrganizerPage:
    page_id: str
    source_path: Path
    source_filename: str
    source_page_index: int
    source_page_count: int
    rotation: int = 0
    duplicate_of: str | None = None

    @property
    def source_label(self) -> str:
        return f"{self.source_filename} - Original page {self.source_page_index + 1}"

    @property
    def thumbnail_key(self) -> tuple[str, int, int]:
        return (pdf_key(self.source_path), self.source_page_index, self.rotation)


@dataclass(frozen=True)
class OrganizerSnapshot:
    pages: tuple[OrganizerPage, ...]
    loaded_sources: frozenset[str]


class PdfOrganizerWorkspace:
    def __init__(self) -> None:
        self.pages: list[OrganizerPage] = []
        self.loaded_sources: set[str] = set()

    def add_pdf(self, info: PdfInfo) -> list[OrganizerPage]:
        source_key = pdf_key(info.path)
        if source_key in self.loaded_sources:
            return []

        pages = [
            OrganizerPage(
                page_id=new_page_id(),
                source_path=info.path,
                source_filename=info.filename,
                source_page_index=page_index,
                source_page_count=info.page_count,
            )
            for page_index in range(info.page_count)
        ]
        self.pages.extend(pages)
        self.loaded_sources.add(source_key)
        return pages

    def clear(self) -> None:
        self.pages.clear()
        self.loaded_sources.clear()

    def reorder_by_ids(self, page_ids: list[str]) -> None:
        if set(page_ids) != {page.page_id for page in self.pages} or len(page_ids) != len(self.pages):
            raise ValueError("Page IDs do not match the workspace.")
        lookup = {page.page_id: page for page in self.pages}
        self.pages = [lookup[page_id] for page_id in page_ids]

    def move_page(self, from_index: int, to_index: int) -> None:
        if from_index < 0 or from_index >= len(self.pages):
            raise ValueError("Source index is outside the workspace.")
        if to_index < 0 or to_index >= len(self.pages):
            raise ValueError("Target index is outside the workspace.")
        page = self.pages.pop(from_index)
        self.pages.insert(to_index, page)

    def delete_pages(self, page_ids: set[str]) -> list[OrganizerPage]:
        removed = [page for page in self.pages if page.page_id in page_ids]
        self.pages = [page for page in self.pages if page.page_id not in page_ids]
        return removed

    def duplicate_pages(self, page_ids: set[str]) -> list[OrganizerPage]:
        duplicated: list[OrganizerPage] = []
        index = 0
        while index < len(self.pages):
            page = self.pages[index]
            if page.page_id in page_ids:
                duplicate = replace(
                    page,
                    page_id=new_page_id(),
                    duplicate_of=page.duplicate_of or page.page_id,
                )
                self.pages.insert(index + 1, duplicate)
                duplicated.append(duplicate)
                index += 2
            else:
                index += 1
        return duplicated

    def rotate_pages(self, page_ids: set[str], degrees: int) -> None:
        self.pages = [
            replace(page, rotation=(page.rotation + degrees) % 360) if page.page_id in page_ids else page
            for page in self.pages
        ]

    def page_ids(self) -> list[str]:
        return [page.page_id for page in self.pages]

    def snapshot(self) -> OrganizerSnapshot:
        return OrganizerSnapshot(tuple(self.pages), frozenset(self.loaded_sources))

    def restore(self, snapshot: OrganizerSnapshot) -> None:
        self.pages = list(snapshot.pages)
        self.loaded_sources = set(snapshot.loaded_sources)


class OrganizerHistory:
    def __init__(self) -> None:
        self.undo_stack: list[OrganizerSnapshot] = []
        self.redo_stack: list[OrganizerSnapshot] = []

    def record(self, snapshot: OrganizerSnapshot) -> None:
        self.undo_stack.append(snapshot)
        self.redo_stack.clear()

    def undo(self, current: OrganizerSnapshot) -> OrganizerSnapshot | None:
        if not self.undo_stack:
            return None
        self.redo_stack.append(current)
        return self.undo_stack.pop()

    def redo(self, current: OrganizerSnapshot) -> OrganizerSnapshot | None:
        if not self.redo_stack:
            return None
        self.undo_stack.append(current)
        return self.redo_stack.pop()

    def clear(self) -> None:
        self.undo_stack.clear()
        self.redo_stack.clear()

    @property
    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self.redo_stack)


def pdf_key(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).resolve(strict=False)))


def new_page_id() -> str:
    return uuid.uuid4().hex
