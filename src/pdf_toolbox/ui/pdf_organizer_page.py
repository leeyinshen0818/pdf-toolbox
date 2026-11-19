from __future__ import annotations

import logging
import math
from pathlib import Path

from PySide6.QtCore import QEvent, QItemSelectionModel, QObject, QPoint, QPointF, QRectF, QSettings, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pdf_toolbox.core.grid_insertion import insertion_index, insertion_marker
from pdf_toolbox.core.organizer_preferences import (
    THUMBNAIL_DPI,
    THUMBNAIL_SIZE_KEY,
    ThumbnailSize,
    thumbnail_size_from_value,
    thumbnail_size_to_value,
)
from pdf_toolbox.core.output_location import open_output_location
from pdf_toolbox.core.pdf_organizer import OrganizerHistory, OrganizerPage, PdfOrganizerWorkspace
from pdf_toolbox.core.pdf_organizer_exporter import PdfOrganizerExportCancelled, PdfOrganizerExporter
from pdf_toolbox.core.pdf_organizer_thumbnail import PdfOrganizerThumbnailService
from pdf_toolbox.core.pdf_to_image import PdfLoadError, PdfToImageService
from pdf_toolbox.ui.components.drop_area import empty_drop_area, local_paths, set_drop_active
from pdf_toolbox.ui.components.job_footer import JobFooter
from pdf_toolbox.ui.components.page import ToolPage
from pdf_toolbox.ui.components.widgets import ElidedLabel, thumbnail_placeholder
from pdf_toolbox.ui.threads import keep_alive_until_finished, thread_is_running
from pdf_toolbox.ui import icons
from pdf_toolbox.ui import tokens as T
from pdf_toolbox.ui.metrics import (
    CARD_THUMBNAIL,
    ORGANIZER_CARD_GAP,
    ORGANIZER_CARD_PADDING,
    caption_label_height,
    organizer_card_size,
    organizer_thumbnail_box,
)
from pdf_toolbox.ui.tokens import (
    BORDER,
    CARD_BG,
    ICON_DELETE,
    ICON_INLINE,
    MIN_TARGET,
    ON_PRIMARY,
    PAGE_BG,
    PRIMARY,
    RADIUS_CARD,
    SHADOW_RGBA,
    SPACE_12,
    SPACE_24,
    SPACE_4,
    SPACE_8,
    TEXT_SECONDARY,
)


PAGE_ID_ROLE = Qt.UserRole + 30
THUMBNAIL_SIZE = CARD_THUMBNAIL  # Medium thumbnail box
SIZE_STEPS = (ThumbnailSize.SMALL, ThumbnailSize.MEDIUM, ThumbnailSize.LARGE)
SELECTION_HINT = "Click a page to select it. Drag pages to reorder."
EXPORT_FOOTER_WIDTH = 320
SIZE_SLIDER_WIDTH = 200
AUTOSCROLL_MARGIN = 56  # px from the top/bottom edge where a drag starts scrolling
AUTOSCROLL_INTERVAL_MS = 30
AUTOSCROLL_MAX_STEP = 22  # px per tick right at the edge
EXPORT_FAILED_MESSAGE = (
    "The organized PDF could not be saved. Check that the original PDFs are still in their folder "
    "and that the save location is available, then try again."
)
WORK_AREA_MIN_HEIGHT = 200  # the page grid shrinks and scrolls so the page fits 1366x768
logger = logging.getLogger(__name__)


