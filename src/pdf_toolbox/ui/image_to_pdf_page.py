from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image
from PySide6.QtCore import (
    QItemSelectionModel,
    QObject,
    QPoint,
    QPointF,
    QRectF,
    QSettings,
    QStandardPaths,
    Qt,
    QThread,
    Signal,
)
from PySide6.QtGui import QColor, QCursor, QDrag, QImage, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pdf_toolbox.core.image_collection import AddImagesResult, ImageCollection, ImageEntry, RejectedImage
from pdf_toolbox.core.image_corrections import (
    CorrectionSettings,
    SharpnessPreset,
    TonePreset,
    apply_corrections,
    flatten_to_white,
)
from pdf_toolbox.core.lru_cache import LruCache
from pdf_toolbox.core.image_validation import SUPPORTED_EXTENSIONS
from pdf_toolbox.core.image_to_pdf_preferences import (
    EXPORT_SETTING_KEYS,
    OUTPUT_FOLDER_KEY,
    export_settings_from_values,
    export_settings_to_values,
)
from pdf_toolbox.core.pdf_exporter import PdfExportCancelled, PdfExportError, PdfExporter
from pdf_toolbox.core.pdf_geometry import (
    ExportSettings,
    FitRect,
    MarginPreset,
    PageOrientation,
    PageSizeMode,
    calculate_page_layout,
    preview_rects,
)
from pdf_toolbox.core.output_location import open_output_location
from pdf_toolbox.ui.components.drop_area import empty_drop_area, local_paths, set_drop_active
from pdf_toolbox.ui.components.page import ToolPage
from pdf_toolbox.ui.components.settings_panel import SettingsPanel
from pdf_toolbox.ui.components.widgets import ElidedLabel, enum_combo, labeled_control
from pdf_toolbox.ui.threads import thread_is_running
from pdf_toolbox.ui import icons
from pdf_toolbox.ui.metrics import ROW_THUMBNAIL, ROW_THUMBNAIL_IMAGE, file_row_height, file_row_size_hint, order_number_width
from pdf_toolbox.ui.tokens import (
    BORDER,
    CARD_BG,
    CONTROL_HEIGHT,
    ICON_DELETE,
    ICON_INLINE,
    MIN_TARGET,
    ON_PRIMARY,
    PAGE_BG,
    PRIMARY,
    PRIMARY_TINT,
    RADIUS_CONTROL,
    SHADOW_RGBA,
    SPACE_16,
    SPACE_4,
    SPACE_8,
    TEXT_SECONDARY,
)


PATH_ROLE = Qt.UserRole + 1
AUTO_ORIENTATION_LABEL = "Auto - Based on Image"
PREVIEW_MAX_SIZE = (1100, 1100)
PREVIEW_CACHE_ENTRIES = 10
UNREADABLE_IMAGE_REASON = "This image could not be opened. The file may be damaged."
EXPORT_FAILED_MESSAGE = (
    "The PDF could not be created. Check that the images are still in their folder and that "
    "the save location is available, then try again."
)
FILE_ERROR_MESSAGE = "Couldn't read {filename}. Remove it and try again."
ORIENTATION_FIT_HINT = "Automatic for Fit"
NO_SELECTION_EDIT_TEXT = "Select an image to edit"
# Plain-language button labels; the presets and their values are unchanged.
SHARPNESS_LABELS = {
    SharpnessPreset.SOFT: "Softer",
    SharpnessPreset.NORMAL: "Original",
    SharpnessPreset.SHARP: "Clearer",
    SharpnessPreset.SHARPER: "Much clearer",
}
TONE_LABELS = {
    TonePreset.NORMAL: "Original",
    TonePreset.BRIGHT_10: "Brighter",
    TonePreset.BRIGHT_20: "Much brighter",
    TonePreset.BRIGHT_CONTRAST: "Brighter and\nsharper contrast",  # two lines: too long for a half-width button
    TonePreset.STRONG: "Vivid",
}
WORK_AREA_MIN_HEIGHT = 200  # list/preview areas shrink and scroll so the page fits 1366x768
logger = logging.getLogger(__name__)


