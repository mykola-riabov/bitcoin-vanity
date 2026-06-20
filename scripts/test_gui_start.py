#!/usr/bin/env python3
"""Headless-ish test: instantiate GUI and trigger START programmatically."""
import multiprocessing as mp
import os
import sys
import time

mp.freeze_support()

os.environ.setdefault("DISPLAY", ":0.0")

from PySide6.QtWidgets import QApplication

from gui.qt.main_window import MainWindow


def main() -> int:
    qt = QApplication(sys.argv)
    app = MainWindow()
    gen = app._generator_page
    gen._prefix.setText("1a")
    gen._batch.setValue(500)
    gen._count.setValue(1)
    import tempfile
    ws = tempfile.mkdtemp(prefix="btc-gui-test-")
    app._apply_workspace(ws)

    gen._start()
    print("start invoked, proc=", gen._proc, flush=True)

    deadline = time.time() + 30
    while time.time() < deadline:
        qt.processEvents()
        gen._poll_queue()
        if gen._proc and not gen._proc.is_alive():
            gen._poll_queue()
            break
        if gen._progress_label.text() in ("Done", "Error", "Stopped", "Finished"):
            break
        time.sleep(0.05)

    print("--- LOG ---")
    print(gen._log.toPlainText())
    print("progress:", gen._progress_label.text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
