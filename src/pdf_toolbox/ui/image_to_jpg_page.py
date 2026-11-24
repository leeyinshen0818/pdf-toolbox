from __future__ import annotations

import logging
import threading
from collections import deque
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pdf_toolbox.core.conversion_preferences import (
    CONVERT_TO_JPG_SETTING_KEYS,
    ConvertToJpgPreferences,
    convert_to_jpg_preferences_from_values,
    convert_to_jpg_preferences_to_values,
)
from pdf_toolbox.core.image_to_jpg import (
    AddPhotoResult,
    PhotoCollection,
    JpgConversionCancelled,
    JpgConversionError,
    PhotoEntry,
    JpgSettings,
    ImageToJpgService,
    PHOTO_FORMATS_BY_EXTENSION,
)
from pdf_toolbox.core.lru_cache import LruCache
from pdf_toolbox.core.output_location import open_output_location
from pdf_toolbox.core.path_keys import path_key as photo_key
from pdf_toolbox.core.pdf_to_image import JpgQuality
from pdf_toolbox.ui.components.drop_area import empty_drop_area
from pdf_toolbox.ui.components.file_list import FileListWidget, FileRowWidget, row_placeholder
from pdf_toolbox.ui.components.page import ToolPage
from pdf_toolbox.ui.components.settings_panel import SettingsPanel
from pdf_toolbox.ui.components.widgets import JPG_QUALITY_CHOICES, default_output_folder, enum_combo, labeled_control
from pdf_toolbox.ui.threads import keep_alive_until_finished, thread_is_running
from pdf_toolbox.ui.metrics import ROW_THUMBNAIL_IMAGE, file_row_size_hint
from pdf_toolbox.ui.tokens import BORDER, CARD_BG, PAGE_BG, SPACE_16, SPACE_4, SPACE_8, TEXT_SECONDARY, WARNING_TEXT


PHOTO_PATH_ROLE = Qt.UserRole + 40
# Key keeps its pre-rename "heic_to_jpg/" prefix so existing users keep their saved folder.
CONVERT_TO_JPG_OUTPUT_FOLDER_SETTING = "heic_to_jpg/output_folder"
PREVIEW_MAX_SIZE = (1000, 1000)
PREVIEW_CACHE_ENTRIES = 10
# Row thumbnails are small (~54 px); the cap only matters for very large batches, where an
# evicted thumbnail costs one more background decode when its row is rebuilt.
THUMBNAIL_CACHE_ENTRIES = 500
OPENING_TEXT = "Opening photo..."
OPEN_FAILED_DETAIL = "Couldn't open this photo"
FILE_ERROR_MESSAGE = "Couldn't open {filename}. Remove it and try again."
CONVERSION_FAILED_MESSAGE = (
    "The photos could not be converted. Check that the files are still in their folder and that "
    "the output folder is available, then try again."
)
# Shown in the empty state, in plain language, for people who don't know the format names.
FORMAT_ROWS = (
    ("HEIC", "iPhone photos"),
    ("WebP", "Images saved from websites or WhatsApp"),
    ("PNG", "Screenshots and graphics with transparent backgrounds"),
)
WORK_AREA_MIN_HEIGHT = 200  # list/preview areas shrink and scroll so the page fits 1366x768
DECODE_READY = "ready"
DECODE_FAILED = "failed"
logger = logging.getLogger(__name__)


