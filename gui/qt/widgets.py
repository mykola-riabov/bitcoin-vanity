"""Reusable Qt widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class Card(QFrame):
    """Dashboard card with accent bar and title."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)
        accent = QFrame()
        accent.setObjectName("cardAccentBar")
        accent.setFixedSize(3, 16)
        header.addWidget(accent)
        title_label = QLabel(title.upper())
        title_label.setObjectName("cardTitle")
        header.addWidget(title_label)
        header.addStretch()
        root.addLayout(header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(8)
        root.addWidget(self.body)


def form_row(label: str, widget: QWidget) -> QHBoxLayout:
    """Label + field row with consistent label width."""
    row = QHBoxLayout()
    row.setSpacing(12)
    lbl = QLabel(label)
    lbl.setObjectName("formLabel")
    lbl.setFixedWidth(118)
    lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(lbl)
    row.addWidget(widget, stretch=1)
    return row
