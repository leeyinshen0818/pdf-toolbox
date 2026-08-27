from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from pdf_toolbox.core.pdf_to_image import (
    ConversionCancelled,
    DpiPreset,
    JpgQuality,
    OutputFormat,
    PdfImageExportSettings,
    PdfLoadError,
    PdfPageRef,
    PdfRenderError,
    PdfToImageService,
    collision_safe_path,
    page_output_name,
)
from pdf_toolbox.core.pdf_to_image_state import PdfToImageState


def make_pdf(path: Path, sizes: list[tuple[int, int]]) -> Path:
    document = pymupdf.open()
    for index, (width, height) in enumerate(sizes):
        page = document.new_page(width=width, height=height)
        page.insert_text((20, 30), f"Page {index + 1}", fontsize=14)
        page.draw_rect(page.rect, color=(0, 0, 0), width=1)
    document.save(path)
    document.close()
    return path


def make_encrypted_pdf(path: Path) -> Path:
    document = pymupdf.open()
    document.new_page(width=72, height=72)
    document.save(
        path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="secret",
    )
    document.close()
    return path


def test_valid_pdf_accepted_and_page_count_returned(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "document.pdf", [(72, 144), (144, 72)])

    info = PdfToImageService().load_pdf_info(pdf)

    assert info.filename == "document.pdf"
    assert info.page_count == 2
    assert info.file_size_bytes > 0


def test_corrupted_pdf_rejected(tmp_path: Path) -> None:
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"not a pdf")

    with pytest.raises(PdfLoadError, match="corrupted"):
        PdfToImageService().load_pdf_info(pdf)


def test_missing_pdf_rejected(tmp_path: Path) -> None:
    with pytest.raises(PdfLoadError, match="source file could not be found"):
        PdfToImageService().load_pdf_info(tmp_path / "missing.pdf")


def test_encrypted_pdf_handled_gracefully(tmp_path: Path) -> None:
    pdf = make_encrypted_pdf(tmp_path / "locked.pdf")

    with pytest.raises(PdfLoadError, match="password protected"):
        PdfToImageService().load_pdf_info(pdf)


def test_state_returns_all_loaded_pages(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "document.pdf", [(72, 72), (72, 72), (72, 72)])
    info = PdfToImageService().load_pdf_info(pdf)
    state = PdfToImageState()

    state.load_pdf(info)
    assert state.page_count == 3
    assert [ref.page_index for ref in state.all_page_refs()] == [0, 1, 2]


def test_multiple_pdfs_can_be_loaded_appended_and_duplicates_rejected(tmp_path: Path) -> None:
    first = make_pdf(tmp_path / "first.pdf", [(72, 72), (72, 72)])
    second = make_pdf(tmp_path / "second.pdf", [(72, 72)])
    service = PdfToImageService()
    state = PdfToImageState()

    assert state.add_pdf(service.load_pdf_info(first))
    assert state.add_pdf(service.load_pdf_info(second))
    assert not state.add_pdf(service.load_pdf_info(first))

    refs = state.all_page_refs()
    assert len(state.loaded_pdfs) == 2
    assert [(ref.source_filename, ref.page_index) for ref in refs] == [
        ("first.pdf", 0),
        ("first.pdf", 1),
        ("second.pdf", 0),
    ]


def test_all_page_refs_include_every_page_across_documents(tmp_path: Path) -> None:
    first = make_pdf(tmp_path / "first.pdf", [(72, 72), (72, 72)])
    second = make_pdf(tmp_path / "second.pdf", [(72, 72), (72, 72)])
    service = PdfToImageService()
    state = PdfToImageState()
    state.add_pdf(service.load_pdf_info(first))
    state.add_pdf(service.load_pdf_info(second))

    assert [(ref.source_filename, ref.page_index) for ref in state.all_page_refs()] == [
        ("first.pdf", 0),
        ("first.pdf", 1),
        ("second.pdf", 0),
        ("second.pdf", 1),
    ]


def test_jpg_output_created(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "report.pdf", [(72, 72)])

    outputs = PdfToImageService().export_pages(
        pdf,
        [0],
        tmp_path,
        PdfImageExportSettings(output_format=OutputFormat.JPG, dpi=DpiPreset.STANDARD),
    )

    assert len(outputs) == 1
    assert outputs[0].suffix == ".jpg"
    with Image.open(outputs[0]) as image:
        assert image.format == "JPEG"


def test_png_output_created(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "report.pdf", [(72, 72)])

    outputs = PdfToImageService().export_pages(
        pdf,
        [0],
        tmp_path,
        PdfImageExportSettings(output_format=OutputFormat.PNG, dpi=DpiPreset.STANDARD),
    )

    assert len(outputs) == 1
    assert outputs[0].suffix == ".png"
    with Image.open(outputs[0]) as image:
        assert image.format == "PNG"


@pytest.mark.parametrize(
    ("dpi", "expected_size"),
    [
        (DpiPreset.STANDARD, (150, 300)),
        (DpiPreset.HIGH, (300, 600)),
    ],
)
def test_rendered_dimensions_correspond_to_page_size_and_dpi(
    tmp_path: Path,
    dpi: DpiPreset,
    expected_size: tuple[int, int],
) -> None:
    pdf = make_pdf(tmp_path / "sized.pdf", [(72, 144)])

    outputs = PdfToImageService().export_pages(
        pdf,
        [0],
        tmp_path,
        PdfImageExportSettings(output_format=OutputFormat.PNG, dpi=dpi),
    )

    with Image.open(outputs[0]) as image:
        assert image.size == expected_size


