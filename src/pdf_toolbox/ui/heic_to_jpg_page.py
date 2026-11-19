from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
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

from pdf_toolbox.core.heic_to_jpg import (
    AddHeicResult,
    HeicCollection,
    HeicConversionCancelled,
    HeicImageEntry,
    HeicJpgSettings,
    HeicToJpgService,
    RejectedHeic,
    SUPPORTED_HEIC_EXTENSIONS,
)
from pdf_toolbox.core.lru_cache import LruCache
from pdf_toolbox.core.output_location import open_output_location
from pdf_toolbox.core.pdf_to_image import JpgQuality
from pdf_toolbox.ui.components.drop_area import empty_drop_area, local_paths, set_drop_active
from pdf_toolbox.ui.components.page import ToolPage
from pdf_toolbox.ui.components.settings_panel import SettingsPanel
from pdf_toolbox.ui.components.widgets import default_output_folder, enum_combo, labeled_control
from pdf_toolbox.ui.threads import thread_is_running
from pdf_toolbox.ui import icons
from pdf_toolbox.ui.metrics import ROW_THUMBNAIL, ROW_THUMBNAIL_IMAGE, file_row_size_hint
from pdf_toolbox.ui.tokens import BORDER, CARD_BG, ICON_DELETE, MIN_TARGET, PAGE_BG, SPACE_16, SPACE_4, SPACE_8, TEXT_SECONDARY


HEIC_PATH_ROLE = Qt.UserRole + 40
HEIC_OUTPUT_FOLDER_SETTING = "heic_to_jpg/output_folder"
HEIC_PREVIEW_MAX_SIZE = (1000, 1000)
HEIC_PREVIEW_CACHE_ENTRIES = 10
# Row thumbnails are small (~54 px); the cap only matters for very large batches, where an
# evicted thumbnail would cost a full decode on the next list rebuild.
HEIC_THUMBNAIL_CACHE_ENTRIES = 500
UNDECODABLE_HEIC_REASON = "This HEIC image could not be opened. The file may be damaged."
CONVERSION_FAILED_MESSAGE = (
    "The photos could not be converted. Check that the files are still in their folder and that "
    "the output folder is available, then try again."
)
WORK_AREA_MIN_HEIGHT = 200  # list/preview areas shrink and scroll so the page fits 1366x768
logger = logging.getLogger(__name__)


class HeicListWidget(QListWidget):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ImageList")
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setSpacing(SPACE_4)
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
            self.files_dropped.emit(local_paths(event.mimeData()))
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
        layout.setContentsMargins(SPACE_8, SPACE_4, SPACE_8, SPACE_4)
        layout.setSpacing(SPACE_8)

        thumbnail_label = QLabel()
        thumbnail_label.setObjectName("RowThumbnail")
        thumbnail_label.setFixedSize(ROW_THUMBNAIL, ROW_THUMBNAIL)
        thumbnail_label.setAlignment(Qt.AlignCenter)
        thumbnail_label.setPixmap(thumbnail)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(SPACE_4)
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
        delete_button.setFixedSize(MIN_TARGET, MIN_TARGET)
        delete_button.setIcon(icons.icon("trash-2", TEXT_SECONDARY, ICON_DELETE))
        delete_button.setIconSize(icons.icon_size(ICON_DELETE))
        delete_button.clicked.connect(lambda: self.delete_requested.emit(str(entry.path)))

        layout.addWidget(thumbnail_label)
        layout.addLayout(text_layout, 1)
        layout.addWidget(delete_button, alignment=Qt.AlignVCenter)


class HeicPreviewWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PreviewWidget")
        self.setMinimumSize(280, WORK_AREA_MIN_HEIGHT)
        self._pixmap: QPixmap | None = None
        self._empty_text = "Add HEIC files to begin"

    def set_preview(self, pixmap: QPixmap | None, empty_text: str = "Select an image to preview") -> None:
        self._pixmap = pixmap
        self._empty_text = empty_text
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(PAGE_BG))
        if self._pixmap is None:
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.drawText(self.rect(), Qt.AlignCenter, self._empty_text)
            return

        inset = SPACE_16
        available = self.rect().adjusted(inset, inset, -inset, -inset)
        fitted = self._pixmap.scaled(available.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = available.x() + (available.width() - fitted.width()) // 2
        y = available.y() + (available.height() - fitted.height()) // 2
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.setBrush(QColor(CARD_BG))
        painter.drawRoundedRect(x - 6, y - 6, fitted.width() + 12, fitted.height() + 12, 4, 4)
        painter.drawPixmap(x, y, fitted)


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


class HeicToJpgPage(ToolPage):
    ACCEPTED_EXTENSIONS = frozenset(SUPPORTED_HEIC_EXTENSIONS)
    ACCEPTED_DESCRIPTION = "HEIC or HEIF photos"

    def __init__(self) -> None:
        super().__init__()
        self.service = HeicToJpgService()
        self.collection = HeicCollection()
        self.thumbnail_cache: LruCache[tuple[str, int], QPixmap] = LruCache(HEIC_THUMBNAIL_CACHE_ENTRIES)
        self.preview_cache: LruCache[tuple[str, int], QPixmap] = LruCache(HEIC_PREVIEW_CACHE_ENTRIES)
        self.conversion_thread: QThread | None = None
        self.conversion_worker: HeicConversionWorker | None = None
        self.output_folder: Path | None = None
        self.open_output_location = open_output_location

        self._build_ui()
        self._load_output_folder_setting()
        self._update_state()
        self._update_preview()

    def _build_ui(self) -> None:
        self.build_scaffold("HEIC \u2192 JPG", "Convert HEIC and HEIF photos into high-quality JPG images.")

        self.add_button = QPushButton("Add HEICs")
        self.add_button.setObjectName("PrimaryButton")
        self.clear_button = QPushButton("Clear")
        self.add_button.clicked.connect(self._choose_heics)
        self.clear_button.clicked.connect(self._clear_files)
        self.action_bar.addWidget(self.add_button)
        self.action_bar.addWidget(self.clear_button)
        self.finish_action_bar()

        self.info_label = self.count_label

        self.list_section = QWidget()
        list_layout = QVBoxLayout(self.list_section)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(SPACE_8)
        self.stack = QStackedWidget()
        self.empty_state, empty = empty_drop_area(
            "Add HEIC files to convert into JPG",
            "Drag and drop HEIC or HEIF files here.",
            "Add HEICs",
        )
        self.empty_state.files_dropped.connect(self.add_dropped_files)
        empty.action_requested.connect(self._choose_heics)
        self.file_list = HeicListWidget()
        self.file_list.files_dropped.connect(self.add_dropped_files)
        self.file_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.file_list)
        self.stack.setMinimumSize(330, WORK_AREA_MIN_HEIGHT)
        list_layout.addWidget(self.stack, 1)

        self.preview_section = QWidget()
        preview_layout = QVBoxLayout(self.preview_section)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(SPACE_8)
        preview_heading = QLabel("Preview")
        preview_heading.setObjectName("PanelHeading")
        self.preview = HeicPreviewWidget()
        preview_layout.addWidget(preview_heading)
        preview_layout.addWidget(self.preview, 1)

        self.settings_panel = self._build_settings_panel()
        self.content_layout.addWidget(self.list_section, 4)
        self.content_layout.addWidget(self.preview_section, 4)
        self.content_layout.addWidget(self.settings_panel, 3)

    def _build_settings_panel(self) -> SettingsPanel:
        panel = SettingsPanel("Conversion Settings", "Convert", min_width=310, max_width=390)
        layout = panel.body_layout

        self.jpg_quality_combo = enum_combo(JpgQuality)
        self.jpg_quality_combo.setCurrentIndex(self.jpg_quality_combo.findData(JpgQuality.MAXIMUM.value))
        layout.addLayout(labeled_control("JPG Quality", self.jpg_quality_combo))

        output_label = QLabel("Output Folder")
        output_label.setObjectName("FieldLabel")
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setReadOnly(True)
        self.output_folder_edit.setAcceptDrops(False)  # let file drops reach the window
        self.output_folder_edit.setPlaceholderText("Choose a folder")
        self.output_folder_edit.setMinimumWidth(120)
        self.output_folder_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.browse_output_folder_button = QPushButton("Browse")
        self.browse_output_folder_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.browse_output_folder_button.clicked.connect(self._choose_output_folder)
        output_row = QHBoxLayout()
        output_row.setSpacing(SPACE_4)
        output_row.addWidget(self.output_folder_edit, 1)
        output_row.addWidget(self.browse_output_folder_button)
        self.set_default_folder_button = QPushButton("Set as Default Folder")
        self.set_default_folder_button.setObjectName("SecondaryActionButton")
        self.set_default_folder_button.clicked.connect(self._set_default_output_folder)
        layout.addWidget(output_label)
        layout.addLayout(output_row)
        layout.addWidget(self.set_default_folder_button)
        panel.finish_body()

        self.job_footer = panel.footer
        self.convert_button = panel.footer.primary_button
        self.convert_button.clicked.connect(self._start_conversion)
        self.progress_bar = panel.footer.progress_bar
        self.cancel_button = panel.footer.cancel_button
        panel.footer.cancel_requested.connect(self._cancel_conversion)
        return panel

    def _choose_heics(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select HEIC Files", "", "HEIC files (*.heic *.heif)")
        if files:
            self._add_heic_paths(files)

    def add_files(self, paths: list[str]) -> None:
        self._add_heic_paths(paths)

    def _add_heic_paths(self, paths: list[str]) -> None:
        had_selection = bool(self.file_list.selectedItems())
        result = self._reject_undecodable(self.collection.add_paths(paths, self.service))
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
            item.setSizeHint(file_row_size_hint())
            self.file_list.addItem(item)
            row = HeicRowWidget(entry, self._thumbnail_for(entry))
            row.delete_requested.connect(self._remove_path)
            self.file_list.setItemWidget(item, row)
            if str(entry.path) in selected:
                item.setSelected(True)
            if str(entry.path) == current:
                self.file_list.setCurrentItem(item)

    def _reject_undecodable(self, result: AddHeicResult) -> AddHeicResult:
        """Header validation no longer decodes pixels; decode each new file once here and reject failures."""
        undecodable = [entry for entry in result.added if not self._decode_into_caches(entry)]
        if not undecodable:
            return result
        for entry in undecodable:
            self.collection.remove_path(entry.path)
        undecodable_paths = {entry.path for entry in undecodable}
        return AddHeicResult(
            added=tuple(entry for entry in result.added if entry.path not in undecodable_paths),
            rejected=result.rejected
            + tuple(RejectedHeic(entry.path, UNDECODABLE_HEIC_REASON) for entry in undecodable),
            duplicates=result.duplicates,
        )

    def _decode_into_caches(self, entry: HeicImageEntry) -> bool:
        """One decode per file: the preview and the row thumbnail are both derived from it."""
        cache_key = self._cache_key(entry.path)
        try:
            image = self.service.decode_preview_image(entry.path, max_size=HEIC_PREVIEW_MAX_SIZE)
            preview = QPixmap.fromImage(pil_rgb_to_qimage(image))
        except Exception:
            logger.warning("HEIC image could not be decoded: %s", entry.path, exc_info=True)
            return False
        if preview.isNull():
            return False
        self.preview_cache[cache_key] = preview
        self.thumbnail_cache[cache_key] = preview.scaled(
            ROW_THUMBNAIL_IMAGE,
            ROW_THUMBNAIL_IMAGE,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        return True

    def _thumbnail_for(self, entry: HeicImageEntry) -> QPixmap:
        cache_key = self._cache_key(entry.path)
        cached = self.thumbnail_cache.get(cache_key)
        if cached is None and self._decode_into_caches(entry):
            cached = self.thumbnail_cache.get(cache_key)
        if cached is not None:
            return cached
        pixmap = QPixmap(ROW_THUMBNAIL_IMAGE, ROW_THUMBNAIL_IMAGE)
        pixmap.fill(QColor(CARD_BG))
        return pixmap

    def _show_import_result(self, result: AddHeicResult) -> None:
        messages: list[str] = []
        if result.added:
            messages.append(f"Added {len(result.added)} HEIC file(s).")
        if result.duplicates:
            messages.append(f"Skipped {len(result.duplicates)} duplicate file(s).")
        if result.rejected:
            messages.append(f"Rejected {len(result.rejected)} unsupported or invalid file(s).")
        if result.rejected or result.duplicates:
            self.status_label.show_warning(" ".join(messages))
        else:
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
        self.status_label.show_success("Default output folder saved.")

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
        self._set_converting(True)
        self.job_footer.set_progress(0, len(self.collection.entries))
        self.status_label.setText(f"Converting 0 of {len(self.collection.entries)} images...")

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

    def has_background_work(self) -> bool:
        return thread_is_running(self.conversion_thread)

    def stop_background_work(self) -> None:
        """Request cancellation; the worker stops after the current image."""
        if self.conversion_worker is not None:
            self.conversion_worker.cancel()

    def _cancel_conversion(self) -> None:
        if self.conversion_worker is not None:
            self.conversion_worker.cancel()
            self.status_label.setText("Cancelling after the current image...")

    def _on_conversion_progress(self, current: int, total: int, source: str, target: str) -> None:
        self.job_footer.set_progress(current, total)
        self.status_label.setText(f"Converting {current} of {total} images...")

    def _on_conversion_finished(self, paths: object) -> None:
        completed = tuple(paths)
        self._set_converting(False)
        self.status_label.show_success(f"Conversion complete - {len(completed)} JPG image(s) saved.")
        if completed and self.output_folder is not None:
            result = self.open_output_location(self.output_folder)
            if not result.success:
                logger.warning("Could not open HEIC output folder: %s", result.message)
                self.status_label.show_warning("Conversion complete, but the output folder could not be opened.")

    def _on_conversion_cancelled(self, paths: object) -> None:
        completed = tuple(paths)
        self._set_converting(False)
        self.status_label.setText(f"Conversion cancelled - {len(completed)} JPG image(s) saved.")

    def _on_conversion_failed(self, message: str) -> None:
        self._set_converting(False)
        logger.error("HEIC to JPG conversion failed: %s", message)
        self.status_label.show_error(CONVERSION_FAILED_MESSAGE)

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
        if pixmap is None and self._decode_into_caches(entry):
            pixmap = self.preview_cache.get(cache_key)
        if pixmap is None:
            message = f"{entry.filename}: {UNDECODABLE_HEIC_REASON}"
            self.preview.set_preview(None, message)
            self.status_label.show_warning(message)
            return
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
        self.job_footer.set_running(converting)
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
        self.job_footer.set_running(converting)
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


def pil_rgb_to_qimage(image: Image.Image) -> QImage:
    rgb = image if image.mode == "RGB" else image.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    return QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888).copy()


def pixmap_from_png_bytes(data: bytes) -> QPixmap:
    pixmap = QPixmap()
    if pixmap.loadFromData(data):
        return pixmap
    fallback = QPixmap(ROW_THUMBNAIL_IMAGE, ROW_THUMBNAIL_IMAGE)
    fallback.fill(QColor(CARD_BG))
    return fallback