class DecodeQueue:
    """Photos waiting to be decoded, shared by the page (GUI thread) and the decode worker.

    Items are (key, path, generation). The page can move the photo the user is looking at to
    the front, drop removed photos, or close the queue so the worker stops after its current photo.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: deque[tuple[str, Path, int]] = deque()
        self._closed = False

    def push(self, item: tuple[str, Path, int], *, front: bool = False) -> None:
        with self._lock:
            if front:
                self._items.appendleft(item)
            else:
                self._items.append(item)

    def pop(self) -> tuple[str, Path, int] | None:
        with self._lock:
            if self._closed or not self._items:
                return None
            return self._items.popleft()

    def move_to_front(self, key: str) -> None:
        with self._lock:
            for item in self._items:
                if item[0] == key:
                    self._items.remove(item)
                    self._items.appendleft(item)
                    return

    def discard(self, key: str) -> None:
        with self._lock:
            self._items = deque(item for item in self._items if item[0] != key)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._items.clear()

    def reopen(self) -> None:
        with self._lock:
            self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


class PhotoDecodeWorker(QObject):
    """Decodes each queued photo once; size, preview and row thumbnail all come from that decode."""

    decoded = Signal(str, int, QImage, QImage, int, int)  # key, generation, preview, thumbnail, width, height
    failed = Signal(str, int, str)  # key, generation, details for the log
    finished = Signal()

    def __init__(self, queue: DecodeQueue) -> None:
        super().__init__()
        self.queue = queue
        self.service = ImageToJpgService()

    def run(self) -> None:
        while (item := self.queue.pop()) is not None:
            key, path, generation = item
            try:
                decoded = self.service.decode_for_display(path, max_size=PREVIEW_MAX_SIZE)
                preview = pil_rgb_to_qimage(decoded.image)
                if preview.isNull():
                    raise ValueError("Decoded image is empty.")
                thumbnail = preview.scaled(
                    ROW_THUMBNAIL_IMAGE, ROW_THUMBNAIL_IMAGE, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            except Exception as exc:
                logger.warning("Photo could not be decoded: %s", path, exc_info=True)
                self.failed.emit(key, generation, str(exc))
                continue
            self.decoded.emit(key, generation, preview, thumbnail, decoded.width, decoded.height)
        self.finished.emit()


class PhotoPreviewWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PreviewWidget")
        self.setMinimumSize(280, WORK_AREA_MIN_HEIGHT)
        self._pixmap: QPixmap | None = None
        self._empty_text = "Add photos to begin"

    def set_preview(self, pixmap: QPixmap | None, empty_text: str = "Select a photo to preview") -> None:
        self._pixmap = pixmap
        self._empty_text = empty_text
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(PAGE_BG))
        if self._pixmap is None:
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.drawText(self.rect().adjusted(SPACE_16, 0, -SPACE_16, 0), Qt.AlignCenter | Qt.TextWordWrap, self._empty_text)
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


class JpgConversionWorker(QObject):
    progress = Signal(int, int, str, str)
    finished = Signal(object)
    cancelled = Signal(object)
    failed = Signal(str, str)  # log details, name of the photo at fault ("" if none)

    def __init__(self, entries: tuple[PhotoEntry, ...], output_folder: Path, settings: JpgSettings) -> None:
        super().__init__()
        self.entries = entries
        self.output_folder = output_folder
        self.settings = settings
        self.service = ImageToJpgService()
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
        except JpgConversionCancelled as exc:
            self.cancelled.emit(exc.completed_paths)
            return
        except Exception as exc:
            logger.exception("JPG conversion failed")
            filename = exc.filename if isinstance(exc, JpgConversionError) else None
            self.failed.emit(str(exc), filename or "")
            return
        self.finished.emit(paths)

    def _on_progress(self, current: int, total: int, source: Path, target: Path) -> None:
        self.progress.emit(current, total, str(source), str(target))


class ConvertToJpgPage(ToolPage):
    ACCEPTED_EXTENSIONS = frozenset(PHOTO_FORMATS_BY_EXTENSION)
    ACCEPTED_DESCRIPTION = "HEIC, WebP or PNG photos"

    def __init__(self) -> None:
        super().__init__()
        self.service = ImageToJpgService()
        self.collection = PhotoCollection()
        self.thumbnail_cache: LruCache[tuple[str, int], QPixmap] = LruCache(THUMBNAIL_CACHE_ENTRIES)
        self.preview_cache: LruCache[tuple[str, int], QPixmap] = LruCache(PREVIEW_CACHE_ENTRIES)
        self.conversion_thread: QThread | None = None
        self.conversion_worker: JpgConversionWorker | None = None
        self.output_folder: Path | None = None
        self.open_output_location = open_output_location

        # Background decoding. A clear bumps the generation so results still in flight are dropped.
        self._decode_queue = DecodeQueue()
        self._decode_thread: QThread | None = None
        self._decode_worker: PhotoDecodeWorker | None = None
        self._decode_generation = 0
        self._pending: set[str] = set()  # keys queued or being decoded
        self._decode_status: dict[str, str] = {}
        self._decoded_sizes: dict[str, tuple[int, int]] = {}
        queue = self._decode_queue
        self.destroyed.connect(lambda *_args: queue.close())

        self._build_ui()
        self._load_output_folder_setting()
        self._load_preferences()
        self._update_info()
        self._update_state()
        self._update_preview()

    def _build_ui(self) -> None:
        self.build_scaffold("Convert to JPG", "Convert HEIC, WebP and PNG photos into high-quality JPG images.")

        self.add_button = QPushButton("Add Photos")
        self.add_button.setObjectName("PrimaryButton")
        self.clear_button = QPushButton("Clear")
        self.add_button.clicked.connect(self._choose_photos)
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
            "Add photos to convert into JPG",
            "Drag and drop photos here, or click Add Photos.",
            "Add Photos",
            format_rows=FORMAT_ROWS,
            format_note="Already JPG? No need to convert.",
        )
        self.empty_state.files_dropped.connect(self.add_dropped_files)
        empty.action_requested.connect(self._choose_photos)
        self.file_list = FileListWidget()
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
        self.preview = PhotoPreviewWidget()
        preview_layout.addWidget(preview_heading)
        preview_layout.addWidget(self.preview, 1)

        self.settings_panel = self._build_settings_panel()
        self.content_layout.addWidget(self.list_section, 4)
        self.content_layout.addWidget(self.preview_section, 4)
        self.content_layout.addWidget(self.settings_panel, 3)

    def _build_settings_panel(self) -> SettingsPanel:
        panel = SettingsPanel("Conversion Settings", "Convert", min_width=310, max_width=390)
        layout = panel.body_layout

        self.jpg_quality_combo = enum_combo(JpgQuality, choices=JPG_QUALITY_CHOICES)
        self.jpg_quality_combo.setCurrentIndex(self.jpg_quality_combo.findData(JpgQuality.MAXIMUM.value))
        self.jpg_quality_combo.currentIndexChanged.connect(self._save_preferences)
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
    def _choose_photos(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select Photos", "", "Photos (*.heic *.heif *.webp *.png)")
        if files:
            self._add_photo_paths(files)

    def add_files(self, paths: list[str]) -> None:
        self._add_photo_paths(paths)

    def _add_photo_paths(self, paths: list[str]) -> None:
        """Rows appear at once (header check only); pixels are decoded in the background."""
        had_selection = bool(self.file_list.selectedItems())
        result = self.collection.add_paths(paths, self.service)
        self._sync_list_from_collection()
        if result.added and not had_selection:
            self._select_path(result.added[0].path)
        for entry in result.added:
            self._request_decode(entry)
        self._show_import_result(result)
        self._update_info()
        self._update_state()
        self._update_preview()

    def _sync_list_from_collection(self) -> None:
        selected = {item.data(PHOTO_PATH_ROLE) for item in self.file_list.selectedItems()}
        current = self._current_path()
        previous_blocked = self.file_list.blockSignals(True)
        try:
            self.file_list.clear()
            for entry in self.collection.entries:
                item = QListWidgetItem()
                item.setData(PHOTO_PATH_ROLE, str(entry.path))
                item.setSizeHint(file_row_size_hint())
                self.file_list.addItem(item)
                row = FileRowWidget(
                    str(entry.path),
                    entry.filename,
                    self._row_detail(entry),
                    self._row_thumbnail(entry),
                    tooltip=str(entry.path),
                    delete_tooltip="Remove photo",
                )
                row.delete_requested.connect(self._remove_path)
                self.file_list.setItemWidget(item, row)
                if str(entry.path) == current:
                    self.file_list.setCurrentItem(item)
                if str(entry.path) in selected:
                    item.setSelected(True)
        finally:
            self.file_list.blockSignals(previous_blocked)

    def _row_detail(self, entry: PhotoEntry) -> str:
        key = photo_key(entry.path)
        status = self._decode_status.get(key)
        if status == DECODE_FAILED:
            return OPEN_FAILED_DETAIL
        size = self._decoded_sizes.get(key)
        if status == DECODE_READY and size is not None:
            detail = f"{size[0]} x {size[1]} px"
            return f"{detail} · first frame only" if entry.n_frames > 1 else detail
        return OPENING_TEXT

    def _row_thumbnail(self, entry: PhotoEntry) -> QPixmap:
        key = photo_key(entry.path)
        if self._decode_status.get(key) == DECODE_FAILED:
            return row_placeholder("triangle-alert", WARNING_TEXT)
        cached = self.thumbnail_cache.get(self._cache_key(entry.path))
        if cached is not None:
            return cached
        if self._decode_status.get(key) == DECODE_READY:
            self._request_decode(entry)  # thumbnail was evicted from the cache; decode it again
        return row_placeholder("image")

    def _show_import_result(self, result: AddPhotoResult) -> None:
        messages: list[str] = []
        if result.added:
            messages.append(f"Added {len(result.added)} photo(s).")
        if result.duplicates:
            messages.append(f"Skipped {len(result.duplicates)} duplicate file(s).")
        if result.rejected:
            messages.append(f"Rejected {len(result.rejected)} unsupported or invalid file(s).")
        if result.rejected or result.duplicates:
            self.status_label.show_warning(" ".join(messages))
        else:
            self.status_label.setText(" ".join(messages) if messages else "No photos added.")
        if result.rejected:
            details = "\n".join(f"{item.path.name}: {item.reason}" for item in result.rejected[:8])
            QMessageBox.warning(self, "Some Files Were Not Added", details)

    def _remove_path(self, path: str) -> None:
        removed_index = self._row_for_path(path)
        removed_current = path == self._current_path()
        key = photo_key(path)
        self._decode_queue.discard(key)
        self._pending.discard(key)  # a result still being decoded is dropped: the entry is gone
        self._decode_status.pop(key, None)
        self._decoded_sizes.pop(key, None)
        self.collection.remove_path(path)
        self._sync_list_from_collection()
        if self.collection.entries and (removed_current or self._current_entry() is None):
            self.file_list.setCurrentRow(min(removed_index, len(self.collection.entries) - 1))
        self.status_label.setText("Photo removed.")
        self._update_info()
        self._update_state()
        self._update_preview()

    def _clear_files(self) -> None:
        self._decode_generation += 1  # results already being decoded are now stale
        self._decode_queue.clear()
        self._pending.clear()
        self._decode_status.clear()
        self._decoded_sizes.clear()
        self.collection.clear()
        self.file_list.clear()
        self.thumbnail_cache.clear()
        self.preview_cache.clear()
        self.status_label.setText("List cleared.")
        self._update_info()
        self._update_state()
        self._update_preview()

    # ---------------------------------------------------------------- background decoding
    def has_pending_decodes(self) -> bool:
        return bool(self._pending)

    def _request_decode(self, entry: PhotoEntry, *, front: bool = False) -> None:
        key = photo_key(entry.path)
        if self._decode_queue.closed:
            # A close was requested and then postponed; pick up where decoding stopped.
            self._decode_queue.reopen()
            self._pending.clear()
            for other in self.collection.entries:
                if photo_key(other.path) not in self._decode_status and photo_key(other.path) != key:
                    self._enqueue(other, front=False)
        if key in self._pending:
            if front:
                self._decode_queue.move_to_front(key)
            return
        self._enqueue(entry, front=front)
        self._ensure_decode_worker()

    def _enqueue(self, entry: PhotoEntry, *, front: bool) -> None:
        key = photo_key(entry.path)
        self._pending.add(key)
        self._decode_queue.push((key, entry.path, self._decode_generation), front=front)

    def _ensure_decode_worker(self) -> None:
        if thread_is_running(self._decode_thread) or not len(self._decode_queue):
            return
        # Unparented and held by ui.threads until finished, so destroying this page mid-decode
        # never deletes a running thread; closing the queue makes the worker stop after one photo.
        thread = QThread()
        worker = PhotoDecodeWorker(self._decode_queue)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.decoded.connect(self._on_decoded)
        worker.failed.connect(self._on_decode_failed)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._on_decode_thread_finished)
        keep_alive_until_finished(thread, worker)
        self._decode_thread = thread
        self._decode_worker = worker
        thread.start()

    def _on_decode_thread_finished(self) -> None:
        self._decode_thread = None
        self._decode_worker = None
        if len(self._decode_queue):
            self._ensure_decode_worker()  # photos queued while the last worker was finishing

    def _on_decoded(self, key: str, generation: int, preview: QImage, thumbnail: QImage, width: int, height: int) -> None:
        entry = self._entry_for_key(key)
        if generation != self._decode_generation or entry is None:
            return  # cleared or removed while it was being decoded
        self._pending.discard(key)
        cache_key = self._cache_key(entry.path)
        self.preview_cache[cache_key] = QPixmap.fromImage(preview)
        self.thumbnail_cache[cache_key] = QPixmap.fromImage(thumbnail)
        self._decode_status[key] = DECODE_READY
        self._decoded_sizes[key] = (width, height)
        row = self._row_widget_for_key(key)
        if row is not None:
            row.set_thumbnail(self.thumbnail_cache[cache_key])
            row.set_detail(self._row_detail(entry))
        current = self._current_entry()
        if current is not None and photo_key(current.path) == key:
            self._update_preview()
        self._update_info()

    def _on_decode_failed(self, key: str, generation: int, message: str) -> None:
        entry = self._entry_for_key(key)
        if generation != self._decode_generation or entry is None:
            return
        self._pending.discard(key)
        self._decode_status[key] = DECODE_FAILED
        row = self._row_widget_for_key(key)
        if row is not None:
            row.set_thumbnail(self._row_thumbnail(entry))
            row.set_detail(OPEN_FAILED_DETAIL)
        self.status_label.show_error(FILE_ERROR_MESSAGE.format(filename=entry.filename))
        current = self._current_entry()
        if current is not None and photo_key(current.path) == key:
            self._update_preview()
        self._update_info()

    # ---------------------------------------------------------------- output folder and settings
    def _choose_output_folder(self) -> None:
        start = str(self.output_folder or Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose Output Folder", start)
        if not folder:
            return
        self._set_output_folder(Path(folder))
        self._remember_output_folder()
        self.status_label.setText("Output folder selected.")
        self._update_state()

    def _set_output_folder(self, folder: Path) -> None:
        self.output_folder = folder
        self.output_folder_edit.setText(str(folder))

    def _remember_output_folder(self) -> None:
        if self.output_folder is not None:
            QSettings().setValue(CONVERT_TO_JPG_OUTPUT_FOLDER_SETTING, str(self.output_folder))

    def _load_output_folder_setting(self) -> None:
        saved = QSettings().value(CONVERT_TO_JPG_OUTPUT_FOLDER_SETTING, "", str)
        folder = Path(saved) if saved else default_output_folder()
        if not folder.exists():
            folder = default_output_folder()
        self._set_output_folder(folder)

    def _load_preferences(self) -> None:
        store = QSettings()
        saved = convert_to_jpg_preferences_from_values({key: store.value(key) for key in CONVERT_TO_JPG_SETTING_KEYS})
        previous_blocked = self.jpg_quality_combo.blockSignals(True)
        try:
            self.jpg_quality_combo.setCurrentIndex(max(0, self.jpg_quality_combo.findData(saved.jpg_quality.value)))
        finally:
            self.jpg_quality_combo.blockSignals(previous_blocked)

    def _save_preferences(self, _index: int | None = None) -> None:
        preferences = ConvertToJpgPreferences(jpg_quality=JpgQuality(self.jpg_quality_combo.currentData()))
        store = QSettings()
        for key, value in convert_to_jpg_preferences_to_values(preferences).items():
            store.setValue(key, value)

    # ---------------------------------------------------------------- conversion
    def _start_conversion(self) -> None:
        if not self.collection.entries or self.output_folder is None or self.conversion_thread is not None:
            return
        failed = [entry for entry in self.collection.entries if self._decode_status.get(photo_key(entry.path)) == DECODE_FAILED]
        if failed:
            self.status_label.show_error(FILE_ERROR_MESSAGE.format(filename=failed[0].filename))
            return
        settings = JpgSettings(jpg_quality=JpgQuality(self.jpg_quality_combo.currentData()))
        self._set_converting(True)
        self.job_footer.set_progress(0, len(self.collection.entries))
        self.status_label.setText(f"Converting 0 of {len(self.collection.entries)} images...")

        thread = QThread(self)
        worker = JpgConversionWorker(self.collection.entries, self.output_folder, settings)
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
        worker.failed.connect(lambda _message, _filename: thread.quit())
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread, worker=worker: self._clear_conversion_worker(thread, worker))
        thread.start()

    def has_background_work(self) -> bool:
        return thread_is_running(self.conversion_thread) or thread_is_running(self._decode_thread)

    def stop_background_work(self) -> None:
        """Request cancellation; the conversion and the photo decoding stop after the current image."""
        if self.conversion_worker is not None:
            self.conversion_worker.cancel()
        self._decode_queue.close()
        self._pending.clear()

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
        self._remember_output_folder()
        self.status_label.show_success(f"Conversion complete - {len(completed)} JPG image(s) saved.")
        if completed and self.output_folder is not None:
            result = self.open_output_location(self.output_folder)
            if not result.success:
                logger.warning("Could not open JPG output folder: %s", result.message)
                self.status_label.show_warning("Conversion complete, but the output folder could not be opened.")

    def _on_conversion_cancelled(self, paths: object) -> None:
        completed = tuple(paths)
        self._set_converting(False)
        self.status_label.setText(f"Conversion cancelled - {len(completed)} JPG image(s) saved.")

    def _on_conversion_failed(self, message: str, filename: str = "") -> None:
        self._set_converting(False)
        logger.error("JPG conversion failed: %s", message)
        if filename:
            self.status_label.show_error(FILE_ERROR_MESSAGE.format(filename=filename))
        else:
            self.status_label.show_error(CONVERSION_FAILED_MESSAGE)

    def _clear_conversion_worker(self, thread: QThread, worker: JpgConversionWorker) -> None:
        if self.conversion_thread is thread:
            self.conversion_thread = None
        if self.conversion_worker is worker:
            self.conversion_worker = None
        self._update_state()

    # ---------------------------------------------------------------- state and preview
    def _on_selection_changed(self) -> None:
        self._update_state()
        self._update_preview()

    def _update_preview(self) -> None:
        entry = self._current_entry()
        if entry is None:
            empty_text = "Add photos to begin" if not self.collection.entries else "Select a photo to preview"
            self.preview.set_preview(None, empty_text)
            return
        key = photo_key(entry.path)
        if self._decode_status.get(key) == DECODE_FAILED:
            self.preview.set_preview(None, FILE_ERROR_MESSAGE.format(filename=entry.filename))
            return
        pixmap = self.preview_cache.get(self._cache_key(entry.path))
        if pixmap is not None:
            self.preview.set_preview(pixmap)
            return
        self.preview.set_preview(None, OPENING_TEXT)
        self._request_decode(entry, front=True)  # the photo being looked at is decoded next

    def _update_info(self) -> None:
        count = len(self.collection)
        if count == 0:
            text = "No photos loaded"
        elif count == 1:
            text = "1 photo loaded"
        else:
            text = f"{count} photos loaded"
        if self._pending:
            text += f" · opening {len(self._pending)}..."
        self.info_label.setText(text)

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
        if not has_files and not self.status_label.text():
            self.status_label.setText("No photos loaded.")

    def _set_converting(self, converting: bool) -> None:
        self.add_button.setEnabled(not converting)
        self.clear_button.setEnabled(not converting and bool(self.collection.entries))
        self.job_footer.set_running(converting)
        self.file_list.setEnabled(not converting)
        self.jpg_quality_combo.setEnabled(not converting)
        self.output_folder_edit.setEnabled(not converting)
        self.browse_output_folder_button.setEnabled(not converting)

    def _select_path(self, path: str | Path) -> None:
        target = str(path)
        self.file_list.clearSelection()
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            if item.data(PHOTO_PATH_ROLE) == target:
                self.file_list.setCurrentItem(item)
                item.setSelected(True)
                return

    def _row_for_path(self, path: str | Path) -> int:
        target = str(path)
        for index in range(self.file_list.count()):
            if self.file_list.item(index).data(PHOTO_PATH_ROLE) == target:
                return index
        return 0

    def _row_widget_for_key(self, key: str) -> FileRowWidget | None:
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            if photo_key(item.data(PHOTO_PATH_ROLE)) == key:
                widget = self.file_list.itemWidget(item)
                return widget if isinstance(widget, FileRowWidget) else None
        return None

    def _entry_for_key(self, key: str) -> PhotoEntry | None:
        for entry in self.collection.entries:
            if photo_key(entry.path) == key:
                return entry
        return None

    def _current_path(self) -> str | None:
        item = self.file_list.currentItem()
        return item.data(PHOTO_PATH_ROLE) if item is not None else None

    def _current_entry(self) -> PhotoEntry | None:
        selected = self.file_list.selectedItems()
        if not selected:
            return None
        current = self.file_list.currentItem()
        target = current.data(PHOTO_PATH_ROLE) if current in selected else selected[0].data(PHOTO_PATH_ROLE)
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
