from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QPixmap
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
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pdf_toolbox.core.pdf_to_image import (
    ConversionCancelled,
    DpiPreset,
    JpgQuality,
    OutputFormat,
    PdfImageExportSettings,
    PdfLoadError,
    PdfRenderError,
    PdfToImageService,
)
from pdf_toolbox.core.pdf_to_image_state import PdfToImageState


PAGE_INDEX_ROLE = Qt.UserRole + 10


class PdfDropArea(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        title = QLabel("Drop a PDF here")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #2f3742; border: none;")
        hint = QLabel("One PDF at a time is supported.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName("SubtleText")

        layout.addWidget(title)
        layout.addWidget(hint)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class PageThumbnailList(QListWidget):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PageThumbnailList")
        self.setAcceptDrops(True)
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSelectionMode(QListWidget.MultiSelection)
        self.setWrapping(True)
        self.setSpacing(10)
        self.setIconSize(QSize(122, 158))
        self.setUniformItemSizes(True)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class PdfPreviewWidget(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PreviewWidget")
        self.setMinimumHeight(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        self.preview_label = QLabel("Select a page to preview")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setObjectName("SubtleText")
        layout.addWidget(self.preview_label, 1)
        self._pixmap: QPixmap | None = None

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self._pixmap = pixmap
        self._refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if self._pixmap is None:
            self.preview_label.setText("Select a page to preview")
            self.preview_label.setPixmap(QPixmap())
            return
        scaled = self._pixmap.scaled(
            self.preview_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.preview_label.setText("")
        self.preview_label.setPixmap(scaled)


class ThumbnailWorker(QObject):
    thumbnail_ready = Signal(int, bytes)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, path: Path, page_count: int) -> None:
        super().__init__()
        self.path = path
        self.page_count = page_count
        self.service = PdfToImageService()
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self) -> None:
        try:
            for page_index in range(self.page_count):
                if self.cancelled:
                    break
                data = self.service.render_page_png_bytes(self.path, page_index, dpi=42)
                self.thumbnail_ready.emit(page_index, data)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit()


class PreviewWorker(QObject):
    preview_ready = Signal(int, int, bytes)
    failed = Signal(int, int, str)

    def __init__(self, request_id: int, path: Path, page_index: int) -> None:
        super().__init__()
        self.request_id = request_id
        self.path = path
        self.page_index = page_index
        self.service = PdfToImageService()

    def run(self) -> None:
        try:
            data = self.service.render_page_png_bytes(self.path, self.page_index, dpi=110)
        except Exception as exc:
            self.failed.emit(self.request_id, self.page_index, str(exc))
            return
        self.preview_ready.emit(self.request_id, self.page_index, data)


class ConversionWorker(QObject):
    progress = Signal(int, int, int, str)
    finished = Signal(object)
    cancelled = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        path: Path,
        page_indices: tuple[int, ...],
        output_folder: Path,
        settings: PdfImageExportSettings,
    ) -> None:
        super().__init__()
        self.path = path
        self.page_indices = page_indices
        self.output_folder = output_folder
        self.settings = settings
        self.service = PdfToImageService()
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True

    def run(self) -> None:
        try:
            paths = self.service.export_pages(
                self.path,
                self.page_indices,
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
        self.preview_threads: list[QThread] = []
        self.preview_request_id = 0
        self.preview_cache: dict[int, QPixmap] = {}
        self.conversion_thread: QThread | None = None
        self.conversion_worker: ConversionWorker | None = None
        self._syncing_selection = False

        self._build_ui()
        self._update_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 34, 22)
        layout.setSpacing(13)

        title = QLabel("PDF -> Image")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #1f2328;")
        subtitle = QLabel("Convert selected PDF pages into JPG or PNG images.")
        subtitle.setObjectName("SubtleText")

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.add_button = QPushButton("Add PDF")
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

        selection_bar = QHBoxLayout()
        self.select_all_button = QPushButton("Select All")
        self.clear_selection_button = QPushButton("Clear Selection")
        self.select_all_button.clicked.connect(self._select_all_pages)
        self.clear_selection_button.clicked.connect(self._clear_page_selection)
        selection_bar.addWidget(self.select_all_button)
        selection_bar.addWidget(self.clear_selection_button)
        selection_bar.addStretch(1)

        self.stack = QStackedWidget()
        self.empty_state = PdfDropArea()
        self.empty_state.files_dropped.connect(self._add_pdf_paths)
        self.thumbnail_list = PageThumbnailList()
        self.thumbnail_list.files_dropped.connect(self._add_pdf_paths)
        self.thumbnail_list.itemSelectionChanged.connect(self._on_page_selection_changed)
        self.thumbnail_list.itemClicked.connect(self._on_page_clicked)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.thumbnail_list)
        self.stack.setMinimumHeight(230)
        self.stack.setMaximumHeight(350)

        self.preview = PdfPreviewWidget()

        main_area.addWidget(self.pdf_info_label)
        main_area.addLayout(selection_bar)
        main_area.addWidget(self.stack)
        main_area.addWidget(self.preview, 1)

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

    def _build_settings_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("SettingsPanel")
        panel.setFixedWidth(350)
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

        self.jpg_quality_combo = self._combo(JpgQuality)
        self.jpg_quality_combo.setCurrentIndex(self.jpg_quality_combo.findData(JpgQuality.HIGH.value))
        layout.addLayout(self._labeled_control("JPG Quality", self.jpg_quality_combo))

        output_label = QLabel("Output Folder")
        output_label.setObjectName("FieldLabel")
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setReadOnly(True)
        self.output_folder_edit.setPlaceholderText("Choose a folder")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._choose_output_folder)
        output_row = QHBoxLayout()
        output_row.setSpacing(6)
        output_row.addWidget(self.output_folder_edit, 1)
        output_row.addWidget(browse_button)
        layout.addWidget(output_label)
        layout.addLayout(output_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        layout.addStretch(1)

        self.convert_button = QPushButton("Convert")
        self.convert_button.setObjectName("PrimaryButton")
        self.convert_button.clicked.connect(self._start_conversion)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel_conversion)
        layout.addWidget(self.convert_button)
        layout.addWidget(self.cancel_button)

        return panel

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
        file_path, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF files (*.pdf)")
        if file_path:
            self._load_pdf(Path(file_path))

    def _add_pdf_paths(self, paths: list[str]) -> None:
        pdf_paths = [Path(path) for path in paths if Path(path).suffix.lower() == ".pdf"]
        if not pdf_paths:
            self.status_label.setText("Unsupported file type. Use a PDF file.")
            return
        self._load_pdf(pdf_paths[0])

    def _load_pdf(self, path: Path) -> None:
        self._stop_thumbnail_worker()
        try:
            info = self.service.load_pdf_info(path)
        except PdfLoadError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "PDF Not Added", str(exc))
            return

        self.state.load_pdf(info)
        self.preview_cache.clear()
        self._populate_page_items(info.page_count)
        self._update_pdf_info()
        self._update_state()
        self._request_preview(0)
        self._start_thumbnail_worker()
        self.status_label.setText(f"Loaded {info.filename}.")

    def _populate_page_items(self, page_count: int) -> None:
        self._syncing_selection = True
        self.thumbnail_list.clear()
        placeholder = QPixmap(122, 158)
        placeholder.fill(Qt.white)
        for index in range(page_count):
            item = QListWidgetItem(f"Page {index + 1}")
            item.setData(PAGE_INDEX_ROLE, index)
            item.setIcon(placeholder)
            item.setSizeHint(QSize(146, 194))
            self.thumbnail_list.addItem(item)
        self.thumbnail_list.setCurrentRow(0)
        for index in range(self.thumbnail_list.count()):
            self.thumbnail_list.item(index).setSelected(True)
        self._syncing_selection = False

    def _start_thumbnail_worker(self) -> None:
        if self.state.pdf_info is None:
            return
        self.thumbnail_thread = QThread(self)
        self.thumbnail_worker = ThumbnailWorker(self.state.pdf_info.path, self.state.pdf_info.page_count)
        self.thumbnail_worker.moveToThread(self.thumbnail_thread)
        self.thumbnail_thread.started.connect(self.thumbnail_worker.run)
        self.thumbnail_worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self.thumbnail_worker.failed.connect(self._on_thumbnail_failed)
        self.thumbnail_worker.finished.connect(self.thumbnail_thread.quit)
        self.thumbnail_worker.failed.connect(lambda _message: self.thumbnail_thread.quit())
        self.thumbnail_thread.finished.connect(self.thumbnail_worker.deleteLater)
        self.thumbnail_thread.finished.connect(self.thumbnail_thread.deleteLater)
        self.thumbnail_thread.finished.connect(self._clear_thumbnail_worker)
        self.thumbnail_thread.start()

    def _stop_thumbnail_worker(self) -> None:
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.cancel()

    def _clear_thumbnail_worker(self) -> None:
        self.thumbnail_thread = None
        self.thumbnail_worker = None

    def _on_thumbnail_ready(self, page_index: int, data: bytes) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        item = self._item_for_page(page_index)
        if item is not None:
            item.setIcon(pixmap)

    def _on_thumbnail_failed(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_page_selection_changed(self) -> None:
        if self._syncing_selection:
            return
        self.state.selected_pages = {
            item.data(PAGE_INDEX_ROLE)
            for item in self.thumbnail_list.selectedItems()
        }
        self._update_state()

    def _on_page_clicked(self, item: QListWidgetItem) -> None:
        page_index = item.data(PAGE_INDEX_ROLE)
        self.state.set_active_page(page_index)
        self._request_preview(page_index)

    def _request_preview(self, page_index: int) -> None:
        if self.state.pdf_info is None:
            self.preview.set_pixmap(None)
            return
        cached = self.preview_cache.get(page_index)
        if cached is not None:
            self.preview.set_pixmap(cached)
            return

        self.preview_request_id += 1
        request_id = self.preview_request_id
        thread = QThread(self)
        worker = PreviewWorker(request_id, self.state.pdf_info.path, page_index)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.preview_ready.connect(self._on_preview_ready)
        worker.failed.connect(self._on_preview_failed)
        worker.preview_ready.connect(lambda _request_id, _page_index, _data: thread.quit())
        worker.failed.connect(lambda _request_id, _page_index, _message: thread.quit())
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread: self._forget_preview_thread(thread))
        self.preview_threads.append(thread)
        thread.start()

    def _forget_preview_thread(self, thread: QThread) -> None:
        if thread in self.preview_threads:
            self.preview_threads.remove(thread)

    def _on_preview_ready(self, request_id: int, page_index: int, data: bytes) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        self.preview_cache[page_index] = pixmap
        if request_id == self.preview_request_id:
            self.preview.set_pixmap(pixmap)

    def _on_preview_failed(self, request_id: int, page_index: int, message: str) -> None:
        if request_id == self.preview_request_id:
            self.preview.set_pixmap(None)
            self.status_label.setText(message)

    def _select_all_pages(self) -> None:
        if self.state.pdf_info is None:
            return
        self.state.select_all()
        self._apply_selection_to_items()
        self._update_state()

    def _clear_page_selection(self) -> None:
        self.state.clear_selection()
        self._apply_selection_to_items()
        self._update_state()

    def _apply_selection_to_items(self) -> None:
        self._syncing_selection = True
        selected = self.state.selected_pages
        for index in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(index)
            item.setSelected(item.data(PAGE_INDEX_ROLE) in selected)
        self._syncing_selection = False

    def _choose_output_folder(self) -> None:
        start = str(self.state.output_folder or Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose Output Folder", start)
        if not folder:
            return
        self.state.output_folder = Path(folder)
        self.output_folder_edit.setText(folder)
        self._update_state()

    def _on_format_changed(self) -> None:
        self.jpg_quality_combo.setEnabled(OutputFormat(self.format_combo.currentData()) == OutputFormat.JPG)
        self._update_state()

    def _start_conversion(self) -> None:
        if self.state.pdf_info is None:
            return
        if self.state.output_folder is None:
            self.status_label.setText("Choose an output folder before converting.")
            return
        selected_pages = self.state.ordered_selected_pages()
        if not selected_pages:
            self.status_label.setText("Select at least one page before converting.")
            return

        settings = PdfImageExportSettings(
            output_format=OutputFormat(self.format_combo.currentData()),
            dpi=DpiPreset(self.dpi_combo.currentData()),
            jpg_quality=JpgQuality(self.jpg_quality_combo.currentData()),
        )
        self.progress_bar.setMaximum(len(selected_pages))
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Converting 0 of {len(selected_pages)} pages...")
        self._set_converting(True)

        self.conversion_thread = QThread(self)
        self.conversion_worker = ConversionWorker(
            self.state.pdf_info.path,
            selected_pages,
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
        self.preview_cache.clear()
        self.preview.set_pixmap(None)
        self.pdf_info_label.setText("No PDF loaded")
        self.progress_bar.setValue(0)
        self.status_label.setText("PDF cleared.")
        self._update_state()

    def _update_pdf_info(self) -> None:
        if self.state.pdf_info is None:
            self.pdf_info_label.setText("No PDF loaded")
            return
        size_mb = self.state.pdf_info.file_size_bytes / (1024 * 1024)
        pages = "page" if self.state.pdf_info.page_count == 1 else "pages"
        self.pdf_info_label.setText(
            f"{self.state.pdf_info.filename}   |   {self.state.pdf_info.page_count} {pages}   |   {size_mb:.1f} MB"
        )

    def _update_state(self) -> None:
        has_pdf = self.state.pdf_info is not None
        has_selection = bool(self.state.selected_pages)
        has_output = self.state.output_folder is not None
        converting = self.conversion_thread is not None and self.conversion_thread.isRunning()
        self.stack.setCurrentWidget(self.thumbnail_list if has_pdf else self.empty_state)
        self.clear_button.setEnabled(has_pdf and not converting)
        self.select_all_button.setEnabled(has_pdf and not converting)
        self.clear_selection_button.setEnabled(has_pdf and not converting)
        self.convert_button.setEnabled(has_pdf and has_selection and has_output and not converting)
        self.cancel_button.setVisible(converting)
        self.cancel_button.setEnabled(converting)
        self.add_button.setEnabled(not converting)
        self.thumbnail_list.setEnabled(not converting)
        self.format_combo.setEnabled(not converting)
        self.dpi_combo.setEnabled(not converting)
        self.jpg_quality_combo.setEnabled(not converting and OutputFormat(self.format_combo.currentData()) == OutputFormat.JPG)

        if not has_pdf and not self.status_label.text():
            self.status_label.setText("No PDF loaded.")

    def _set_converting(self, converting: bool) -> None:
        self.add_button.setEnabled(not converting)
        self.clear_button.setEnabled(not converting and self.state.pdf_info is not None)
        self.select_all_button.setEnabled(not converting and self.state.pdf_info is not None)
        self.clear_selection_button.setEnabled(not converting and self.state.pdf_info is not None)
        self.convert_button.setVisible(not converting)
        self.cancel_button.setVisible(converting)
        self.cancel_button.setEnabled(converting)
        self.thumbnail_list.setEnabled(not converting)
        self.format_combo.setEnabled(not converting)
        self.dpi_combo.setEnabled(not converting)
        self.jpg_quality_combo.setEnabled(not converting and OutputFormat(self.format_combo.currentData()) == OutputFormat.JPG)

    def _item_for_page(self, page_index: int) -> QListWidgetItem | None:
        for index in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(index)
            if item.data(PAGE_INDEX_ROLE) == page_index:
                return item
        return None
