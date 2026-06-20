"""Qt stylesheets built from palette definitions."""

from __future__ import annotations

from gui.qt.palettes import DEFAULT_THEME, THEMES, ThemeColors, theme_names

__all__ = ["DEFAULT_THEME", "THEMES", "ThemeColors", "build_stylesheet", "get_colors", "theme_names"]


def get_colors(name: str) -> ThemeColors:
    if name not in THEMES:
        name = DEFAULT_THEME
    return THEMES[name]


def build_stylesheet(name: str) -> str:
    c = get_colors(name)
    return f"""
QWidget {{
    color: {c["fg"]};
    font-family: "Ubuntu", "Inter", "Cantarell", "Segoe UI", "Noto Sans", sans-serif;
    font-size: 10pt;
}}
QMainWindow, QWidget#contentRoot {{
    background-color: {c["bg"]};
}}
QFrame#sidebar {{
    background-color: {c["sidebar"]};
    border: none;
    border-right: 1px solid {c["border"]};
}}
QLabel#brandTitle {{
    color: {c["fg"]};
    font-size: 18pt;
    font-weight: 700;
}}
QLabel#brandIcon {{
    color: {c["accent"]};
    font-size: 28pt;
}}
QLabel#brandVersion, QLabel#sidebarCaption, QLabel#formLabel {{
    color: {c["fg_dim"]};
}}
QLabel#sidebarCaption {{
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#navLabel {{
    color: {c["fg"]};
    font-weight: 600;
}}
QFrame#navIndicator {{
    background-color: {c["accent"]};
    border-radius: 2px;
}}
QLabel#pageTitle {{
    color: {c["fg"]};
    font-size: 22pt;
    font-weight: 700;
}}
QLabel#pageSubtitle {{
    color: {c["fg_dim"]};
    font-size: 11pt;
}}
QLabel#badge {{
    background-color: {c["card"]};
    color: {c["accent"]};
    border: 1px solid {c["border"]};
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}}
QFrame#card {{
    background-color: {c["card"]};
    border: 1px solid {c["border"]};
    border-radius: 10px;
}}
QFrame#cardAccentBar {{
    background-color: {c["accent"]};
    border-radius: 2px;
}}
QLabel#cardTitle {{
    color: {c["fg"]};
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#cardHint, QLabel#cardDim {{
    color: {c["fg_dim"]};
    font-size: 9pt;
}}
QLineEdit, QSpinBox, QComboBox {{
    background-color: {c["input_bg"]};
    color: {c["fg"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    padding: 8px 10px;
    min-height: 18px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {c["accent"]};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {c["surface2"]};
    border: none;
    width: 18px;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {c["input_bg"]};
    color: {c["fg"]};
    border: 1px solid {c["border"]};
    selection-background-color: {c["accent"]};
    selection-color: {c["accent_btn_fg"]};
}}
QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid {c["border"]};
    background: {c["input_bg"]};
}}
QCheckBox::indicator:checked {{
    background: {c["accent"]};
    border-color: {c["accent"]};
}}
QPushButton {{
    background-color: {c["surface2"]};
    color: {c["fg"]};
    border: none;
    border-radius: 8px;
    padding: 10px 18px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {c["surface"]};
}}
QPushButton:disabled {{
    color: {c["fg_dim"]};
    background-color: {c["surface"]};
}}
QPushButton#accentBtn {{
    background-color: {c["accent"]};
    color: {c["accent_btn_fg"]};
    padding: 14px 32px;
    font-size: 11pt;
}}
QPushButton#accentBtn:hover {{
    background-color: {c["accent_hover"]};
}}
QPushButton#dangerBtn {{
    color: {c["danger"]};
    padding: 12px 24px;
}}
QPushButton#ghostBtn {{
    background-color: transparent;
    color: {c["fg_dim"]};
    border: 1px solid {c["border"]};
}}
QPushButton#ghostBtn:hover {{
    color: {c["fg"]};
    background-color: {c["surface2"]};
}}
QProgressBar {{
    background-color: {c["surface2"]};
    border: none;
    border-radius: 5px;
    min-height: 10px;
    max-height: 10px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {c["accent"]};
    border-radius: 5px;
}}
QTextEdit#logView {{
    background-color: {c["log_bg"]};
    color: {c["log_fg"]};
    border: 1px solid {c["border"]};
    border-radius: 8px;
    padding: 12px;
    font-family: "Ubuntu Mono", "JetBrains Mono", "Consolas", monospace;
    font-size: 10pt;
}}
QTableView#foundTable {{
    background-color: {c["input_bg"]};
    color: {c["fg"]};
    border: 1px solid {c["border"]};
    border-radius: 8px;
    gridline-color: {c["border"]};
    alternate-background-color: {c["card"]};
    selection-background-color: {c["accent"]};
    selection-color: {c["accent_btn_fg"]};
}}
QTableView#foundTable QHeaderView::section {{
    background-color: {c["surface2"]};
    color: {c["fg"]};
    border: none;
    border-bottom: 1px solid {c["border"]};
    padding: 8px 10px;
    font-weight: 600;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: {c["bg"]};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c["surface2"]};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QFrame#sidebarSep {{
    background-color: {c["border"]};
    max-height: 1px;
}}
"""