def test_portrait_and_landscape_orientation_preserved(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "mixed.pdf", [(72, 144), (144, 72)])

    outputs = PdfToImageService().export_pages(
        pdf,
        [0, 1],
        tmp_path,
        PdfImageExportSettings(output_format=OutputFormat.PNG, dpi=DpiPreset.STANDARD),
    )

    with Image.open(outputs[0]) as portrait, Image.open(outputs[1]) as landscape:
        assert portrait.height > portrait.width
        assert landscape.width > landscape.height


def test_multi_page_pdf_converts_in_requested_page_order(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "report.pdf", [(72, 72), (72, 72), (72, 72)])

    outputs = PdfToImageService().export_pages(
        pdf,
        [2, 0],
        tmp_path,
        PdfImageExportSettings(output_format=OutputFormat.PNG, dpi=DpiPreset.STANDARD),
    )

    assert [path.name for path in outputs] == ["report_page_003.png", "report_page_001.png"]


def test_page_refs_from_multiple_pdfs_export_with_source_names(tmp_path: Path) -> None:
    first = make_pdf(tmp_path / "report.pdf", [(72, 72), (72, 72)])
    second = make_pdf(tmp_path / "invoice.pdf", [(72, 72), (72, 72)])
    refs = (
        PdfPageRef(first, "report.pdf", 1, 2),
        PdfPageRef(second, "invoice.pdf", 0, 2),
    )

    outputs = PdfToImageService().export_page_refs(
        refs,
        tmp_path,
        PdfImageExportSettings(output_format=OutputFormat.PNG, dpi=DpiPreset.STANDARD),
    )

    assert [path.name for path in outputs] == ["report_page_002.png", "invoice_page_001.png"]
    assert all(path.exists() for path in outputs)


def test_same_basename_pdfs_use_collision_safe_names(tmp_path: Path) -> None:
    first_dir = tmp_path / "one"
    second_dir = tmp_path / "two"
    first_dir.mkdir()
    second_dir.mkdir()
    first = make_pdf(first_dir / "report.pdf", [(72, 72)])
    second = make_pdf(second_dir / "report.pdf", [(72, 72)])
    refs = (
        PdfPageRef(first, "report.pdf", 0, 1),
        PdfPageRef(second, "report.pdf", 0, 1),
    )

    outputs = PdfToImageService().export_page_refs(
        refs,
        tmp_path,
        PdfImageExportSettings(output_format=OutputFormat.JPG, dpi=DpiPreset.STANDARD),
    )

    assert [path.name for path in outputs] == ["report_page_001.jpg", "report_page_001_1.jpg"]


def test_automatic_page_naming_and_zero_padding() -> None:
    assert page_output_name("report", 0, 3, OutputFormat.JPG) == "report_page_001.jpg"
    assert page_output_name("report", 249, 250, OutputFormat.PNG) == "report_page_250.png"
    assert page_output_name("report", 1499, 1500, OutputFormat.JPG) == "report_page_1500.jpg"


def test_collision_safe_naming(tmp_path: Path) -> None:
    existing = tmp_path / "report_page_001.jpg"
    existing.write_bytes(b"already here")

    assert collision_safe_path(tmp_path, "report_page_001.jpg").name == "report_page_001_1.jpg"

    (tmp_path / "report_page_001_1.jpg").write_bytes(b"also here")
    assert collision_safe_path(tmp_path, "report_page_001.jpg").name == "report_page_001_2.jpg"


def test_existing_files_are_not_silently_overwritten(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "report.pdf", [(72, 72)])
    existing = tmp_path / "report_page_001.jpg"
    existing.write_bytes(b"original")

    outputs = PdfToImageService().export_pages(
        pdf,
        [0],
        tmp_path,
        PdfImageExportSettings(output_format=OutputFormat.JPG, jpg_quality=JpgQuality.MAXIMUM),
    )

    assert existing.read_bytes() == b"original"
    assert outputs[0].name == "report_page_001_1.jpg"


def test_explicit_page_indices_are_exported(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "report.pdf", [(72, 72), (72, 72), (72, 72)])

    outputs = PdfToImageService().export_pages(
        pdf,
        [1],
        tmp_path,
        PdfImageExportSettings(output_format=OutputFormat.PNG, dpi=DpiPreset.STANDARD),
    )

    assert len(outputs) == 1
    assert outputs[0].name == "report_page_002.png"


def test_empty_page_selection_rejected(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "report.pdf", [(72, 72)])

    with pytest.raises(PdfRenderError, match="No pages available"):
        PdfToImageService().export_pages(pdf, [], tmp_path, PdfImageExportSettings())


def test_cancellation_stops_before_later_pages_and_keeps_completed_files(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "report.pdf", [(72, 72), (72, 72), (72, 72)])
    cancel = {"requested": False}

    def on_progress(current: int, total: int, page_index: int, path: Path) -> None:
        cancel["requested"] = True

    with pytest.raises(ConversionCancelled) as exc_info:
        PdfToImageService().export_pages(
            pdf,
            [0, 1, 2],
            tmp_path,
            PdfImageExportSettings(output_format=OutputFormat.PNG, dpi=DpiPreset.STANDARD),
            progress_callback=on_progress,
            cancel_callback=lambda: cancel["requested"],
        )

    assert len(exc_info.value.completed_paths) == 1
    assert exc_info.value.completed_paths[0].exists()
    assert not (tmp_path / "report_page_002.png").exists()
