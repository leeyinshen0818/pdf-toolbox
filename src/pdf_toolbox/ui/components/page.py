"""Shared anatomy for the four tool pages."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from pdf_toolbox.ui.components.job_footer import JobFooter
from pdf_toolbox.ui.components.status_line import StatusLine
from pdf_toolbox.ui.tokens import SPACE_8, SPACE_12, SPACE_16, SPACE_24, SPACE_32


class ToolPage(QWidget):
    """Base class giving every tool page the same layout, top to bottom:

    title, one-line description, action bar, file-count line, content row
    (work areas plus an optional settings panel), optional job footer, status line.

    Subclasses call `build_scaffold()`, fill `action_bar` and `content_layout`, and implement
    `add_files()`, `has_background_work()` and `stop_background_work()`.
    """

    #: Lower-case file extensions this page accepts from drops (e.g. {".pdf"}).
    ACCEPTED_EXTENSIONS: frozenset[str] = frozenset()
    #: Plain description of the accepted files, used in the "wrong file type" message.
    ACCEPTED_DESCRIPTION = ""

    def build_scaffold(self, title: str, description: str) -> None:
        self.page_layout = QVBoxLayout(self)
        self.page_layout.setContentsMargins(SPACE_32, SPACE_24, SPACE_32, SPACE_24)
        self.page_layout.setSpacing(SPACE_12)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        self.description_label = QLabel(description)
        self.description_label.setObjectName("SubtleText")

        self.action_bar = QHBoxLayout()
        self.action_bar.setSpacing(SPACE_8)

        self.count_label = QLabel("")
        self.count_label.setObjectName("SubtleText")

        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(SPACE_16)

        self.status_label = StatusLine()

        self.page_layout.addWidget(self.title_label)
        self.page_layout.addWidget(self.description_label)
        self.page_layout.addLayout(self.action_bar)
        self.page_layout.addWidget(self.count_label)
        self.page_layout.addLayout(self.content_layout, 1)
        self.page_layout.addWidget(self.status_label)

    def finish_action_bar(self) -> None:
        self.action_bar.addStretch(1)

    def add_job_footer(self, footer: JobFooter) -> None:
        """Place a page-level job footer between the content and the status line."""
        self.page_layout.insertWidget(self.page_layout.indexOf(self.status_label), footer)

    # File drops ------------------------------------------------------------
    def accepts_path(self, path: str) -> bool:
        return Path(path).suffix.lower() in self.ACCEPTED_EXTENSIONS

    def add_dropped_files(self, paths: list[str]) -> None:
        """Entry point for every drop on this page (drop area, lists, or anywhere in the window)."""
        accepted = [path for path in paths if self.accepts_path(path)]
        skipped = len(paths) - len(accepted)
        if not accepted:
            self.status_label.show_warning(f"These files can't be used here. Add {self.ACCEPTED_DESCRIPTION}.")
            return
        self.add_files(accepted)
        if skipped:
            note = f"Skipped {skipped} file(s) that are not {self.ACCEPTED_DESCRIPTION}."
            current = self.status_label.text()
            self.status_label.show_warning(f"{current} {note}".strip())

    def is_job_running(self) -> bool:
        """True while an export or conversion runs (thumbnail rendering does not count)."""
        footer = getattr(self, "job_footer", None)
        return bool(footer is not None and footer.running)

    # Page contract ---------------------------------------------------------
    def add_files(self, paths: list[str]) -> None:
        raise NotImplementedError

    def has_background_work(self) -> bool:
        raise NotImplementedError

    def stop_background_work(self) -> None:
        raise NotImplementedError
