"""Balance scanner core for Bitcoin — shared by CLI (scan.py) and GUI."""

from __future__ import annotations

import gc
import glob
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

import requests

MAINNET_API = "https://blockstream.info/api"
TESTNET_API = "https://blockstream.info/testnet/api"
BALANCE_UNIT = "sats"


@dataclass
class ScanConfig:
    input_glob: str = "*.jsonl"
    input_files: list[str] | None = None
    api_endpoint: str = MAINNET_API
    testnet: bool = False
    num_workers: int = 20
    http_timeout: float = 10.0
    http_retries: int = 2
    result_dir: str = "found_wallets"
    cache_file: str = "checked_cache.json"
    cache_flush_every_ok: int = 10_000
    found_flush_every: int = 1
    in_flight_multiplier: int = 20
    create_empty_cache_on_start: bool = False


# =============================================================================
# Cache helpers
# =============================================================================


def load_cache(path: str) -> Dict[str, dict]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RuntimeError(f"Cache file '{path}' must be a JSON object/dict at root.")
    return data


def save_cache_atomic(path: str, cache: Dict[str, dict]) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def cache_is_ok(cache: Dict[str, dict], addr: str) -> bool:
    rec = cache.get(addr)
    return bool(rec) and rec.get("status") == "ok"


def cache_put_ok(cache: Dict[str, dict], addr: str, amount: int, unit: str = BALANCE_UNIT) -> None:
    cache[addr] = {
        "checked_at": int(time.time()),
        "status": "ok",
        "unit": unit,
        unit: amount,
    }


def _secure_chmod(path: str) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# =============================================================================
# HTTP
# =============================================================================


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "bitcoin-vanity-scan/1.0",
            "Accept": "application/json",
        }
    )
    return session


def get_json_with_retries(
    session: requests.Session,
    url: str,
    *,
    timeout: float,
    retries: int,
) -> Tuple[Optional[dict], Optional[str]]:
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 429:
                wait = min(5.0, 0.5 * (attempt + 1) ** 2)
                time.sleep(wait)
                continue
            if r.status_code != 200:
                body = (r.text or "").strip()
                return None, f"HTTP {r.status_code}: {body[:200]}"
            return r.json(), None
        except requests.exceptions.RequestException as e:
            last_err = str(e)
            time.sleep(0.25 * (attempt + 1))
    return None, f"EXC: {last_err}"


def _address_balance(data: dict) -> int:
    chain = data.get("chain_stats") or {}
    mempool = data.get("mempool_stats") or {}
    funded = int(chain.get("funded_txo_sum", 0)) + int(mempool.get("funded_txo_sum", 0))
    spent = int(chain.get("spent_txo_sum", 0)) + int(mempool.get("spent_txo_sum", 0))
    return max(0, funded - spent)


def worker_check(
    session: requests.Session,
    wallet: dict,
    *,
    api_endpoint: str,
    timeout: float,
    retries: int,
) -> Tuple[str, Optional[str], object, dict]:
    addr = wallet.get("address")
    if not addr:
        return ("BAD", None, "no address field", wallet)
    url = f"{api_endpoint.rstrip('/')}/address/{addr}"
    data, err = get_json_with_retries(session, url, timeout=timeout, retries=retries)
    if err:
        return ("ERR", addr, err, wallet)
    amount = _address_balance(data or {})
    return ("OK", addr, amount, wallet)


# =============================================================================
# Wallet reader
# =============================================================================


def iter_wallets_streaming(path: str) -> Iterable[dict]:
    lower = path.lower()
    if lower.endswith(".jsonl"):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)
        return

    with open(path, "r", encoding="utf-8") as f:
        first = ""
        while True:
            ch = f.read(1)
            if not ch:
                break
            if not ch.isspace():
                first = ch
                break

    if first == "[":
        try:
            import ijson  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                f"{path}: looks like a JSON array, but 'ijson' is not installed.\n"
                "Install: pip install ijson\n"
                "Or use JSONL input (.jsonl) from your generator."
            ) from e
        with open(path, "r", encoding="utf-8") as f:
            for item in ijson.items(f, "item"):
                yield item
        return

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def jsonl_to_array_streaming(jsonl_path: str, array_path: str) -> None:
    with open(array_path, "w", encoding="utf-8") as out:
        out.write("[\n")
        first = True
        if os.path.exists(jsonl_path):
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if not first:
                        out.write(",\n")
                    out.write(line)
                    first = False
        out.write("\n]\n")
    _secure_chmod(array_path)


