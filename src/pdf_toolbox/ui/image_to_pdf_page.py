from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QRectF, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
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
    QSizePolicy,
    QStackedWidget,
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
    rotate_180,
    rotate_left,
    rotate_right,
)
from pdf_toolbox.core.pdf_exporter import PdfExporter
from pdf_toolbox.core.pdf_geometry import (
    ExportSettings,
    MarginPreset,
    PageOrientation,
    PageSizeMode,
    calculate_page_layout,
)


PATH_ROLE = Qt.UserRole + 1


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
        self.setSpacing(6)

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
        self.order_changed.emit(self.paths_in_order())

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


class ImageRowWidget(QWidget):
    def __init__(self, entry: ImageEntry, thumbnail: QPixmap) -> None:
        super().__init__()
        self.setObjectName("ImageRow")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)

        thumbnail_label = QLabel()
        thumbnail_label.setFixedSize(78, 78)
        thumbnail_label.setAlignment(Qt.AlignCenter)
        thumbnail_label.setPixmap(thumbnail)
        thumbnail_label.setStyleSheet(
            "background: #f6f7f9; border: 1px solid #e1e6ec; border-radius: 5px;"
        )

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        filename = QLabel(entry.filename)
        filename.setObjectName("ImageName")
        filename.setTextInteractionFlags(Qt.TextSelectableByMouse)

        dimensions = QLabel(f"{entry.width} × {entry.height} px")
        dimensions.setObjectName("ImageDimensions")

        text_layout.addStretch(1)
        text_layout.addWidget(filename)
        text_layout.addWidget(dimensions)
        text_layout.addStretch(1)

        layout.addWidget(thumbnail_label)
        layout.addLayout(text_layout, 1)


class PreviewWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PreviewWidget")
        self.setMinimumHeight(260)
        self._pixmap: QPixmap | None = None
        self._image_size: tuple[int, int] | None = None
        self._settings = ExportSettings()

    def set_preview(
        self,
        pixmap: QPixmap | None,
        image_size: tuple[int, int] | None,
        settings: ExportSettings,
    ) -> None:
        self._pixmap = pixmap
        self._image_size = image_size
        self._settings = settings
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8fafc"))

        if self._pixmap is None or self._image_size is None:
            painter.setPen(QColor("#7a8491"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Select an image to preview")
            return

        layout = calculate_page_layout(self._image_size[0], self._image_size[1], self._settings)
        available = self.rect().adjusted(18, 18, -18, -18)
        scale = min(
            available.width() / layout.page_size.width,
            available.height() / layout.page_size.height,
        )
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
            self.failed.emit(str(exc))
            return

        self.finished.emit(str(result))


class ImageToPdfPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.collection = ImageCollection()
        self.export_thread: QThread | None = None
        self.export_worker: ExportWorker | None = None
        self.preview_cache: dict[tuple[str, int, tuple[int, bool, bool, str, str]], tuple[QPixmap, tuple[int, int]]] = {}

        self._build_ui()
        self._update_state()
        self._update_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 22)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(18)
        title_block = QVBoxLayout()
        title_block.setSpacing(3)
        title = QLabel("Image -> PDF")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #1f2328;")
        subtitle = QLabel("Import images, arrange their order, and export them as one PDF.")
        subtitle.setObjectName("SubtleText")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)

        self.add_button = QPushButton("Add Images")
        self.remove_button = QPushButton("Remove Selected")
        self.clear_button = QPushButton("Clear")
        self.add_button.clicked.connect(self._choose_images)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self._clear_images)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.add_button)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.clear_button)

        header.addLayout(title_block, 1)
        header.addLayout(actions)

        content = QHBoxLayout()
        content.setSpacing(16)

        main_area = QVBoxLayout()
        main_area.setSpacing(12)

        self.stack = QStackedWidget()
        self.empty_state = self._build_empty_state()
        self.image_list = ImageListWidget()
        self.image_list.files_dropped.connect(self._add_images)
        self.image_list.order_changed.connect(self._sync_order_from_list)
        self.image_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.image_list)

        self.preview = PreviewWidget()

        main_area.addWidget(self.stack, 3)
        main_area.addWidget(self.preview, 2)

        settings_panel = self._build_settings_panel()
        content.addLayout(main_area, 1)
        content.addWidget(settings_panel)

        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusText")
        self.status_label.setWordWrap(True)

        status_frame = QFrame()
        status_frame.setObjectName("StatusBar")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(10, 7, 10, 7)
        status_layout.addWidget(self.status_label)

        layout.addLayout(header)
        layout.addLayout(content, 1)
        layout.addWidget(status_frame)

    def _build_settings_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("SettingsPanel")
        panel.setFixedWidth(280)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        heading = QLabel("Conversion Settings")
        heading.setObjectName("PanelHeading")
        layout.addWidget(heading)

        self.page_size_combo = self._combo(PageSizeMode)
        self.page_size_combo.currentIndexChanged.connect(self._on_export_settings_changed)
        layout.addLayout(self._labeled_control("Page Size", self.page_size_combo))

        self.orientation_combo = self._combo(PageOrientation)
        self.orientation_combo.currentIndexChanged.connect(self._on_export_settings_changed)
        layout.addLayout(self._labeled_control("Page Orientation", self.orientation_combo))

        self.margin_combo = self._combo(MarginPreset)
        self.margin_combo.currentIndexChanged.connect(self._on_export_settings_changed)
        layout.addLayout(self._labeled_control("Margin", self.margin_combo))

        self.export_button = QPushButton("Export PDF")
        self.export_button.setObjectName("PrimaryButton")
        self.export_button.clicked.connect(self._export_pdf)
        layout.addWidget(self.export_button)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setObjectName("Divider")
        layout.addWidget(divider)

        corrections_heading = QLabel("Corrections")
        corrections_heading.setObjectName("PanelHeading")
        layout.addWidget(corrections_heading)

        self.selection_label = QLabel("Select an image")
        self.selection_label.setObjectName("SubtleText")
        layout.addWidget(self.selection_label)

        correction_grid = QGridLayout()
        correction_grid.setSpacing(6)

        self.flip_h_button = QPushButton("Flip H")
        self.flip_v_button = QPushButton("Flip V")
        self.rotate_left_button = QPushButton("Rotate Left")
        self.rotate_right_button = QPushButton("Rotate Right")
        self.rotate_180_button = QPushButton("Rotate 180")
        self.reset_orientation_button = QPushButton("Reset Orientation")

        self.flip_h_button.clicked.connect(lambda: self._update_selected_corrections(flip_h=True))
        self.flip_v_button.clicked.connect(lambda: self._update_selected_corrections(flip_v=True))
        self.rotate_left_button.clicked.connect(lambda: self._update_selected_corrections(rotation="left"))
        self.rotate_right_button.clicked.connect(lambda: self._update_selected_corrections(rotation="right"))
        self.rotate_180_button.clicked.connect(lambda: self._update_selected_corrections(rotation="180"))
        self.reset_orientation_button.clicked.connect(lambda: self._update_selected_corrections(reset_orientation=True))

        correction_grid.addWidget(self.flip_h_button, 0, 0)
        correction_grid.addWidget(self.flip_v_button, 0, 1)
        correction_grid.addWidget(self.rotate_left_button, 1, 0)
        correction_grid.addWidget(self.rotate_right_button, 1, 1)
        correction_grid.addWidget(self.rotate_180_button, 2, 0)
        correction_grid.addWidget(self.reset_orientation_button, 2, 1)
        layout.addLayout(correction_grid)

        self.sharpness_combo = self._combo(SharpnessPreset)
        self.sharpness_combo.activated.connect(self._on_sharpness_changed)
        layout.addLayout(self._labeled_control("Sharpness", self.sharpness_combo))

        self.tone_combo = self._combo(TonePreset)
        self.tone_combo.activated.connect(self._on_tone_changed)
        layout.addLayout(self._labeled_control("Brightness / Contrast", self.tone_combo))

        self.reset_corrections_button = QPushButton("Reset Corrections")
        self.reset_corrections_button.clicked.connect(lambda: self._update_selected_corrections(reset_all=True))
        layout.addWidget(self.reset_corrections_button)
        layout.addStretch(1)

        return panel

    def _combo(self, enum_type) -> QComboBox:
        combo = QComboBox()
        for item in enum_type:
            combo.addItem(item.value, item.value)
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
        layout.setSpacing(8)

        title = QLabel("Drop images here")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #2f3742; border: none;")

        hint = QLabel("JPG, JPEG, and PNG files are supported.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName("SubtleText")

        button = QPushButton("Select Images")
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        button.clicked.connect(self._choose_images)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(button, alignment=Qt.AlignCenter)

        return frame

    def _choose_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            "",
            "Images (*.jpg *.jpeg *.png)",
        )
        if files:
            self._add_images(files)

    def _add_images(self, paths: list[str]) -> None:
        result = self.collection.add_paths(paths)
        self._sync_list_from_collection()
        if result.added and not self.image_list.selectedItems():
            self.image_list.setCurrentRow(0)
        self._show_import_result(result)
        self._update_state()
        self._update_preview()

    def _append_item(self, entry: ImageEntry) -> None:
        item = QListWidgetItem()
        item.setData(PATH_ROLE, str(entry.path))
        item.setSizeHint(QSize(240, 104))
        self.image_list.addItem(item)
        self.image_list.setItemWidget(item, ImageRowWidget(entry, self._thumbnail_for(entry.path)))

    def _thumbnail_for(self, path: Path) -> QPixmap:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            pixmap = QPixmap(76, 76)
            pixmap.fill(Qt.white)
            return pixmap

        return QPixmap.fromImage(image).scaled(74, 74, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _sync_list_from_collection(self) -> None:
        selected_paths = {item.data(PATH_ROLE) for item in self.image_list.selectedItems()}
        current_path = self._current_path()
        self.image_list.clear()
        for entry in self.collection.entries:
            self._append_item(entry)
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
        self._update_state()
        self._update_preview()

    def _remove_selected(self) -> None:
        selected_paths = [item.data(PATH_ROLE) for item in self.image_list.selectedItems()]
        self.collection.remove_paths(selected_paths)
        self._sync_list_from_collection()
        self.status_label.setText("Selected images removed.")
        self._update_state()
        self._update_preview()

    def _clear_images(self) -> None:
        self.collection.clear()
        self.image_list.clear()
        self.preview_cache.clear()
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
        self.status_label.setText(f"Export complete - {output_path}")

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
        self.remove_button.setEnabled(not exporting and has_selection)
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
        self.remove_button.setEnabled(not exporting and has_selection)
        self.clear_button.setEnabled(not exporting and has_images)
        self.export_button.setEnabled(not exporting and has_images)
        self._set_correction_controls_enabled(not exporting and has_selection)
        self.orientation_combo.setEnabled(self._page_size_mode() != PageSizeMode.FIT)

        if not has_selection:
            self.selection_label.setText("Select an image")
        elif len(self.image_list.selectedItems()) == 1:
            self.selection_label.setText(Path(self.image_list.selectedItems()[0].data(PATH_ROLE)).name)
        else:
            self.selection_label.setText(f"{len(self.image_list.selectedItems())} images selected")

        if not has_images and not self.status_label.text():
            self.status_label.setText("No images loaded.")

    def _set_correction_controls_enabled(self, enabled: bool) -> None:
        controls = [
            self.flip_h_button,
            self.flip_v_button,
            self.rotate_left_button,
            self.rotate_right_button,
            self.rotate_180_button,
            self.reset_orientation_button,
            self.sharpness_combo,
            self.tone_combo,
            self.reset_corrections_button,
        ]
        for control in controls:
            control.setEnabled(enabled)

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
        self.orientation_combo.setEnabled(self._page_size_mode() != PageSizeMode.FIT)
        self._update_preview()

    def _on_sharpness_changed(self, _index: int | None = None) -> None:
        preset = SharpnessPreset(self.sharpness_combo.currentData())
        self._update_selected_corrections(sharpness=preset)

    def _on_tone_changed(self, _index: int | None = None) -> None:
        preset = TonePreset(self.tone_combo.currentData())
        self._update_selected_corrections(tone=preset)

    def _update_selected_corrections(
        self,
        *,
        flip_h: bool = False,
        flip_v: bool = False,
        rotation: str | None = None,
        sharpness: SharpnessPreset | None = None,
        tone: TonePreset | None = None,
        reset_orientation: bool = False,
        reset_all: bool = False,
    ) -> None:
        for item in self.image_list.selectedItems():
            entry = self._entry_for_path(item.data(PATH_ROLE))
            if entry is None:
                continue

            corrections = entry.corrections
            if reset_all:
                corrections = corrections.reset_all()
            elif reset_orientation:
                corrections = corrections.reset_orientation()
            elif flip_h:
                corrections = CorrectionSettings(
                    rotation_degrees=corrections.rotation_degrees,
                    flip_horizontal=not corrections.flip_horizontal,
                    flip_vertical=corrections.flip_vertical,
                    sharpness=corrections.sharpness,
                    tone=corrections.tone,
                )
            elif flip_v:
                corrections = CorrectionSettings(
                    rotation_degrees=corrections.rotation_degrees,
                    flip_horizontal=corrections.flip_horizontal,
                    flip_vertical=not corrections.flip_vertical,
                    sharpness=corrections.sharpness,
                    tone=corrections.tone,
                )
            elif rotation == "left":
                corrections = rotate_left(corrections)
            elif rotation == "right":
                corrections = rotate_right(corrections)
            elif rotation == "180":
                corrections = rotate_180(corrections)
            elif sharpness is not None:
                corrections = CorrectionSettings(
                    rotation_degrees=corrections.rotation_degrees,
                    flip_horizontal=corrections.flip_horizontal,
                    flip_vertical=corrections.flip_vertical,
                    sharpness=sharpness,
                    tone=corrections.tone,
                )
            elif tone is not None:
                corrections = CorrectionSettings(
                    rotation_degrees=corrections.rotation_degrees,
                    flip_horizontal=corrections.flip_horizontal,
                    flip_vertical=corrections.flip_vertical,
                    sharpness=corrections.sharpness,
                    tone=tone,
                )

            self.collection.update_corrections(entry.path, corrections)

        self._sync_correction_controls()
        self._update_preview()

    def _sync_correction_controls(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return

        self.sharpness_combo.blockSignals(True)
        self.tone_combo.blockSignals(True)
        self._set_combo_to_value(self.sharpness_combo, entry.corrections.sharpness.value)
        self._set_combo_to_value(self.tone_combo, entry.corrections.tone.value)
        self.sharpness_combo.blockSignals(False)
        self.tone_combo.blockSignals(False)

    def _update_preview(self) -> None:
        entry = self._current_entry() or (self.collection.entries[0] if self.collection.entries else None)
        if entry is None:
            self.preview.set_preview(None, None, self._export_settings())
            return

        try:
            pixmap, size = self._preview_pixmap_for_entry(entry)
        except Exception:
            self.preview.set_preview(None, None, self._export_settings())
            return

        self.preview.set_preview(pixmap, size, self._export_settings())

    def _preview_pixmap_for_entry(self, entry: ImageEntry) -> tuple[QPixmap, tuple[int, int]]:
        stat = entry.path.stat()
        cache_key = (str(entry.path), stat.st_mtime_ns, entry.corrections.cache_key())
        cached = self.preview_cache.get(cache_key)
        if cached is not None:
            return cached

        with Image.open(entry.path) as image:
            working = image.copy()
            working.thumbnail((1100, 1100), Image.Resampling.LANCZOS)
            corrected = apply_corrections(working, entry.corrections)
            flattened = flatten_to_white(corrected)
            qimage = self._pil_to_qimage(flattened)
            pixmap = QPixmap.fromImage(qimage)
            result = (pixmap, self._corrected_source_size(entry))
            self.preview_cache[cache_key] = result
            return result

    def _corrected_source_size(self, entry: ImageEntry) -> tuple[int, int]:
        width, height = entry.width, entry.height
        if entry.corrections.normalized().rotation_degrees in {90, 270}:
            return height, width
        return width, height

    def _pil_to_qimage(self, image: Image.Image) -> QImage:
        rgb = image.convert("RGB")
        data = rgb.tobytes("raw", "RGB")
        return QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888).copy()

    def _export_settings(self) -> ExportSettings:
        return ExportSettings(
            page_size=self._page_size_mode(),
            orientation=PageOrientation(self.orientation_combo.currentData()),
            margin=MarginPreset(self.margin_combo.currentData()),
        )

    def _page_size_mode(self) -> PageSizeMode:
        return PageSizeMode(self.page_size_combo.currentData())

    def _set_combo_to_value(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _current_path(self) -> str | None:
        item = self.image_list.currentItem()
        return item.data(PATH_ROLE) if item is not None else None

    def _current_entry(self) -> ImageEntry | None:
        current_path = self._current_path()
        if current_path is None:
            return None
        return self._entry_for_path(current_path)

    def _entry_for_path(self, path: str | Path) -> ImageEntry | None:
        target = str(path)
        for entry in self.collection.entries:
            if str(entry.path) == target:
                return entry
        return None
