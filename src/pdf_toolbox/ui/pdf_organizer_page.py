from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from pdf_toolbox.core.output_location import open_output_location
from pdf_toolbox.core.pdf_organizer import OrganizerHistory, OrganizerPage, PdfOrganizerWorkspace
from pdf_toolbox.core.pdf_organizer_exporter import PdfOrganizerExporter
from pdf_toolbox.core.pdf_organizer_thumbnail import PdfOrganizerThumbnailService
from pdf_toolbox.core.pdf_to_image import PdfLoadError, PdfToImageService


PAGE_ID_ROLE = Qt.UserRole + 30
THUMBNAIL_SIZE = QSize(136, 176)
CARD_SIZE = QSize(190, 282)
logger = logging.getLogger(__name__)


class OrganizerDropArea(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        title = QLabel("Add PDFs to start organizing pages")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #2f3742; border: none;")
        hint = QLabel("Drop one or more PDF files here.")
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


class OrganizerPageGrid(QListWidget):
    files_dropped = Signal(list)
    order_changed = Signal(list, list)
    delete_pressed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._drag_start_global_pos = None
        self._drag_start_item: QListWidgetItem | None = None
        self._dragging_item: QListWidgetItem | None = None
        self.setObjectName("OrganizerPageGrid")
        self.setAcceptDrops(True)
        self.setDragEnabled(False)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setViewMode(QListWidget.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Snap)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setWrapping(True)
        self.setGridSize(CARD_SIZE)
        self.setSpacing(14)
        self.setUniformItemSizes(True)
        self.setAutoScroll(True)
        self.setAutoScrollMargin(72)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setMouseTracking(True)

    def register_drag_widgets(self, card: "PageCardWidget") -> None:
        card.installEventFilter(self)
        for label in card.findChildren(QLabel):
            label.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
            viewport_pos = watched.mapTo(self.viewport(), event.position().toPoint())
            item = self.itemAt(viewport_pos)
            if item is not None:
                self._drag_start_global_pos = event.globalPosition().toPoint()
                self._drag_start_item = item
                if event.modifiers() & Qt.ControlModifier:
                    item.setSelected(not item.isSelected())
                elif not item.isSelected():
                    self.clearSelection()
                    item.setSelected(True)
                self.setCurrentItem(item)
            return False

        if (
            event.type() == QEvent.Type.MouseMove
            and self._drag_start_item is not None
            and event.buttons() & Qt.LeftButton
        ):
            distance = (event.globalPosition().toPoint() - self._drag_start_global_pos).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._dragging_item = self._drag_start_item
                self.viewport().setCursor(Qt.ClosedHandCursor)
                viewport_pos = watched.mapTo(self.viewport(), event.position().toPoint())
                self._auto_scroll_for_drag(viewport_pos)
                return True

        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.LeftButton:
            viewport_pos = watched.mapTo(self.viewport(), event.position().toPoint())
            if self._dragging_item is not None:
                self._finish_card_drag(viewport_pos)
                self.viewport().unsetCursor()
                return True
            self._drag_start_item = None
            self._drag_start_global_pos = None
        return super().eventFilter(watched, event)

    def _auto_scroll_for_drag(self, viewport_pos) -> None:
        bar = self.verticalScrollBar()
        margin = self.autoScrollMargin()
        step = 18
        if viewport_pos.y() < margin:
            bar.setValue(bar.value() - step)
        elif viewport_pos.y() > self.viewport().height() - margin:
            bar.setValue(bar.value() + step)

    def _finish_card_drag(self, viewport_pos) -> None:
        dragged = self._dragging_item
        self._dragging_item = None
        self._drag_start_item = None
        self._drag_start_global_pos = None
        if dragged is None:
            return

        before = self.page_ids()
        dragged_id = dragged.data(PAGE_ID_ROLE)
        from_index = before.index(dragged_id)
        to_index = self._drop_index_for_position(viewport_pos)
        if to_index > from_index:
            to_index -= 1
        to_index = max(0, min(to_index, len(before) - 1))
        if to_index == from_index:
            return

        after = before[:]
        moved = after.pop(from_index)
        after.insert(to_index, moved)
        self.order_changed.emit(before, after)

    def _drop_index_for_position(self, viewport_pos) -> int:
        target = self.itemAt(viewport_pos)
        if target is None:
            return self.count()
        target_index = self.row(target)
        rect = self.visualItemRect(target)
        if viewport_pos.x() > rect.center().x():
            return target_index + 1
        return target_index

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

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Delete:
            self.delete_pressed.emit()
            return
        super().keyPressEvent(event)

    def page_ids(self) -> list[str]:
        return [self.item(index).data(PAGE_ID_ROLE) for index in range(self.count())]


class PageCardWidget(QFrame):
    delete_requested = Signal(str)

    def __init__(self, page: OrganizerPage, workspace_number: int) -> None:
        super().__init__()
        self.setObjectName("OrganizerPageCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(CARD_SIZE)
        self.page_id = page.page_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 9)
        layout.setSpacing(6)

        header = QHBoxLayout()
        page_label = QLabel(f"Page {workspace_number}")
        page_label.setObjectName("CardTitle")
        delete_button = QPushButton()
        delete_button.setObjectName("IconButton")
        delete_button.setToolTip("Remove page")
        delete_button.setFixedSize(28, 28)
        delete_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        delete_button.clicked.connect(lambda: self.delete_requested.emit(self.page_id))
        header.addWidget(page_label)
        header.addStretch(1)
        header.addWidget(delete_button)

        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(THUMBNAIL_SIZE)
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setPixmap(thumbnail_placeholder("Loading"))

        source = ElidedLabel(page.source_filename)
        source.setObjectName("CardMeta")
        source.setFixedHeight(18)

        original_page = QLabel(f"Original page {page.source_page_index + 1}")
        original_page.setObjectName("CardMeta")
        original_page.setFixedHeight(16)

        rotation = QLabel("" if page.rotation == 0 else f"Rotated {page.rotation} deg")
        rotation.setObjectName("CardMeta")
        rotation.setFixedHeight(16)

        layout.addLayout(header)
        layout.addWidget(self.thumbnail, alignment=Qt.AlignCenter)
        layout.addWidget(source)
        layout.addWidget(original_page)
        layout.addWidget(rotation)
        layout.addStretch(1)

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        self.thumbnail.setPixmap(pixmap)


class ElidedLabel(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.full_text = text
        self.setToolTip(text)
        self.setText(text)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_text()

    def _refresh_text(self) -> None:
        available_width = max(24, self.width())
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.ElideMiddle, available_width))


