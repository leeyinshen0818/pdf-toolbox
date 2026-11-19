"""Settings card: a scrollable body with the job footer pinned underneath."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from pdf_toolbox.ui.components.job_footer import JobFooter
from pdf_toolbox.ui.tokens import SCROLLBAR_WIDTH, SPACE_12, SPACE_16


class SettingsPanel(QFrame):
    """Right-hand settings card.

    Controls go into `body_layout` (scrolls when space is short); the primary action lives in
    `footer`, outside the scroll area, so expanding a section never pushes it out of view.
    """

    def __init__(self, heading: str, primary_text: str, *, min_width: int, max_width: int) -> None:
        super().__init__()
        self.setObjectName("SettingsPanel")
        self.setMinimumWidth(min_width)
        self.setMaximumWidth(max_width)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("SettingsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)

        body = QWidget()
        body.setObjectName("SettingsBody")
        # Leave room for the 10px scrollbar inside the card (matches the pre-scaffold panel widths).
        body.setMinimumWidth(min_width - SCROLLBAR_WIDTH)
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(SPACE_16, SPACE_16, SPACE_16, SPACE_12)
        self.body_layout.setSpacing(SPACE_12)
        self.heading = QLabel(heading)
        self.heading.setObjectName("PanelHeading")
        self.body_layout.addWidget(self.heading)
        self.scroll.setWidget(body)

        self.footer = JobFooter(primary_text)
        footer_frame = QWidget()
        footer_layout = QVBoxLayout(footer_frame)
        footer_layout.setContentsMargins(SPACE_16, SPACE_12, SPACE_16, SPACE_16)
        footer_layout.addWidget(self.footer)
        footer_frame.setObjectName("SettingsFooter")
        footer_frame.setAttribute(Qt.WA_StyledBackground, True)

        outer.addWidget(self.scroll, 1)
        outer.addWidget(footer_frame)

    def finish_body(self) -> None:
        """Push the body controls to the top once every control has been added."""
        self.body_layout.addStretch(1)