class OrganizerPageGrid(QListWidget):
    """Wrapping grid of page cards with a custom drag.

    Qt's built-in item drag is disabled: with item widgets it shows no picture and drops by
    item rect rather than card position. Instead a press on a card plus movement starts our own
    drag: a translucent copy of the card follows the cursor, a primary line marks the drop
    position (core.grid_insertion decides both the line and the drop), the view autoscrolls
    near the top/bottom edge on a timer, and Esc cancels.
    """

    files_dropped = Signal(list)
    order_changed = Signal(list, list)
    delete_pressed = Signal()
    move_requested = Signal(int)  # -1 = left, 1 = right

    def __init__(self) -> None:
        super().__init__()
        self._card_size = organizer_card_size()
        self._press_global: QPoint | None = None
        self._press_item: QListWidgetItem | None = None
        self._press_offset = QPoint()
        self._dragging = False
        self._drag_ids: list[str] = []
        self._ghost: QLabel | None = None
        self._ghost_offset = QPoint()
        self._drop_index: int | None = None
        self._drag_pos = QPoint()
        self._suppress_release = False
        self._autoscroll_timer = QTimer(self)
        self._autoscroll_timer.setInterval(AUTOSCROLL_INTERVAL_MS)
        self._autoscroll_timer.timeout.connect(self._autoscroll_tick)

        self.setObjectName("OrganizerPageGrid")
        self.setAcceptDrops(True)
        self.setDragEnabled(False)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.setViewMode(QListWidget.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setWrapping(True)
        self.setSpacing(0)  # the gap is part of each grid cell (see _update_grid_size)
        self.setUniformItemSizes(True)
        self.setAutoScroll(False)  # our own timer-driven autoscroll runs during a card drag
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setMouseTracking(True)
        self._update_grid_size()

    # ------------------------------------------------------------ card size and spacing
    def set_card_size(self, card_size: QSize) -> None:
        self._card_size = card_size
        self._update_grid_size()

    def card_size(self) -> QSize:
        return self._card_size

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_grid_size()

    def _update_grid_size(self) -> None:
        """Fit as many columns as possible, then share the spare width so gaps stay even (>= 12px)."""
        available = max(1, self.viewport().width())
        cell = self._card_size.width() + ORGANIZER_CARD_GAP
        columns = max(1, available // cell)
        spare = max(0, available - columns * cell)
        grid = QSize(cell + spare // columns, self._card_size.height() + ORGANIZER_CARD_GAP)
        if grid != self.gridSize():
            self.setGridSize(grid)

    def card_gap(self) -> int:
        return max(ORGANIZER_CARD_GAP, self.gridSize().width() - self._card_size.width())

    # ------------------------------------------------------------ cards
    def register_drag_widgets(self, card: "PageCardWidget") -> None:
        card.installEventFilter(self)
        for label in card.findChildren(QLabel):
            label.installEventFilter(self)

    def page_ids(self) -> list[str]:
        return [self.item(index).data(PAGE_ID_ROLE) for index in range(self.count())]

    def card_rects(self) -> list[tuple[float, float, float, float]]:
        """Card rectangles in viewport coordinates, in display order."""
        rects = []
        for index in range(self.count()):
            card = self.itemWidget(self.item(index))
            geometry = card.geometry() if card is not None else self.visualItemRect(self.item(index))
            rects.append((geometry.x(), geometry.y(), geometry.x() + geometry.width(), geometry.y() + geometry.height()))
        return rects

    def _item_for_watched(self, watched: QObject) -> QListWidgetItem | None:
        widget = watched
        while widget is not None and not isinstance(widget, PageCardWidget):
            widget = widget.parent()
        if widget is None:
            return None
        for index in range(self.count()):
            if self.itemWidget(self.item(index)) is widget:
                return self.item(index)
        return None

    # ------------------------------------------------------------ mouse and keys
    def eventFilter(self, watched, event) -> bool:
        event_type = event.type()
        if event_type == QEvent.Type.KeyPress and self._dragging:
            if event.key() == Qt.Key_Escape:
                self.cancel_card_drag()
                return True
            return False

        if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
            item = self._item_for_watched(watched)
            if item is not None:
                self._press_global = event.globalPosition().toPoint()
                self._press_item = item
                card = self.itemWidget(item)
                self._press_offset = card.mapFromGlobal(self._press_global) if card is not None else QPoint()
                if event.modifiers() & Qt.ControlModifier:
                    item.setSelected(not item.isSelected())
                elif not item.isSelected():
                    self.clearSelection()
                    item.setSelected(True)
                self.setCurrentItem(item, QItemSelectionModel.NoUpdate)
            return False

        if event_type == QEvent.Type.MouseMove and event.buttons() & Qt.LeftButton:
            viewport_pos = self.viewport().mapFromGlobal(event.globalPosition().toPoint())
            if self._dragging:
                self.update_card_drag(viewport_pos)
                return True
            if self._press_item is not None and self._press_global is not None:
                distance = (event.globalPosition().toPoint() - self._press_global).manhattanLength()
                if distance >= QApplication.startDragDistance():
                    self.start_card_drag(self._press_item, viewport_pos, self._press_offset)
                    return True

        if event_type == QEvent.Type.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self._dragging:
                self.finish_card_drag(self.viewport().mapFromGlobal(event.globalPosition().toPoint()))
                return True
            if self._suppress_release:  # the drag was cancelled with Esc; ignore this release
                self._suppress_release = False
                return True
            self._press_item = None
            self._press_global = None
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if self._dragging and event.key() == Qt.Key_Escape:
            self.cancel_card_drag()
            return
        modifiers = event.modifiers() & ~Qt.KeypadModifier
        if modifiers == Qt.AltModifier and event.key() in (Qt.Key_Left, Qt.Key_Right):
            self.move_requested.emit(-1 if event.key() == Qt.Key_Left else 1)
            event.accept()
            return
        if event.key() == Qt.Key_Delete:
            self.delete_pressed.emit()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------ card drag
    def is_dragging(self) -> bool:
        return self._dragging

    def start_card_drag(self, item: QListWidgetItem, viewport_pos: QPoint, offset: QPoint | None = None) -> None:
        if self._dragging:
            return
        if not item.isSelected():
            self.clearSelection()
            item.setSelected(True)
        selected = {selected_item.data(PAGE_ID_ROLE) for selected_item in self.selectedItems()}
        self._drag_ids = [page_id for page_id in self.page_ids() if page_id in selected]
        card = self.itemWidget(item)
        self._ghost_offset = offset if offset is not None else QPoint(self._card_size.width() // 2, self._card_size.height() // 2)
        self._ghost = QLabel(self.viewport())
        self._ghost.setObjectName("DragGhost")
        self._ghost.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._ghost.setPixmap(self._ghost_pixmap(card, len(self._drag_ids)))
        self._ghost.adjustSize()
        self._ghost.show()
        self._ghost.raise_()
        self._dragging = True
        self.viewport().setCursor(Qt.ClosedHandCursor)
        QApplication.instance().installEventFilter(self)  # catch Esc wherever focus is
        self._autoscroll_timer.start()
        self.update_card_drag(viewport_pos)

    def update_card_drag(self, viewport_pos: QPoint) -> None:
        if not self._dragging:
            return
        self._drag_pos = QPoint(viewport_pos)
        if self._ghost is not None:
            self._ghost.move(viewport_pos - self._ghost_offset)
        drop_index = insertion_index(viewport_pos.x(), viewport_pos.y(), self.card_rects())
        if drop_index != self._drop_index:
            self._drop_index = drop_index
        self.viewport().update()

    def finish_card_drag(self, viewport_pos: QPoint) -> None:
        if not self._dragging:
            return
        self.update_card_drag(viewport_pos)
        target = self._drop_index
        dropped_inside = self.viewport().rect().contains(viewport_pos)
        moving = list(self._drag_ids)
        self._end_drag()
        if target is None or not dropped_inside:
            return  # released outside the page grid: treat as cancelled
        before = self.page_ids()
        after = reordered_ids(before, moving, target)
        if after != before:
            self.order_changed.emit(before, after)

    def cancel_card_drag(self) -> None:
        if not self._dragging:
            return
        self._end_drag()
        self._suppress_release = QApplication.mouseButtons() & Qt.LeftButton != Qt.NoButton

    def _end_drag(self) -> None:
        self._dragging = False
        self._autoscroll_timer.stop()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        if self._ghost is not None:
            self._ghost.hide()
            self._ghost.deleteLater()
            self._ghost = None
        self._drop_index = None
        self._drag_ids = []
        self._press_item = None
        self._press_global = None
        self.viewport().unsetCursor()
        self.viewport().update()

    def _autoscroll_tick(self) -> None:
        """Scroll while the cursor rests near the top or bottom edge, even if the mouse is still."""
        if not self._dragging:
            self._autoscroll_timer.stop()
            return
        position = self.viewport().mapFromGlobal(QCursor.pos())
        height = self.viewport().height()
        if position.y() < AUTOSCROLL_MARGIN:
            closeness = min(1.0, (AUTOSCROLL_MARGIN - position.y()) / AUTOSCROLL_MARGIN)
            step = -math.ceil(AUTOSCROLL_MAX_STEP * closeness)
        elif position.y() > height - AUTOSCROLL_MARGIN:
            closeness = min(1.0, (position.y() - (height - AUTOSCROLL_MARGIN)) / AUTOSCROLL_MARGIN)
            step = math.ceil(AUTOSCROLL_MAX_STEP * closeness)
        else:
            return
        bar = self.verticalScrollBar()
        previous = bar.value()
        bar.setValue(previous + step)
        if bar.value() != previous:
            self.update_card_drag(position)

    def _ghost_pixmap(self, card: QWidget | None, count: int) -> QPixmap:
        size = self._card_size
        ratio = self.devicePixelRatioF()
        canvas = QPixmap(round(size.width() * ratio), round(size.height() * ratio))
        canvas.setDevicePixelRatio(ratio)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(0.85)
        if card is not None:
            painter.drawPixmap(0, 0, card.grab())
        painter.setOpacity(1.0)
        painter.setPen(QPen(QColor(PRIMARY), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(1, 1, size.width() - 2, size.height() - 2), RADIUS_CARD, RADIUS_CARD)
        if count > 1:
            badge = f"{count} pages"
            metrics = painter.fontMetrics()
            badge_rect = QRectF(0, 0, metrics.horizontalAdvance(badge) + 2 * SPACE_8, metrics.height() + SPACE_4)
            badge_rect.moveTopRight(QPointF(size.width() - SPACE_8, SPACE_8))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(PRIMARY))
            painter.drawRoundedRect(badge_rect, badge_rect.height() / 2, badge_rect.height() / 2)
            painter.setPen(QColor(ON_PRIMARY))
            painter.drawText(badge_rect, Qt.AlignCenter, badge)
        painter.end()
        return canvas

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._dragging or self._drop_index is None:
            return
        marker = insertion_marker(self._drop_index, self._drag_pos.x(), self._drag_pos.y(), self.card_rects(), self.card_gap())
        if marker is None:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(PRIMARY), 3, Qt.SolidLine, Qt.RoundCap))
        top, bottom = marker.top + SPACE_4, marker.bottom - SPACE_4
        painter.drawLine(QPointF(marker.x, top), QPointF(marker.x, bottom))
        painter.setBrush(QColor(PRIMARY))
        painter.drawEllipse(QPointF(marker.x, top), 4, 4)
        painter.drawEllipse(QPointF(marker.x, bottom), 4, 4)
        painter.end()

    # ------------------------------------------------------------ file drops
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


def reordered_ids(order: list[str], moving: list[str], target: int) -> list[str]:
    """`moving` (kept in their current order) inserted before position `target` of `order`."""
    moving_set = set(moving)
    return (
        [page_id for page_id in order[:target] if page_id not in moving_set]
        + [page_id for page_id in order if page_id in moving_set]
        + [page_id for page_id in order[target:] if page_id not in moving_set]
    )


class PageCardWidget(QFrame):
    """Page card: thumbnail, "Page N", and "<file> · page M"; a trash button shows on hover or selection."""

    delete_requested = Signal(str)

    def __init__(self, page: OrganizerPage, workspace_number: int, size: ThumbnailSize = ThumbnailSize.MEDIUM) -> None:
        super().__init__()
        self.setObjectName("OrganizerPageCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(organizer_card_size(size))
        self.page_id = page.page_id
        self._hovered = False
        self._selected = False
        box = organizer_thumbnail_box(size)
        margin = ORGANIZER_CARD_PADDING + 2  # 2px reserved for the selected border

        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(0)

        self.thumbnail = QLabel()
        self.thumbnail.setObjectName("OrganizerCardThumbnail")
        self.thumbnail.setFixedSize(box)
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setPixmap(thumbnail_placeholder("Loading", box))

        self.title = QLabel(f"Page {workspace_number}")
        self.title.setObjectName("OrganizerCardTitle")
        self.title.setFixedHeight(T.line_height(T.TYPE_BODY_STRONG))

        self.source = ElidedLabel(f"{page.source_filename} · page {page.source_page_index + 1}")
        self.source.setObjectName("CardMeta")
        self.source.setFixedHeight(caption_label_height())
        self.source.setToolTip(str(page.source_path))

        layout.addWidget(self.thumbnail, alignment=Qt.AlignHCenter)
        layout.addSpacing(SPACE_8)
        layout.addWidget(self.title)
        layout.addSpacing(SPACE_4)
        layout.addWidget(self.source)
        layout.addStretch(1)

        self.delete_button = QPushButton(self)
        self.delete_button.setObjectName("CardDeleteButton")
        self.delete_button.setToolTip("Remove this page")
        self.delete_button.setFixedSize(MIN_TARGET, MIN_TARGET)
        self.delete_button.setIcon(icons.icon("trash-2", TEXT_SECONDARY, ICON_DELETE))
        self.delete_button.setIconSize(icons.icon_size(ICON_DELETE))
        self.delete_button.move(self.width() - margin - MIN_TARGET - SPACE_4, margin + SPACE_4)
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.page_id))
        self.delete_button.hide()

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        self.thumbnail.setPixmap(pixmap)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if bool(self.property("selected")) != selected:
            self.setProperty("selected", selected)
            self.style().unpolish(self)
            self.style().polish(self)
        self._sync_delete_button()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._sync_delete_button()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._sync_delete_button()
        super().leaveEvent(event)

    def _sync_delete_button(self) -> None:
        visible = self._hovered or self._selected
        if visible:
            self.delete_button.raise_()
        self.delete_button.setVisible(visible)


class ThumbnailSizeControl(QWidget):
    """Three-step slider labelled Small / Medium / Large; the words can be clicked too."""

    size_changed = Signal(object)

    def __init__(self, size: ThumbnailSize) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_8)

        caption = QLabel("Thumbnail size")
        caption.setObjectName("FieldLabel")
        layout.addWidget(caption)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setObjectName("SizeSlider")
        self.slider.setRange(0, len(SIZE_STEPS) - 1)
        self.slider.setPageStep(1)
        self.slider.setSingleStep(1)
        self.slider.setTickPosition(QSlider.NoTicks)
        self.slider.setFixedWidth(SIZE_SLIDER_WIDTH)
        self.slider.setToolTip("Make the page pictures smaller or larger")
        self.slider.setAccessibleName("Thumbnail size")

        self.step_buttons: dict[ThumbnailSize, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        words: list[QPushButton] = []
        for size_step in SIZE_STEPS:
            button = QPushButton(size_step.value)
            button.setObjectName("SizeStepButton")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.NoFocus)  # the slider is the keyboard control
            button.clicked.connect(lambda _checked=False, value=size_step: self.set_size(value, notify=True))
            group.addButton(button)
            self.step_buttons[size_step] = button
            words.append(button)

        # The three words sit under the slider's three steps (and can be clicked too).
        scale = QWidget()
        scale.setFixedWidth(SIZE_SLIDER_WIDTH)
        scale_layout = QVBoxLayout(scale)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        scale_layout.setSpacing(0)
        word_row = QHBoxLayout()
        word_row.setContentsMargins(0, 0, 0, 0)
        word_row.addWidget(words[0])
        word_row.addStretch(1)
        word_row.addWidget(words[1])
        word_row.addStretch(1)
        word_row.addWidget(words[2])
        scale_layout.addWidget(self.slider)
        scale_layout.addLayout(word_row)
        layout.addWidget(scale)
        layout.setAlignment(caption, Qt.AlignTop)
        caption.setFixedHeight(self.slider.sizeHint().height())
        caption.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.slider.valueChanged.connect(lambda value: self.size_changed.emit(SIZE_STEPS[value]))
        self.slider.valueChanged.connect(lambda value: self.step_buttons[SIZE_STEPS[value]].setChecked(True))
        self.set_size(size, notify=False)

    def size(self) -> ThumbnailSize:  # noqa: A003 - mirrors the slider's value as a ThumbnailSize
        return SIZE_STEPS[self.slider.value()]

    def set_size(self, size: ThumbnailSize, *, notify: bool) -> None:
        previous = self.slider.blockSignals(not notify)
        try:
            self.slider.setValue(SIZE_STEPS.index(ThumbnailSize(size)))
        finally:
            self.slider.blockSignals(previous)
        self.step_buttons[ThumbnailSize(size)].setChecked(True)


