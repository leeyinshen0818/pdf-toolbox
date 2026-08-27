from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QSize, QStandardPaths, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
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
    QStyle,
    QVBoxLayout,
    QWidget,
)

from pdf_toolbox.core.heic_to_jpg import (
    AddHeicResult,
    HeicCollection,
    HeicConversionCancelled,
    HeicImageEntry,
    HeicJpgSettings,
    HeicToJpgService,
)
from pdf_toolbox.core.output_location import open_output_location
from pdf_toolbox.core.pdf_to_image import JpgQuality


HEIC_PATH_ROLE = Qt.UserRole + 40
HEIC_OUTPUT_FOLDER_SETTING = "heic_to_jpg/output_folder"
logger = logging.getLogger(__name__)


class HeicDropArea(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        title = QLabel("Add HEIC files to convert into JPG")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #2f3742; border: none;")
        hint = QLabel("Drag and drop HEIC or HEIF files here.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName("SubtleText")
        button = QPushButton("Add HEICs")
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


class HeicListWidget(QListWidget):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ImageList")
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setSpacing(5)
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


class HeicRowWidget(QWidget):
    delete_requested = Signal(str)

    def __init__(self, entry: HeicImageEntry, thumbnail: QPixmap) -> None:
        super().__init__()
        self.setObjectName("ImageRow")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(9)

        thumbnail_label = QLabel()
        thumbnail_label.setFixedSize(58, 58)
        thumbnail_label.setAlignment(Qt.AlignCenter)
        thumbnail_label.setPixmap(thumbnail)
        thumbnail_label.setStyleSheet("background: #f6f7f9; border: 1px solid #e1e6ec; border-radius: 5px;")

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        filename = QLabel(entry.filename)
        filename.setObjectName("ImageName")
        filename.setToolTip(entry.filename)
        dimensions = QLabel(f"{entry.width} x {entry.height} px")
        dimensions.setObjectName("ImageDimensions")
        text_layout.addWidget(filename)
        text_layout.addWidget(dimensions)

        delete_button = QPushButton()
        delete_button.setObjectName("IconButton")
        delete_button.setToolTip("Remove file")
        delete_button.setFixedSize(28, 28)
        delete_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        delete_button.setIconSize(QSize(16, 16))
        delete_button.clicked.connect(lambda: self.delete_requested.emit(str(entry.path)))

        layout.addWidget(thumbnail_label)
        layout.addLayout(text_layout, 1)
        layout.addWidget(delete_button, alignment=Qt.AlignVCenter)


class HeicPreviewWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PreviewWidget")
        self.setMinimumSize(280, 360)
        self._pixmap: QPixmap | None = None
        self._empty_text = "Add HEIC files to begin"

    def set_preview(self, pixmap: QPixmap | None, empty_text: str = "Select an image to preview") -> None:
        self._pixmap = pixmap
        self._empty_text = empty_text
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8fafc"))
        if self._pixmap is None:
            painter.setPen(QColor("#7a8491"))
            painter.drawText(self.rect(), Qt.AlignCenter, self._empty_text)
            return

        available = self.rect().adjusted(18, 18, -18, -18)
        scaled = self._pixmap.scaled(available.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = available.x() + (available.width() - scaled.width()) // 2
        y = available.y() + (available.height() - scaled.height()) // 2
        painter.setPen(QPen(QColor("#cfd7e2"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(x - 6, y - 6, scaled.width() + 12, scaled.height() + 12, 4, 4)
        painter.drawPixmap(x, y, scaled)


class HeicConversionWorker(QObject):
    progress = Signal(int, int, str, str)
    finished = Signal(object)
    cancelled = Signal(object)
    failed = Signal(str)

    def __init__(self, entries: tuple[HeicImageEntry, ...], output_folder: Path, settings: HeicJpgSettings) -> None:
        super().__init__()
        self.entries = entries
        self.output_folder = output_folder
        self.settings = settings
        self.service = HeicToJpgService()
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True

    def run(self) -> None:
        try:
            paths = self.service.convert_entries(
                self.entries,
                self.output_folder,
                self.settings,
                progress_callback=self._on_progress,
                cancel_callback=lambda: self.cancel_requested,
            )
        except HeicConversionCancelled as exc:
            self.cancelled.emit(exc.completed_paths)
            return
        except Exception as exc:
            logger.exception("HEIC to JPG conversion failed")
            self.failed.emit(str(exc))
            return
        self.finished.emit(paths)

    def _on_progress(self, current: int, total: int, source: Path, target: Path) -> None:
        self.progress.emit(current, total, str(source), str(target))


class HeicToJpgPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.service = HeicToJpgService()
        self.collection = HeicCollection()
        self.thumbnail_cache: dict[tuple[str, int], QPixmap] = {}
        self.preview_cache: dict[tuple[str, int], QPixmap] = {}
        self.conversion_thread: QThread | None = None
        self.conversion_worker: HeicConversionWorker | None = None
        self.output_folder: Path | None = None
        self.open_output_location = open_output_location

        self._build_ui()
        self._load_output_folder_setting()
        self._update_state()
        self._update_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 34, 22)
        layout.setSpacing(13)

        title = QLabel("HEIC -> JPG")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #1f2328;")
        subtitle = QLabel("Convert HEIC and HEIF photos into high-quality JPG images.")
        subtitle.setObjectName("SubtleText")

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.add_button = QPushButton("Add HEICs")
        self.add_button.setObjectName("PrimaryButton")
        self.clear_button = QPushButton("Clear")
        self.add_button.clicked.connect(self._choose_heics)
        self.clear_button.clicked.connect(self._clear_files)
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.clear_button)
        toolbar.addStretch(1)

        content = QHBoxLayout()
        content.setSpacing(18)

        list_layout = QVBoxLayout()
        list_layout.setSpacing(8)
        self.info_label = QLabel("No HEIC files loaded")
        self.info_label.setObjectName("SubtleText")
        self.stack = QStackedWidget()
        self.empty_state = HeicDropArea()
        self.empty_state.files_dropped.connect(self._handle_empty_add)
        self.file_list = HeicListWidget()
        self.file_list.files_dropped.connect(self._add_heic_paths)
        self.file_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.file_list)
        self.stack.setMinimumSize(330, 360)
        list_layout.addWidget(self.info_label)
        list_layout.addWidget(self.stack, 1)

        preview_layout = QVBoxLayout()
        preview_layout.setSpacing(8)
        preview_heading = QLabel("Preview")
        preview_heading.setObjectName("PanelHeading")
        self.preview = HeicPreviewWidget()
        preview_layout.addWidget(preview_heading)
        preview_layout.addWidget(self.preview, 1)

        content.addLayout(list_layout, 4)
        content.addLayout(preview_layout, 4)
        content.addWidget(self._build_settings_panel(), 3)

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
        scroll.setMinimumWidth(310)
        scroll.setMaximumWidth(390)

        panel = QFrame()
        panel.setObjectName("SettingsPanel")
        panel.setMinimumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        heading = QLabel("Conversion Settings")
        heading.setObjectName("PanelHeading")
        layout.addWidget(heading)

        self.jpg_quality_combo = self._combo(JpgQuality)
        self.jpg_quality_combo.setCurrentIndex(self.jpg_quality_combo.findData(JpgQuality.MAXIMUM.value))
        layout.addLayout(self._labeled_control("JPG Quality", self.jpg_quality_combo))

        output_label = QLabel("Output Folder")
        output_label.setObjectName("FieldLabel")
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setReadOnly(True)
        self.output_folder_edit.setPlaceholderText("Choose a folder")
        self.browse_output_folder_button = QPushButton("Browse")
        self.browse_output_folder_button.clicked.connect(self._choose_output_folder)
        output_row = QHBoxLayout()
        output_row.setSpacing(6)
        output_row.addWidget(self.output_folder_edit, 1)
        output_row.addWidget(self.browse_output_folder_button)
        self.set_default_folder_button = QPushButton("Set as Default Folder")
        self.set_default_folder_button.setObjectName("SecondaryActionButton")
        self.set_default_folder_button.clicked.connect(self._set_default_output_folder)
        layout.addWidget(output_label)
        layout.addLayout(output_row)
        layout.addWidget(self.set_default_folder_button)

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

        scroll.setWidget(panel)
        return scroll

    def _combo(self, enum_type) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumHeight(36)
        combo.setMinimumWidth(260)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for item in enum_type:
            combo.addItem(item.value, item.value)
        combo.view().setObjectName("ComboPopup")
        combo.view().setMinimumWidth(300)
        return combo

    def _labeled_control(self, label: str, control: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(4)
        text = QLabel(label)
        text.setObjectName("FieldLabel")
        layout.addWidget(text)
        layout.addWidget(control)
        return layout

    def _choose_heics(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select HEIC Files", "", "HEIC files (*.heic *.heif)")
        if files:
            self._add_heic_paths(files)

    def _handle_empty_add(self, paths: list[str]) -> None:
        if paths:
            self._add_heic_paths(paths)
        else:
            self._choose_heics()

    def _add_heic_paths(self, paths: list[str]) -> None:
        had_selection = bool(self.file_list.selectedItems())
        result = self.collection.add_paths(paths, self.service)
        self._sync_list_from_collection()
        if result.added and not had_selection:
            self._select_path(result.added[0].path)
        self._show_import_result(result)
        self._update_info()
        self._update_state()
        self._update_preview()

    def _sync_list_from_collection(self) -> None:
        selected = {item.data(HEIC_PATH_ROLE) for item in self.file_list.selectedItems()}
        current = self._current_path()
        self.file_list.clear()
        for entry in self.collection.entries:
            item = QListWidgetItem()
            item.setData(HEIC_PATH_ROLE, str(entry.path))
            item.setSizeHint(QSize(300, 84))
            self.file_list.addItem(item)
            row = HeicRowWidget(entry, self._thumbnail_for(entry))
            row.delete_requested.connect(self._remove_path)
            self.file_list.setItemWidget(item, row)
            if str(entry.path) in selected:
                item.setSelected(True)
            if str(entry.path) == current:
                self.file_list.setCurrentItem(item)

    def _thumbnail_for(self, entry: HeicImageEntry) -> QPixmap:
        cache_key = self._cache_key(entry.path)
        cached = self.thumbnail_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            data = self.service.render_preview_png_bytes(entry.path, max_size=(96, 96))
            pixmap = pixmap_from_png_bytes(data).scaled(54, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception:
            pixmap = QPixmap(56, 56)
            pixmap.fill(Qt.white)
        self.thumbnail_cache[cache_key] = pixmap
        return pixmap

    def _show_import_result(self, result: AddHeicResult) -> None:
        messages: list[str] = []
        if result.added:
            messages.append(f"Added {len(result.added)} HEIC file(s).")
        if result.duplicates:
            messages.append(f"Skipped {len(result.duplicates)} duplicate file(s).")
        if result.rejected:
            messages.append(f"Rejected {len(result.rejected)} unsupported or invalid file(s).")
        self.status_label.setText(" ".join(messages) if messages else "No HEIC files added.")
        if result.rejected:
            details = "\n".join(f"{item.path.name}: {item.reason}" for item in result.rejected[:8])
            QMessageBox.warning(self, "Some Files Were Not Added", details)

    def _remove_path(self, path: str) -> None:
        removed_index = self._row_for_path(path)
        removed_current = path == self._current_path()
        self.collection.remove_path(path)
        self._sync_list_from_collection()
        if self.collection.entries and (removed_current or self._current_entry() is None):
            self.file_list.setCurrentRow(min(removed_index, len(self.collection.entries) - 1))
        self.status_label.setText("HEIC file removed.")
        self._update_info()
        self._update_state()
        self._update_preview()

    def _clear_files(self) -> None:
        self.collection.clear()
        self.file_list.clear()
        self.thumbnail_cache.clear()
        self.preview_cache.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("HEIC list cleared.")
        self._update_info()
        self._update_state()
        self._update_preview()

    def _choose_output_folder(self) -> None:
        start = str(self.output_folder or Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose Output Folder", start)
        if not folder:
            return
        self._set_output_folder(Path(folder))
        self.status_label.setText("Output folder selected.")
        self._update_state()

    def _set_output_folder(self, folder: Path) -> None:
        self.output_folder = folder
        self.output_folder_edit.setText(str(folder))

    def _set_default_output_folder(self) -> None:
        if self.output_folder is None:
            self.status_label.setText("Choose an output folder before saving a default.")
            return
        QSettings().setValue(HEIC_OUTPUT_FOLDER_SETTING, str(self.output_folder))
        self.status_label.setText("Default output folder saved.")

    def _load_output_folder_setting(self) -> None:
        saved = QSettings().value(HEIC_OUTPUT_FOLDER_SETTING, "", str)
        folder = Path(saved) if saved else default_output_folder()
        if not folder.exists():
            folder = default_output_folder()
        self._set_output_folder(folder)

    def _start_conversion(self) -> None:
        if not self.collection.entries or self.output_folder is None or self.conversion_thread is not None:
            return
        settings = HeicJpgSettings(jpg_quality=JpgQuality(self.jpg_quality_combo.currentData()))
        self.progress_bar.setMaximum(len(self.collection.entries))
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Converting 0 of {len(self.collection.entries)} images...")
        self._set_converting(True)

        thread = QThread(self)
        worker = HeicConversionWorker(self.collection.entries, self.output_folder, settings)
        self.conversion_thread = thread
        self.conversion_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_conversion_progress)
        worker.finished.connect(self._on_conversion_finished)
        worker.cancelled.connect(self._on_conversion_cancelled)
        worker.failed.connect(self._on_conversion_failed)
        worker.finished.connect(lambda _paths: thread.quit())
        worker.cancelled.connect(lambda _paths: thread.quit())
        worker.failed.connect(lambda _message: thread.quit())
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread, worker=worker: self._clear_conversion_worker(thread, worker))
        thread.start()

    def _cancel_conversion(self) -> None:
        if self.conversion_worker is not None:
            self.conversion_worker.cancel()
            self.status_label.setText("Cancelling after the current image...")
            self.cancel_button.setEnabled(False)

    def _on_conversion_progress(self, current: int, total: int, source: str, target: str) -> None:
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Converting {current} of {total} images...")

    def _on_conversion_finished(self, paths: object) -> None:
        completed = tuple(paths)
        self._set_converting(False)
        self.status_label.setText(f"Conversion complete - {len(completed)} JPG image(s) saved.")
        if completed and self.output_folder is not None:
            result = self.open_output_location(self.output_folder)
            if not result.success:
                logger.warning("Could not open HEIC output folder: %s", result.message)
                self.status_label.setText("Conversion complete, but the output folder could not be opened.")

    def _on_conversion_cancelled(self, paths: object) -> None:
        completed = tuple(paths)
        self._set_converting(False)
        self.status_label.setText(f"Conversion cancelled - {len(completed)} JPG image(s) saved.")

    def _on_conversion_failed(self, message: str) -> None:
        self._set_converting(False)
        self.status_label.setText(message)
        QMessageBox.critical(self, "Conversion Failed", message)

    def _clear_conversion_worker(self, thread: QThread, worker: HeicConversionWorker) -> None:
        if self.conversion_thread is thread:
            self.conversion_thread = None
        if self.conversion_worker is worker:
            self.conversion_worker = None
        self._update_state()

    def _on_selection_changed(self) -> None:
        self._update_state()
        self._update_preview()

    def _update_preview(self) -> None:
        entry = self._current_entry()
        if entry is None:
            empty_text = "Add HEIC files to begin" if not self.collection.entries else "Select an image to preview"
            self.preview.set_preview(None, empty_text)
            return
        cache_key = self._cache_key(entry.path)
        pixmap = self.preview_cache.get(cache_key)
        if pixmap is None:
            try:
                pixmap = pixmap_from_png_bytes(self.service.render_preview_png_bytes(entry.path))
            except Exception:
                self.preview.set_preview(None, "Select an image to preview")
                return
            self.preview_cache[cache_key] = pixmap
        self.preview.set_preview(pixmap)

    def _update_info(self) -> None:
        count = len(self.collection)
        if count == 0:
            self.info_label.setText("No HEIC files loaded")
        elif count == 1:
            self.info_label.setText("1 HEIC file loaded")
        else:
            self.info_label.setText(f"{count} HEIC files loaded")

    def _update_state(self) -> None:
        has_files = bool(self.collection.entries)
        converting = self.conversion_thread is not None and self.conversion_thread.isRunning()
        self.stack.setCurrentWidget(self.file_list if has_files else self.empty_state)
        self.add_button.setEnabled(not converting)
        self.clear_button.setEnabled(has_files and not converting)
        self.convert_button.setEnabled(has_files and self.output_folder is not None and not converting)
        self.convert_button.setVisible(not converting)
        self.cancel_button.setVisible(converting)
        self.cancel_button.setEnabled(converting)
        self.file_list.setEnabled(not converting)
        self.jpg_quality_combo.setEnabled(not converting)
        self.output_folder_edit.setEnabled(not converting)
        self.browse_output_folder_button.setEnabled(not converting)
        self.set_default_folder_button.setEnabled(self.output_folder is not None and not converting)
        if not has_files and not self.status_label.text():
            self.status_label.setText("No HEIC files loaded.")

    def _set_converting(self, converting: bool) -> None:
        self.add_button.setEnabled(not converting)
        self.clear_button.setEnabled(not converting and bool(self.collection.entries))
        self.convert_button.setVisible(not converting)
        self.cancel_button.setVisible(converting)
        self.cancel_button.setEnabled(converting)
        self.file_list.setEnabled(not converting)
        self.jpg_quality_combo.setEnabled(not converting)
        self.output_folder_edit.setEnabled(not converting)
        self.browse_output_folder_button.setEnabled(not converting)
        self.set_default_folder_button.setEnabled(not converting and self.output_folder is not None)

    def _select_path(self, path: str | Path) -> None:
        target = str(path)
        self.file_list.clearSelection()
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            if item.data(HEIC_PATH_ROLE) == target:
                self.file_list.setCurrentItem(item)
                item.setSelected(True)
                return

    def _row_for_path(self, path: str | Path) -> int:
        target = str(path)
        for index in range(self.file_list.count()):
            if self.file_list.item(index).data(HEIC_PATH_ROLE) == target:
                return index
        return 0

    def _current_path(self) -> str | None:
        item = self.file_list.currentItem()
        return item.data(HEIC_PATH_ROLE) if item is not None else None

    def _current_entry(self) -> HeicImageEntry | None:
        selected = self.file_list.selectedItems()
        if not selected:
            return None
        current = self.file_list.currentItem()
        target = current.data(HEIC_PATH_ROLE) if current in selected else selected[0].data(HEIC_PATH_ROLE)
        for entry in self.collection.entries:
            if str(entry.path) == target:
                return entry
        return None

    def _cache_key(self, path: Path) -> tuple[str, int]:
        try:
            return (str(path), path.stat().st_mtime_ns)
        except OSError:
            return (str(path), 0)


def default_output_folder() -> Path:
    pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    if pictures:
        path = Path(pictures)
        if path.exists():
            return path
    return Path.home()


def pixmap_from_png_bytes(data: bytes) -> QPixmap:
    pixmap = QPixmap()
    if pixmap.loadFromData(data):
        return pixmap
    fallback = QPixmap(56, 56)
    fallback.fill(Qt.white)
    return fallback


def set_drop_active(widget: QWidget, active: bool) -> None:
    widget.setProperty("dropActive", active)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
