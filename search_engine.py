"""Parallel vanity search: every worker process generates, derives and checks keys on its own.

Only matches travel between processes, plus a shared attempt counter, so speed grows with the
number of workers. Three key sources:

- ``key``      — random 32-byte private key (fastest, no recovery phrase);
- ``mnemonic`` — a new BIP39 phrase for every attempt (slow: PBKDF2 with 2048 rounds per phrase);
- ``index``    — one BIP39 phrase per worker, then address indexes 0, 1, 2… of the given path
                 (as fast as ``key`` and still gives a phrase; the found index is in ``path``).
"""

from __future__ import annotations

import hashlib
import multiprocessing as mp
import os
import queue
import sys
from dataclasses import dataclass
from typing import Any, Callable

from mnemonic import Mnemonic

import secp
from bip32_pure import BIP32, MAX_NON_HARDENED, parse_path

MODES = ("key", "mnemonic", "index")
ALLOWED_STRENGTHS = [128, 160, 192, 224, 256]


@dataclass(frozen=True)
class Job:
    matcher: Callable[[bytes], str | None]
    mode: str = "key"
    strength: int = 256
    path: str = ""
    report_every: int = 500


def default_workers() -> int:
    return os.cpu_count() or 1


def validate_job(job: Job) -> None:
    if job.mode not in MODES:
        raise ValueError(f"Unknown mode {job.mode!r}; expected one of {', '.join(MODES)}")
    if job.strength not in ALLOWED_STRENGTHS:
        raise ValueError(f"Invalid strength: {job.strength}")
    if job.report_every < 1:
        raise ValueError("report_every must be >= 1")
    if job.mode in ("mnemonic", "index"):
        indexes = parse_path(job.path)
        if not indexes:
            raise ValueError("Derivation path is empty")
        if job.mode == "index" and indexes[-1] > MAX_NON_HARDENED:
            raise ValueError("Index search needs a non-hardened last path element, e.g. m/44'/118'/0'/0/0")


def random_privkey(strength_bits: int) -> bytes:
    nbytes = strength_bits // 8
    while True:
        raw = os.urandom(nbytes)
        if len(raw) != 32:
            raw = hashlib.sha256(raw).digest()
        if 1 <= int.from_bytes(raw, "big") < secp.CURVE_ORDER:
            return raw


def _with_last_index(path: str, index: int) -> str:
    head = path.strip().rstrip("/").rsplit("/", 1)[0]
    return f"{head}/{index}"


class _Source:
    """Yields (private_key, mnemonic_or_None, path_or_None) for one worker."""

    def __init__(self, job: Job) -> None:
        self._job = job
        self._mnemo = Mnemonic("english")
        self._path = parse_path(job.path) if job.mode != "key" else []
        self._scanner = None
        self._words: str | None = None
        self._index = 0
        self._last = MAX_NON_HARDENED

    def _new_phrase(self) -> tuple[str, BIP32]:
        words = self._mnemo.to_mnemonic(os.urandom(self._job.strength // 8))
        return words, BIP32.from_seed(self._mnemo.to_seed(words))

    def _new_index_root(self) -> None:
        words, root = self._new_phrase()
        start = self._path[-1]
        self._words = words
        self._scanner = root.derive(self._path[:-1]).index_scanner()
        self._index = start

    def next(self) -> tuple[bytes | None, str | None, str | None]:
        job = self._job
        if job.mode == "key":
            return random_privkey(job.strength), None, None
        if job.mode == "mnemonic":
            words, root = self._new_phrase()
            return root.get_privkey_from_path(self._path), words, job.path
        if self._scanner is None or self._index > self._last:
            self._new_index_root()
        index = self._index
        self._index += 1
        return self._scanner.child(index), self._words, _with_last_index(job.path, index)


def worker_loop(job: Job, results: Any, counter: Any, stop: Any) -> None:
    secp.rerandomize()
    parent = os.getppid()
    try:
        source = _Source(job)
        # Also stop when the parent is gone (killed without a chance to stop us).
        while not stop.is_set() and os.getppid() == parent:
            for _ in range(job.report_every):
                priv, words, path = source.next()
                if priv is None:
                    continue
                addr = job.matcher(priv)
                if addr:
                    rec: dict[str, Any] = {"address": addr, "private_key": priv.hex()}
                    if words:
                        rec["mnemonic"] = words
                        rec["path"] = path
                    results.put(rec)
            with counter.get_lock():
                counter.value += job.report_every
    except Exception as e:  # reported to the parent instead of dying silently
        results.put({"error": f"{type(e).__name__}: {e}"})


def _context() -> mp.context.BaseContext:
    """fork on Linux: workers inherit the job without pickling; spawn elsewhere."""
    if sys.platform == "linux":
        try:
            return mp.get_context("fork")
        except ValueError:
            pass
    return mp.get_context("spawn")


class SearchEngine:
    def __init__(self, job: Job, workers: int) -> None:
        validate_job(job)
        if workers < 1:
            raise ValueError("workers must be >= 1")
        ctx = _context()
        self.job = job
        self.workers = workers
        self._results = ctx.Queue()
        self._counter = ctx.Value("Q", 0)
        self._stop = ctx.Event()
        self._procs = [
            ctx.Process(target=worker_loop, args=(job, self._results, self._counter, self._stop), daemon=True)
            for _ in range(workers)
        ]

    def start(self) -> "SearchEngine":
        for p in self._procs:
            p.start()
        return self

    @property
    def attempts(self) -> int:
        return int(self._counter.value)

    def alive(self) -> bool:
        return any(p.is_alive() for p in self._procs)

    def next_match(self, timeout: float) -> dict[str, Any] | None:
        """A found record, or None after `timeout` seconds. Raises RuntimeError if a worker failed."""
        try:
            rec = self._results.get(timeout=timeout)
        except queue.Empty:
            return None
        if "error" in rec:
            raise RuntimeError(rec["error"])
        return rec

    def stop(self, join_timeout: float = 2.0) -> None:
        self._stop.set()
        for p in self._procs:
            p.join(timeout=join_timeout)
        for p in self._procs:
            if p.is_alive():
                p.terminate()
                p.join(timeout=join_timeout)
        self._results.cancel_join_thread()

    def __enter__(self) -> "SearchEngine":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()
