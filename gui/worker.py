"""Background search process for the GUI (keeps Qt main thread responsive)."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import signal
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bitcoin_address import (  # noqa: E402
    ALLOWED_STRENGTHS,
    DEFAULT_PATHS,
    AddressType,
    estimate_difficulty,
    make_matcher,
    privkey_to_wif,
    validate_pattern,
)
import secp  # noqa: E402
from search_engine import Job, SearchEngine, default_workers  # noqa: E402

OUTPUT_MODE = 0o600
_PROGRESS_INTERVAL_S = 0.5
_DETAIL_FOUND_LIMIT = 100


def _worker_mp_context() -> mp.context.BaseContext:
    if sys.platform == "linux":
        for method in ("forkserver", "spawn"):
            try:
                return mp.get_context(method)
            except ValueError:
                continue
    return mp.get_context("spawn")



@dataclass
class SearchConfig:
    prefix: str = "1"
    suffix: str = ""
    address_type: AddressType = "p2pkh"
    testnet: bool = False
    batch: int = 500
    count: int = 1
    strength: int = 256
    mnemonic: bool = False
    index_search: bool = False
    path: str = "m/44'/0'/0'/0/0"
    output: str = "btc_addrs.jsonl"
    no_private_key: bool = False
    workers: int = default_workers()
    per_file: int = 0

    @property
    def mode(self) -> str:
        if not self.mnemonic:
            return "key"
        return "index" if self.index_search else "mnemonic"


def _split_output_name(path: str) -> str:
    root, _ = os.path.splitext(path)
    return root or path


def _part_path(out_root: str, part_idx: int, per_file: int) -> str:
    if per_file > 0:
        return f"{out_root}_{part_idx:03d}.jsonl"
    return f"{out_root}.jsonl"


def _secure_chmod(path: str) -> None:
    try:
        os.chmod(path, OUTPUT_MODE)
    except OSError:
        pass


def _build_record(
    addr: str,
    priv: bytes,
    mnemonic: str | None,
    *,
    include_secrets: bool,
    testnet: bool,
    address_type: AddressType,
    path: str | None = None,
) -> dict[str, Any]:
    rec: dict[str, Any] = {"address": addr, "address_type": address_type}
    if include_secrets:
        rec["private_key"] = priv.hex()
        rec["wif"] = privkey_to_wif(priv, testnet=testnet)
        if mnemonic:
            rec["mnemonic"] = mnemonic
    if path:
        rec["path"] = path
    return rec


def _exit_on_sigterm(signum: int, frame: Any) -> None:
    raise SystemExit(0)


def run_search(config: SearchConfig, msg_queue: mp.Queue, stop_event: mp.Event) -> None:
    # A terminate() from the GUI must still run the finally blocks that stop the workers.
    signal.signal(signal.SIGTERM, _exit_on_sigterm)
    try:
        validate_pattern(
            config.prefix,
            config.suffix,
            address_type=config.address_type,
            testnet=config.testnet,
        )
    except ValueError as e:
        msg_queue.put({"type": "error", "message": str(e)})
        return

    if config.strength not in ALLOWED_STRENGTHS:
        msg_queue.put({"type": "error", "message": f"Invalid strength: {config.strength}"})
        return

    diff = estimate_difficulty(
        config.prefix,
        config.suffix,
        address_type=config.address_type,
        testnet=config.testnet,
    )
    msg_queue.put(
        {
            "type": "info",
            "address_type": config.address_type,
            "testnet": config.testnet,
            "difficulty": asdict(diff),
            "workers": config.workers,
            "mode": config.mode,
            "backend": secp.BACKEND,
        }
    )

    out_root = _split_output_name(config.output)
    include_secrets = not config.no_private_key

    attempts = 0
    found_count = 0
    start = time.time()
    current_part = 1
    written_in_part = 0
    current_path = _part_path(out_root, current_part, config.per_file)
    last_found_ui_at = 0
    found_ui_step = max(1_000, config.count // 500) if config.count > _DETAIL_FOUND_LIMIT else 1
    flush_every = max(1, min(500, config.count // 1000))

    def maybe_emit_found_progress(*, force: bool = False) -> None:
        nonlocal last_found_ui_at
        if config.count <= _DETAIL_FOUND_LIMIT and not force:
            return
        if (
            not force
            and found_count != 1
            and found_count < config.count
            and found_count - last_found_ui_at < found_ui_step
        ):
            return
        last_found_ui_at = found_count
        elapsed = time.time() - start
        speed = attempts / elapsed if elapsed > 0 else 0.0
        msg_queue.put(
            {
                "type": "progress",
                "attempts": attempts,
                "speed": speed,
                "found": found_count,
                "target": config.count,
            }
        )

    def rotate_if_needed(out_f) -> Any:
        nonlocal current_part, current_path, written_in_part
        if config.per_file <= 0 or written_in_part < config.per_file:
            return out_f
        out_f.flush()
        out_f.close()
        current_part += 1
        current_path = _part_path(out_root, current_part, config.per_file)
        os.makedirs(os.path.dirname(current_path) or ".", exist_ok=True)
        new_f = open(current_path, "a", encoding="utf-8")
        _secure_chmod(current_path)
        written_in_part = 0
        msg_queue.put({"type": "rotated", "path": current_path, "part": current_part})
        return new_f

    def write_match(out_f, rec: dict[str, Any]) -> Any:
        nonlocal found_count, written_in_part
        out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        found_count += 1
        written_in_part += 1
        if found_count % flush_every == 0:
            out_f.flush()
        if config.count <= _DETAIL_FOUND_LIMIT:
            msg_queue.put({"type": "found", "record": rec, "found": found_count})
        else:
            maybe_emit_found_progress(force=found_count >= config.count)
        return rotate_if_needed(out_f)

    def emit_progress() -> None:
        elapsed = time.time() - start
        speed = attempts / elapsed if elapsed > 0 else 0.0
        msg_queue.put(
            {
                "type": "progress",
                "attempts": attempts,
                "speed": speed,
                "found": found_count,
                "target": config.count,
            }
        )

    engine: SearchEngine | None = None
    try:
        job = Job(
            matcher=make_matcher(config.prefix, config.suffix, address_type=config.address_type, testnet=config.testnet),
            mode=config.mode,
            strength=config.strength,
            path=config.path or DEFAULT_PATHS[config.address_type],
            report_every=config.batch,
        )
        os.makedirs(os.path.dirname(current_path) or ".", exist_ok=True)
        out_f = open(current_path, "a", encoding="utf-8")
        _secure_chmod(current_path)
        msg_queue.put(
            {
                "type": "output",
                "path": current_path,
                "pattern": f"{out_root}_*.jsonl" if config.per_file > 0 else current_path,
                "per_file": config.per_file,
            }
        )

        try:
            engine = SearchEngine(job, config.workers).start()
            start = time.time()
            last_progress = start
            while found_count < config.count and not stop_event.is_set():
                found = engine.next_match(timeout=0.1)
                attempts = engine.attempts
                if found:
                    rec = _build_record(
                        found["address"],
                        bytes.fromhex(found["private_key"]),
                        found.get("mnemonic"),
                        include_secrets=include_secrets,
                        testnet=config.testnet,
                        address_type=config.address_type,
                        path=found.get("path"),
                    )
                    out_f = write_match(out_f, rec)
                elif not engine.alive():
                    raise RuntimeError("all search workers exited unexpectedly")
                now = time.time()
                if now - last_progress >= _PROGRESS_INTERVAL_S:
                    emit_progress()
                    last_progress = now
        finally:
            if engine is not None:
                engine.stop()
                attempts = engine.attempts
            out_f.flush()
            out_f.close()

        maybe_emit_found_progress(force=True)
        output_desc = f"{out_root}_*.jsonl" if config.per_file > 0 else current_path
        if stop_event.is_set():
            msg_queue.put(
                {"type": "stopped", "attempts": attempts, "found": found_count, "output": output_desc}
            )
        else:
            msg_queue.put(
                {
                    "type": "done",
                    "attempts": attempts,
                    "found": found_count,
                    "output": output_desc,
                }
            )
    except Exception as e:
        msg_queue.put({"type": "error", "message": str(e)})


def start_search_process(
    config: SearchConfig,
) -> tuple[mp.Process, mp.Queue, mp.Event]:
    ctx = _worker_mp_context()
    msg_queue: mp.Queue = ctx.Queue()
    stop_event = ctx.Event()
    proc = ctx.Process(
        target=run_search,
        args=(config, msg_queue, stop_event),
        daemon=False,
    )
    proc.start()
    return proc, msg_queue, stop_event