class OrganizerThumbnailWorker(QObject):
    thumbnail_ready = Signal(str, object, bytes)
    thumbnail_failed = Signal(str, object)
    finished = Signal()

    def __init__(self, requests: tuple[tuple[str, object, Path, int, int, int], ...]) -> None:
        super().__init__()
        self.requests = requests
        self.service = PdfOrganizerThumbnailService()
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self) -> None:
        for page_id, cache_key, path, page_index, rotation, dpi in self.requests:
            if self.cancelled:
                break
            try:
                data = self.service.render_page_png_bytes(path, page_index, rotation, dpi=dpi)
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
    cancelled = Signal()

    def __init__(self, pages: tuple[OrganizerPage, ...], output_path: Path, overwrite: bool) -> None:
        super().__init__()
        self.pages = pages
        self.output_path = output_path
        self.overwrite = overwrite
        self.exporter = PdfOrganizerExporter()
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True

    def run(self) -> None:
        try:
            result = self.exporter.export(
                self.pages,
                self.output_path,
                overwrite=self.overwrite,
                progress_callback=self.progress.emit,
                cancel_callback=lambda: self.cancel_requested,
            )
        except PdfOrganizerExportCancelled:
            self.cancelled.emit()
            return
        except Exception as exc:
            logger.exception("PDF organizer export failed")
            self.failed.emit(str(exc))
            return
        self.finished.emit(str(result))


