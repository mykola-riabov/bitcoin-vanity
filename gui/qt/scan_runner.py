"""Background scan thread for the GUI."""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from scanner import ScanConfig, run_scan


class ScanThread(QThread):
    message = Signal(dict)
    finished_scan = Signal()

    def __init__(self, config: ScanConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        run_scan(self._config, stop_event=self._stop_event, on_message=self.message.emit)
        self.finished_scan.emit()
