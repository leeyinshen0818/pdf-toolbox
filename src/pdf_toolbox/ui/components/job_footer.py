"""Primary action area that turns into progress + Cancel while a job runs."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from pdf_toolbox.ui.tokens import SPACE_12


class JobFooter(QWidget):
    """Idle: the primary button. Running: a progress bar and a Cancel button in its place.

    The progress bar is hidden whenever no job runs. A footer without a primary button
    (the Organizer keeps Export in its toolbar) is hidden entirely while idle.
    """

    cancel_requested = Signal()

    def __init__(self, primary_text: str | None) -> None:
        super().__init__()
        self.setObjectName("JobFooter")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.primary_button: QPushButton | None = None
        if primary_text is not None:
            self.primary_button = QPushButton(primary_text)
            self.primary_button.setObjectName("PrimaryButton")
            layout.addWidget(self.primary_button)

        self.running_row = QWidget()
        running_layout = QHBoxLayout(self.running_row)
        running_layout.setContentsMargins(0, 0, 0, 0)
        running_layout.setSpacing(SPACE_12)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        running_layout.addWidget(self.progress_bar, 1, Qt.AlignVCenter)
        running_layout.addWidget(self.cancel_button)
        layout.addWidget(self.running_row)

        self.set_running(False)

    def set_running(self, running: bool) -> None:
        self.running = running
        if self.primary_button is not None:
            self.primary_button.setVisible(not running)
        self.running_row.setVisible(running)
        self.progress_bar.setVisible(running)
        self.cancel_button.setVisible(running)
        self.cancel_button.setEnabled(running)
        if running:
            self.progress_bar.setValue(0)
        if self.primary_button is None:
            self.setVisible(running)

    def set_progress(self, current: int, total: int) -> None:
        self.progress_bar.setMaximum(max(1, total))
        self.progress_bar.setValue(current)

    def _on_cancel_clicked(self) -> None:
        self.cancel_button.setEnabled(False)
        self.cancel_requested.emit()