class OrganizerThumbnailWorker(QObject):
    thumbnail_ready = Signal(str, object, bytes)
    thumbnail_failed = Signal(str, object)
    finished = Signal()

    def __init__(self, requests: tuple[tuple[str, tuple[str, int, int], Path, int, int], ...]) -> None:
        super().__init__()
        self.requests = requests
        self.service = PdfOrganizerThumbnailService()
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self) -> None:
        for page_id, cache_key, path, page_index, rotation in self.requests:
            if self.cancelled:
                break
            try:
                data = self.service.render_page_png_bytes(path, page_index, rotation)
            except Exception:
                logger.exception("Organizer thumbnail generation failed")
                self.thumbnail_failed.emit(page_id, cache_key)
                continue
            self.thumbnail_ready.emit(page_id, cache_key, data)
        self.finished.emit()


class OrganizerExportWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, pages: tuple[OrganizerPage, ...], output_path: Path, overwrite: bool) -> None:
        super().__init__()
        self.pages = pages
        self.output_path = output_path
        self.overwrite = overwrite
        self.exporter = PdfOrganizerExporter()

    def run(self) -> None:
        try:
            result = self.exporter.export(
                self.pages,
                self.output_path,
                overwrite=self.overwrite,
                progress_callback=self.progress.emit,
            )
        except Exception as exc:
            logger.exception("PDF organizer export failed")
            self.failed.emit(str(exc))
            return
        self.finished.emit(str(result))


class PdfOrganizerPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.service = PdfToImageService()
        self.workspace = PdfOrganizerWorkspace()
        self.history = OrganizerHistory()
        self.thumbnail_cache: dict[tuple[str, int, int], QPixmap] = {}
        self.thumbnail_thread: QThread | None = None
        self.thumbnail_worker: OrganizerThumbnailWorker | None = None
        self.export_thread: QThread | None = None
        self.export_worker: OrganizerExportWorker | None = None
        self.open_output_location = open_output_location

        self._build_ui()
        self._install_shortcuts()
        self._update_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 34, 22)
        layout.setSpacing(13)

        title = QLabel("PDF Organizer")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #1f2328;")
        subtitle = QLabel("Arrange, duplicate, rotate, and export PDF pages without changing the originals.")
        subtitle.setObjectName("SubtleText")

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.add_button = QPushButton("Add PDFs")
        self.add_button.setObjectName("PrimaryButton")
        self.clear_button = QPushButton("Clear")
        self.undo_button = QPushButton("Undo")
        self.redo_button = QPushButton("Redo")
        self.rotate_left_button = QPushButton("Rotate Left")
        self.rotate_right_button = QPushButton("Rotate Right")
        self.duplicate_button = QPushButton("Duplicate")
        self.delete_button = QPushButton("Delete Selected")
        self.export_button = QPushButton("Export PDF")
        self.export_button.setObjectName("PrimaryButton")

        for button in [
            self.add_button,
            self.clear_button,
            self.undo_button,
            self.redo_button,
            self.rotate_left_button,
            self.rotate_right_button,
            self.duplicate_button,
            self.delete_button,
            self.export_button,
        ]:
            toolbar.addWidget(button)
        toolbar.addStretch(1)

        self.add_button.clicked.connect(self._choose_pdfs)
        self.clear_button.clicked.connect(self._clear_workspace)
        self.undo_button.clicked.connect(self._undo)
        self.redo_button.clicked.connect(self._redo)
        self.rotate_left_button.clicked.connect(lambda: self._rotate_selected(-90))
        self.rotate_right_button.clicked.connect(lambda: self._rotate_selected(90))
        self.duplicate_button.clicked.connect(self._duplicate_selected)
        self.delete_button.clicked.connect(self._delete_selected)
        self.export_button.clicked.connect(self._export_pdf)

        self.info_label = QLabel("No pages loaded")
        self.info_label.setObjectName("SubtleText")

        self.stack = QStackedWidget()
        self.empty_state = OrganizerDropArea()
        self.empty_state.files_dropped.connect(self._handle_empty_add)
        self.page_grid = OrganizerPageGrid()
        self.page_grid.files_dropped.connect(self._add_pdf_paths)
        self.page_grid.order_changed.connect(self._on_order_changed)
        self.page_grid.delete_pressed.connect(self._delete_selected)
        self.page_grid.itemSelectionChanged.connect(self._on_selection_changed)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.page_grid)
        self.stack.setMinimumHeight(460)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)

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
        layout.addWidget(self.info_label)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.progress_bar)
        layout.addWidget(status_frame)

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._choose_pdfs)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self._redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self._redo)
        QShortcut(QKeySequence("Ctrl+A"), self, activated=self.page_grid.selectAll)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._export_pdf)

    def _handle_empty_add(self, paths: list[str]) -> None:
        if paths:
            self._add_pdf_paths(paths)
        else:
            self._choose_pdfs()

    def _choose_pdfs(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDFs", "", "PDF files (*.pdf)")
        if files:
            self._add_pdf_paths(files)

    def _add_pdf_paths(self, paths: list[str]) -> None:
        pdf_paths = [Path(path) for path in paths if Path(path).suffix.lower() == ".pdf"]
        if not pdf_paths:
            self.status_label.setText("Unsupported file type. Use PDF files.")
            return

        before = self.workspace.snapshot()
        added_pdfs = 0
        added_pages = 0
        duplicates = 0
        errors: list[str] = []

        for path in pdf_paths:
            try:
                info = self.service.load_pdf_info(path)
            except PdfLoadError as exc:
                errors.append(f"{path.name}: {exc}")
                continue
            pages = self.workspace.add_pdf(info)
            if not pages:
                duplicates += 1
                continue
            added_pdfs += 1
            added_pages += len(pages)

        if added_pages:
            self.history.record(before)
        self._rebuild_grid()
        self._update_info()
        self._update_state()
        self._start_thumbnail_worker()

        messages: list[str] = []
        if added_pdfs:
            messages.append(f"Added {added_pdfs} PDF(s) - {added_pages} page(s).")
        if duplicates:
            messages.append(f"Skipped {duplicates} duplicate PDF(s).")
        if errors:
            messages.append(f"Rejected {len(errors)} PDF(s).")
        self.status_label.setText(" ".join(messages) if messages else "No PDFs added.")
        if errors:
            QMessageBox.warning(self, "Some PDFs Were Not Added", "\n".join(errors[:8]))

    def _rebuild_grid(self, selected_ids: set[str] | None = None) -> None:
        selected = selected_ids or self._selected_page_ids()
        self.page_grid.setUpdatesEnabled(False)
        try:
            self.page_grid.clear()
            for position, page in enumerate(self.workspace.pages, start=1):
                item = QListWidgetItem()
                item.setData(PAGE_ID_ROLE, page.page_id)
                item.setSizeHint(CARD_SIZE)
                self.page_grid.addItem(item)

                card = PageCardWidget(page, position)
                card.delete_requested.connect(self._delete_one)
                self.page_grid.register_drag_widgets(card)
                pixmap = self.thumbnail_cache.get(page.thumbnail_key)
                if pixmap is not None:
                    card.set_thumbnail(pixmap)
                self.page_grid.setItemWidget(item, card)
                item.setSelected(page.page_id in selected)
        finally:
            self.page_grid.setUpdatesEnabled(True)
        self._sync_card_selection()

    def _start_thumbnail_worker(self) -> None:
        missing_keys: set[tuple[str, int, int]] = set()
        requests_list: list[tuple[str, tuple[str, int, int], Path, int, int]] = []
        for page in self.workspace.pages:
            if page.thumbnail_key in self.thumbnail_cache or page.thumbnail_key in missing_keys:
                continue
            missing_keys.add(page.thumbnail_key)
            requests_list.append((page.page_id, page.thumbnail_key, page.source_path, page.source_page_index, page.rotation))
        requests = tuple(requests_list)
        if not requests:
            return
        self._stop_thumbnail_worker()
        thread = QThread(self)
        worker = OrganizerThumbnailWorker(requests)
        self.thumbnail_thread = thread
        self.thumbnail_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        worker.thumbnail_failed.connect(self._on_thumbnail_failed)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread, worker=worker: self._clear_thumbnail_worker(thread, worker))
        thread.start()

    def _stop_thumbnail_worker(self) -> None:
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.cancel()

    def _clear_thumbnail_worker(self, thread: QThread, worker: OrganizerThumbnailWorker) -> None:
        if self.thumbnail_thread is thread:
            self.thumbnail_thread = None
        if self.thumbnail_worker is worker:
            self.thumbnail_worker = None

    def _on_thumbnail_ready(self, page_id: str, cache_key: object, data: bytes) -> None:
        pixmap = thumbnail_from_png_bytes(data)
        self.thumbnail_cache[cache_key] = pixmap
        self._set_matching_page_thumbnails(cache_key, pixmap)

    def _on_thumbnail_failed(self, page_id: str, cache_key: object) -> None:
        pixmap = thumbnail_placeholder("Preview\nunavailable")
        self.thumbnail_cache[cache_key] = pixmap
        self._set_matching_page_thumbnails(cache_key, pixmap)
        self.status_label.setText("Some page thumbnails could not be generated.")

    def _set_matching_page_thumbnails(self, cache_key: object, pixmap: QPixmap) -> None:
        for page in self.workspace.pages:
            if page.thumbnail_key == cache_key:
                self._set_page_thumbnail(page.page_id, pixmap)

    def _set_page_thumbnail(self, page_id: str, pixmap: QPixmap) -> None:
        item = self._item_for_page(page_id)
        if item is None:
            return
        card = self.page_grid.itemWidget(item)
        if isinstance(card, PageCardWidget):
            card.set_thumbnail(pixmap)

    def _on_order_changed(self, before_ids: list[str], after_ids: list[str]) -> None:
        selected = self._selected_page_ids()
        try:
            self.history.record(self.workspace.snapshot())
            self.workspace.reorder_by_ids(after_ids)
        except ValueError:
            self.workspace.reorder_by_ids(before_ids)
        self._rebuild_grid(selected)
        self._update_state()
        self.status_label.setText("Pages reordered.")

    def _delete_one(self, page_id: str) -> None:
        self._delete_page_ids({page_id})

    def _delete_selected(self) -> None:
        self._delete_page_ids(self._selected_page_ids())

    def _delete_page_ids(self, page_ids: set[str]) -> None:
        if not page_ids:
            return
        self.history.record(self.workspace.snapshot())
        removed = self.workspace.delete_pages(page_ids)
        self._rebuild_grid()
        self._update_info()
        self._update_state()
        self.status_label.setText(f"{len(removed)} page(s) deleted.")

    def _duplicate_selected(self) -> None:
        selected = self._selected_page_ids()
        if not selected:
            return
        self.history.record(self.workspace.snapshot())
        duplicated = self.workspace.duplicate_pages(selected)
        self._rebuild_grid({page.page_id for page in duplicated})
        self._update_info()
        self._update_state()
        self._start_thumbnail_worker()
        self.status_label.setText(f"{len(duplicated)} page(s) duplicated.")

    def _rotate_selected(self, degrees: int) -> None:
        selected = self._selected_page_ids()
        if not selected:
            return
        self.history.record(self.workspace.snapshot())
        self.workspace.rotate_pages(selected, degrees)
        self._rebuild_grid(selected)
        self._update_state()
        self._start_thumbnail_worker()
        self.status_label.setText("Page rotation updated.")

    def _undo(self) -> None:
        snapshot = self.history.undo(self.workspace.snapshot())
        if snapshot is None:
            return
        self.workspace.restore(snapshot)
        self._rebuild_grid()
        self._update_info()
        self._update_state()
        self._start_thumbnail_worker()
        self.status_label.setText("Undo.")

    def _redo(self) -> None:
        snapshot = self.history.redo(self.workspace.snapshot())
        if snapshot is None:
            return
        self.workspace.restore(snapshot)
        self._rebuild_grid()
        self._update_info()
        self._update_state()
        self._start_thumbnail_worker()
        self.status_label.setText("Redo.")

    def _clear_workspace(self) -> None:
        if not self.workspace.pages:
            return
        answer = QMessageBox.question(
            self,
            "Clear Organizer?",
            "Clear all pages from the organizer?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._stop_thumbnail_worker()
        self.workspace.clear()
        self.history.clear()
        self.thumbnail_cache.clear()
        self.page_grid.clear()
        self.progress_bar.setValue(0)
        self._update_info()
        self._update_state()
        self.status_label.setText("Organizer cleared.")

    def _export_pdf(self) -> None:
        if not self.workspace.pages or self.export_thread is not None:
            return
        output, _ = QFileDialog.getSaveFileName(self, "Export Organized PDF", "organized.pdf", "PDF files (*.pdf)")
        if not output:
            return
        output_path = Path(output)
        if output_path.suffix.lower() != ".pdf":
            output_path = output_path.with_suffix(".pdf")

        overwrite = False
        if output_path.exists():
            answer = QMessageBox.question(
                self,
                "Replace PDF?",
                f"{output_path.name} already exists. Replace it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                self.status_label.setText("Export cancelled.")
                return
            overwrite = True

        self._set_exporting(True)
        self.progress_bar.setMaximum(len(self.workspace.pages))
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Exporting 0 of {len(self.workspace.pages)} pages...")

        thread = QThread(self)
        worker = OrganizerExportWorker(tuple(self.workspace.pages), output_path, overwrite)
        self.export_thread = thread
        self.export_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_export_progress)
        worker.finished.connect(self._on_export_finished)
        worker.failed.connect(self._on_export_failed)
        worker.finished.connect(lambda _path: thread.quit())
        worker.failed.connect(lambda _message: thread.quit())
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread, worker=worker: self._clear_export_worker(thread, worker))
        thread.start()

    def _on_export_progress(self, current: int, total: int) -> None:
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Exporting {current} of {total} pages...")

    def _on_export_finished(self, output_path: str) -> None:
        self._set_exporting(False)
        self.status_label.setText("Organized PDF exported successfully.")
        result = self.open_output_location(output_path, reveal=True)
        if not result.success:
            logger.warning("Could not reveal organized PDF: %s", result.message)
            self.status_label.setText("Organized PDF exported successfully, but the output folder could not be opened.")

    def _on_export_failed(self, message: str) -> None:
        self._set_exporting(False)
        self.status_label.setText("Export failed.")
        QMessageBox.critical(self, "Export Failed", message)

    def _clear_export_worker(self, thread: QThread, worker: OrganizerExportWorker) -> None:
        if self.export_thread is thread:
            self.export_thread = None
        if self.export_worker is worker:
            self.export_worker = None
        self._update_state()

    def _selected_page_ids(self) -> set[str]:
        return {item.data(PAGE_ID_ROLE) for item in self.page_grid.selectedItems()}

    def _on_selection_changed(self) -> None:
        self._sync_card_selection()
        self._update_state()

    def _sync_card_selection(self) -> None:
        for index in range(self.page_grid.count()):
            item = self.page_grid.item(index)
            card = self.page_grid.itemWidget(item)
            if card is not None:
                card.setProperty("selected", item.isSelected())
                card.style().unpolish(card)
                card.style().polish(card)

    def _item_for_page(self, page_id: str) -> QListWidgetItem | None:
        for index in range(self.page_grid.count()):
            item = self.page_grid.item(index)
            if item.data(PAGE_ID_ROLE) == page_id:
                return item
        return None

    def _update_info(self) -> None:
        if not self.workspace.pages:
            self.info_label.setText("No pages loaded")
            return
        pdf_count = len(self.workspace.loaded_sources)
        page_count = len(self.workspace.pages)
        pdf_label = "PDF" if pdf_count == 1 else "PDFs"
        page_label = "page" if page_count == 1 else "pages"
        self.info_label.setText(f"{pdf_count} {pdf_label} loaded - {page_count} {page_label}")

    def _update_state(self) -> None:
        has_pages = bool(self.workspace.pages)
        has_selection = bool(self._selected_page_ids())
        exporting = self.export_thread is not None and self.export_thread.isRunning()
        self.stack.setCurrentWidget(self.page_grid if has_pages else self.empty_state)
        self.clear_button.setEnabled(has_pages and not exporting)
        self.undo_button.setEnabled(self.history.can_undo and not exporting)
        self.redo_button.setEnabled(self.history.can_redo and not exporting)
        self.rotate_left_button.setEnabled(has_selection and not exporting)
        self.rotate_right_button.setEnabled(has_selection and not exporting)
        self.duplicate_button.setEnabled(has_selection and not exporting)
        self.delete_button.setEnabled(has_selection and not exporting)
        self.export_button.setEnabled(has_pages and not exporting)
        self.add_button.setEnabled(not exporting)
        self.page_grid.setEnabled(not exporting)
        if not has_pages and not self.status_label.text():
            self.status_label.setText("No pages loaded.")

    def _set_exporting(self, exporting: bool) -> None:
        self.add_button.setEnabled(not exporting)
        self.clear_button.setEnabled(not exporting and bool(self.workspace.pages))
        self.undo_button.setEnabled(not exporting and self.history.can_undo)
        self.redo_button.setEnabled(not exporting and self.history.can_redo)
        self.rotate_left_button.setEnabled(False if exporting else bool(self._selected_page_ids()))
        self.rotate_right_button.setEnabled(False if exporting else bool(self._selected_page_ids()))
        self.duplicate_button.setEnabled(False if exporting else bool(self._selected_page_ids()))
        self.delete_button.setEnabled(False if exporting else bool(self._selected_page_ids()))
        self.export_button.setVisible(not exporting)
        self.page_grid.setEnabled(not exporting)


