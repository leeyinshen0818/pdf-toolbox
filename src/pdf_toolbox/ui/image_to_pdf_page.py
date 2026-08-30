from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QRectF, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from pdf_toolbox.core.image_collection import AddImagesResult, ImageCollection, ImageEntry
from pdf_toolbox.core.image_corrections import (
    CorrectionSettings,
    SharpnessPreset,
    TonePreset,
    apply_corrections,
    flatten_to_white,
)
from pdf_toolbox.core.pdf_exporter import PdfExporter
from pdf_toolbox.core.pdf_geometry import (
    ExportSettings,
    MarginPreset,
    PageOrientation,
    PageSizeMode,
    calculate_page_layout,
)
from pdf_toolbox.core.output_location import open_output_location
from pdf_toolbox.ui.scale import scaled, scaled_size


PATH_ROLE = Qt.UserRole + 1
AUTO_ORIENTATION_LABEL = "Auto - Based on Image"
logger = logging.getLogger(__name__)


class ImageListWidget(QListWidget):
    files_dropped = Signal(list)
    order_changed = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ImageList")
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setSpacing(scaled(5, minimum=3))
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setAutoScroll(True)
        self.setAutoScrollMargin(scaled(48, minimum=32))

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
        self.order_changed.emit(self.paths_in_order())

    def dragLeaveEvent(self, event) -> None:
        set_drop_active(self, False)
        super().dragLeaveEvent(event)

    def paths_in_order(self) -> list[str]:
        return [self.item(index).data(PATH_ROLE) for index in range(self.count())]


class DropAreaFrame(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)

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


class ImageRowWidget(QWidget):
    delete_requested = Signal(str)

    def __init__(self, entry: ImageEntry, thumbnail: QPixmap, order_number: int) -> None:
        super().__init__()
        self.setObjectName("ImageRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.path = str(entry.path)
        self.setMinimumHeight(scaled(76, minimum=52))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(scaled(8), scaled(6), scaled(8), scaled(6))
        layout.setSpacing(scaled(9))

        order_label = QLabel(str(order_number))
        order_label.setObjectName("ImageOrderNumber")
        order_label.setFixedWidth(scaled(24, minimum=18))
        order_label.setAlignment(Qt.AlignCenter)

        thumbnail_label = QLabel()
        thumbnail_label.setFixedSize(scaled(58, minimum=40), scaled(58, minimum=40))
        thumbnail_label.setAlignment(Qt.AlignCenter)
        thumbnail_label.setPixmap(thumbnail)
        thumbnail_label.setStyleSheet(
            "background: #f6f7f9; border: 1px solid #e1e6ec; border-radius: 5px;"
        )

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(scaled(4))

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
        delete_button.setFixedSize(scaled(28, minimum=22), scaled(28, minimum=22))
        delete_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        delete_button.setIconSize(scaled_size(16, 16, minimum=12))
        delete_button.clicked.connect(lambda: self.delete_requested.emit(self.path))

        layout.addWidget(order_label)
        layout.addWidget(thumbnail_label)
        layout.addLayout(text_layout, 1)
        layout.addWidget(delete_button, alignment=Qt.AlignVCenter)


class ElidedLabel(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.full_text = text
        self.setText(text)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_text()

    def _refresh_text(self) -> None:
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.ElideMiddle, max(24, self.width())))


class PreviewWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PreviewWidget")
        self.setMinimumSize(scaled(280, minimum=190), scaled(360, minimum=245))
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
        painter.fillRect(self.rect(), QColor("#f8fafc"))

        if self._pixmap is None or self._image_size is None:
            painter.setPen(QColor("#7a8491"))
            painter.drawText(self.rect(), Qt.AlignCenter, self._empty_text)
            return

        layout = self.current_layout()
        if layout is None:
            return
        inset = scaled(18, minimum=10)
        available = self.rect().adjusted(inset, inset, -inset, -inset)
        scale = min(available.width() / layout.page_size.width, available.height() / layout.page_size.height)
        page_width = layout.page_size.width * scale
        page_height = layout.page_size.height * scale
        page_rect = QRectF(
            available.center().x() - page_width / 2,
            available.center().y() - page_height / 2,
            page_width,
            page_height,
        )

        painter.setPen(QPen(QColor("#cfd7e2"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(page_rect, 4, 4)

        image_rect = QRectF(
            page_rect.x() + layout.image_rect.x0 * scale,
            page_rect.y() + layout.image_rect.y0 * scale,
            layout.image_rect.width * scale,
            layout.image_rect.height * scale,
        )
        painter.drawPixmap(image_rect, self._pixmap, QRectF(self._pixmap.rect()))


class ExportWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)
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

    def run(self) -> None:
        try:
            result = self.exporter.export(
                self.entries,
                self.output_path,
                settings=self.settings,
                overwrite=self.overwrite,
                progress_callback=self.progress.emit,
            )
        except Exception as exc:
            logger.exception("Image to PDF export failed")
            self.failed.emit(str(exc))
            return

        self.finished.emit(str(result))


class ImageToPdfPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.collection = ImageCollection()
        self.export_thread: QThread | None = None
        self.export_worker: ExportWorker | None = None
        self.preview_cache: dict[tuple[str, int, tuple[str, str]], tuple[QPixmap, tuple[int, int]]] = {}
        self.thumbnail_cache: dict[tuple[str, int], QPixmap] = {}
        self.sharpness_buttons: dict[SharpnessPreset, QPushButton] = {}
        self.tone_buttons: dict[TonePreset, QPushButton] = {}
        self.open_output_location = open_output_location
        self._fixed_orientation = PageOrientation.PORTRAIT

        self._build_ui()
        self._sync_orientation_control()
        self._update_state()
        self._update_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(scaled(32), scaled(26), scaled(34), scaled(22))
        layout.setSpacing(scaled(13))

        title = QLabel("Image -> PDF")
        title.setStyleSheet(f"font-size: {scaled(22, minimum=15)}px; font-weight: 700; color: #1f2328;")
        subtitle = QLabel("Import images, arrange their order, and export them as one PDF.")
        subtitle.setObjectName("SubtleText")

        toolbar = QHBoxLayout()
        toolbar.setSpacing(scaled(8))
        self.add_button = QPushButton("Add Images")
        self.add_button.setObjectName("PrimaryButton")
        self.clear_button = QPushButton("Clear")
        self.add_button.clicked.connect(self._choose_images)
        self.clear_button.clicked.connect(self._clear_images)
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.clear_button)
        toolbar.addStretch(1)

        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(scaled(18))

        self.list_heading = QLabel("Imported Images")
        self.list_heading.setObjectName("PanelHeading")
        self.stack = QStackedWidget()
        self.empty_state = self._build_empty_state()
        self.image_list = ImageListWidget()
        self.image_list.files_dropped.connect(self._add_images)
        self.image_list.order_changed.connect(self._sync_order_from_list)
        self.image_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.image_list)
        self.stack.setMinimumSize(scaled(330, minimum=225), scaled(360, minimum=245))

        self.preview = PreviewWidget()

        self.list_section = QWidget()
        list_area = QVBoxLayout(self.list_section)
        list_area.setContentsMargins(0, 0, 0, 0)
        list_area.setSpacing(scaled(8))
        list_area.addWidget(self.list_heading)
        list_area.addWidget(self.stack, 1)

        self.preview_section = QWidget()
        preview_area = QVBoxLayout(self.preview_section)
        preview_area.setContentsMargins(0, 0, 0, 0)
        preview_area.setSpacing(scaled(8))
        self.preview_heading = QLabel("Preview")
        self.preview_heading.setObjectName("PanelHeading")
        preview_area.addWidget(self.preview_heading)
        preview_area.addWidget(self.preview, 1)

        self.settings_panel = self._build_settings_panel()
        self.content_layout.addWidget(self.list_section, 4)
        self.content_layout.addWidget(self.preview_section, 4)
        self.content_layout.addWidget(self.settings_panel, 3)

        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusText")
        self.status_label.setWordWrap(True)
        status_frame = QFrame()
        status_frame.setObjectName("StatusBar")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(scaled(10), scaled(7), scaled(10), scaled(7))
        status_layout.addWidget(self.status_label)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(toolbar)
        layout.addLayout(self.content_layout, 1)
        layout.addWidget(status_frame)

    def _build_settings_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("SettingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumWidth(scaled(310, minimum=210))
        scroll.setMaximumWidth(scaled(390, minimum=265))

        panel = QFrame()
        panel.setObjectName("SettingsPanel")
        panel.setMinimumWidth(scaled(300, minimum=205))
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(scaled(18), scaled(18), scaled(18), scaled(18))
        layout.setSpacing(scaled(14))

        heading = QLabel("Settings")
        heading.setObjectName("PanelHeading")
        layout.addWidget(heading)

        self.page_size_combo = self._combo(PageSizeMode)
        self.page_size_combo.currentIndexChanged.connect(self._on_export_settings_changed)
        layout.addLayout(self._labeled_control("Page Size", self.page_size_combo))

        self.orientation_combo = self._combo(PageOrientation)
        self.orientation_combo.currentIndexChanged.connect(self._on_export_settings_changed)
        layout.addLayout(self._labeled_control("Orientation", self.orientation_combo))

        self.margin_combo = self._combo(MarginPreset)
        self.margin_combo.currentIndexChanged.connect(self._on_export_settings_changed)
        layout.addLayout(self._labeled_control("Margin", self.margin_combo))

        self.corrections_toggle = QPushButton("Corrections v")
        self.corrections_toggle.setCheckable(True)
        self.corrections_toggle.clicked.connect(self._toggle_corrections)
        layout.addWidget(self.corrections_toggle)

        self.corrections_panel = self._build_corrections_panel()
        self.corrections_panel.setVisible(False)
        layout.addWidget(self.corrections_panel)
        layout.addStretch(1)

        self.export_button = QPushButton("Export PDF")
        self.export_button.setObjectName("PrimaryButton")
        self.export_button.clicked.connect(self._export_pdf)
        layout.addWidget(self.export_button)

        scroll.setWidget(panel)
        return scroll

    def _build_corrections_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("CorrectionsPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, scaled(4), 0, 0)
        layout.setSpacing(scaled(10))

        self.selection_label = QLabel("Select an image")
        self.selection_label.setObjectName("SubtleText")
        layout.addWidget(self.selection_label)

        layout.addWidget(self._preset_section("Sharpen / Soften", SharpnessPreset, self._set_sharpness))
        layout.addWidget(self._preset_section("Brightness / Contrast", TonePreset, self._set_tone))

        self.reset_corrections_button = QPushButton("Reset Corrections")
        self.reset_corrections_button.clicked.connect(self._reset_selected_corrections)
        layout.addWidget(self.reset_corrections_button)

        return panel

    def _preset_section(self, title: str, enum_type, callback) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scaled(6))

        label = QLabel(title)
        label.setObjectName("FieldLabel")
        layout.addWidget(label)

        grid = QGridLayout()
        grid.setSpacing(scaled(6))
        group = QButtonGroup(section)
        group.setExclusive(True)

        for index, preset in enumerate(enum_type):
            button = QPushButton(preset.value)
            button.setObjectName("PresetButton")
            button.setCheckable(True)
            button.setMinimumHeight(scaled(34, minimum=24))
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.clicked.connect(lambda _checked=False, value=preset: callback(value))
            group.addButton(button)
            grid.addWidget(button, index // 2, index % 2)
            if enum_type is SharpnessPreset:
                self.sharpness_buttons[preset] = button
            else:
                self.tone_buttons[preset] = button

        layout.addLayout(grid)
        return section

    def _combo(self, enum_type) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumHeight(scaled(36, minimum=24))
        combo.setMinimumWidth(scaled(260, minimum=177))
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(24)
        for item in enum_type:
            combo.addItem(item.value, item.value)
        combo.view().setObjectName("ComboPopup")
        combo.view().setMinimumWidth(scaled(300, minimum=204))
        return combo

    def _labeled_control(self, label: str, control: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(4)
        text = QLabel(label)
        text.setObjectName("FieldLabel")
        layout.addWidget(text)
        layout.addWidget(control)
        return layout

    def _build_empty_state(self) -> QWidget:
        frame = DropAreaFrame()
        frame.files_dropped.connect(self._add_images)
        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(scaled(8))

        title = QLabel("Add images to create a PDF")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"font-size: {scaled(18, minimum=12)}px; font-weight: 700; color: #2f3742; border: none;")
        hint = QLabel("Drag and drop JPG, JPEG, or PNG files here.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName("SubtleText")
        button = QPushButton("Add Images")
        button.setObjectName("PrimaryButton")
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        button.clicked.connect(self._choose_images)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(button, alignment=Qt.AlignCenter)
        return frame

    def _choose_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select Images", "", "Images (*.jpg *.jpeg *.png)")
        if files:
            self._add_images(files)

    def _add_images(self, paths: list[str]) -> None:
        had_selection = bool(self.image_list.selectedItems())
        result = self.collection.add_paths(paths)
        self._sync_list_from_collection()
        if result.added and not had_selection:
            self._select_path(result.added[0].path)
        self._show_import_result(result)
        self._update_state()
        self._update_preview()

    def _append_item(self, entry: ImageEntry, order_number: int) -> None:
        item = QListWidgetItem()
        item.setData(PATH_ROLE, str(entry.path))
        item.setSizeHint(scaled_size(300, 84, minimum=56))
        self.image_list.addItem(item)
        row = ImageRowWidget(entry, self._thumbnail_for(entry.path), order_number)
        row.delete_requested.connect(self._remove_path)
        self.image_list.setItemWidget(item, row)

    def _thumbnail_for(self, path: Path) -> QPixmap:
        try:
            stat = path.stat()
        except OSError:
            pixmap = QPixmap(scaled(56, minimum=38), scaled(56, minimum=38))
            pixmap.fill(Qt.white)
            return pixmap
        cache_key = (str(path), stat.st_mtime_ns)
        cached = self.thumbnail_cache.get(cache_key)
        if cached is not None:
            return cached

        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            pixmap = QPixmap(scaled(56, minimum=38), scaled(56, minimum=38))
            pixmap.fill(Qt.white)
            return pixmap
        pixmap = QPixmap.fromImage(image).scaled(
            scaled(54, minimum=37),
            scaled(54, minimum=37),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.thumbnail_cache[cache_key] = pixmap
        return pixmap

    def _sync_list_from_collection(self) -> None:
        selected_paths = {item.data(PATH_ROLE) for item in self.image_list.selectedItems()}
        current_path = self._current_path()
        self.image_list.clear()
        for order_number, entry in enumerate(self.collection.entries, start=1):
            self._append_item(entry, order_number)
            item = self.image_list.item(self.image_list.count() - 1)
            if str(entry.path) in selected_paths:
                item.setSelected(True)
            if str(entry.path) == current_path:
                self.image_list.setCurrentItem(item)

    def _sync_order_from_list(self, paths: list[str]) -> None:
        try:
            self.collection.reorder_by_paths(paths)
        except ValueError:
            self._sync_list_from_collection()
            return
        self._sync_list_from_collection()
        self._update_state()
        self._update_preview()

    def _remove_path(self, path: str) -> None:
        removed_index = self._row_for_path(path)
        removed_current = path == self._current_path()
        self.collection.remove_paths([path])
        self._sync_list_from_collection()
        if self.collection.entries and (removed_current or self._current_entry() is None):
            next_row = min(max(removed_index, 0), len(self.collection.entries) - 1)
            self.image_list.setCurrentRow(next_row)
        self.status_label.setText("Image removed.")
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
        output, _ = QFileDialog.getSaveFileName(self, "Export PDF", "", "PDF files (*.pdf)")
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
        self.status_label.setText("Exporting PDF...")
        self.export_thread = QThread(self)
        self.export_worker = ExportWorker(self.collection.entries, output_path, self._export_settings(), overwrite)
        self.export_worker.moveToThread(self.export_thread)
        self.export_thread.started.connect(self.export_worker.run)
        self.export_worker.progress.connect(self._on_export_progress)
        self.export_worker.finished.connect(self._on_export_finished)
        self.export_worker.failed.connect(self._on_export_failed)
        self.export_worker.finished.connect(self.export_thread.quit)
        self.export_worker.failed.connect(self.export_thread.quit)
        self.export_thread.finished.connect(self.export_worker.deleteLater)
        self.export_thread.finished.connect(self.export_thread.deleteLater)
        self.export_thread.finished.connect(self._clear_export_worker)
        self.export_thread.start()

    def _on_export_progress(self, current: int, total: int) -> None:
        self.status_label.setText(f"Exporting PDF... {current}/{total}")

    def _on_export_finished(self, output_path: str) -> None:
        self._set_exporting(False)
        self.status_label.setText("PDF exported successfully.")
        result = self.open_output_location(output_path, reveal=True)
        if not result.success:
            logger.warning("Could not reveal exported PDF: %s", result.message)
            self.status_label.setText("PDF exported successfully, but the output folder could not be opened.")

    def _on_export_failed(self, message: str) -> None:
        self._set_exporting(False)
        self.status_label.setText("Export failed.")
        QMessageBox.critical(self, "Export Failed", message)

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

        if not has_selection:
            self.selection_label.setText("Select an image")
        elif len(self.image_list.selectedItems()) == 1:
            self.selection_label.setText(Path(self.image_list.selectedItems()[0].data(PATH_ROLE)).name)
        else:
            self.selection_label.setText(f"{len(self.image_list.selectedItems())} images selected")

        if not has_images and not self.status_label.text():
            self.status_label.setText("No images loaded.")

    def _set_correction_controls_enabled(self, enabled: bool) -> None:
        for button in [*self.sharpness_buttons.values(), *self.tone_buttons.values(), self.reset_corrections_button]:
            button.setEnabled(enabled)

    def _show_import_result(self, result: AddImagesResult) -> None:
        messages: list[str] = []
        if result.added:
            messages.append(f"Added {len(result.added)} image(s).")
        if result.duplicates:
            messages.append(f"Skipped {len(result.duplicates)} duplicate file(s).")
        if result.rejected:
            messages.append(f"Rejected {len(result.rejected)} unsupported or invalid file(s).")
        if messages:
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
        self._update_preview()

    def _toggle_corrections(self, checked: bool) -> None:
        self.corrections_panel.setVisible(checked)
        self.corrections_toggle.setText("Corrections ^" if checked else "Corrections v")

    def _set_sharpness(self, preset: SharpnessPreset) -> None:
        self._update_selected_corrections(sharpness=preset)

    def _set_tone(self, preset: TonePreset) -> None:
        self._update_selected_corrections(tone=preset)

    def _reset_selected_corrections(self) -> None:
        self._update_selected_corrections(reset_all=True)

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
            return
        try:
            pixmap, size = self._preview_pixmap_for_entry(entry)
        except Exception:
            self.preview.set_preview(None, None, self._export_settings(), "Select an image to preview")
            return
        self.preview.set_preview(pixmap, size, self._export_settings())

    def _preview_pixmap_for_entry(self, entry: ImageEntry) -> tuple[QPixmap, tuple[int, int]]:
        stat = entry.path.stat()
        cache_key = (str(entry.path), stat.st_mtime_ns, entry.corrections.cache_key())
        cached = self.preview_cache.get(cache_key)
        if cached is not None:
            return cached

        with Image.open(entry.path) as image:
            corrected = apply_corrections(image, entry.corrections)
            source_size = corrected.size
            corrected.thumbnail((1100, 1100), Image.Resampling.LANCZOS)
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
                return

            current = self._fixed_orientation
            self.orientation_combo.clear()
            for orientation in PageOrientation:
                self.orientation_combo.addItem(orientation.value, orientation.value)
            self.orientation_combo.setCurrentIndex(self.orientation_combo.findData(current.value))
            self.orientation_combo.setEnabled(True)
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


def set_drop_active(widget: QWidget, active: bool) -> None:
    widget.setProperty("dropActive", active)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