class PdfOrganizerPage(ToolPage):
    ACCEPTED_EXTENSIONS = frozenset({".pdf"})
    ACCEPTED_DESCRIPTION = "PDF files"

    def __init__(self) -> None:
        super().__init__()
        self.service = PdfToImageService()
        self.workspace = PdfOrganizerWorkspace()
        self.history = OrganizerHistory()
        # Keyed by (page.thumbnail_key, ThumbnailSize): each size keeps its own rendering.
        self.thumbnail_cache: dict[object, QPixmap] = {}
        self._items_by_page_id: dict[str, QListWidgetItem] = {}
        self.thumbnail_thread: QThread | None = None
        self.thumbnail_worker: OrganizerThumbnailWorker | None = None
        self.export_thread: QThread | None = None
        self.export_worker: OrganizerExportWorker | None = None
        self.open_output_location = open_output_location
        self.thumbnail_size = thumbnail_size_from_value(QSettings().value(THUMBNAIL_SIZE_KEY))

        self._build_ui()
        self._install_shortcuts()
        self._update_info()
        self._update_state()

    # ------------------------------------------------------------ layout
    def _build_ui(self) -> None:
        self.build_scaffold(
            "PDF Organizer",
            "Arrange, duplicate, rotate, and export PDF pages without changing the originals.",
        )

        self.add_button = self._tool_button("Add PDFs", "plus", "Add PDF files (Ctrl+O)", primary=True)
        self.rotate_left_button = self._tool_button("Rotate Left", "rotate-ccw", "Turn the selected pages to the left")
        self.rotate_right_button = self._tool_button("Rotate Right", "rotate-cw", "Turn the selected pages to the right")
        self.duplicate_button = self._tool_button("Duplicate", "copy", "Make a copy of the selected pages")
        self.delete_button = self._tool_button("Delete Selected", "trash-2", "Remove the selected pages (Delete)")
        self.undo_button = self._tool_button("Undo", "undo-2", "Undo the last change (Ctrl+Z)")
        self.redo_button = self._tool_button("Redo", "redo-2", "Redo the change you undid (Ctrl+Y)")
        self.clear_button = self._tool_button("Clear", "trash-2", "Remove all pages from the organizer")
        self.clear_button.setObjectName("QuietButton")

        groups = (
            (self.add_button,),
            (self.rotate_left_button, self.rotate_right_button, self.duplicate_button, self.delete_button),
            (self.undo_button, self.redo_button),
        )
        for group_index, group in enumerate(groups):
            if group_index:
                self.action_bar.addSpacing(SPACE_24 - self.action_bar.spacing())
            for button in group:
                self.action_bar.addWidget(button)
        self.action_bar.addStretch(1)
        self.action_bar.addWidget(self.clear_button)

        self.add_button.clicked.connect(self._choose_pdfs)
        self.clear_button.clicked.connect(self._clear_workspace)
        self.undo_button.clicked.connect(self._undo)
        self.redo_button.clicked.connect(self._redo)
        self.rotate_left_button.clicked.connect(lambda: self._rotate_selected(-90))
        self.rotate_right_button.clicked.connect(lambda: self._rotate_selected(90))
        self.duplicate_button.clicked.connect(self._duplicate_selected)
        self.delete_button.clicked.connect(self._delete_selected)

        self.info_label = self.count_label

        self.stack = QStackedWidget()
        self.empty_state, empty = empty_drop_area(
            "Add PDFs to start organizing pages",
            "Drop one or more PDF files here.",
            "Add PDFs",
        )
        self.empty_state.files_dropped.connect(self.add_dropped_files)
        empty.action_requested.connect(self._choose_pdfs)
        self.page_grid = OrganizerPageGrid()
        self.page_grid.set_card_size(organizer_card_size(self.thumbnail_size))
        self.page_grid.files_dropped.connect(self.add_dropped_files)
        self.page_grid.order_changed.connect(self._on_order_changed)
        self.page_grid.delete_pressed.connect(self._delete_selected)
        self.page_grid.move_requested.connect(self._move_selected)
        self.page_grid.itemSelectionChanged.connect(self._on_selection_changed)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.page_grid)
        self.stack.setMinimumHeight(WORK_AREA_MIN_HEIGHT)

        # Content header: the thumbnail size control, right-aligned above the pages.
        self.size_control = ThumbnailSizeControl(self.thumbnail_size)
        self.size_control.size_changed.connect(self._set_thumbnail_size)
        self.content_header = QWidget()
        header_layout = QHBoxLayout(self.content_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addStretch(1)
        header_layout.addWidget(self.size_control)

        self.content_section = QWidget()
        section_layout = QVBoxLayout(self.content_section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(SPACE_8)
        section_layout.addWidget(self.content_header)
        section_layout.addWidget(self.stack, 1)
        self.content_layout.addWidget(self.content_section, 1)

        # Export lives in the page footer, right-aligned and always visible; while an export
        # runs the same footer shows progress and Cancel in its place.
        self.job_footer = JobFooter("Export PDF")
        self.job_footer.setFixedWidth(EXPORT_FOOTER_WIDTH)
        self.export_button = self.job_footer.primary_button
        self.export_button.setToolTip("Save the pages as one new PDF (Ctrl+S)")
        self.export_button.clicked.connect(self._export_pdf)
        self.progress_bar = self.job_footer.progress_bar
        self.cancel_button = self.job_footer.cancel_button
        self.job_footer.cancel_requested.connect(self._cancel_export)
        self.footer_row = QWidget()
        footer_layout = QHBoxLayout(self.footer_row)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self.job_footer)
        self.page_layout.insertWidget(self.page_layout.indexOf(self.status_label), self.footer_row)

    def _tool_button(self, text: str, icon_name: str, tooltip: str, *, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        if primary:
            button.setObjectName("PrimaryButton")
        button.setIcon(icons.icon(icon_name, ON_PRIMARY if primary else TEXT_SECONDARY, ICON_INLINE))
        button.setIconSize(icons.icon_size(ICON_INLINE))
        button.setToolTip(tooltip)
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        return button

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._choose_pdfs)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self._redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self._redo)
        QShortcut(QKeySequence("Ctrl+A"), self, activated=self.page_grid.selectAll)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._export_pdf)

    # ------------------------------------------------------------ adding PDFs
    def add_files(self, paths: list[str]) -> None:
        self._add_pdf_paths(paths)

    def _choose_pdfs(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDFs", "", "PDF files (*.pdf)")
        if files:
            self._add_pdf_paths(files)

    def _add_pdf_paths(self, paths: list[str]) -> None:
        pdf_paths = [Path(path) for path in paths if Path(path).suffix.lower() == ".pdf"]
        if not pdf_paths:
            self.status_label.show_warning("Unsupported file type. Use PDF files.")
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

    # ------------------------------------------------------------ grid
    def _rebuild_grid(self, selected_ids: set[str] | None = None, *, keep_scroll: bool = True) -> None:
        selected = selected_ids if selected_ids is not None else self._selected_page_ids()
        scroll_value = self.page_grid.verticalScrollBar().value()
        self.page_grid.setUpdatesEnabled(False)
        # Restoring selection item by item would emit itemSelectionChanged once per item and
        # repolish every card each time; callers refresh state once after the rebuild.
        previous_blocked = self.page_grid.blockSignals(True)
        try:
            self.page_grid.clear()
            self._items_by_page_id = {}
            card_size = organizer_card_size(self.thumbnail_size)
            for position, page in enumerate(self.workspace.pages, start=1):
                item = QListWidgetItem()
                item.setData(PAGE_ID_ROLE, page.page_id)
                item.setSizeHint(card_size)
                self.page_grid.addItem(item)
                self._items_by_page_id[page.page_id] = item

                card = PageCardWidget(page, position, self.thumbnail_size)
                card.delete_requested.connect(self._delete_one)
                self.page_grid.register_drag_widgets(card)
                pixmap = self.thumbnail_cache.get(self._cache_key(page))
                if pixmap is not None:
                    card.set_thumbnail(pixmap)
                self.page_grid.setItemWidget(item, card)
                if page.page_id in selected:
                    item.setSelected(True)
        finally:
            self.page_grid.blockSignals(previous_blocked)
            self.page_grid.setUpdatesEnabled(True)
        self._sync_card_selection()
        if keep_scroll:
            self.page_grid.doItemsLayout()
            self.page_grid.verticalScrollBar().setValue(scroll_value)

    def _scroll_to_selection(self) -> None:
        for page_id in self.page_grid.page_ids():
            item = self._items_by_page_id.get(page_id)
            if item is not None and item.isSelected():
                self.page_grid.doItemsLayout()
                self.page_grid.setCurrentItem(item, QItemSelectionModel.NoUpdate)
                self.page_grid.scrollToItem(item)
                return

    def _cache_key(self, page: OrganizerPage) -> tuple[object, ThumbnailSize]:
        return (page.thumbnail_key, self.thumbnail_size)

    def _set_thumbnail_size(self, size: ThumbnailSize) -> None:
        size = ThumbnailSize(size)
        if size == self.thumbnail_size:
            return
        self.thumbnail_size = size
        QSettings().setValue(THUMBNAIL_SIZE_KEY, thumbnail_size_to_value(size))
        self.page_grid.set_card_size(organizer_card_size(size))
        self._rebuild_grid()
        self._start_thumbnail_worker()

    # ------------------------------------------------------------ thumbnails
    def _start_thumbnail_worker(self) -> None:
        missing_keys: set[object] = set()
        requests_list: list[tuple[str, object, Path, int, int, int]] = []
        dpi = THUMBNAIL_DPI[self.thumbnail_size]
        for page in self.workspace.pages:
            cache_key = self._cache_key(page)
            if cache_key in self.thumbnail_cache or cache_key in missing_keys:
                continue
            missing_keys.add(cache_key)
            requests_list.append((page.page_id, cache_key, page.source_path, page.source_page_index, page.rotation, dpi))
        requests = tuple(requests_list)
        if not requests:
            return
        self._stop_thumbnail_worker()
        thread = QThread()
        worker = OrganizerThumbnailWorker(requests)
        self.thumbnail_thread = thread
        self.thumbnail_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        worker.thumbnail_failed.connect(self._on_thumbnail_failed)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._on_thumbnail_thread_finished)
        keep_alive_until_finished(thread, worker)  # never deleted while running, even if this page is
        thread.start()

    def _stop_thumbnail_worker(self) -> None:
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.cancel()

    def _on_thumbnail_thread_finished(self) -> None:
        if self.sender() is self.thumbnail_thread:
            self.thumbnail_thread = None
            self.thumbnail_worker = None

    def _on_thumbnail_ready(self, page_id: str, cache_key: object, data: bytes) -> None:
        size = cache_key[1]
        pixmap = thumbnail_from_png_bytes(data, organizer_thumbnail_box(size), self.devicePixelRatioF())
        self.thumbnail_cache[cache_key] = pixmap
        self._set_matching_page_thumbnails(cache_key, pixmap)

    def _on_thumbnail_failed(self, page_id: str, cache_key: object) -> None:
        pixmap = thumbnail_placeholder("Preview\nunavailable", organizer_thumbnail_box(cache_key[1]))
        self.thumbnail_cache[cache_key] = pixmap
        self._set_matching_page_thumbnails(cache_key, pixmap)
        self.status_label.setText("Some page thumbnails could not be generated.")

    def _set_matching_page_thumbnails(self, cache_key: object, pixmap: QPixmap) -> None:
        for page in self.workspace.pages:
            if self._cache_key(page) == cache_key:
                self._set_page_thumbnail(page.page_id, pixmap)

    def _set_page_thumbnail(self, page_id: str, pixmap: QPixmap) -> None:
        item = self._item_for_page(page_id)
        if item is None:
            return
        card = self.page_grid.itemWidget(item)
        if isinstance(card, PageCardWidget):
            card.set_thumbnail(pixmap)

    # ------------------------------------------------------------ editing
    def _on_order_changed(self, before_ids: list[str], after_ids: list[str]) -> None:
        selected = self._selected_page_ids()
        try:
            self.history.record(self.workspace.snapshot())
            self.workspace.reorder_by_ids(after_ids)
        except ValueError:
            self.workspace.reorder_by_ids(before_ids)
        self._rebuild_grid(selected)
        self._scroll_to_selection()
        self._update_info()
        self._update_state()
        self.status_label.setText("Pages reordered.")

    def _move_selected(self, step: int) -> None:
        """Alt+Left / Alt+Right: move the selected pages one place, keeping them selected and in view."""
        if self.has_job_running():
            return
        selected = self._selected_page_ids()
        if not selected:
            return
        before = self.workspace.snapshot()
        if not self.workspace.move_pages(selected, step):
            return
        self.history.record(before)
        self._rebuild_grid(selected)
        self._scroll_to_selection()
        self._update_info()
        self._update_state()
        self.status_label.setText("Pages moved.")

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
        self._items_by_page_id = {}
        self.progress_bar.setValue(0)
        self._update_info()
        self._update_state()
        self.status_label.setText("Organizer cleared.")

    # ------------------------------------------------------------ export
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
        self.job_footer.set_progress(0, len(self.workspace.pages))
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
        worker.cancelled.connect(self._on_export_cancelled)
        worker.finished.connect(lambda _path: thread.quit())
        worker.failed.connect(lambda _message: thread.quit())
        worker.cancelled.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread, worker=worker: self._clear_export_worker(thread, worker))
        thread.start()

    def _cancel_export(self) -> None:
        if self.export_worker is not None:
            self.export_worker.cancel()
            self.status_label.setText("Cancelling after the current page...")

    def _on_export_progress(self, current: int, total: int) -> None:
        self.job_footer.set_progress(current, total)
        self.status_label.setText(f"Exporting {current} of {total} pages...")

    def _on_export_finished(self, output_path: str) -> None:
        self._set_exporting(False)
        self.status_label.show_success("Organized PDF exported successfully.")
        result = self.open_output_location(output_path, reveal=True)
        if not result.success:
            logger.warning("Could not reveal organized PDF: %s", result.message)
            self.status_label.show_warning(
                "Organized PDF exported successfully, but the output folder could not be opened."
            )

    def _on_export_cancelled(self) -> None:
        self._set_exporting(False)
        self.status_label.setText("Export cancelled.")

    def _on_export_failed(self, message: str) -> None:
        self._set_exporting(False)
        logger.error("PDF organizer export failed: %s", message)
        self.status_label.show_error(EXPORT_FAILED_MESSAGE)

    def _clear_export_worker(self, thread: QThread, worker: OrganizerExportWorker) -> None:
        if self.export_thread is thread:
            self.export_thread = None
        if self.export_worker is worker:
            self.export_worker = None
        self._update_state()

    def has_background_work(self) -> bool:
        return thread_is_running(self.export_thread) or thread_is_running(self.thumbnail_thread)

    def has_job_running(self) -> bool:
        return thread_is_running(self.export_thread)

    def stop_background_work(self) -> None:
        """Thumbnails and exports both stop after the current page."""
        self.page_grid.cancel_card_drag()
        self._stop_thumbnail_worker()
        if self.export_worker is not None:
            self.export_worker.cancel()

    # ------------------------------------------------------------ state
    def _selected_page_ids(self) -> set[str]:
        return {item.data(PAGE_ID_ROLE) for item in self.page_grid.selectedItems()}

    def _on_selection_changed(self) -> None:
        self._sync_card_selection()
        self._update_info()
        self._update_state()

    def _sync_card_selection(self) -> None:
        for index in range(self.page_grid.count()):
            item = self.page_grid.item(index)
            card = self.page_grid.itemWidget(item)
            if isinstance(card, PageCardWidget):
                card.set_selected(item.isSelected())

    def _item_for_page(self, page_id: str) -> QListWidgetItem | None:
        return self._items_by_page_id.get(page_id)

    def _update_info(self) -> None:
        if not self.workspace.pages:
            self.info_label.setText("No pages loaded")
            return
        pdf_count = len(self.workspace.loaded_sources)
        page_count = len(self.workspace.pages)
        pdf_label = "PDF" if pdf_count == 1 else "PDFs"
        page_label = "page" if page_count == 1 else "pages"
        text = f"{pdf_count} {pdf_label} loaded - {page_count} {page_label}"
        if not self._selected_page_ids():
            text += f"  ·  {SELECTION_HINT}"
        self.info_label.setText(text)

    def _update_state(self) -> None:
        has_pages = bool(self.workspace.pages)
        has_selection = bool(self._selected_page_ids())
        exporting = self.export_thread is not None and self.export_thread.isRunning()
        self.stack.setCurrentWidget(self.page_grid if has_pages else self.empty_state)
        self.size_control.setVisible(has_pages)
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
        self.size_control.setEnabled(not exporting)
        if not has_pages and not self.status_label.text():
            self.status_label.setText("No pages loaded.")

    def _set_exporting(self, exporting: bool) -> None:
        if exporting:
            self.page_grid.cancel_card_drag()
        self.add_button.setEnabled(not exporting)
        self.clear_button.setEnabled(not exporting and bool(self.workspace.pages))
        self.undo_button.setEnabled(not exporting and self.history.can_undo)
        self.redo_button.setEnabled(not exporting and self.history.can_redo)
        self.rotate_left_button.setEnabled(False if exporting else bool(self._selected_page_ids()))
        self.rotate_right_button.setEnabled(False if exporting else bool(self._selected_page_ids()))
        self.duplicate_button.setEnabled(False if exporting else bool(self._selected_page_ids()))
        self.delete_button.setEnabled(False if exporting else bool(self._selected_page_ids()))
        self.page_grid.setEnabled(not exporting)
        self.size_control.setEnabled(not exporting)
        self.job_footer.set_running(exporting)


