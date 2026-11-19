from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pdf_toolbox.core.conversion_preferences import (
    PDF_TO_IMAGE_SETTING_KEYS,
    PdfToImagePreferences,
    pdf_to_image_preferences_from_values,
    pdf_to_image_preferences_to_values,
)
from pdf_toolbox.core.output_location import open_output_location
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
)
from pdf_toolbox.core.pdf_to_image_state import LoadedPdf, PdfToImageState
from pdf_toolbox.ui.components.drop_area import empty_drop_area
from pdf_toolbox.ui.components.file_list import FileListWidget, FileRowWidget, file_size_text, row_placeholder, row_thumbnail
from pdf_toolbox.ui.components.page import ToolPage
from pdf_toolbox.ui.components.settings_panel import SettingsPanel
from pdf_toolbox.ui.components.widgets import JPG_QUALITY_CHOICES, default_output_folder, enum_combo, labeled_control
from pdf_toolbox.ui.threads import keep_alive_until_finished, thread_is_running
from pdf_toolbox.ui.metrics import file_row_size_hint
from pdf_toolbox.ui.tokens import SPACE_12, SPACE_4, WARNING_TEXT


SOURCE_KEY_ROLE = Qt.UserRole + 11
OUTPUT_FOLDER_SETTING = "pdf_to_image/output_folder"
THUMBNAIL_DPI = 24  # first page only, shown at row-thumbnail size; leaves headroom for HiDPI screens
FILE_ERROR_MESSAGE = "Couldn't open {filename}. Remove it and try again."
CONVERSION_FAILED_MESSAGE = (
    "The pages could not be converted. Check that the PDF still opens and that the output folder "
    "is available, then try again."
)
WORK_AREA_MIN_HEIGHT = 200  # the PDF list shrinks and scrolls so the page fits 1366x768
logger = logging.getLogger(__name__)


class ThumbnailWorker(QObject):
    thumbnail_ready = Signal(str, int, bytes)
    thumbnail_failed = Signal(str, int, str)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, requests: tuple[tuple[str, Path, int], ...], dpi: int = THUMBNAIL_DPI) -> None:
        super().__init__()
        self.requests = requests
        self.dpi = dpi
        self.service = PdfToImageService()
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self) -> None:
        for source_key, path, page_index in self.requests:
            if self.cancelled:
                break
            try:
                data = self.service.render_page_png_bytes(path, page_index, dpi=self.dpi)
            except Exception as exc:
                logger.exception("PDF page thumbnail generation failed")
                self.thumbnail_failed.emit(source_key, page_index, str(exc))
                continue
            self.thumbnail_ready.emit(source_key, page_index, data)
        self.finished.emit()


class ConversionWorker(QObject):
    progress = Signal(int, int, int, str)
    finished = Signal(object)
    cancelled = Signal(object)
    failed = Signal(str, str)  # log details, name of the PDF at fault ("" if none)

    def __init__(
        self,
        page_refs: tuple[PdfPageRef, ...],
        output_folder: Path,
        settings: PdfImageExportSettings,
    ) -> None:
        super().__init__()
        self.page_refs = page_refs
        self.output_folder = output_folder
        self.settings = settings
        self.service = PdfToImageService()
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True

    def run(self) -> None:
        try:
            paths = self.service.export_page_refs(
                self.page_refs,
                self.output_folder,
                self.settings,
                progress_callback=self._on_progress,
                cancel_callback=lambda: self.cancel_requested,
            )
        except ConversionCancelled as exc:
            self.cancelled.emit(exc.completed_paths)
            return
        except Exception as exc:
            logger.exception("PDF to image conversion failed")
            filename = exc.filename if isinstance(exc, PdfRenderError) else None
            self.failed.emit(str(exc), filename or "")
            return
        self.finished.emit(paths)

    def _on_progress(self, current: int, total: int, page_index: int, path: Path) -> None:
        self.progress.emit(current, total, page_index, str(path))


