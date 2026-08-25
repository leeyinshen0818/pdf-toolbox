from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
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
from pdf_toolbox.core.pdf_exporter import PdfExporter


PATH_ROLE = Qt.UserRole + 1


class ImageListWidget(QListWidget):
    files_dropped = Signal(list)
    order_changed = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setIconSize(QSize(96, 96))
        self.setSpacing(6)
        self.setAlternatingRowColors(True)

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


class ExportWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, entries: tuple[ImageEntry, ...], output_path: Path, overwrite: bool) -> None:
        super().__init__()
        self.entries = entries
        self.output_path = output_path
        self.overwrite = overwrite
        self.exporter = PdfExporter()

    def run(self) -> None:
        try:
            result = self.exporter.export(
                self.entries,
                self.output_path,
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

        self._build_ui()
        self._update_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("Image -> PDF")
        title.setStyleSheet("font-size: 26px; font-weight: 700; color: #111827;")
        subtitle = QLabel("Import JPG, JPEG, or PNG files, arrange them, then export one PDF.")
        subtitle.setStyleSheet("color: #5b6472;")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)

        self.add_button = QPushButton("Add Images")
        self.remove_button = QPushButton("Remove Selected")
        self.clear_button = QPushButton("Clear")
        self.export_button = QPushButton("Export PDF")
        self.export_button.setObjectName("PrimaryButton")

        self.add_button.clicked.connect(self._choose_images)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self._clear_images)
        self.export_button.clicked.connect(self._export_pdf)

        actions = QHBoxLayout()
        actions.addWidget(self.add_button)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.clear_button)
        actions.addWidget(self.export_button)

        header.addLayout(title_block, 1)
        header.addLayout(actions)

        self.stack = QStackedWidget()
        self.empty_state = self._build_empty_state()

        self.image_list = ImageListWidget()
        self.image_list.files_dropped.connect(self._add_images)
        self.image_list.order_changed.connect(self._sync_order_from_list)
        self.image_list.itemSelectionChanged.connect(self._update_state)

        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.image_list)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #4b5563;")

        layout.addLayout(header)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.status_label)

        self.setStyleSheet(
            """
            QWidget {
                background: #fbfcfe;
                font-size: 13px;
            }
            QPushButton {
                border: 1px solid #cfd8e3;
                border-radius: 6px;
                background: #ffffff;
                color: #1f2937;
                padding: 8px 12px;
            }
            QPushButton:hover:enabled {
                background: #f5f7fb;
            }
            QPushButton:disabled {
                color: #9aa4b2;
                background: #eef1f5;
            }
            QPushButton#PrimaryButton {
                background: #0f766e;
                border-color: #0f766e;
                color: white;
                font-weight: 600;
            }
            QPushButton#PrimaryButton:hover:enabled {
                background: #115e59;
            }
            QListWidget {
                border: 1px solid #d8dee7;
                border-radius: 6px;
                background: #ffffff;
                outline: 0;
            }
            QListWidget::item {
                border-bottom: 1px solid #eef1f5;
                padding: 8px;
            }
            QListWidget::item:selected {
                background: #d7f2ed;
                color: #12342f;
            }
            """
        )

    def _build_empty_state(self) -> QWidget:
        frame = DropAreaFrame()
        frame.files_dropped.connect(self._add_images)
        frame.setStyleSheet(
            """
            QFrame {
                border: 1px dashed #aeb8c7;
                border-radius: 8px;
                background: #ffffff;
            }
            """
        )

        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        title = QLabel("Drop images here")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #374151; border: none;")

        hint = QLabel("JPG, JPEG, and PNG files are supported.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #6b7280; border: none;")

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
        for entry in result.added:
            self._append_item(entry)

        self._sync_list_from_collection()
        self._show_import_result(result)
        self._update_state()

    def _append_item(self, entry: ImageEntry) -> None:
        item = QListWidgetItem()
        item.setData(PATH_ROLE, str(entry.path))
        item.setIcon(QIcon(self._thumbnail_for(entry.path)))
        item.setText(f"{entry.filename}\n{entry.width} x {entry.height} px")
        item.setSizeHint(QSize(240, 116))
        self.image_list.addItem(item)

    def _thumbnail_for(self, path: Path) -> QPixmap:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            pixmap = QPixmap(96, 96)
            pixmap.fill(Qt.white)
            return pixmap

        return QPixmap.fromImage(image).scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _sync_list_from_collection(self) -> None:
        self.image_list.clear()
        for entry in self.collection.entries:
            self._append_item(entry)

    def _sync_order_from_list(self, paths: list[str]) -> None:
        try:
            self.collection.reorder_by_paths(paths)
        except ValueError:
            self._sync_list_from_collection()
        self._update_state()

    def _remove_selected(self) -> None:
        selected_paths = [item.data(PATH_ROLE) for item in self.image_list.selectedItems()]
        self.collection.remove_paths(selected_paths)
        self._sync_list_from_collection()
        self.status_label.setText("Selected images removed.")
        self._update_state()

    def _clear_images(self) -> None:
        self.collection.clear()
        self.image_list.clear()
        self.status_label.setText("Image list cleared.")
        self._update_state()

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
        self.export_worker = ExportWorker(self.collection.entries, output_path, overwrite)
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
        self.status_label.setText(f"Export complete: {output_path}")
        QMessageBox.information(self, "Export Complete", "PDF exported successfully.")

    def _on_export_failed(self, message: str) -> None:
        self._set_exporting(False)
        self.status_label.setText("Export failed.")
        QMessageBox.critical(self, "Export Failed", message)

    def _clear_export_worker(self) -> None:
        self.export_thread = None
        self.export_worker = None
        self._update_state()

    def _set_exporting(self, exporting: bool) -> None:
        self.add_button.setEnabled(not exporting)
        self.remove_button.setEnabled(not exporting and bool(self.image_list.selectedItems()))
        self.clear_button.setEnabled(not exporting and len(self.collection) > 0)
        self.export_button.setEnabled(not exporting and len(self.collection) > 0)
        self.image_list.setEnabled(not exporting)

    def _update_state(self) -> None:
        has_images = len(self.collection) > 0
        has_selection = bool(self.image_list.selectedItems())
        exporting = self.export_thread is not None and self.export_thread.isRunning()

        self.stack.setCurrentWidget(self.image_list if has_images else self.empty_state)
        self.add_button.setEnabled(not exporting)
        self.remove_button.setEnabled(not exporting and has_selection)
        self.clear_button.setEnabled(not exporting and has_images)
        self.export_button.setEnabled(not exporting and has_images)

        if not has_images and not self.status_label.text():
            self.status_label.setText("No images loaded.")

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
