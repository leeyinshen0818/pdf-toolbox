from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from pdf_toolbox.core.pdf_organizer import OrganizerHistory, PdfOrganizerWorkspace
from pdf_toolbox.core.pdf_organizer_exporter import PdfOrganizerExportError, PdfOrganizerExporter
from pdf_toolbox.core.pdf_to_image import PdfToImageService


def make_pdf(path: Path, labels: list[str]) -> Path:
    document = pymupdf.open()
    for label in labels:
        page = document.new_page(width=144, height=144)
        page.insert_text((24, 72), label, fontsize=16)
    document.save(path)
    document.close()
    return path


def page_texts(path: Path) -> list[str]:
    with pymupdf.open(path) as document:
        return [document[index].get_text().strip() for index in range(document.page_count)]


def load_workspace(*pdfs: Path) -> PdfOrganizerWorkspace:
    service = PdfToImageService()
    workspace = PdfOrganizerWorkspace()
    for pdf in pdfs:
        workspace.add_pdf(service.load_pdf_info(pdf))
    return workspace


def test_pages_from_one_pdf_load_in_correct_order(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "one.pdf", ["A1", "A2", "A3"])
    workspace = load_workspace(pdf)

    assert [(page.source_filename, page.source_page_index) for page in workspace.pages] == [
        ("one.pdf", 0),
        ("one.pdf", 1),
        ("one.pdf", 2),
    ]


def test_pages_from_multiple_pdfs_load_in_correct_order(tmp_path: Path) -> None:
    first = make_pdf(tmp_path / "a.pdf", ["A1", "A2"])
    second = make_pdf(tmp_path / "b.pdf", ["B1", "B2"])
    workspace = load_workspace(first, second)

    assert [(page.source_filename, page.source_page_index) for page in workspace.pages] == [
        ("a.pdf", 0),
        ("a.pdf", 1),
        ("b.pdf", 0),
        ("b.pdf", 1),
    ]


def test_duplicate_sources_are_rejected(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "a.pdf", ["A1"])
    service = PdfToImageService()
    workspace = PdfOrganizerWorkspace()

    assert workspace.add_pdf(service.load_pdf_info(pdf))
    assert workspace.add_pdf(service.load_pdf_info(pdf)) == []
    assert len(workspace.pages) == 1


def test_reorder_updates_state_and_supports_edges(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "a.pdf", ["A1", "A2", "A3"])
    workspace = load_workspace(pdf)

    workspace.move_page(0, 2)
    assert [page.source_page_index for page in workspace.pages] == [1, 2, 0]

    workspace.move_page(2, 0)
    assert [page.source_page_index for page in workspace.pages] == [0, 1, 2]

    ids = workspace.page_ids()
    workspace.reorder_by_ids([ids[0], ids[2], ids[1]])
    assert [page.source_page_index for page in workspace.pages] == [0, 2, 1]


def test_cross_pdf_reordering_keeps_source_references(tmp_path: Path) -> None:
    first = make_pdf(tmp_path / "a.pdf", ["A1", "A2"])
    second = make_pdf(tmp_path / "b.pdf", ["B1", "B2"])
    workspace = load_workspace(first, second)
    pages = workspace.pages

    workspace.reorder_by_ids([pages[0].page_id, pages[3].page_id, pages[1].page_id, pages[2].page_id])

    assert [(page.source_filename, page.source_page_index) for page in workspace.pages] == [
        ("a.pdf", 0),
        ("b.pdf", 1),
        ("a.pdf", 1),
        ("b.pdf", 0),
    ]


def test_duplicate_delete_and_rotation_state(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "a.pdf", ["A1", "A2", "A3"])
    workspace = load_workspace(pdf)
    first_id = workspace.pages[0].page_id
    second_id = workspace.pages[1].page_id

    duplicated = workspace.duplicate_pages({first_id, second_id})
    assert len(duplicated) == 2
    assert [page.source_page_index for page in workspace.pages] == [0, 0, 1, 1, 2]
    assert duplicated[0].duplicate_of == first_id

    workspace.delete_pages({duplicated[0].page_id, workspace.pages[-1].page_id})
    assert [page.source_page_index for page in workspace.pages] == [0, 1, 1]

    workspace.rotate_pages({first_id}, 90)
    workspace.rotate_pages({first_id}, 90)
    workspace.rotate_pages({first_id}, 180)
    assert workspace.pages[0].rotation == 0
    workspace.rotate_pages({first_id}, -90)
    assert workspace.pages[0].rotation == 270