class ImageListWidget(QListWidget):
    """Image rows that can be reordered by dragging or with Alt+Up / Alt+Down.

    Internal moves are applied here (not by Qt's row move) so the drop line drawn while
    dragging is exactly where the rows land; the page then rebuilds the rows from the collection.
    """

    files_dropped = Signal(list)
    order_changed = Signal(list)
    move_requested = Signal(int)  # -1 = up, 1 = down

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ImageList")
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        # Qt's own indicator is a thin black outline; paintEvent draws a primary-colour line instead.
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setSpacing(SPACE_4)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setAutoScroll(True)
        self.setAutoScrollMargin(48)
        self._drop_row: int | None = None  # insertion point 0..count while an internal drag is over the list

    def keyPressEvent(self, event) -> None:
        modifiers = event.modifiers() & ~Qt.KeypadModifier
        if modifiers == Qt.AltModifier and event.key() in (Qt.Key_Up, Qt.Key_Down):
            self.move_requested.emit(-1 if event.key() == Qt.Key_Up else 1)
            event.accept()
            return
        super().keyPressEvent(event)

    def startDrag(self, supported_actions) -> None:
        items = self.selectedItems()
        if not items:
            return
        mime = self.model().mimeData([self.indexFromItem(item) for item in items])
        if mime is None:
            return
        grabbed = self.currentItem() if self.currentItem() in items else items[0]
        drag = QDrag(self)
        drag.setMimeData(mime)
        ghost = self._drag_ghost(grabbed, len(items))
        drag.setPixmap(ghost)
        item_rect = self.visualItemRect(grabbed)
        cursor = self.viewport().mapFromGlobal(QCursor.pos())
        hot_x = min(max(cursor.x() - item_rect.left(), 0), item_rect.width() - 1)
        hot_y = min(max(cursor.y() - item_rect.top(), 0), item_rect.height() - 1)
        drag.setHotSpot(QPoint(hot_x, hot_y))
        drag.exec(Qt.MoveAction, Qt.MoveAction)
        self._set_drop_row(None)

    def _drag_ghost(self, item: QListWidgetItem, count: int) -> QPixmap:
        """A picture of the dragged row (card, primary border) so the user sees what they are moving."""
        rect = self.visualItemRect(item)
        ratio = self.devicePixelRatioF()
        canvas = QPixmap(round(rect.width() * ratio), round(rect.height() * ratio))
        canvas.setDevicePixelRatio(ratio)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        frame = QRectF(0.75, 0.75, rect.width() - 1.5, rect.height() - 1.5)
        painter.setPen(QPen(QColor(PRIMARY), 1.5))
        painter.setBrush(QColor(PRIMARY_TINT))
        painter.drawRoundedRect(frame, RADIUS_CONTROL, RADIUS_CONTROL)
        row = self.itemWidget(item)
        if row is not None:
            painter.drawPixmap(row.geometry().topLeft() - rect.topLeft(), row.grab())
        if count > 1:
            badge = f"{count} images"
            metrics = painter.fontMetrics()
            badge_rect = QRectF(0, 0, metrics.horizontalAdvance(badge) + 2 * SPACE_8, metrics.height() + SPACE_4)
            badge_rect.moveTopRight(QPointF(rect.width() - SPACE_8, SPACE_4))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(PRIMARY))
            painter.drawRoundedRect(badge_rect, badge_rect.height() / 2, badge_rect.height() / 2)
            painter.setPen(QColor(ON_PRIMARY))
            painter.drawText(badge_rect, Qt.AlignCenter, badge)
        painter.end()
        faded = QPixmap(canvas.size())
        faded.setDevicePixelRatio(ratio)
        faded.fill(Qt.transparent)
        painter = QPainter(faded)
        painter.setOpacity(0.92)
        painter.drawPixmap(0, 0, canvas)
        painter.end()
        return faded

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
        super().dragMoveEvent(event)  # also drives autoscroll near the top and bottom edges
        if event.source() is self:
            self._set_drop_row(self._insertion_row(event.position().toPoint()))
            event.setDropAction(Qt.MoveAction)
            event.accept()

    def dropEvent(self, event) -> None:
        set_drop_active(self, False)
        if event.mimeData().hasUrls():
            self.files_dropped.emit(local_paths(event.mimeData()))
            event.acceptProposedAction()
            return

        if event.source() is not self:
            event.ignore()
            return
        target = self._insertion_row(event.position().toPoint())
        self._set_drop_row(None)
        event.setDropAction(Qt.MoveAction)
        event.accept()
        paths = self.paths_in_order()
        moving = {item.data(PATH_ROLE) for item in self.selectedItems()}
        new_order = (
            [path for path in paths[:target] if path not in moving]
            + [path for path in paths if path in moving]
            + [path for path in paths[target:] if path not in moving]
        )
        if new_order != paths:
            self.order_changed.emit(new_order)

    def dragLeaveEvent(self, event) -> None:
        set_drop_active(self, False)
        self._set_drop_row(None)
        super().dragLeaveEvent(event)

    def _insertion_row(self, position: QPoint) -> int:
        """Row the dragged images would be inserted before (count = after the last row)."""
        for row in range(self.count()):
            if position.y() < self.visualItemRect(self.item(row)).center().y():
                return row
        return self.count()

    def _set_drop_row(self, row: int | None) -> None:
        if row != self._drop_row:
            self._drop_row = row
            self.viewport().update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._drop_row is None or self.count() == 0:
            return
        gap = self.spacing() / 2
        if self._drop_row < self.count():
            rect = self.visualItemRect(self.item(self._drop_row))
            y = rect.top() - gap
        else:
            rect = self.visualItemRect(self.item(self.count() - 1))
            y = rect.bottom() + gap + 1
        y = min(max(y, 2), self.viewport().height() - 2)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(PRIMARY), 2.5, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(rect.left() + 10, y), QPointF(rect.right() - 4, y))
        painter.setBrush(QColor(PRIMARY))
        painter.drawEllipse(QPointF(rect.left() + 6, y), 3.5, 3.5)
        painter.end()

    def paths_in_order(self) -> list[str]:
        return [self.item(index).data(PATH_ROLE) for index in range(self.count())]


