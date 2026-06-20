"""GUI entry point (PySide6 / Qt 6)."""

from __future__ import annotations

import multiprocessing as mp
import sys

from gui.qt.main_window import MainWindow, VanityGuiApp

__all__ = ["MainWindow", "VanityGuiApp", "main"]


def main() -> None:
    mp.freeze_support()
    if sys.platform == "linux":
        try:
            import multiprocessing.forkserver as forkserver

            forkserver.ensure_running()
        except (ValueError, ImportError, OSError):
            pass
    from gui.qt.main_window import run_app

    run_app()


if __name__ == "__main__":
    main()
