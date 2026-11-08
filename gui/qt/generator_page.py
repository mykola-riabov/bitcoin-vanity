"""Vanity address generator page."""

from __future__ import annotations

import multiprocessing as mp
import queue

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bitcoin_address import (
    ADDRESS_TYPES,
    ALLOWED_STRENGTHS,
    DEFAULT_PATHS,
    estimate_difficulty,
    validate_pattern,
)
from gui.qt.theme import get_colors
from gui.qt.widgets import Card, form_row
from gui.worker import SearchConfig, start_search_process
from search_engine import default_workers
from workspace import WorkspaceLayout, default_workspace, ensure_workspace

_MAX_MSGS_PER_TICK = 80
_MAX_LOG_LINES = 400

_TYPE_LABELS = {
    "p2pkh": "P2PKH (1…)",
    "p2sh": "P2SH (3…)",
    "p2wpkh": "SegWit (bc1…)",
}
_DEFAULT_PREFIX = {"p2pkh": "1", "p2sh": "3", "p2wpkh": "bc1q"}
_TESTNET_PREFIX = {"p2pkh": "m", "p2sh": "2", "p2wpkh": "tb1q"}


class GeneratorPage(QWidget):
    def __init__(self, *, theme_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme_name = theme_name
        self._proc: mp.Process | None = None
        self._msg_queue: mp.Queue | None = None
        self._stop_event: mp.Event | None = None
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_queue)
        self._saw_worker_message = False
        self._workspace = ensure_workspace(default_workspace())
        self._build_ui()
        self._refresh_workspace_labels()

    def set_theme_name(self, name: str) -> None:
        self._theme_name = name
        self._update_difficulty_hint()

    def set_workspace(self, layout: WorkspaceLayout) -> None:
        self._workspace = layout
        self._refresh_workspace_labels()

    def get_output_path(self) -> str:
        return str(self._workspace.generated_file)

    def _refresh_workspace_labels(self) -> None:
        if not hasattr(self, "_output_generated"):
            return
        self._output_generated.setText(str(self._workspace.generated_file))
        self._output_generated.setToolTip(str(self._workspace.generated_file))
        self._output_dir.setText(str(self._workspace.generated_dir))
        self._output_dir.setToolTip(str(self._workspace.generated_dir))

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)

        prog = Card("Progress")
        self._progress_label = QLabel("Ready — configure settings and press Start")
        prog.body_layout.addWidget(self._progress_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setVisible(False)
        prog.body_layout.addWidget(self._progress_bar)
        grid.addWidget(prog, 0, 0, 1, 2)

        pattern = Card("Pattern")
        self._address_type = QComboBox()
        self._address_type.addItems([_TYPE_LABELS[t] for t in ADDRESS_TYPES])
        self._address_type.currentIndexChanged.connect(self._on_address_type_changed)
        self._testnet = QCheckBox("Testnet")
        self._testnet.toggled.connect(self._on_testnet_toggled)
        self._prefix = QLineEdit("1")
        self._suffix = QLineEdit()
        pattern.body_layout.addLayout(form_row("Address type", self._address_type))
        pattern.body_layout.addWidget(self._testnet)
        pattern.body_layout.addLayout(form_row("Prefix", self._prefix))
        pattern.body_layout.addLayout(form_row("Suffix", self._suffix))
        self._prefix.textChanged.connect(self._update_difficulty_hint)
        self._suffix.textChanged.connect(self._update_difficulty_hint)
        grid.addWidget(pattern, 1, 0)

        perf = Card("Performance")
        self._batch = QSpinBox()
        self._batch.setRange(10, 1_000_000)
        self._batch.setSingleStep(100)
        self._batch.setValue(500)
        self._batch.setToolTip("Keys each worker checks between progress reports and Stop checks.")
        self._count = QSpinBox()
        self._count.setRange(1, 2_147_483_647)
        self._count.setValue(1)
        self._workers = QSpinBox()
        self._workers.setRange(1, 256)
        self._workers.setValue(default_workers())
        self._workers.setToolTip("Processes; each one generates and checks keys on its own. Default: CPU count.")
        perf.body_layout.addLayout(form_row("Target count", self._count))
        perf.body_layout.addLayout(form_row("Workers", self._workers))
        perf.body_layout.addLayout(form_row("Report every", self._batch))
        grid.addWidget(perf, 1, 1)

        wallet = Card("Wallet")
        self._strength = QComboBox()
        self._strength.addItems([str(s) for s in ALLOWED_STRENGTHS])
        self._strength.setCurrentText("256")
        self._path = QLineEdit(DEFAULT_PATHS["p2pkh"])
        self._mnemonic = QCheckBox("BIP39 mnemonic mode")
        self._index_search = QCheckBox("Fast: one phrase per worker, search the address index")
        self._index_search.setToolTip(
            "Keeps one phrase and tries the last path number 0, 1, 2… — as fast as raw keys. "
            "The found path is saved with the result: open it in the wallet with that account/index."
        )
        self._index_search.setEnabled(False)
        self._mnemonic.toggled.connect(self._index_search.setEnabled)
        wallet.body_layout.addLayout(form_row("Strength", self._strength))
        wallet.body_layout.addLayout(form_row("Derivation path", self._path))
        wallet.body_layout.addWidget(self._mnemonic)
        wallet.body_layout.addWidget(self._index_search)
        grid.addWidget(wallet, 2, 0)

        output = Card("Output")
        self._output_dir = QLabel()
        self._output_dir.setObjectName("cardDim")
        self._output_dir.setWordWrap(True)
        self._output_generated = QLabel()
        self._output_generated.setObjectName("cardDim")
        self._output_generated.setWordWrap(True)
        output.body_layout.addLayout(form_row("Folder", self._output_dir))
        output.body_layout.addLayout(form_row("File", self._output_generated))
        ws_hint = QLabel(
            "Paths come from the workspace folder in the sidebar. "
            "Change workspace once — generator and scanner stay in sync."
        )
        ws_hint.setObjectName("cardHint")
        output.body_layout.addWidget(ws_hint)
        self._per_file = QSpinBox()
        self._per_file.setRange(0, 2_147_483_647)
        self._per_file.setSingleStep(50_000)
        self._per_file.setSpecialValueText("No limit (single file)")
        self._per_file.setValue(0)
        output.body_layout.addLayout(form_row("Max per file", self._per_file))
        self._no_secrets = QCheckBox("Address only (no private keys in file)")
        output.body_layout.addWidget(self._no_secrets)
        hint = QLabel(
            "Max per file: split output into parts, e.g. 500000 → btc_addrs_001.jsonl… "
            "0 = one file. Files are appended on restart."
        )
        hint.setObjectName("cardHint")
        output.body_layout.addWidget(hint)
        grid.addWidget(output, 2, 1)

        log_card = Card("Activity log")
        self._log = QTextEdit()
        self._log.setObjectName("logView")
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(180)
        log_card.body_layout.addWidget(self._log)
        grid.addWidget(log_card, 3, 0, 1, 2)
        grid.setRowStretch(3, 1)

        actions = QHBoxLayout()
        self._start_btn = QPushButton("START SEARCH")
        self._start_btn.setObjectName("accentBtn")
        self._start_btn.clicked.connect(self._start)
        self._stop_btn = QPushButton("STOP")
        self._stop_btn.setObjectName("dangerBtn")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop)
        actions.addWidget(self._start_btn)
        actions.addWidget(self._stop_btn)
        actions.addStretch()
        outer.addLayout(actions)

        self._append_log("Configure pattern and press Start to generate vanity Bitcoin addresses.")
        self._bulk_mode = False

    def _selected_address_type(self) -> str:
        idx = self._address_type.currentIndex()
        return ADDRESS_TYPES[idx]

    def _on_address_type_changed(self) -> None:
        addr_type = self._selected_address_type()
        self._path.setText(DEFAULT_PATHS[addr_type])  # type: ignore[index]
        prefixes = _TESTNET_PREFIX if self._testnet.isChecked() else _DEFAULT_PREFIX
        current = self._prefix.text().strip()
        if not current or current in set(_DEFAULT_PREFIX.values()) | set(_TESTNET_PREFIX.values()):
            self._prefix.setText(prefixes[addr_type])  # type: ignore[index]
        self._update_difficulty_hint()

    def _on_testnet_toggled(self, checked: bool) -> None:
        addr_type = self._selected_address_type()
        prefixes = _TESTNET_PREFIX if checked else _DEFAULT_PREFIX
        self._prefix.setText(prefixes[addr_type])  # type: ignore[index]
        self._update_difficulty_hint()

    def update_difficulty_badge(self, badge: QLabel) -> None:
        self._badge = badge
        self._update_difficulty_hint()

    def _update_difficulty_hint(self) -> None:
        if not hasattr(self, "_badge"):
            return
        c = get_colors(self._theme_name)
        addr_type = self._selected_address_type()
        testnet = self._testnet.isChecked()
        try:
            validate_pattern(
                self._prefix.text().strip(),
                self._suffix.text().strip(),
                address_type=addr_type,  # type: ignore[arg-type]
                testnet=testnet,
            )
            d = estimate_difficulty(
                self._prefix.text().strip(),
                self._suffix.text().strip(),
                address_type=addr_type,  # type: ignore[arg-type]
                testnet=testnet,
            )
            if d.constrained_chars == 0:
                text = "Difficulty: trivial"
                color = c["accent"]
            else:
                text = (
                    f"~{d.expected_attempts:,.0f} attempts · {d.constrained_chars} char(s) "
                    f"(×{d.charset_size})"
                )
                color = c["accent"]
            self._badge.setText(text)
            self._badge.setStyleSheet(
                f"background-color: {c['card']}; color: {color}; "
                f"border: 1px solid {c['border']}; border-radius: 8px; padding: 8px 14px;"
            )
        except ValueError as e:
            self._badge.setText(str(e)[:48])
            self._badge.setStyleSheet(
                f"background-color: {c['card']}; color: {c['warning']}; "
                f"border: 1px solid {c['border']}; border-radius: 8px; padding: 8px 14px;"
            )

    def _append_log(self, line: str) -> None:
        self._log.append(line)
        excess = self._log.document().blockCount() - _MAX_LOG_LINES
        if excess > 50:
            cursor = self._log.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            for _ in range(min(excess, 100)):
                cursor.select(cursor.SelectionType.BlockUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()
            self._log.setTextCursor(cursor)

    def _apply_progress(self, msg: dict) -> None:
        self._progress_label.setText(
            f"Checked: {msg['attempts']:,}  ·  {msg['speed']:,.0f} keys/s  ·  "
            f"found {msg['found']:,}/{msg['target']:,}"
        )

    def _consume_queue(self, *, limit: int | None = None) -> dict | None:
        terminal: dict | None = None
        processed = 0
        while limit is None or processed < limit:
            try:
                msg = self._msg_queue.get_nowait()  # type: ignore[union-attr]
            except queue.Empty:
                break
            self._saw_worker_message = True
            processed += 1
            kind = msg.get("type")
            if kind in ("done", "stopped", "error"):
                terminal = msg
                continue
            if kind == "progress":
                self._apply_progress(msg)
                continue
            self._handle_message(msg)
        return terminal

    def _set_running(self, running: bool) -> None:
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._progress_bar.setVisible(running)

    def _config_from_ui(self) -> SearchConfig:
        addr_type = self._selected_address_type()
        return SearchConfig(
            prefix=self._prefix.text().strip(),
            suffix=self._suffix.text().strip(),
            address_type=addr_type,  # type: ignore[arg-type]
            testnet=self._testnet.isChecked(),
            batch=int(self._batch.value()),
            count=int(self._count.value()),
            strength=int(self._strength.currentText()),
            mnemonic=self._mnemonic.isChecked(),
            index_search=self._mnemonic.isChecked() and self._index_search.isChecked(),
            path=self._path.text().strip() or DEFAULT_PATHS[addr_type],  # type: ignore[index]
            output=self.get_output_path(),
            no_private_key=self._no_secrets.isChecked(),
            workers=int(self._workers.value()),
            per_file=int(self._per_file.value()),
        )

    def _start(self) -> None:
        if self._proc and self._proc.is_alive():
            return
        try:
            config = self._config_from_ui()
            validate_pattern(
                config.prefix,
                config.suffix,
                address_type=config.address_type,
                testnet=config.testnet,
            )
            if not config.output:
                raise ValueError("Workspace output path is not set.")
        except ValueError as e:
            QMessageBox.critical(self, "Invalid input", str(e))
            return

        self._saw_worker_message = False
        self._bulk_mode = int(self._count.value()) > 100
        self._append_log("——— Starting search ———")
        if self._bulk_mode:
            self._append_log(
                f"Bulk mode ({self._count.value():,} targets): progress in status bar, "
                "addresses saved to file — log stays minimal."
            )
        self._set_running(True)
        self._progress_label.setText("Starting worker…")

        try:
            self._proc, self._msg_queue, self._stop_event = start_search_process(config)
        except Exception as e:
            self._set_running(False)
            self._progress_label.setText("Error")
            QMessageBox.critical(self, "Error", f"Failed to start worker: {e}")
            self._append_log(f"ERROR: failed to start worker: {e}")
            return

        self._append_log(f"Worker started (pid {self._proc.pid}). Generating keys…")
        self._poll_timer.start(100)

    def _cleanup_process(self, *, terminate: bool = False) -> None:
        if self._stop_event:
            self._stop_event.set()
        if not self._proc:
            return
        if self._proc.is_alive():
            self._proc.join(timeout=4)
        if terminate and self._proc.is_alive():
            self._proc.terminate()
            self._proc.join(timeout=2)
        self._proc = None
        self._msg_queue = None
        self._stop_event = None

    def _stop(self) -> None:
        self._progress_label.setText("Stopping…")
        self._append_log("Stop requested…")
        self._cleanup_process(terminate=True)
        self._poll_timer.stop()
        self._set_running(False)
        if self._progress_label.text() == "Stopping…":
            self._progress_label.setText("Stopped")

    def _poll_queue(self) -> None:
        if not self._msg_queue:
            return
        terminal = self._consume_queue(limit=_MAX_MSGS_PER_TICK)
        if terminal:
            self._handle_message(terminal)

        if self._proc and not self._proc.is_alive():
            self._proc.join(timeout=0.2)
            terminal = self._consume_queue(limit=None)
            if terminal:
                self._handle_message(terminal)
            elif not self._saw_worker_message:
                self._handle_worker_failure(self._proc.exitcode)
            self._cleanup_process()
            self._poll_timer.stop()
            self._set_running(False)
            if self._progress_label.text() not in ("Done", "Stopped", "Error"):
                self._progress_label.setText("Finished")

    def _handle_worker_failure(self, exit_code: int | None) -> None:
        message = (
            f"Worker exited unexpectedly (code {exit_code}). "
            "Try launching from terminal: btc-vanity-gui"
        )
        self._progress_label.setText("Error")
        QMessageBox.critical(self, "Error", message)
        self._append_log(f"ERROR: {message}")

    def _handle_message(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "info":
            d = msg.get("difficulty", {})
            net = "testnet" if msg.get("testnet") else "mainnet"
            self._append_log(
                f"Type: {msg.get('address_type')} | {net} | "
                f"constrained chars: {d.get('constrained_chars', 0)}"
            )
            self._append_log(
                f"Workers: {msg.get('workers')} | mode: {msg.get('mode')} | curve: {msg.get('backend')}"
            )
        elif kind == "output":
            if msg.get("per_file", 0) > 0:
                self._append_log(
                    f"Output split: up to {msg['per_file']:,} per file → {msg.get('pattern')}"
                )
            else:
                self._append_log(f"Output: {msg.get('path')}")
        elif kind == "rotated":
            self._append_log(f"Rotated to part {msg.get('part')}: {msg.get('path')}")
        elif kind == "progress":
            self._apply_progress(msg)
        elif kind == "found":
            rec = msg["record"]
            self._apply_progress(
                {
                    "attempts": 0,
                    "speed": 0,
                    "found": msg["found"],
                    "target": int(self._count.value()),
                }
            )
            self._append_log(f"✅ Found ({msg['found']}): {rec['address']}")
            if "wif" in rec:
                self._append_log(f"   WIF: {rec['wif']}")
            if "mnemonic" in rec:
                self._append_log(f"   mnemonic: {rec['mnemonic']}")
            if "path" in rec:
                self._append_log(f"   path: {rec['path']}")
        elif kind == "done":
            self._progress_label.setText("Done")
            self._set_running(False)
            self._poll_timer.stop()
            self._append_log(
                f"Done. Found {msg['found']} / attempts {msg['attempts']:,}. Saved to {msg['output']}"
            )
        elif kind == "stopped":
            self._progress_label.setText("Stopped")
            self._set_running(False)
            self._poll_timer.stop()
            self._append_log(f"Stopped. Found {msg['found']}, attempts {msg['attempts']:,}")
        elif kind == "error":
            self._progress_label.setText("Error")
            self._set_running(False)
            self._poll_timer.stop()
            QMessageBox.critical(self, "Error", msg.get("message", "Unknown error"))
            self._append_log(f"ERROR: {msg.get('message')}")

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.is_alive()

    def request_stop(self) -> None:
        if self.is_running():
            self._stop()