class ImageRowWidget(QWidget):
    delete_requested = Signal(str)

    def __init__(self, entry: ImageEntry, thumbnail: QPixmap, order_number: int) -> None:
        super().__init__()
        self.setObjectName("ImageRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.path = str(entry.path)
        self.setMinimumHeight(file_row_height())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_4, SPACE_4, SPACE_8, SPACE_4)
        layout.setSpacing(SPACE_8)

        handle = QLabel()
        handle.setObjectName("DragHandle")
        handle.setFixedSize(ICON_DELETE, MIN_TARGET)
        handle.setAlignment(Qt.AlignCenter)
        handle.setPixmap(
            icons.icon("grip-vertical", TEXT_SECONDARY, ICON_DELETE).pixmap(icons.icon_size(ICON_DELETE), self.devicePixelRatioF())
        )
        handle.setCursor(Qt.OpenHandCursor)
        handle.setToolTip("Drag to change the order.\nOr select an image and press Alt+Up or Alt+Down.")
        layout.addWidget(handle, alignment=Qt.AlignVCenter)

        order_label = QLabel(str(order_number))
        order_label.setObjectName("ImageOrderNumber")
        order_label.setFixedWidth(order_number_width())
        order_label.setAlignment(Qt.AlignCenter)

        thumbnail_label = QLabel()
        thumbnail_label.setObjectName("RowThumbnail")
        thumbnail_label.setFixedSize(ROW_THUMBNAIL, ROW_THUMBNAIL)
        thumbnail_label.setAlignment(Qt.AlignCenter)
        thumbnail_label.setPixmap(thumbnail)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(SPACE_4)

        filename = ElidedLabel(entry.filename)
        filename.setObjectName("ImageName")
        filename.setToolTip(entry.filename)

        dimensions = QLabel(f"{entry.width} x {entry.height} px")
        dimensions.setObjectName("ImageDimensions")

        text_layout.addWidget(filename)
        text_layout.addWidget(dimensions)

        delete_button = QPushButton()
        delete_button.setObjectName("IconButton")
        delete_button.setToolTip("Remove image")
        delete_button.setFixedSize(MIN_TARGET, MIN_TARGET)
        delete_button.setIcon(icons.icon("trash-2", TEXT_SECONDARY, ICON_DELETE))
        delete_button.setIconSize(icons.icon_size(ICON_DELETE))
        delete_button.clicked.connect(lambda: self.delete_requested.emit(self.path))

        layout.addWidget(order_label)
        layout.addWidget(thumbnail_label)
        layout.addLayout(text_layout, 1)
        layout.addWidget(delete_button, alignment=Qt.AlignVCenter)


class PreviewWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PreviewWidget")
        self.setMinimumSize(280, WORK_AREA_MIN_HEIGHT)
        self._pixmap: QPixmap | None = None
        self._image_size: tuple[int, int] | None = None
        self._settings = ExportSettings()
        self._empty_text = "Add images to begin"

    def set_preview(
        self,
        pixmap: QPixmap | None,
        image_size: tuple[int, int] | None,
        settings: ExportSettings,
        empty_text: str = "Select an image to preview",
    ) -> None:
        self._pixmap = pixmap
        self._image_size = image_size
        self._settings = settings
        self._empty_text = empty_text
        self.update()

    def current_layout(self):
        if self._image_size is None:
            return None
        return calculate_page_layout(self._image_size[0], self._image_size[1], self._settings)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(PAGE_BG))

        if self._pixmap is None or self._image_size is None:
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.drawText(self.rect(), Qt.AlignCenter, self._empty_text)
            return

        layout = self.current_layout()
        if layout is None:
            return
        rects = preview_rects(layout, self.width(), self.height(), inset=SPACE_16)
        if rects is None:
            return
        page_rect = _qrect(rects.page)

        # White page with a soft shadow, as it will print.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(*SHADOW_RGBA))
        painter.drawRect(page_rect.translated(2, 3))
        painter.setBrush(QColor(CARD_BG))
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.drawRect(page_rect)

        if layout.margin > 0:
            # Margin guide: a faint dashed line where the printable area starts (not printed).
            guide = QPen(QColor(BORDER), 1, Qt.DashLine)
            painter.setPen(guide)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(_qrect(rects.content))

        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(_qrect(rects.image), self._pixmap, QRectF(self._pixmap.rect()))


def _qrect(rect: FitRect) -> QRectF:
    return QRectF(rect.x0, rect.y0, rect.width, rect.height)


class ExportWorker(QObject):
    finished = Signal(str)
    failed = Signal(str, str)  # log details, name of the image at fault ("" if none)
    cancelled = Signal()
    progress = Signal(int, int)

    def __init__(
        self,
        entries: tuple[ImageEntry, ...],
        output_path: Path,
        settings: ExportSettings,
        overwrite: bool,
    ) -> None:
        super().__init__()
        self.entries = entries
        self.output_path = output_path
        self.settings = settings
        self.overwrite = overwrite
        self.exporter = PdfExporter()
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True

    def run(self) -> None:
        try:
            result = self.exporter.export(
                self.entries,
                self.output_path,
                settings=self.settings,
                overwrite=self.overwrite,
                progress_callback=self.progress.emit,
                cancel_callback=lambda: self.cancel_requested,
            )
        except PdfExportCancelled:
            self.cancelled.emit()
            return
        except Exception as exc:
            logger.exception("Image to PDF export failed")
            filename = exc.filename if isinstance(exc, PdfExportError) else None
            self.failed.emit(str(exc), filename or "")
            return

        self.finished.emit(str(result))


