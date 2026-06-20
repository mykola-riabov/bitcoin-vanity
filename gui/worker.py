"""Background search process for the GUI (keeps Qt main thread responsive)."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
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
    check_key_indexed,
    estimate_difficulty,
    generate_keys_batch,
    privkey_to_wif,
    try_match_privkey,
    validate_pattern,
)

OUTPUT_MODE = 0o600
_PROGRESS_EVERY = 2_000
_DETAIL_FOUND_LIMIT = 100


def _worker_mp_context() -> mp.context.BaseContext:
    if sys.platform == "linux":
        for method in ("forkserver", "spawn"):
            try:
                return mp.get_context(method)
            except ValueError:
                continue
    return mp.get_context("spawn")


def _pool_mp_context() -> mp.context.BaseContext:
    if sys.platform == "linux":
        try:
            return mp.get_context("fork")
        except ValueError:
            pass
    return mp.get_context("spawn")


@dataclass
class SearchConfig:
    prefix: str = "1"
    suffix: str = ""
    address_type: AddressType = "p2pkh"
    testnet: bool = False
    batch: int = 10_000
    count: int = 1
    strength: int = 256
    mnemonic: bool = False
    path: str = "m/44'/0'/0'/0/0"
    output: str = "btc_addrs.jsonl"
    no_private_key: bool = False
    pool: bool = False
    pool_workers: int = 2
    per_file: int = 0


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
) -> dict[str, Any]:
    rec: dict[str, Any] = {"address": addr, "address_type": address_type}
    if include_secrets:
        rec["private_key"] = priv.hex()
        rec["wif"] = privkey_to_wif(priv, testnet=testnet)
        if mnemonic:
            rec["mnemonic"] = mnemonic
    return rec


def run_search(config: SearchConfig, msg_queue: mp.Queue, stop_event: mp.Event) -> None:
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
        }
    )

    out_root = _split_output_name(config.output)
    include_secrets = not config.no_private_key
    pool_args = (config.prefix, config.suffix, config.address_type, config.testnet)

    attempts = 0
    found_count = 0
    start = time.time()
    last_progress_at = 0
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

    def emit_progress(*, force: bool = False, attempt_count: int | None = None) -> None:
        nonlocal last_progress_at
        current = attempt_count if attempt_count is not None else attempts
        if not force and current - last_progress_at < _PROGRESS_EVERY:
            return
        last_progress_at = current
        elapsed = time.time() - start
        speed = current / elapsed if elapsed > 0 else 0.0
        msg_queue.put(
            {
                "type": "progress",
                "attempts": current,
                "speed": speed,
                "found": found_count,
                "target": config.count,
            }
        )

    def process_batch(out_f, keys: list[bytes], mnemonics: list[str] | None, pool: mp.Pool | None) -> tuple[Any, bool]:
        nonlocal attempts

        if pool is not None:
            work = [(i, k, *pool_args) for i, k in enumerate(keys)]
            checked_in_batch = 0
            for idx, addr in pool.imap_unordered(check_key_indexed, work, chunksize=256):
                if stop_event.is_set():
                    return out_f, True
                checked_in_batch += 1
                if checked_in_batch % _PROGRESS_EVERY == 0:
                    emit_progress(force=True, attempt_count=attempts + checked_in_batch)
                if not addr:
                    continue
                rec = _build_record(
                    addr,
                    keys[idx],
                    mnemonics[idx] if mnemonics else None,
                    include_secrets=include_secrets,
                    testnet=config.testnet,
                    address_type=config.address_type,
                )
                out_f = write_match(out_f, rec)
                if found_count >= config.count:
                    return out_f, True
            return out_f, stop_event.is_set()

        for idx, priv in enumerate(keys):
            if stop_event.is_set():
                return out_f, True
            addr = try_match_privkey(
                priv,
                config.prefix,
                config.suffix,
                address_type=config.address_type,
                testnet=config.testnet,
            )
            if idx and idx % _PROGRESS_EVERY == 0:
                emit_progress(force=True, attempt_count=attempts + idx + 1)
            if not addr:
                continue
            rec = _build_record(
                addr,
                priv,
                mnemonics[idx] if mnemonics else None,
                include_secrets=include_secrets,
                testnet=config.testnet,
                address_type=config.address_type,
            )
            out_f = write_match(out_f, rec)
            if found_count >= config.count:
                return out_f, True
        return out_f, stop_event.is_set()

    try:
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

        pool_ctx = _pool_mp_context().Pool(processes=config.pool_workers) if config.pool else None
        derivation_path = config.path or DEFAULT_PATHS[config.address_type]
        try:
            while found_count < config.count and not stop_event.is_set():
                keys, mnemonics = generate_keys_batch(
                    config.batch,
                    config.strength,
                    mnemonic=config.mnemonic,
                    derivation_path=derivation_path,
                )
                attempts += len(keys)

                out_f, stop = process_batch(out_f, keys, mnemonics, pool_ctx)
                if stop:
                    break

                emit_progress(force=True)
        finally:
            if pool_ctx is not None:
                pool_ctx.close()
                pool_ctx.join()
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