def thumbnail_from_png_bytes(data: bytes) -> QPixmap:
    pixmap = QPixmap()
    if not pixmap.loadFromData(data):
        return thumbnail_placeholder("Preview\nunavailable")
    return framed_thumbnail(pixmap)


def thumbnail_placeholder(text: str) -> QPixmap:
    canvas = QPixmap(THUMBNAIL_SIZE)
    canvas.fill(QColor("#ffffff"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.fillRect(canvas.rect(), QColor("#f8fafc"))
    page_rect = canvas.rect().adjusted(12, 10, -12, -10)
    painter.fillRect(page_rect.adjusted(3, 3, 3, 3), QColor(0, 0, 0, 14))
    painter.fillRect(page_rect, QColor("#ffffff"))
    painter.setPen(QPen(QColor("#d7dee8"), 1))
    painter.drawRect(page_rect)
    painter.setPen(QColor("#7a8491"))
    painter.drawText(page_rect, Qt.AlignCenter, text)
    painter.end()
    return canvas


def framed_thumbnail(source: QPixmap) -> QPixmap:
    canvas = QPixmap(THUMBNAIL_SIZE)
    canvas.fill(QColor("#ffffff"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.fillRect(canvas.rect(), QColor("#f8fafc"))
    scaled = source.scaled(canvas.size().boundedTo(QSize(122, 162)), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    x = (canvas.width() - scaled.width()) // 2
    y = (canvas.height() - scaled.height()) // 2
    painter.fillRect(x + 3, y + 3, scaled.width(), scaled.height(), QColor(0, 0, 0, 14))
    painter.fillRect(x, y, scaled.width(), scaled.height(), QColor("#ffffff"))
    painter.drawPixmap(x, y, scaled)
    painter.setPen(QPen(QColor("#cfd7e2"), 1))
    painter.drawRect(x, y, scaled.width(), scaled.height())
    painter.end()
    return canvas


def set_drop_active(widget: QWidget, active: bool) -> None:
    widget.setProperty("dropActive", active)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
