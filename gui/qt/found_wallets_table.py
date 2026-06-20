"""Table view for wallets found with a positive balance."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)


class FoundWalletsModel(QAbstractTableModel):
    HEADERS = ("Address", "Balance (sats)", "Unit")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[tuple[str, int, str]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        address, amount, denom = self._rows[index.row()]
        col = index.column()
        if col == 0:
            return address
        if col == 1:
            return f"{amount:,}"
        if col == 2:
            return denom
        return None

    def add_found(self, address: str, amount: int, denom: str) -> None:
        row = len(self._rows)
        self.beginInsertRows(QModelIndex(), row, row)
        self._rows.append((address, amount, denom))
        self.endInsertRows()

    def clear(self) -> None:
        if not self._rows:
            return
        self.beginResetModel()
        self._rows.clear()
        self.endResetModel()

    def load_jsonl(self, path: str, *, replace: bool = False) -> int:
        """Load found wallets from a JSONL results file. Returns rows loaded."""
        file_path = Path(path)
        if not file_path.is_file():
            return 0

        loaded: list[tuple[str, int, str]] = []
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                address = rec.get("address")
                if not address:
                    continue
                amount = 0
                denom = ""
                for key, value in rec.items():
                    if key == "address":
                        continue
                    if key in ("private_key", "mnemonic", "wif", "address_type"):
                        continue
                    try:
                        amount = int(value)
                        denom = key
                        break
                    except (TypeError, ValueError):
                        continue
                if amount > 0:
                    loaded.append((address, amount, denom))

        if replace:
            self.beginResetModel()
            self._rows = loaded
            self.endResetModel()
        elif loaded:
            start = len(self._rows)
            self.beginInsertRows(QModelIndex(), start, start + len(loaded) - 1)
            self._rows.extend(loaded)
            self.endInsertRows()
        return len(loaded)

    def all_addresses(self) -> list[str]:
        return [row[0] for row in self._rows]

    def selected_rows_text(self, indexes) -> str:
        rows = sorted({i.row() for i in indexes if i.column() == 0})
        lines = []
        for row in rows:
            address, amount, denom = self._rows[row]
            lines.append(f"{address}\t{amount}\t{denom}")
        return "\n".join(lines)


class FoundWalletsPanel(QWidget):
    """Scrollable table of found wallets, separate from the scan log."""

    count_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = FoundWalletsModel(self)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self._count_label = QLabel("0 wallets with balance")
        self._count_label.setObjectName("cardDim")
        toolbar.addWidget(self._count_label)
        toolbar.addStretch()

        copy_sel = QPushButton("Copy selected")
        copy_sel.setObjectName("ghostBtn")
        copy_sel.clicked.connect(self._copy_selected)
        copy_all = QPushButton("Copy all")
        copy_all.setObjectName("ghostBtn")
        copy_all.clicked.connect(self._copy_all)
        clear = QPushButton("Clear")
        clear.setObjectName("ghostBtn")
        clear.clicked.connect(self.clear)
        self._open_dir_btn = QPushButton("Open folder")
        self._open_dir_btn.setObjectName("ghostBtn")
        toolbar.addWidget(copy_sel)
        toolbar.addWidget(copy_all)
        toolbar.addWidget(clear)
        toolbar.addWidget(self._open_dir_btn)
        layout.addLayout(toolbar)

        self._table = QTableView()
        self._table.setObjectName("foundTable")
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setMinimumHeight(220)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setDefaultSectionSize(120)
        self._table.setColumnWidth(0, 420)
        self._table.doubleClicked.connect(self._copy_row_address)
        layout.addWidget(self._table)

        hint = QLabel("Double-click a row to copy the address. Full export is always saved to the results folder.")
        hint.setObjectName("cardHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._update_count()

    def _update_count(self) -> None:
        n = self._model.rowCount()
        word = "wallet" if n == 1 else "wallets"
        self._count_label.setText(f"{n:,} {word} with balance")
        self.count_changed.emit(n)

    def add_found(self, address: str, amount: int, denom: str) -> None:
        self._model.add_found(address, amount, denom)
        self._update_count()
        self._table.scrollToBottom()

    def load_jsonl(self, path: str, *, replace: bool = False) -> int:
        n = self._model.load_jsonl(path, replace=replace)
        self._update_count()
        if n:
            self._table.scrollToBottom()
        return n

    def clear(self) -> None:
        self._model.clear()
        self._update_count()

    @property
    def count(self) -> int:
        return self._model.rowCount()

    def open_results_dir(self, path: str) -> None:
        import subprocess

        folder = Path(path).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603, S607
        except OSError:
            pass

    def _copy_row_address(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        address = self._model.data(self._model.index(index.row(), 0))
        if address:
            QGuiApplication.clipboard().setText(str(address))

    def _copy_selected(self) -> None:
        text = self._model.selected_rows_text(self._table.selectedIndexes())
        if text:
            QGuiApplication.clipboard().setText(text)

    def _copy_all(self) -> None:
        if not self._model.rowCount():
            return
        lines = []
        for row in range(self._model.rowCount()):
            address = self._model.data(self._model.index(row, 0))
            balance = self._model.data(self._model.index(row, 1))
            denom = self._model.data(self._model.index(row, 2))
            lines.append(f"{address}\t{balance}\t{denom}")
        QGuiApplication.clipboard().setText("\n".join(lines))