def test_undo_redo_reorder_delete_duplicate_rotate_and_redo_clear(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "a.pdf", ["A1", "A2", "A3"])
    workspace = load_workspace(pdf)
    history = OrganizerHistory()

    history.record(workspace.snapshot())
    workspace.move_page(0, 2)
    history.record(workspace.snapshot())
    removed = workspace.delete_pages({workspace.pages[0].page_id})
    history.record(workspace.snapshot())
    duplicated = workspace.duplicate_pages({workspace.pages[0].page_id})
    history.record(workspace.snapshot())
    workspace.rotate_pages({workspace.pages[0].page_id}, 90)

    snapshot = history.undo(workspace.snapshot())
    assert snapshot is not None
    workspace.restore(snapshot)
    assert workspace.pages[0].rotation == 0

    snapshot = history.undo(workspace.snapshot())
    assert snapshot is not None
    workspace.restore(snapshot)
    assert all(page.page_id != duplicated[0].page_id for page in workspace.pages)

    snapshot = history.undo(workspace.snapshot())
    assert snapshot is not None
    workspace.restore(snapshot)
    assert any(page.page_id == removed[0].page_id for page in workspace.pages)

    snapshot = history.redo(workspace.snapshot())
    assert snapshot is not None
    workspace.restore(snapshot)
    assert all(page.page_id != removed[0].page_id for page in workspace.pages)

    history.record(workspace.snapshot())
    workspace.rotate_pages({workspace.pages[0].page_id}, 90)
    assert not history.can_redo


def test_export_one_pdf_unchanged_preserves_text(tmp_path: Path) -> None:
    source = make_pdf(tmp_path / "source.pdf", ["A1", "A2"])
    workspace = load_workspace(source)
    output = tmp_path / "organized.pdf"

    PdfOrganizerExporter().export(tuple(workspace.pages), output)

    assert page_texts(output) == ["A1", "A2"]


def test_export_reordered_pages_from_multiple_pdfs(tmp_path: Path) -> None:
    first = make_pdf(tmp_path / "a.pdf", ["A1", "A2"])
    second = make_pdf(tmp_path / "b.pdf", ["B1", "B2"])
    workspace = load_workspace(first, second)
    pages = workspace.pages
    workspace.reorder_by_ids([pages[3].page_id, pages[0].page_id, pages[2].page_id, pages[1].page_id])
    output = tmp_path / "organized.pdf"

    PdfOrganizerExporter().export(tuple(workspace.pages), output)

    assert page_texts(output) == ["B2", "A1", "B1", "A2"]


def test_export_excludes_deleted_pages_and_includes_duplicates(tmp_path: Path) -> None:
    source = make_pdf(tmp_path / "source.pdf", ["A1", "A2", "A3"])
    workspace = load_workspace(source)
    workspace.delete_pages({workspace.pages[2].page_id})
    workspace.duplicate_pages({workspace.pages[0].page_id})
    output = tmp_path / "organized.pdf"

    PdfOrganizerExporter().export(tuple(workspace.pages), output)

    assert page_texts(output) == ["A1", "A1", "A2"]


def test_export_applies_rotation(tmp_path: Path) -> None:
    source = make_pdf(tmp_path / "source.pdf", ["A1"])
    workspace = load_workspace(source)
    workspace.rotate_pages({workspace.pages[0].page_id}, 90)
    output = tmp_path / "organized.pdf"

    PdfOrganizerExporter().export(tuple(workspace.pages), output)

    with pymupdf.open(output) as document:
        assert document.page_count == 1
        assert document[0].rotation == 90


def test_export_does_not_modify_or_overwrite_source_pdf(tmp_path: Path) -> None:
    source = make_pdf(tmp_path / "source.pdf", ["A1"])
    before = source.read_bytes()
    before_mtime = source.stat().st_mtime_ns
    workspace = load_workspace(source)

    with pytest.raises(PdfOrganizerExportError, match="source PDFs"):
        PdfOrganizerExporter().export(tuple(workspace.pages), source, overwrite=True)

    assert source.read_bytes() == before
    assert source.stat().st_mtime_ns == before_mtime


def test_export_missing_source_fails_cleanly_without_output(tmp_path: Path) -> None:
    source = make_pdf(tmp_path / "source.pdf", ["A1"])
    workspace = load_workspace(source)
    source.unlink()
    output = tmp_path / "organized.pdf"

    with pytest.raises(PdfOrganizerExportError, match="missing"):
        PdfOrganizerExporter().export(tuple(workspace.pages), output)

    assert not output.exists()


def test_clear_workspace_does_not_delete_source_files(tmp_path: Path) -> None:
    source = make_pdf(tmp_path / "source.pdf", ["A1"])
    workspace = load_workspace(source)

    workspace.clear()

    assert source.exists()
    assert workspace.pages == []