class ImageToPdfPage(ToolPage):
    ACCEPTED_EXTENSIONS = frozenset(SUPPORTED_EXTENSIONS)
    ACCEPTED_DESCRIPTION = "JPG, JPEG or PNG images"

    def __init__(self) -> None:
        super().__init__()
        self.collection = ImageCollection()
        self.export_thread: QThread | None = None
        self.export_worker: ExportWorker | None = None
        self.preview_cache: LruCache[tuple[str, int, tuple[str, str]], tuple[QPixmap, tuple[int, int]]] = LruCache(
            PREVIEW_CACHE_ENTRIES
        )
        self.thumbnail_cache: dict[tuple[str, int], QPixmap] = {}
        self.sharpness_buttons: dict[SharpnessPreset, QPushButton] = {}
        self.tone_buttons: dict[TonePreset, QPushButton] = {}
        self.open_output_location = open_output_location
        self._fixed_orientation = PageOrientation.PORTRAIT

        self._build_ui()
        self._load_export_preferences()
        self._sync_orientation_control()
        self._update_state()
        self._update_preview()

    def _build_ui(self) -> None:
        self.build_scaffold("Image → PDF", "Import images, arrange their order, and export them as one PDF.")

        self.add_button = QPushButton("Add Images")
        self.add_button.setObjectName("PrimaryButton")
        self.clear_button = QPushButton("Clear")
        self.add_button.clicked.connect(self._choose_images)
        self.clear_button.clicked.connect(self._clear_images)
        self.action_bar.addWidget(self.add_button)
        self.action_bar.addWidget(self.clear_button)
        self.finish_action_bar()

        self.list_heading = QLabel("Imported Images")
        self.list_heading.setObjectName("PanelHeading")
        self.stack = QStackedWidget()
        self.empty_state, empty = empty_drop_area(
            "Add images to create a PDF",
            "Drag and drop JPG, JPEG, or PNG files here.",
            "Add Images",
        )
        self.empty_state.files_dropped.connect(self.add_dropped_files)
        empty.action_requested.connect(self._choose_images)
        self.image_list = ImageListWidget()
        self.image_list.files_dropped.connect(self.add_dropped_files)
        self.image_list.order_changed.connect(self._sync_order_from_list)
        self.image_list.move_requested.connect(self._move_selected)
        self.image_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.image_list)
        self.stack.setMinimumSize(330, WORK_AREA_MIN_HEIGHT)

        self.preview = PreviewWidget()

        self.list_section = QWidget()
        list_area = QVBoxLayout(self.list_section)
        list_area.setContentsMargins(0, 0, 0, 0)
        list_area.setSpacing(SPACE_8)
        list_area.addWidget(self.list_heading)
        list_area.addWidget(self.stack, 1)

        self.preview_section = QWidget()
        preview_area = QVBoxLayout(self.preview_section)
        preview_area.setContentsMargins(0, 0, 0, 0)
        preview_area.setSpacing(SPACE_8)
        self.preview_heading = QLabel("Preview")
        self.preview_heading.setObjectName("PanelHeading")
        preview_area.addWidget(self.preview_heading)
        preview_area.addWidget(self.preview, 1)
        self.preview_caption = QLabel("")
        self.preview_caption.setObjectName("SubtleText")
        self.preview_caption.setAlignment(Qt.AlignCenter)
        self.preview_caption.setMinimumHeight(self.preview_caption.fontMetrics().height())
        preview_area.addWidget(self.preview_caption)

        self.settings_panel = self._build_settings_panel()
        self.content_layout.addWidget(self.list_section, 4)
        self.content_layout.addWidget(self.preview_section, 4)
        self.content_layout.addWidget(self.settings_panel, 3)

    def _build_settings_panel(self) -> SettingsPanel:
        panel = SettingsPanel("Settings", "Export PDF", min_width=310, max_width=390)
        layout = panel.body_layout

        self.page_size_combo = enum_combo(PageSizeMode, min_contents_length=24)
        self.page_size_combo.currentIndexChanged.connect(self._on_export_settings_changed)
        layout.addLayout(labeled_control("Page Size", self.page_size_combo))

        self.orientation_combo = enum_combo(PageOrientation, min_contents_length=24)
        self.orientation_combo.currentIndexChanged.connect(self._on_export_settings_changed)
        # The hint sits on the label's line so the field keeps the same height as its neighbours.
        orientation_field = QVBoxLayout()
        orientation_field.setSpacing(SPACE_4)
        orientation_label_row = QHBoxLayout()
        orientation_label_row.setSpacing(SPACE_8)
        orientation_label = QLabel("Orientation")
        orientation_label.setObjectName("FieldLabel")
        self.orientation_hint = QLabel(ORIENTATION_FIT_HINT)
        self.orientation_hint.setObjectName("FieldHint")
        orientation_label_row.addWidget(orientation_label)
        orientation_label_row.addStretch(1)
        orientation_label_row.addWidget(self.orientation_hint)
        orientation_field.addLayout(orientation_label_row)
        orientation_field.addWidget(self.orientation_combo)
        layout.addLayout(orientation_field)

        self.margin_combo = enum_combo(MarginPreset, min_contents_length=24)
        self.margin_combo.currentIndexChanged.connect(self._on_export_settings_changed)
        layout.addLayout(labeled_control("Margin", self.margin_combo))

        self.corrections_toggle = QPushButton("Corrections")
        self.corrections_toggle.setCheckable(True)
        # Right-to-left puts the chevron after the label; the label itself is left unchanged.
        self.corrections_toggle.setLayoutDirection(Qt.RightToLeft)
        self.corrections_toggle.setIconSize(icons.icon_size(ICON_INLINE))
        self.corrections_toggle.setIcon(icons.icon("chevron-down", TEXT_SECONDARY, ICON_INLINE))
        self.corrections_toggle.clicked.connect(self._toggle_corrections)
        layout.addWidget(self.corrections_toggle)

        self.corrections_panel = self._build_corrections_panel()
        self.corrections_panel.setVisible(False)
        layout.addWidget(self.corrections_panel)
        panel.finish_body()

        self.job_footer = panel.footer
        self.export_button = panel.footer.primary_button
        self.export_button.clicked.connect(self._export_pdf)
        self.progress_bar = panel.footer.progress_bar
        self.cancel_button = panel.footer.cancel_button
        panel.footer.cancel_requested.connect(self._cancel_export)
        return panel

    def _build_corrections_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("CorrectionsPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, SPACE_4, 0, 0)
        layout.setSpacing(SPACE_8)

        self.selection_label = ElidedLabel(NO_SELECTION_EDIT_TEXT)
        self.selection_label.setObjectName("EditingLabel")
        layout.addWidget(self.selection_label)

        layout.addWidget(self._preset_section("Sharpen / Soften", SharpnessPreset, SHARPNESS_LABELS, self._set_sharpness))
        layout.addWidget(self._preset_section("Brightness / Contrast", TonePreset, TONE_LABELS, self._set_tone))

        self.apply_all_button = QPushButton("Apply to all images")
        self.apply_all_button.setToolTip("Give every image the same corrections as this one.")
        self.apply_all_button.clicked.connect(self._apply_corrections_to_all)
        layout.addWidget(self.apply_all_button)

        self.reset_corrections_button = QPushButton("Reset Corrections")
        self.reset_corrections_button.clicked.connect(self._reset_selected_corrections)
        layout.addWidget(self.reset_corrections_button)

        return panel

    def _preset_section(self, title: str, enum_type, labels: dict, callback) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_4)

        label = QLabel(title)
        label.setObjectName("FieldLabel")
        layout.addWidget(label)

        grid = QGridLayout()
        grid.setSpacing(SPACE_4)
        group = QButtonGroup(section)
        group.setExclusive(True)

        presets = list(enum_type)
        for index, preset in enumerate(presets):
            button = QPushButton(labels[preset])
            button.setObjectName("PresetButton")
            button.setCheckable(True)
            button.setMinimumHeight(CONTROL_HEIGHT)
            button.setToolTip(labels[preset].replace("\n", " "))
            # Ignored width keeps both columns equal; Preferred height lets a one-line button
            # match a two-line neighbour in the same row.
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            button.clicked.connect(lambda _checked=False, value=preset: callback(value))
            group.addButton(button)
            lone_last = index == len(presets) - 1 and index % 2 == 0
            grid.addWidget(button, index // 2, index % 2, 1, 2 if lone_last else 1)
            if enum_type is SharpnessPreset:
                self.sharpness_buttons[preset] = button
            else:
                self.tone_buttons[preset] = button

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return section

    def _choose_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select Images", "", "Images (*.jpg *.jpeg *.png)")
        if files:
            self._add_images(files)

    def add_files(self, paths: list[str]) -> None:
        self._add_images(paths)

    def _add_images(self, paths: list[str]) -> None:
        had_selection = bool(self.image_list.selectedItems())
        result = self._reject_unreadable(self.collection.add_paths(paths))
        # Selection changes during the rebuild would each regenerate the preview; refresh once below.
        previous_blocked = self.image_list.blockSignals(True)
        try:
            self._sync_list_from_collection()
            if result.added and not had_selection:
                self._select_path(result.added[0].path)
        finally:
            self.image_list.blockSignals(previous_blocked)
        self._show_import_result(result)
        self._sync_correction_controls()
        self._update_state()
        self._update_preview()

    def _reject_unreadable(self, result: AddImagesResult) -> AddImagesResult:
        """Header validation no longer decodes pixels; files whose thumbnail cannot be decoded are rejected here."""
        unreadable = [entry for entry in result.added if self._load_thumbnail(entry.path) is None]
        if not unreadable:
            return result
        self.collection.remove_paths([entry.path for entry in unreadable])
        unreadable_paths = {entry.path for entry in unreadable}
        return AddImagesResult(
            added=tuple(entry for entry in result.added if entry.path not in unreadable_paths),
            rejected=result.rejected + tuple(RejectedImage(entry.path, UNREADABLE_IMAGE_REASON) for entry in unreadable),
            duplicates=result.duplicates,
        )

    def _append_item(self, entry: ImageEntry, order_number: int) -> None:
        item = QListWidgetItem()
        item.setData(PATH_ROLE, str(entry.path))
        item.setSizeHint(file_row_size_hint())
        self.image_list.addItem(item)
        row = ImageRowWidget(entry, self._thumbnail_for(entry.path), order_number)
        row.delete_requested.connect(self._remove_path)
        self.image_list.setItemWidget(item, row)

    def _thumbnail_for(self, path: Path) -> QPixmap:
        pixmap = self._load_thumbnail(path)
        if pixmap is None:
            pixmap = QPixmap(ROW_THUMBNAIL_IMAGE, ROW_THUMBNAIL_IMAGE)
            pixmap.fill(QColor(CARD_BG))
        return pixmap

    def _load_thumbnail(self, path: Path) -> QPixmap | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        cache_key = (str(path), stat.st_mtime_ns)
        cached = self.thumbnail_cache.get(cache_key)
        if cached is not None:
            return cached

        target = ROW_THUMBNAIL_IMAGE
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        raw_size = reader.size()
        if raw_size.isValid() and raw_size.width() > 0 and raw_size.height() > 0:
            # Decode at reduced size (JPEG uses DCT scaling). The scaled size applies before
            # auto-transform, so fit the raw aspect ratio; 2x headroom keeps the final smooth downscale sharp.
            decode_size = raw_size.scaled(target * 2, target * 2, Qt.KeepAspectRatio)
            if decode_size.width() < raw_size.width():
                reader.setScaledSize(decode_size)
        image = reader.read()
        if image.isNull():
            logger.warning("Thumbnail could not be decoded: %s (%s)", path, reader.errorString())
            return None
        pixmap = QPixmap.fromImage(image).scaled(target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.thumbnail_cache[cache_key] = pixmap
        return pixmap

    def _sync_list_from_collection(self) -> None:
        selected_paths = {item.data(PATH_ROLE) for item in self.image_list.selectedItems()}
        current_path = self._current_path()
        # Rebuilding restores selection item by item; keep that from firing a preview per item.
        # Callers refresh controls, state, and preview once afterwards.
        previous_blocked = self.image_list.blockSignals(True)
        try:
            self.image_list.clear()
            for order_number, entry in enumerate(self.collection.entries, start=1):
                self._append_item(entry, order_number)
                item = self.image_list.item(self.image_list.count() - 1)
                if str(entry.path) == current_path:
                    self.image_list.setCurrentItem(item, QItemSelectionModel.NoUpdate)
                if str(entry.path) in selected_paths:
                    item.setSelected(True)
        finally:
            self.image_list.blockSignals(previous_blocked)

    def _sync_order_from_list(self, paths: list[str]) -> None:
        try:
            self.collection.reorder_by_paths(paths)
        except ValueError:
            self._sync_list_from_collection()
            self._sync_correction_controls()
            self._update_state()
            return
        self._sync_list_from_collection()
        self._scroll_to_current()
        self._sync_correction_controls()
        self._update_state()
        self._update_preview()

    def _move_selected(self, step: int) -> None:
        """Alt+Up / Alt+Down: move the selected images one place, keeping them selected and in view."""
        if self.has_background_work():
            return
        selected = [item.data(PATH_ROLE) for item in self.image_list.selectedItems()]
        if not selected or not self.collection.move_paths(selected, step):
            return
        self._sync_list_from_collection()
        self._scroll_to_current()
        self._sync_correction_controls()
        self._update_state()
        self._update_preview()

    def _scroll_to_current(self) -> None:
        current = self.image_list.currentItem()
        if current is not None:
            self.image_list.scrollToItem(current)

    def _remove_path(self, path: str) -> None:
        removed_index = self._row_for_path(path)
        removed_current = path == self._current_path()
        self.collection.remove_paths([path])
        self._sync_list_from_collection()
        if self.collection.entries and (removed_current or self._current_entry() is None):
            next_row = min(max(removed_index, 0), len(self.collection.entries) - 1)
            self.image_list.setCurrentRow(next_row)
        self.status_label.setText("Image removed.")
        self._sync_correction_controls()
        self._update_state()
        self._update_preview()

    def _clear_images(self) -> None:
        self.collection.clear()
        self.image_list.clear()
        self.preview_cache.clear()
        self.thumbnail_cache.clear()
        self.status_label.setText("Image list cleared.")
        self._update_state()
        self._update_preview()

    def _export_pdf(self) -> None:
        if not self.collection.entries:
            return
        output, _ = QFileDialog.getSaveFileName(self, "Export PDF", self._suggested_output_path(), "PDF files (*.pdf)")
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
        self.job_footer.set_progress(0, len(self.collection.entries))
        self.status_label.setText("Exporting PDF...")
        self.export_thread = QThread(self)
        self.export_worker = ExportWorker(self.collection.entries, output_path, self._export_settings(), overwrite)
        self.export_worker.moveToThread(self.export_thread)
        self.export_thread.started.connect(self.export_worker.run)
        self.export_worker.progress.connect(self._on_export_progress)
        self.export_worker.finished.connect(self._on_export_finished)
        self.export_worker.failed.connect(self._on_export_failed)
        self.export_worker.cancelled.connect(self._on_export_cancelled)
        self.export_worker.finished.connect(self.export_thread.quit)
        self.export_worker.failed.connect(self.export_thread.quit)
        self.export_worker.cancelled.connect(self.export_thread.quit)
        self.export_thread.finished.connect(self.export_worker.deleteLater)
        self.export_thread.finished.connect(self.export_thread.deleteLater)
        self.export_thread.finished.connect(self._clear_export_worker)
        self.export_thread.start()

    def _suggested_output_path(self) -> str:
        """Last folder a PDF was saved to (or Documents), named after the first image."""
        saved = QSettings().value(OUTPUT_FOLDER_KEY, "", str)
        folder = Path(saved) if saved else None
        if folder is None or not folder.is_dir():
            folder = _documents_folder()
        return str(folder / f"{self.collection.entries[0].path.stem}.pdf")

    def has_background_work(self) -> bool:
        return thread_is_running(self.export_thread)

    def stop_background_work(self) -> None:
        """Ask a running export to stop before its next image."""
        if self.export_worker is not None:
            self.export_worker.cancel()

    def _cancel_export(self) -> None:
        if self.export_worker is not None:
            self.export_worker.cancel()
            self.status_label.setText("Cancelling after the current image...")

    def _on_export_progress(self, current: int, total: int) -> None:
        self.job_footer.set_progress(current, total)
        self.status_label.setText(f"Exporting PDF... {current}/{total}")

    def _on_export_finished(self, output_path: str) -> None:
        self._set_exporting(False)
        QSettings().setValue(OUTPUT_FOLDER_KEY, str(Path(output_path).parent))
        self.status_label.show_success("PDF exported successfully.")
        result = self.open_output_location(output_path, reveal=True)
        if not result.success:
            logger.warning("Could not reveal exported PDF: %s", result.message)
            self.status_label.show_warning("PDF exported successfully, but the output folder could not be opened.")

    def _on_export_cancelled(self) -> None:
        self._set_exporting(False)
        self.status_label.setText("Export cancelled.")

    def _on_export_failed(self, message: str, filename: str = "") -> None:
        self._set_exporting(False)
        logger.error("Image to PDF export failed: %s", message)
        if filename:
            self.status_label.show_error(FILE_ERROR_MESSAGE.format(filename=filename))
        else:
            self.status_label.show_error(EXPORT_FAILED_MESSAGE)

    def _clear_export_worker(self) -> None:
        self.export_thread = None
        self.export_worker = None
        self._update_state()

    def _set_exporting(self, exporting: bool) -> None:
        has_images = len(self.collection) > 0
        has_selection = bool(self.image_list.selectedItems())
        self.add_button.setEnabled(not exporting)
        self.clear_button.setEnabled(not exporting and has_images)
        self.export_button.setEnabled(not exporting and has_images)
        self.image_list.setEnabled(not exporting)
        self._set_correction_controls_enabled(not exporting and has_selection)
        self.job_footer.set_running(exporting)

    def _update_state(self) -> None:
        has_images = len(self.collection) > 0
        has_selection = bool(self.image_list.selectedItems())
        exporting = self.export_thread is not None and self.export_thread.isRunning()
        self.stack.setCurrentWidget(self.image_list if has_images else self.empty_state)
        self.add_button.setEnabled(not exporting)
        self.clear_button.setEnabled(not exporting and has_images)
        self.export_button.setEnabled(not exporting and has_images)
        self._set_correction_controls_enabled(not exporting and has_selection)
        self._sync_orientation_control()
        count = len(self.collection)
        self.count_label.setText(
            "No images loaded" if count == 0 else "1 image loaded" if count == 1 else f"{count} images loaded"
        )

        selected_count = len(self.image_list.selectedItems())
        if not has_selection:
            self.selection_label.set_full_text(NO_SELECTION_EDIT_TEXT)
        elif selected_count == 1:
            self.selection_label.set_full_text(f"Editing: {Path(self.image_list.selectedItems()[0].data(PATH_ROLE)).name}")
        else:
            self.selection_label.set_full_text(f"Editing: {selected_count} selected images")

        if not has_images and not self.status_label.text():
            self.status_label.setText("No images loaded.")

    def _set_correction_controls_enabled(self, enabled: bool) -> None:
        for button in [*self.sharpness_buttons.values(), *self.tone_buttons.values(), self.reset_corrections_button]:
            button.setEnabled(enabled)
        self.apply_all_button.setEnabled(enabled and len(self.collection) > 1)

    def _show_import_result(self, result: AddImagesResult) -> None:
        messages: list[str] = []
        if result.added:
            messages.append(f"Added {len(result.added)} image(s).")
        if result.duplicates:
            messages.append(f"Skipped {len(result.duplicates)} duplicate file(s).")
        if result.rejected:
            messages.append(f"Rejected {len(result.rejected)} unsupported or invalid file(s).")
        if messages:
            if result.rejected or result.duplicates:
                self.status_label.show_warning(" ".join(messages))
            else:
                self.status_label.setText(" ".join(messages))
        if result.rejected:
            details = "\n".join(f"{item.path.name}: {item.reason}" for item in result.rejected[:8])
            if len(result.rejected) > 8:
                details += f"\n...and {len(result.rejected) - 8} more."
            QMessageBox.warning(self, "Some Files Were Not Added", details)

    def _on_selection_changed(self) -> None:
        self._sync_correction_controls()
        self._update_state()
        self._update_preview()

    def _on_export_settings_changed(self, _index: int | None = None) -> None:
        if self.sender() is self.orientation_combo and self._page_size_mode() != PageSizeMode.FIT:
            self._fixed_orientation = PageOrientation(self.orientation_combo.currentData())
        self._sync_orientation_control()
        self._save_export_preferences()
        self._update_preview()

    def _load_export_preferences(self) -> None:
        store = QSettings()
        saved = export_settings_from_values({key: store.value(key) for key in EXPORT_SETTING_KEYS})
        self._fixed_orientation = PageOrientation(saved.orientation)
        for combo, value in ((self.page_size_combo, saved.page_size), (self.margin_combo, saved.margin)):
            previous_blocked = combo.blockSignals(True)
            try:
                combo.setCurrentIndex(max(0, combo.findData(value.value)))
            finally:
                combo.blockSignals(previous_blocked)

    def _save_export_preferences(self) -> None:
        store = QSettings()
        for key, value in export_settings_to_values(self._export_settings()).items():
            store.setValue(key, value)

    def _toggle_corrections(self, checked: bool) -> None:
        self.corrections_panel.setVisible(checked)
        chevron = "chevron-up" if checked else "chevron-down"
        self.corrections_toggle.setIcon(icons.icon(chevron, TEXT_SECONDARY, ICON_INLINE))

    def _set_sharpness(self, preset: SharpnessPreset) -> None:
        self._update_selected_corrections(sharpness=preset)

    def _set_tone(self, preset: TonePreset) -> None:
        self._update_selected_corrections(tone=preset)

    def _reset_selected_corrections(self) -> None:
        self._update_selected_corrections(reset_all=True)

    def _apply_corrections_to_all(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        count = self.collection.apply_corrections_to_all(entry.corrections)
        self._sync_correction_controls()
        self._update_preview()
        self.status_label.show_success(f"Applied the same corrections to all {count} images.")

    def _update_selected_corrections(
        self,
        *,
        sharpness: SharpnessPreset | None = None,
        tone: TonePreset | None = None,
        reset_all: bool = False,
    ) -> None:
        for item in self.image_list.selectedItems():
            entry = self._entry_for_path(item.data(PATH_ROLE))
            if entry is None:
                continue
            corrections = entry.corrections.reset_all() if reset_all else entry.corrections
            corrections = CorrectionSettings(
                sharpness=sharpness or corrections.sharpness,
                tone=tone or corrections.tone,
            )
            self.collection.update_corrections(entry.path, corrections)
        self._sync_correction_controls()
        self._update_preview()

    def _sync_correction_controls(self) -> None:
        entry = self._current_entry()
        corrections = entry.corrections if entry is not None else CorrectionSettings()
        for preset, button in self.sharpness_buttons.items():
            button.setChecked(preset == corrections.sharpness)
        for preset, button in self.tone_buttons.items():
            button.setChecked(preset == corrections.tone)

    def _update_preview(self) -> None:
        entry = self._current_entry()
        if entry is None:
            empty_text = "Add images to begin" if not self.collection.entries else "Select an image to preview"
            self.preview.set_preview(None, None, self._export_settings(), empty_text)
            self.preview_caption.setText("")
            return
        self.preview_caption.setText(self._preview_caption(entry))
        try:
            pixmap, size = self._preview_pixmap_for_entry(entry)
        except Exception:
            logger.warning("Preview could not be generated for %s", entry.path, exc_info=True)
            message = f"{entry.filename}: {UNREADABLE_IMAGE_REASON}"
            self.preview.set_preview(None, None, self._export_settings(), message)
            self.status_label.show_warning(message)
            return
        self.preview.set_preview(pixmap, size, self._export_settings())

    def _preview_caption(self, entry: ImageEntry) -> str:
        entries = self.collection.entries
        position = next((index for index, item in enumerate(entries, start=1) if item.path == entry.path), 1)
        settings = self._export_settings()
        if settings.page_size == PageSizeMode.FIT:
            page_text = "Original size"
        else:
            page_text = f"{settings.page_size.value} {settings.orientation.value.lower()}"
        return f"Image {position} of {len(entries)} \u00b7 {page_text}"

    def _preview_pixmap_for_entry(self, entry: ImageEntry) -> tuple[QPixmap, tuple[int, int]]:
        stat = entry.path.stat()
        cache_key = (str(entry.path), stat.st_mtime_ns, entry.corrections.cache_key())
        cached = self.preview_cache.get(cache_key)
        if cached is not None:
            return cached

        # Orientation-corrected full size from validation drives the page layout; the pixels
        # are shrunk first (JPEG draft decode) and corrections run on the small image.
        source_size = (entry.width, entry.height)
        with Image.open(entry.path) as image:
            image.draft("RGB", PREVIEW_MAX_SIZE)
            image.thumbnail(PREVIEW_MAX_SIZE, Image.Resampling.LANCZOS)
            corrected = apply_corrections(image, entry.corrections)
        flattened = flatten_to_white(corrected)
        qimage = self._pil_to_qimage(flattened)
        pixmap = QPixmap.fromImage(qimage)
        result = (pixmap, source_size)
        self.preview_cache[cache_key] = result
        return result

    def _pil_to_qimage(self, image: Image.Image) -> QImage:
        rgb = image.convert("RGB")
        data = rgb.tobytes("raw", "RGB")
        return QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888).copy()

    def _export_settings(self) -> ExportSettings:
        return ExportSettings(
            page_size=self._page_size_mode(),
            orientation=self._current_orientation(),
            margin=MarginPreset(self.margin_combo.currentData()),
        )

    def _current_orientation(self) -> PageOrientation:
        if self._page_size_mode() == PageSizeMode.FIT:
            return self._fixed_orientation
        return PageOrientation(self.orientation_combo.currentData())

    def _sync_orientation_control(self) -> None:
        mode = self._page_size_mode()
        previous_blocked = self.orientation_combo.blockSignals(True)
        try:
            if mode == PageSizeMode.FIT:
                self.orientation_combo.clear()
                self.orientation_combo.addItem(AUTO_ORIENTATION_LABEL, AUTO_ORIENTATION_LABEL)
                self.orientation_combo.setCurrentIndex(0)
                self.orientation_combo.setEnabled(False)
                self.orientation_hint.setVisible(True)
                return

            current = self._fixed_orientation
            self.orientation_combo.clear()
            for orientation in PageOrientation:
                self.orientation_combo.addItem(orientation.value, orientation.value)
            self.orientation_combo.setCurrentIndex(self.orientation_combo.findData(current.value))
            self.orientation_combo.setEnabled(True)
            self.orientation_hint.setVisible(False)
        finally:
            self.orientation_combo.blockSignals(previous_blocked)

    def _page_size_mode(self) -> PageSizeMode:
        return PageSizeMode(self.page_size_combo.currentData())

    def _select_path(self, path: str | Path) -> None:
        target = str(path)
        self.image_list.clearSelection()
        for index in range(self.image_list.count()):
            item = self.image_list.item(index)
            if item.data(PATH_ROLE) == target:
                self.image_list.setCurrentItem(item)
                item.setSelected(True)
                return

    def _row_for_path(self, path: str | Path) -> int:
        target = str(path)
        for index in range(self.image_list.count()):
            item = self.image_list.item(index)
            if item.data(PATH_ROLE) == target:
                return index
        return 0

    def _current_path(self) -> str | None:
        item = self.image_list.currentItem()
        return item.data(PATH_ROLE) if item is not None else None

    def _current_entry(self) -> ImageEntry | None:
        selected = self.image_list.selectedItems()
        if not selected:
            return None
        current_item = self.image_list.currentItem()
        current_path = current_item.data(PATH_ROLE) if current_item in selected else selected[0].data(PATH_ROLE)
        return self._entry_for_path(current_path)

    def _entry_for_path(self, path: str | Path) -> ImageEntry | None:
        target = str(path)
        for entry in self.collection.entries:
            if str(entry.path) == target:
                return entry
        return None


def _documents_folder() -> Path:
    """The user's Documents folder, or their home folder if it is unavailable."""
    documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    if documents and Path(documents).is_dir():
        return Path(documents)
    return Path.home()
