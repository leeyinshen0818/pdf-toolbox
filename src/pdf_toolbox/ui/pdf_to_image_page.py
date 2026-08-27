from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRect, QSettings, QSize, QStandardPaths, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
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
    PdfToImageService,
)
from pdf_toolbox.core.pdf_to_image_state import PdfToImageState, pdf_key


PAGE_INDEX_ROLE = Qt.UserRole + 10
SOURCE_KEY_ROLE = Qt.UserRole + 11
OUTPUT_FOLDER_SETTING = "pdf_to_image/output_folder"
THUMBNAIL_ICON_SIZE = QSize(140, 180)
THUMBNAIL_PAGE_MAX_SIZE = QSize(122, 158)


class PdfDropArea(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        title = QLabel("Add PDF files to convert pages into images")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #2f3742; border: none;")
        hint = QLabel("You can add multiple PDF files.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName("SubtleText")
        button = QPushButton("Add PDFs")
        button.setObjectName("PrimaryButton")
        button.clicked.connect(lambda: self.files_dropped.emit([]))

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(button, alignment=Qt.AlignCenter)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            set_drop_active(self, True)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        set_drop_active(self, False)
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def dragLeaveEvent(self, event) -> None:
        set_drop_active(self, False)
        super().dragLeaveEvent(event)


class PageThumbnailList(QListWidget):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PageThumbnailList")
        self.setAcceptDrops(True)
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSelectionMode(QListWidget.NoSelection)
        self.setWrapping(True)
        self.setSpacing(10)
        self.setIconSize(THUMBNAIL_ICON_SIZE)
        self.setUniformItemSizes(True)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            set_drop_active(self, True)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        set_drop_active(self, False)
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def dragLeaveEvent(self, event) -> None:
        set_drop_active(self, False)
        super().dragLeaveEvent(event)


class ThumbnailWorker(QObject):
    thumbnail_ready = Signal(str, int, bytes)
    thumbnail_failed = Signal(str, int, str)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, requests: tuple[tuple[str, Path, int], ...]) -> None:
        super().__init__()
        self.requests = requests
        self.service = PdfToImageService()
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self) -> None:
        for source_key, path, page_index in self.requests:
            if self.cancelled:
                break
            try:
                data = self.service.render_page_png_bytes(path, page_index, dpi=72)
            except Exception as exc:
                self.thumbnail_failed.emit(source_key, page_index, str(exc))
                continue
            self.thumbnail_ready.emit(source_key, page_index, data)
        self.finished.emit()


class ConversionWorker(QObject):
    progress = Signal(int, int, int, str)
    finished = Signal(object)
    cancelled = Signal(object)
    failed = Signal(str)

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
            self.failed.emit(str(exc))
            return
        self.finished.emit(paths)

    def _on_progress(self, current: int, total: int, page_index: int, path: Path) -> None:
        self.progress.emit(current, total, page_index, str(path))


class PdfToImagePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.service = PdfToImageService()
        self.state = PdfToImageState()
        self.thumbnail_thread: QThread | None = None
        self.thumbnail_worker: ThumbnailWorker | None = None
        self.thumbnail_cache: dict[tuple[str, int], QPixmap] = {}
        self.conversion_thread: QThread | None = None
        self.conversion_worker: ConversionWorker | None = None
        self.open_output_location = open_output_location

        self._build_ui()
        self._load_output_folder_setting()
        self._update_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 34, 22)
        layout.setSpacing(13)

        title = QLabel("PDF -> Image")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #1f2328;")
        subtitle = QLabel("Convert every page from uploaded PDFs into JPG or PNG images.")
        subtitle.setObjectName("SubtleText")

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.add_button = QPushButton("Add PDFs")
        self.add_button.setObjectName("PrimaryButton")
        self.clear_button = QPushButton("Clear")
        self.add_button.clicked.connect(self._choose_pdf)
        self.clear_button.clicked.connect(self._clear_pdf)
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.clear_button)
        toolbar.addStretch(1)

        content = QHBoxLayout()
        content.setSpacing(20)

        main_area = QVBoxLayout()
        main_area.setSpacing(12)

        self.pdf_info_label = QLabel("No PDF loaded")
        self.pdf_info_label.setObjectName("SubtleText")

        self.stack = QStackedWidget()
        self.empty_state = PdfDropArea()
        self.empty_state.files_dropped.connect(self._handle_empty_add)
        self.thumbnail_list = PageThumbnailList()
        self.thumbnail_list.files_dropped.connect(self._add_pdf_paths)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.thumbnail_list)
        self.stack.setMinimumHeight(420)

        main_area.addWidget(self.pdf_info_label)
        main_area.addWidget(self.stack, 1)

        content.addLayout(main_area, 1)
        content.addWidget(self._build_settings_panel())

        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusText")
        self.status_label.setWordWrap(True)
        status_frame = QFrame()
        status_frame.setObjectName("StatusBar")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(10, 7, 10, 7)
        status_layout.addWidget(self.status_label)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(toolbar)
        layout.addLayout(content, 1)
        layout.addWidget(status_frame)

    def _build_settings_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("SettingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumWidth(340)
        scroll.setMaximumWidth(430)

        panel = QFrame()
        panel.setObjectName("SettingsPanel")
        panel.setMinimumWidth(330)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        heading = QLabel("Conversion Settings")
        heading.setObjectName("PanelHeading")
        layout.addWidget(heading)

        self.format_combo = self._combo(OutputFormat)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        layout.addLayout(self._labeled_control("Format", self.format_combo))

        self.dpi_combo = self._combo(DpiPreset)
        self.dpi_combo.setCurrentIndex(self.dpi_combo.findData(DpiPreset.HIGH.value))
        layout.addLayout(self._labeled_control("Resolution", self.dpi_combo))

        self.jpg_quality_container = QWidget()
        self.jpg_quality_combo = self._combo(JpgQuality)
        jpg_quality_layout = self._labeled_control("JPG Quality", self.jpg_quality_combo)
        self.jpg_quality_combo.setCurrentIndex(self.jpg_quality_combo.findData(JpgQuality.MAXIMUM.value))
        self.jpg_quality_container.setLayout(jpg_quality_layout)
        layout.addWidget(self.jpg_quality_container)

        output_label = QLabel("Output Folder")
        output_label.setObjectName("FieldLabel")
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setReadOnly(True)
        self.output_folder_edit.setPlaceholderText("Choose a folder")
        self.browse_output_folder_button = QPushButton("Browse")
        self.browse_output_folder_button.clicked.connect(self._choose_output_folder)
        self.set_default_folder_button = QPushButton("Set as Default Folder")
        self.set_default_folder_button.setObjectName("SecondaryActionButton")
        self.set_default_folder_button.clicked.connect(self._set_default_output_folder)
        output_row = QHBoxLayout()
        output_row.setSpacing(6)
        output_row.addWidget(self.output_folder_edit, 1)
        output_row.addWidget(self.browse_output_folder_button)
        layout.addWidget(output_label)
        layout.addLayout(output_row)
        layout.addWidget(self.set_default_folder_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        layout.addStretch(1)

        self.convert_button = QPushButton("Convert All Pages")
        self.convert_button.setObjectName("PrimaryButton")
        self.convert_button.clicked.connect(self._start_conversion)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel_conversion)
        layout.addWidget(self.convert_button)
        layout.addWidget(self.cancel_button)

        scroll.setWidget(panel)
        return scroll

    def _combo(self, enum_type) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumHeight(36)
        combo.setMinimumWidth(300)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(18)
        for item in enum_type:
            combo.addItem(item.value, item.value)
        combo.view().setObjectName("ComboPopup")
        combo.view().setMinimumWidth(320)
        return combo

    def _labeled_control(self, label: str, control: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(4)
        text = QLabel(label)
        text.setObjectName("FieldLabel")
        layout.addWidget(text)
        layout.addWidget(control)
        return layout

    def _choose_pdf(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select PDFs", "", "PDF files (*.pdf)")
        if file_paths:
            self._add_pdf_paths(file_paths)

    def _handle_empty_add(self, paths: list[str]) -> None:
        if paths:
            self._add_pdf_paths(paths)
        else:
            self._choose_pdf()

    def _add_pdf_paths(self, paths: list[str]) -> None:
        pdf_paths = [Path(path) for path in paths if Path(path).suffix.lower() == ".pdf"]
        if not pdf_paths:
            self.status_label.setText("Unsupported file type. Use a PDF file.")
            return
        self._load_pdfs(pdf_paths)

    def _load_pdfs(self, paths: list[Path]) -> None:
        self._stop_thumbnail_worker()
        added = 0
        duplicates = 0
        errors: list[str] = []

        for path in paths:
            try:
                info = self.service.load_pdf_info(path)
            except PdfLoadError as exc:
                errors.append(f"{path.name}: {exc}")
                continue
            if not self.state.add_pdf(info):
                duplicates += 1
                continue
            added += 1

        self._populate_page_items()
        self._update_pdf_info()
        self._update_state()
        self._start_thumbnail_worker()

        messages: list[str] = []
        if added:
            messages.append(f"Added {added} PDF(s).")
        if duplicates:
            messages.append(f"Skipped {duplicates} duplicate PDF(s).")
        if errors:
            messages.append(f"Rejected {len(errors)} PDF(s).")
        self.status_label.setText(" ".join(messages) if messages else "No PDFs added.")
        if errors:
            QMessageBox.warning(self, "Some PDFs Were Not Added", "\n".join(errors[:8]))

    def _populate_page_items(self) -> None:
        self.thumbnail_list.clear()
        placeholder = thumbnail_placeholder("Loading")
        for document in self.state.loaded_pdfs:
            for page_index in range(document.info.page_count):
                item = QListWidgetItem(f"{document.info.filename}\nPage {page_index + 1}")
                item.setData(SOURCE_KEY_ROLE, document.source_key)
                item.setData(PAGE_INDEX_ROLE, page_index)
                item.setIcon(self.thumbnail_cache.get((document.source_key, page_index), placeholder))
                item.setSizeHint(QSize(184, 230))
                self.thumbnail_list.addItem(item)

    def _start_thumbnail_worker(self, source_keys: list[str] | None = None) -> None:
        requests = self._thumbnail_requests(source_keys)
        if not requests:
            return
        thread = QThread(self)
        worker = ThumbnailWorker(requests)
        self.thumbnail_thread = thread
        self.thumbnail_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        worker.thumbnail_failed.connect(self._on_thumbnail_preview_failed)
        worker.failed.connect(self._on_thumbnail_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(lambda _message: thread.quit())
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread, worker=worker: self._clear_thumbnail_worker(thread, worker))
        thread.start()

    def _stop_thumbnail_worker(self) -> None:
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.cancel()

    def _thumbnail_requests(self, source_keys: list[str] | None = None) -> tuple[tuple[str, Path, int], ...]:
        if not self.state.loaded_pdfs:
            return ()
        keys = set(source_keys or [document.source_key for document in self.state.loaded_pdfs])
        return tuple(
            (document.source_key, document.info.path, page_index)
            for document in self.state.loaded_pdfs
            if document.source_key in keys
            for page_index in range(document.info.page_count)
            if (document.source_key, page_index) not in self.thumbnail_cache
        )

    def _clear_thumbnail_worker(self, thread: QThread, worker: ThumbnailWorker) -> None:
        if self.thumbnail_thread is thread:
            self.thumbnail_thread = None
        if self.thumbnail_worker is worker:
            self.thumbnail_worker = None

    def _on_thumbnail_ready(self, source_key: str, page_index: int, data: bytes) -> None:
        pixmap = thumbnail_from_png_bytes(data)
        self.thumbnail_cache[(source_key, page_index)] = pixmap
        item = self._item_for_page(source_key, page_index)
        if item is not None:
            item.setIcon(pixmap)

    def _on_thumbnail_preview_failed(self, source_key: str, page_index: int, message: str) -> None:
        pixmap = thumbnail_placeholder("Preview\nunavailable")
        self.thumbnail_cache[(source_key, page_index)] = pixmap
        item = self._item_for_page(source_key, page_index)
        if item is not None:
            item.setIcon(pixmap)
        self.status_label.setText("Some page previews could not be generated, but conversion can continue.")

    def _on_thumbnail_failed(self, message: str) -> None:
        self.status_label.setText(message)

    def _choose_output_folder(self) -> None:
        start = str(self.state.output_folder or Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose Output Folder", start)
        if not folder:
            return
        self._set_output_folder(Path(folder))
        self.status_label.setText("Output folder selected.")
        self._update_state()

    def _set_output_folder(self, folder: Path) -> None:
        self.state.output_folder = folder
        self.output_folder_edit.setText(str(folder))

    def _set_default_output_folder(self) -> None:
        if self.state.output_folder is None:
            self.status_label.setText("Choose an output folder before saving a default.")
            return
        self._save_output_folder_setting(self.state.output_folder)
        self.status_label.setText("Default output folder saved.")

    def _on_format_changed(self, _index: int | None = None) -> None:
        self.state.output_format = OutputFormat(self.format_combo.currentData())
        self.jpg_quality_container.setVisible(self.state.output_format == OutputFormat.JPG)
        self._update_state()

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

        settings = PdfImageExportSettings(
            output_format=OutputFormat(self.format_combo.currentData()),
            dpi=DpiPreset(self.dpi_combo.currentData()),
            jpg_quality=JpgQuality(self.jpg_quality_combo.currentData()),
        )
        self.progress_bar.setMaximum(len(page_refs))
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Converting 0 of {len(page_refs)} pages...")
        self._set_converting(True)

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
        self.conversion_worker.failed.connect(lambda _message: self.conversion_thread.quit())
        self.conversion_thread.finished.connect(self.conversion_worker.deleteLater)
        self.conversion_thread.finished.connect(self.conversion_thread.deleteLater)
        self.conversion_thread.finished.connect(self._clear_conversion_worker)
        self.conversion_thread.start()

    def _cancel_conversion(self) -> None:
        if self.conversion_worker is not None:
            self.conversion_worker.cancel()
            self.status_label.setText("Cancelling after the current page...")
            self.cancel_button.setEnabled(False)

    def _on_conversion_progress(self, current: int, total: int, page_index: int, path: str) -> None:
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Converting {current} of {total} pages...")

    def _on_conversion_finished(self, paths: object) -> None:
        completed = tuple(paths)
        self._set_converting(False)
        self.status_label.setText(f"Conversion complete - {len(completed)} image(s) saved.")
        if completed and self.state.output_folder is not None:
            result = self.open_output_location(self.state.output_folder)
            if not result.success:
                self.status_label.setText("Conversion complete, but the output folder could not be opened.")

    def _on_conversion_cancelled(self, paths: object) -> None:
        completed = tuple(paths)
        self._set_converting(False)
        self.status_label.setText(f"Conversion cancelled - {len(completed)} image(s) saved.")

    def _on_conversion_failed(self, message: str) -> None:
        self._set_converting(False)
        self.status_label.setText(message)
        QMessageBox.critical(self, "Conversion Failed", message)

    def _clear_conversion_worker(self) -> None:
        self.conversion_thread = None
        self.conversion_worker = None
        self._update_state()

    def _clear_pdf(self) -> None:
        self._stop_thumbnail_worker()
        self.state.clear_pdf()
        self.thumbnail_list.clear()
        self.thumbnail_cache.clear()
        self.pdf_info_label.setText("No PDF loaded")
        self.progress_bar.setValue(0)
        self.status_label.setText("PDF cleared.")
        self._update_state()

    def _update_pdf_info(self) -> None:
        if not self.state.loaded_pdfs:
            self.pdf_info_label.setText("No PDF loaded")
            return
        pdf_count = len(self.state.loaded_pdfs)
        page_count = sum(document.info.page_count for document in self.state.loaded_pdfs)
        size_mb = sum(document.info.file_size_bytes for document in self.state.loaded_pdfs) / (1024 * 1024)
        pdf_label = "PDF" if pdf_count == 1 else "PDFs"
        page_label = "page" if page_count == 1 else "pages"
        self.pdf_info_label.setText(f"{pdf_count} {pdf_label}   |   {page_count} {page_label}   |   {size_mb:.1f} MB")

    def _update_state(self) -> None:
        has_pdf = bool(self.state.loaded_pdfs)
        has_pages = self.state.page_count > 0
        has_output = self.state.output_folder is not None
        converting = self.conversion_thread is not None and self.conversion_thread.isRunning()
        self.stack.setCurrentWidget(self.thumbnail_list if has_pdf else self.empty_state)
        self.clear_button.setEnabled(has_pdf and not converting)
        self.convert_button.setEnabled(has_pages and has_output and not converting)
        self.cancel_button.setVisible(converting)
        self.cancel_button.setEnabled(converting)
        self.add_button.setEnabled(not converting)
        self.thumbnail_list.setEnabled(not converting)
        self.format_combo.setEnabled(not converting)
        self.dpi_combo.setEnabled(not converting)
        self.output_folder_edit.setEnabled(not converting)
        self.browse_output_folder_button.setEnabled(not converting)
        self.set_default_folder_button.setEnabled(not converting and has_output)
        self.jpg_quality_container.setVisible(OutputFormat(self.format_combo.currentData()) == OutputFormat.JPG)
        self.jpg_quality_combo.setEnabled(not converting)

        if not has_pdf and not self.status_label.text():
            self.status_label.setText("No PDF loaded.")

    def _set_converting(self, converting: bool) -> None:
        self.add_button.setEnabled(not converting)
        self.clear_button.setEnabled(not converting and bool(self.state.loaded_pdfs))
        self.convert_button.setVisible(not converting)
        self.cancel_button.setVisible(converting)
        self.cancel_button.setEnabled(converting)
        self.thumbnail_list.setEnabled(not converting)
        self.format_combo.setEnabled(not converting)
        self.dpi_combo.setEnabled(not converting)
        self.jpg_quality_combo.setEnabled(not converting)
        self.output_folder_edit.setEnabled(not converting)
        self.browse_output_folder_button.setEnabled(not converting)
        self.set_default_folder_button.setEnabled(not converting and self.state.output_folder is not None)

    def _item_for_page(self, source_key: str, page_index: int) -> QListWidgetItem | None:
        for index in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(index)
            if item.data(SOURCE_KEY_ROLE) == source_key and item.data(PAGE_INDEX_ROLE) == page_index:
                return item
        return None

    def _page_refs_for_conversion(self) -> tuple[PdfPageRef, ...]:
        return self.state.all_page_refs()

    def _load_output_folder_setting(self) -> None:
        saved = QSettings().value(OUTPUT_FOLDER_SETTING, "", str)
        folder = Path(saved) if saved else default_output_folder()
        if not folder.exists():
            folder = default_output_folder()
        self._set_output_folder(folder)

    def _save_output_folder_setting(self, folder: Path) -> None:
        QSettings().setValue(OUTPUT_FOLDER_SETTING, str(folder))


def default_output_folder() -> Path:
    pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    if pictures:
        path = Path(pictures)
        if path.exists():
            return path
    return Path.home()


def thumbnail_from_png_bytes(data: bytes) -> QPixmap:
    source = QPixmap()
    if not source.loadFromData(data):
        return thumbnail_placeholder("Preview\nunavailable")
    return framed_thumbnail(source)


def thumbnail_placeholder(text: str) -> QPixmap:
    canvas = QPixmap(THUMBNAIL_ICON_SIZE)
    canvas.fill(QColor("#ffffff"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.fillRect(canvas.rect(), QColor("#f8fafc"))
    page_rect = QRect(13, 12, THUMBNAIL_ICON_SIZE.width() - 26, THUMBNAIL_ICON_SIZE.height() - 34)
    painter.fillRect(page_rect.adjusted(3, 3, 3, 3), QColor(0, 0, 0, 14))
    painter.fillRect(page_rect, QColor("#ffffff"))
    painter.setPen(QPen(QColor("#d7dee8"), 1))
    painter.drawRect(page_rect)
    painter.setPen(QColor("#7a8491"))
    painter.drawText(page_rect, Qt.AlignCenter, text)
    painter.end()
    return canvas


def framed_thumbnail(source: QPixmap) -> QPixmap:
    canvas = QPixmap(THUMBNAIL_ICON_SIZE)
    canvas.fill(QColor("#ffffff"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.fillRect(canvas.rect(), QColor("#f8fafc"))

    scaled = source.scaled(THUMBNAIL_PAGE_MAX_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    x = (THUMBNAIL_ICON_SIZE.width() - scaled.width()) // 2
    y = (THUMBNAIL_ICON_SIZE.height() - scaled.height()) // 2
    page_rect = QRect(x, y, scaled.width(), scaled.height())
    painter.fillRect(page_rect.adjusted(3, 3, 3, 3), QColor(0, 0, 0, 14))
    painter.fillRect(page_rect, QColor("#ffffff"))
    painter.drawPixmap(page_rect.topLeft(), scaled)
    painter.setPen(QPen(QColor("#cfd7e2"), 1))
    painter.drawRect(page_rect)
    painter.end()
    return canvas


def set_drop_active(widget: QWidget, active: bool) -> None:
    widget.setProperty("dropActive", active)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