def resolve_input_files(config: ScanConfig) -> list[str]:
    result_dir = os.path.abspath(config.result_dir)
    cache_path = os.path.abspath(config.cache_file)

    def ok_file(path: str) -> bool:
        return (
            os.path.isfile(path)
            and not os.path.basename(path).startswith("found_")
            and not os.path.abspath(path).startswith(result_dir)
            and os.path.abspath(path) != cache_path
        )

    if config.input_files:
        files: list[str] = []
        for entry in config.input_files:
            entry = entry.strip()
            if not entry:
                continue
            if os.path.isdir(entry):
                for pattern in ("*.jsonl", "*.json"):
                    for path in sorted(glob.glob(os.path.join(entry, pattern))):
                        if ok_file(path):
                            files.append(path)
            elif ok_file(entry):
                files.append(entry)
        return sorted(set(files))

    if os.path.isdir(config.input_glob):
        files = []
        for pattern in ("*.jsonl", "*.json"):
            for path in sorted(glob.glob(os.path.join(config.input_glob, pattern))):
                if ok_file(path):
                    files.append(path)
        return files

    return sorted(
        f
        for f in glob.glob(config.input_glob)
        if ok_file(f)
    )


# =============================================================================
# Processing
# =============================================================================


def _emit(
    msg_queue: Queue | None,
    msg: dict[str, Any],
    on_message: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    if msg_queue is not None:
        msg_queue.put(msg)
    if on_message is not None:
        on_message(msg)


def process_file(
    file_path: str,
    config: ScanConfig,
    cache: Dict[str, dict],
    cache_lock: threading.Lock,
    ok_since_flush_ref: List[int],
    *,
    msg_queue: Queue | None = None,
    stop_event: threading.Event | None = None,
    session: requests.Session | None = None,
    on_message: Callable[[dict[str, Any]], None] | None = None,
) -> Tuple[int, int, int, int, List[str], str, str]:
    session = session or _make_session()
    stop_event = stop_event or threading.Event()
    max_in_flight = max(config.num_workers, config.num_workers * config.in_flight_multiplier)
    unit = BALANCE_UNIT
    api_endpoint = config.api_endpoint or (TESTNET_API if config.testnet else MAINNET_API)

    found_lock = threading.Lock()
    found_buffer: List[dict] = []
    found_jsonl_path: Optional[str] = None

    def append_found_jsonl(batch: List[dict], path: str) -> None:
        if not batch:
            return
        with open(path, "a", encoding="utf-8") as f:
            for item in batch:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        _secure_chmod(path)

    def flush_found(force: bool = False) -> int:
        if not found_jsonl_path:
            return 0
        with found_lock:
            if not force and len(found_buffer) < config.found_flush_every:
                return 0
            batch = list(found_buffer)
            found_buffer.clear()
        append_found_jsonl(batch, found_jsonl_path)
        return len(batch)

    base = os.path.splitext(os.path.basename(file_path))[0]
    os.makedirs(config.result_dir, exist_ok=True)
    found_jsonl_path = os.path.join(config.result_dir, f"found_from_{base}.jsonl")
    found_array_path = os.path.join(config.result_dir, f"found_from_{base}.json")

    skipped_this_file = 0
    ok_checked_this_file = 0
    found_this_file = 0
    errors: List[str] = []
    errors_count_this_file = 0
    checked_total = 0

    def emit(msg: dict[str, Any]) -> None:
        _emit(msg_queue, msg, on_message)

    emit({"type": "file_start", "file": file_path})

    in_flight: Set = set()

    def handle_result(status: str, addr: Optional[str], payload: object, wallet: dict) -> None:
        nonlocal ok_checked_this_file, found_this_file, errors_count_this_file, checked_total
        checked_total += 1

        if status == "OK":
            amount = int(payload)  # type: ignore[arg-type]
            with cache_lock:
                if addr and not cache_is_ok(cache, addr):
                    cache_put_ok(cache, addr, amount, unit)
                    ok_checked_this_file += 1
                    ok_since_flush_ref[0] += 1

            if amount > 0:
                out = dict(wallet)
                out[unit] = amount
                with found_lock:
                    found_buffer.append(out)
                found_this_file += 1
                flush_found(force=False)
                emit(
                    {
                        "type": "found",
                        "address": addr,
                        "amount": amount,
                        "denom": unit,
                        "file": file_path,
                    }
                )

            with cache_lock:
                should_flush_cache = ok_since_flush_ref[0] >= config.cache_flush_every_ok
            if should_flush_cache:
                with cache_lock:
                    if ok_since_flush_ref[0] >= config.cache_flush_every_ok:
                        save_cache_atomic(config.cache_file, cache)
                        ok_since_flush_ref[0] = 0
                        emit({"type": "cache_flush", "cache_size": len(cache)})

        elif status == "ERR":
            errors_count_this_file += 1
            errors.append(f"{addr} {payload}")
        else:
            errors.append(f"BAD_WALLET {payload}")

        if checked_total % 500 == 0 or status == "OK" and int(payload) > 0:  # type: ignore[arg-type]
            emit(
                {
                    "type": "progress",
                    "file": file_path,
                    "checked": checked_total,
                    "skipped": skipped_this_file,
                    "found": found_this_file,
                    "errors": errors_count_this_file,
                }
            )

    with ThreadPoolExecutor(max_workers=config.num_workers) as executor:
        for wallet in iter_wallets_streaming(file_path):
            if stop_event.is_set():
                break
            addr = wallet.get("address")
            if addr and cache_is_ok(cache, addr):
                skipped_this_file += 1
                if skipped_this_file % 1000 == 0:
                    emit(
                        {
                            "type": "progress",
                            "file": file_path,
                            "checked": checked_total,
                            "skipped": skipped_this_file,
                            "found": found_this_file,
                            "errors": errors_count_this_file,
                        }
                    )
                continue

            fut = executor.submit(
                worker_check,
                session,
                wallet,
                api_endpoint=api_endpoint,
                timeout=config.http_timeout,
                retries=config.http_retries,
            )
            in_flight.add(fut)

            if len(in_flight) >= max_in_flight:
                done = next(as_completed(in_flight))
                in_flight.remove(done)
                handle_result(*done.result())
                if stop_event.is_set():
                    break

        if not stop_event.is_set():
            for done in as_completed(in_flight):
                handle_result(*done.result())
                if stop_event.is_set():
                    break

    flush_found(force=True)

    with cache_lock:
        if ok_since_flush_ref[0] > 0:
            save_cache_atomic(config.cache_file, cache)
            ok_since_flush_ref[0] = 0

    if errors:
        err_file = os.path.join(config.result_dir, f"errors_from_{base}.log")
        with open(err_file, "w", encoding="utf-8") as f:
            f.write("\n".join(errors) + "\n")

    jsonl_to_array_streaming(found_jsonl_path, found_array_path)

    in_flight.clear()
    with found_lock:
        found_buffer.clear()
    gc.collect()

    emit(
        {
            "type": "file_done",
            "file": file_path,
            "skipped": skipped_this_file,
            "checked": ok_checked_this_file,
            "found": found_this_file,
            "errors": errors_count_this_file,
            "out_jsonl": found_jsonl_path,
            "out_json": found_array_path,
        }
    )

    return (
        skipped_this_file,
        ok_checked_this_file,
        errors_count_this_file,
        found_this_file,
        errors,
        found_jsonl_path,
        found_array_path,
    )


def run_scan(
    config: ScanConfig,
    msg_queue: Queue | None = None,
    stop_event: threading.Event | None = None,
    on_message: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Run balance scan; push dict messages to msg_queue. Thread-safe."""
    stop_event = stop_event or threading.Event()
    cache_lock = threading.Lock()
    cache = load_cache(config.cache_file)

    if config.create_empty_cache_on_start and not os.path.exists(config.cache_file):
        save_cache_atomic(config.cache_file, cache)

    ok_since_flush_ref = [0]
    session = _make_session()

    def emit(msg: dict[str, Any]) -> None:
        _emit(msg_queue, msg, on_message)

    try:
        wallet_files = resolve_input_files(config)
        if not wallet_files:
            emit({"type": "error", "message": f"No input files found for '{config.input_glob}'."})
            return

        _emit(
            msg_queue,
            {
                "type": "info",
                "api": config.api_endpoint or (TESTNET_API if config.testnet else MAINNET_API),
                "testnet": config.testnet,
                "unit": BALANCE_UNIT,
                "files": wallet_files,
                "cache_size": len(cache),
                "cache_file": config.cache_file,
            },
            on_message,
        )

        total_skipped = 0
        total_ok_checked = 0
        total_errors = 0
        total_found = 0

        for file_path in wallet_files:
            if stop_event.is_set():
                emit(
                    {
                        "type": "stopped",
                        "skipped": total_skipped,
                        "checked": total_ok_checked,
                        "found": total_found,
                        "errors": total_errors,
                    }
                )
                return

            (
                skipped_this_file,
                ok_checked_this_file,
                errors_this_file,
                found_this_file,
                _errors_list,
                _out_jsonl,
                _out_json,
            ) = process_file(
                file_path,
                config,
                cache,
                cache_lock,
                ok_since_flush_ref,
                msg_queue=msg_queue,
                stop_event=stop_event,
                session=session,
                on_message=on_message,
            )

            total_skipped += skipped_this_file
            total_ok_checked += ok_checked_this_file
            total_errors += errors_this_file
            total_found += found_this_file

        emit(
            {
                "type": "done",
                "skipped": total_skipped,
                "checked": total_ok_checked,
                "found": total_found,
                "errors": total_errors,
                "cache_file": config.cache_file,
                "result_dir": config.result_dir,
            }
        )
    except Exception as e:
        emit({"type": "error", "message": str(e)})


def drain_queue(msg_queue: Queue) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    while True:
        try:
            items.append(msg_queue.get_nowait())
        except Empty:
            break
    return items