class PdfToImagePage(ToolPage):
    ACCEPTED_EXTENSIONS = frozenset({".pdf"})
    ACCEPTED_DESCRIPTION = "PDF files"

    def __init__(self) -> None:
        super().__init__()
        self.service = PdfToImageService()
        self.state = PdfToImageState()
        self.thumbnail_thread: QThread | None = None
        self.thumbnail_worker: ThumbnailWorker | None = None
        self.thumbnail_cache: dict[str, QPixmap] = {}  # first-page thumbnail per PDF source key
        self.conversion_thread: QThread | None = None
        self.conversion_worker: ConversionWorker | None = None
        self.open_output_location = open_output_location

        self._build_ui()
        self._load_output_folder_setting()
        self._load_preferences()
        self._update_pdf_info()
        self._update_state()

    def _build_ui(self) -> None:
        self.build_scaffold(
            "PDF → Image",
            "Every page of each PDF you add is saved as its own JPG or PNG image.",
        )

        self.add_button = QPushButton("Add PDFs")
        self.add_button.setObjectName("PrimaryButton")
        self.clear_button = QPushButton("Clear")
        self.add_button.clicked.connect(self._choose_pdf)
        self.clear_button.clicked.connect(self._clear_pdf)
        self.action_bar.addWidget(self.add_button)
        self.action_bar.addWidget(self.clear_button)
        self.finish_action_bar()

        self.pdf_info_label = self.count_label

        self.main_section = QWidget()
        main_area = QVBoxLayout(self.main_section)
        main_area.setContentsMargins(0, 0, 0, 0)
        main_area.setSpacing(SPACE_12)

        self.stack = QStackedWidget()
        self.empty_state, empty = empty_drop_area(
            "Add PDF files to turn their pages into images",
            "You can add several PDFs. Every page of each one is converted.",
            "Add PDFs",
        )
        self.empty_state.files_dropped.connect(self.add_dropped_files)
        empty.action_requested.connect(self._choose_pdf)
        self.file_list = FileListWidget(QListWidget.NoSelection)
        self.file_list.files_dropped.connect(self.add_dropped_files)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.file_list)
        self.stack.setMinimumSize(520, WORK_AREA_MIN_HEIGHT)

        main_area.addWidget(self.stack, 1)

        self.settings_panel = self._build_settings_panel()
        self.content_layout.addWidget(self.main_section, 1)
        self.content_layout.addWidget(self.settings_panel)

    def _build_settings_panel(self) -> SettingsPanel:
        panel = SettingsPanel("Conversion Settings", "Convert All Pages", min_width=340, max_width=430)
        layout = panel.body_layout

        self.format_combo = enum_combo(OutputFormat, min_contents_length=14, popup_min_width=320)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        layout.addLayout(labeled_control("Format", self.format_combo))

        self.dpi_combo = enum_combo(DpiPreset, min_contents_length=14, popup_min_width=320)
        self.dpi_combo.setCurrentIndex(self.dpi_combo.findData(DpiPreset.HIGH.value))
        self.dpi_combo.currentIndexChanged.connect(self._save_preferences)
        layout.addLayout(labeled_control("Resolution", self.dpi_combo))

        self.jpg_quality_container = QWidget()
        self.jpg_quality_combo = enum_combo(
            JpgQuality, min_contents_length=14, popup_min_width=320, choices=JPG_QUALITY_CHOICES
        )
        jpg_quality_layout = labeled_control("JPG Quality", self.jpg_quality_combo)
        jpg_quality_layout.setContentsMargins(0, 0, 0, 0)  # line up with the fields above and below
        self.jpg_quality_combo.setCurrentIndex(self.jpg_quality_combo.findData(JpgQuality.MAXIMUM.value))
        self.jpg_quality_combo.currentIndexChanged.connect(self._save_preferences)
        self.jpg_quality_container.setLayout(jpg_quality_layout)
        layout.addWidget(self.jpg_quality_container)

        output_label = QLabel("Output Folder")
        output_label.setObjectName("FieldLabel")
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setReadOnly(True)
        self.output_folder_edit.setAcceptDrops(False)  # let file drops reach the window
        self.output_folder_edit.setPlaceholderText("Choose a folder")
        self.output_folder_edit.setMinimumWidth(150)
        self.output_folder_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.browse_output_folder_button = QPushButton("Browse")
        self.browse_output_folder_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.browse_output_folder_button.clicked.connect(self._choose_output_folder)
        output_row = QHBoxLayout()
        output_row.setSpacing(SPACE_4)
        output_row.addWidget(self.output_folder_edit, 1)
        output_row.addWidget(self.browse_output_folder_button)
        layout.addWidget(output_label)
        layout.addLayout(output_row)
        panel.finish_body()

        self.job_footer = panel.footer
        self.convert_button = panel.footer.primary_button
        self.convert_button.clicked.connect(self._start_conversion)
        self.progress_bar = panel.footer.progress_bar
        self.cancel_button = panel.footer.cancel_button
        panel.footer.cancel_requested.connect(self._cancel_conversion)
        return panel

    # ---------------------------------------------------------------- adding and removing
    def _choose_pdf(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select PDFs", "", "PDF files (*.pdf)")
        if file_paths:
            self._add_pdf_paths(file_paths)

    def add_files(self, paths: list[str]) -> None:
        self._add_pdf_paths(paths)

    def _add_pdf_paths(self, paths: list[str]) -> None:
        pdf_paths = [Path(path) for path in paths if Path(path).suffix.lower() == ".pdf"]
        if not pdf_paths:
            self.status_label.setText("Unsupported file type. Use a PDF file.")
            return
        self._load_pdfs(pdf_paths)

    def _load_pdfs(self, paths: list[Path]) -> None:
        added = 0
        duplicates = 0
        errors: list[tuple[str, str]] = []

        for path in paths:
            try:
                info = self.service.load_pdf_info(path)
            except PdfLoadError as exc:
                errors.append((path.name, str(exc)))
                continue
            if not self.state.add_pdf(info):
                duplicates += 1
                continue
            added += 1

        self._populate_rows()
        self._update_pdf_info()
        self._update_state()
        self._start_thumbnail_worker()

        if errors:
            names = ", ".join(name for name, _reason in errors[:3]) + (", ..." if len(errors) > 3 else "")
            message = f"Couldn't open {names}. " + ("It was" if len(errors) == 1 else "They were") + " not added."
            if added:
                message = f"Added {added} PDF(s). {message}"
            self.status_label.show_warning(message)
            details = "\n".join(f"{name}: {reason}" for name, reason in errors[:8])
            QMessageBox.warning(self, "Some PDFs Were Not Added", details)
            return
        messages: list[str] = []
        if added:
            messages.append(f"Added {added} PDF(s).")
        if duplicates:
            messages.append(f"Skipped {duplicates} duplicate PDF(s).")
        if duplicates:
            self.status_label.show_warning(" ".join(messages))
        else:
            self.status_label.setText(" ".join(messages) if messages else "No PDFs added.")

    def _populate_rows(self) -> None:
        self.file_list.clear()
        for document in self.state.loaded_pdfs:
            item = QListWidgetItem()
            item.setData(SOURCE_KEY_ROLE, document.source_key)
            item.setSizeHint(file_row_size_hint())
            self.file_list.addItem(item)
            row = FileRowWidget(
                document.source_key,
                document.info.filename,
                pdf_row_detail(document),
                self.thumbnail_cache.get(document.source_key) or row_placeholder("file-image"),
                tooltip=str(document.info.path),
                delete_tooltip="Remove this PDF",
            )
            row.delete_requested.connect(self._remove_pdf)
            self.file_list.setItemWidget(item, row)

    def _remove_pdf(self, source_key: str) -> None:
        document = self.state.document_for_key(source_key)
        self.state.remove_pdf(source_key)
        self.thumbnail_cache.pop(source_key, None)
        self._populate_rows()
        self._update_pdf_info()
        self._update_state()
        if document is not None:
            self.status_label.setText(f"Removed {document.info.filename}.")

    def _clear_pdf(self) -> None:
        self._stop_thumbnail_worker()
        self.state.clear_pdf()
        self.file_list.clear()
        self.thumbnail_cache.clear()
        self._update_pdf_info()
        self.status_label.setText("PDF list cleared.")
        self._update_state()

    # ---------------------------------------------------------------- first-page thumbnails
    def _start_thumbnail_worker(self) -> None:
        requests = self._thumbnail_requests()
        if not requests:
            return
        self._stop_thumbnail_worker()  # its remaining requests are part of the new list
        thread = QThread()
        worker = ThumbnailWorker(requests)
        self.thumbnail_thread = thread
        self.thumbnail_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        worker.thumbnail_failed.connect(self._on_thumbnail_preview_failed)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._on_thumbnail_thread_finished)  # queued to the GUI thread
        keep_alive_until_finished(thread, worker)  # never deleted while running, even if this page is
        thread.start()

    def _stop_thumbnail_worker(self) -> None:
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.cancel()

    def _thumbnail_requests(self) -> tuple[tuple[str, Path, int], ...]:
        """Only the first page of each PDF that has no thumbnail yet."""
        return tuple(
            (document.source_key, document.info.path, 0)
            for document in self.state.loaded_pdfs
            if document.source_key not in self.thumbnail_cache
        )

    def _on_thumbnail_thread_finished(self) -> None:
        if self.sender() is self.thumbnail_thread:
            self.thumbnail_thread = None
            self.thumbnail_worker = None

    def _on_thumbnail_ready(self, source_key: str, page_index: int, data: bytes) -> None:
        if self.state.document_for_key(source_key) is None:
            return  # removed while its thumbnail was rendering
        source = QPixmap()
        pixmap = row_thumbnail(source) if source.loadFromData(data) else row_placeholder("triangle-alert", WARNING_TEXT)
        self._set_row_thumbnail(source_key, pixmap)

    def _on_thumbnail_preview_failed(self, source_key: str, page_index: int, message: str) -> None:
        if self.state.document_for_key(source_key) is None:
            return
        self._set_row_thumbnail(source_key, row_placeholder("triangle-alert", WARNING_TEXT))

    def _set_row_thumbnail(self, source_key: str, pixmap: QPixmap) -> None:
        self.thumbnail_cache[source_key] = pixmap
        row = self._row_widget_for_key(source_key)
        if row is not None:
            row.set_thumbnail(pixmap)

    # ---------------------------------------------------------------- output folder and settings
    def _choose_output_folder(self) -> None:
        start = str(self.state.output_folder or Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose Output Folder", start)
        if not folder:
            return
        self._set_output_folder(Path(folder))
        self._remember_output_folder()
        self.status_label.setText("Output folder selected.")
        self._update_state()

    def _set_output_folder(self, folder: Path) -> None:
        self.state.output_folder = folder
        self.output_folder_edit.setText(str(folder))

    def _remember_output_folder(self) -> None:
        if self.state.output_folder is not None:
            QSettings().setValue(OUTPUT_FOLDER_SETTING, str(self.state.output_folder))

    def _load_output_folder_setting(self) -> None:
        saved = QSettings().value(OUTPUT_FOLDER_SETTING, "", str)
        folder = Path(saved) if saved else default_output_folder()
        if not folder.exists():
            folder = default_output_folder()
        self._set_output_folder(folder)

    def _load_preferences(self) -> None:
        store = QSettings()
        saved = pdf_to_image_preferences_from_values({key: store.value(key) for key in PDF_TO_IMAGE_SETTING_KEYS})
        for combo, value in (
            (self.format_combo, saved.output_format),
            (self.dpi_combo, saved.dpi),
            (self.jpg_quality_combo, saved.jpg_quality),
        ):
            previous_blocked = combo.blockSignals(True)
            try:
                combo.setCurrentIndex(max(0, combo.findData(value.value)))
            finally:
                combo.blockSignals(previous_blocked)
        self.state.output_format = saved.output_format
        self.state.dpi = saved.dpi
        self.state.jpg_quality = saved.jpg_quality

    def _current_preferences(self) -> PdfToImagePreferences:
        return PdfToImagePreferences(
            output_format=OutputFormat(self.format_combo.currentData()),
            dpi=DpiPreset(self.dpi_combo.currentData()),
            jpg_quality=JpgQuality(self.jpg_quality_combo.currentData()),
        )

    def _save_preferences(self, _index: int | None = None) -> None:
        preferences = self._current_preferences()
        self.state.dpi = preferences.dpi
        self.state.jpg_quality = preferences.jpg_quality
        store = QSettings()
        for key, value in pdf_to_image_preferences_to_values(preferences).items():
            store.setValue(key, value)

    def _on_format_changed(self, _index: int | None = None) -> None:
        self.state.output_format = OutputFormat(self.format_combo.currentData())
        self.jpg_quality_container.setVisible(self.state.output_format == OutputFormat.JPG)
        self._save_preferences()
        self._update_state()

    # ---------------------------------------------------------------- conversion
    def _start_conversion(self) -> None:
        if not self.state.loaded_pdfs:
            return
        if self.state.output_folder is None:
            self.status_label.setText("Choose an output folder before converting.")
            return
        page_refs = self._page_refs_for_conversion()
        if not page_refs:
            self.status_label.setText("No pages available to convert.")
            return

        preferences = self._current_preferences()
        settings = PdfImageExportSettings(
            output_format=preferences.output_format,
            dpi=preferences.dpi,
            jpg_quality=preferences.jpg_quality,
        )
        self._set_converting(True)
        self.job_footer.set_progress(0, len(page_refs))
        self.status_label.setText(f"Converting 0 of {len(page_refs)} pages...")

        self.conversion_thread = QThread(self)
        self.conversion_worker = ConversionWorker(
            page_refs,
            self.state.output_folder,
            settings,
        )
        self.conversion_worker.moveToThread(self.conversion_thread)
        self.conversion_thread.started.connect(self.conversion_worker.run)
        self.conversion_worker.progress.connect(self._on_conversion_progress)
        self.conversion_worker.finished.connect(self._on_conversion_finished)
        self.conversion_worker.cancelled.connect(self._on_conversion_cancelled)
        self.conversion_worker.failed.connect(self._on_conversion_failed)
        self.conversion_worker.finished.connect(lambda _paths: self.conversion_thread.quit())
        self.conversion_worker.cancelled.connect(lambda _paths: self.conversion_thread.quit())
        self.conversion_worker.failed.connect(lambda _message, _filename: self.conversion_thread.quit())
        self.conversion_thread.finished.connect(self.conversion_worker.deleteLater)
        self.conversion_thread.finished.connect(self.conversion_thread.deleteLater)
        self.conversion_thread.finished.connect(self._clear_conversion_worker)
        self.conversion_thread.start()

    def has_background_work(self) -> bool:
        return thread_is_running(self.conversion_thread) or thread_is_running(self.thumbnail_thread)

    def stop_background_work(self) -> None:
        """Request cancellation; workers stop after the current page."""
        self._stop_thumbnail_worker()
        if self.conversion_worker is not None:
            self.conversion_worker.cancel()

    def _cancel_conversion(self) -> None:
        if self.conversion_worker is not None:
            self.conversion_worker.cancel()
            self.status_label.setText("Cancelling after the current page...")

    def _on_conversion_progress(self, current: int, total: int, page_index: int, path: str) -> None:
        self.job_footer.set_progress(current, total)
        self.status_label.setText(f"Converting {current} of {total} pages...")

    def _on_conversion_finished(self, paths: object) -> None:
        completed = tuple(paths)
        self._set_converting(False)
        self._remember_output_folder()
        self.status_label.show_success(f"Conversion complete - {len(completed)} image(s) saved.")
        if completed and self.state.output_folder is not None:
            result = self.open_output_location(self.state.output_folder)
            if not result.success:
                logger.warning("Could not open PDF to image output folder: %s", result.message)
                self.status_label.show_warning("Conversion complete, but the output folder could not be opened.")

    def _on_conversion_cancelled(self, paths: object) -> None:
        completed = tuple(paths)
        self._set_converting(False)
        self.status_label.setText(f"Conversion cancelled - {len(completed)} image(s) saved.")

    def _on_conversion_failed(self, message: str, filename: str = "") -> None:
        self._set_converting(False)
        logger.error("PDF to image conversion failed: %s", message)
        if filename:
            self.status_label.show_error(FILE_ERROR_MESSAGE.format(filename=filename))
        else:
            self.status_label.show_error(CONVERSION_FAILED_MESSAGE)

    def _clear_conversion_worker(self) -> None:
        self.conversion_thread = None
        self.conversion_worker = None
        self._update_state()

    # ---------------------------------------------------------------- state
    def _update_pdf_info(self) -> None:
        if not self.state.loaded_pdfs:
            self.pdf_info_label.setText("No PDF loaded")
            return
        pdf_count = len(self.state.loaded_pdfs)
        page_count = sum(document.info.page_count for document in self.state.loaded_pdfs)
        size_bytes = sum(document.info.file_size_bytes for document in self.state.loaded_pdfs)
        pdf_label = "PDF" if pdf_count == 1 else "PDFs"
        page_label = "page" if page_count == 1 else "pages"
        self.pdf_info_label.setText(
            f"{pdf_count} {pdf_label}   |   {page_count} {page_label}   |   {file_size_text(size_bytes)}"
        )

    def _update_state(self) -> None:
        has_pdf = bool(self.state.loaded_pdfs)
        has_pages = self.state.page_count > 0
        has_output = self.state.output_folder is not None
        converting = self.conversion_thread is not None and self.conversion_thread.isRunning()
        self.stack.setCurrentWidget(self.file_list if has_pdf else self.empty_state)
        self.clear_button.setEnabled(has_pdf and not converting)
        self.convert_button.setEnabled(has_pages and has_output and not converting)
        self.job_footer.set_running(converting)
        self.add_button.setEnabled(not converting)
        self.file_list.setEnabled(not converting)
        self.format_combo.setEnabled(not converting)
        self.dpi_combo.setEnabled(not converting)
        self.output_folder_edit.setEnabled(not converting)
        self.browse_output_folder_button.setEnabled(not converting)
        self.jpg_quality_container.setVisible(OutputFormat(self.format_combo.currentData()) == OutputFormat.JPG)
        self.jpg_quality_combo.setEnabled(not converting)

        if not has_pdf and not self.status_label.text():
            self.status_label.setText("No PDF loaded.")

    def _set_converting(self, converting: bool) -> None:
        self.add_button.setEnabled(not converting)
        self.clear_button.setEnabled(not converting and bool(self.state.loaded_pdfs))
        self.job_footer.set_running(converting)
        self.file_list.setEnabled(not converting)
        self.format_combo.setEnabled(not converting)
        self.dpi_combo.setEnabled(not converting)
        self.jpg_quality_combo.setEnabled(not converting)
        self.output_folder_edit.setEnabled(not converting)
        self.browse_output_folder_button.setEnabled(not converting)

    def _row_widget_for_key(self, source_key: str) -> FileRowWidget | None:
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            if item.data(SOURCE_KEY_ROLE) == source_key:
                widget = self.file_list.itemWidget(item)
                return widget if isinstance(widget, FileRowWidget) else None
        return None

    def _page_refs_for_conversion(self) -> tuple[PdfPageRef, ...]:
        return self.state.all_page_refs()


def pdf_row_detail(document: LoadedPdf) -> str:
    pages = document.info.page_count
    return f"{pages} page{'' if pages == 1 else 's'} · {file_size_text(document.info.file_size_bytes)}"