def thumbnail_from_png_bytes(data: bytes, box: QSize = THUMBNAIL_SIZE, ratio: float = 1.0) -> QPixmap:
    pixmap = QPixmap()
    if not pixmap.loadFromData(data):
        return thumbnail_placeholder("Preview\nunavailable", box)
    return framed_thumbnail(pixmap, box, ratio)


def framed_thumbnail(source: QPixmap, box: QSize = THUMBNAIL_SIZE, ratio: float = 1.0) -> QPixmap:
    """The page centred in `box` with a soft shadow and hairline border, at device resolution."""
    ratio = max(1.0, ratio)
    canvas = QPixmap(round(box.width() * ratio), round(box.height() * ratio))
    canvas.setDevicePixelRatio(ratio)
    canvas.fill(QColor(CARD_BG))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.fillRect(QRectF(0, 0, box.width(), box.height()), QColor(PAGE_BG))
    inner = QSize(box.width() - 2 * SPACE_8, box.height() - 2 * SPACE_8)
    fitted = source.size().scaled(inner, Qt.KeepAspectRatio)
    x = (box.width() - fitted.width()) / 2
    y = (box.height() - fitted.height()) / 2
    page_rect = QRectF(x, y, fitted.width(), fitted.height())
    painter.fillRect(page_rect.translated(2, 3), QColor(*SHADOW_RGBA))
    painter.fillRect(page_rect, QColor(CARD_BG))
    painter.drawPixmap(page_rect, source, QRectF(source.rect()))
    painter.setPen(QPen(QColor(BORDER), 1))
    painter.drawRect(page_rect)
    painter.end()
    return canvas

