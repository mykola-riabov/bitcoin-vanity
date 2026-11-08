#!/usr/bin/env python3
"""CLI for Bitcoin vanity address generation (P2PKH, P2SH, SegWit)."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import signal
import sys
import time

import secp
from bitcoin_address import (
    ADDRESS_TYPES,
    ALLOWED_STRENGTHS,
    DEFAULT_PATHS,
    VERSION,
    AddressType,
    detect_address_type,
    estimate_difficulty,
    make_matcher,
    privkey_to_wif,
    validate_pattern,
)
from search_engine import Job, SearchEngine, default_workers

OUTPUT_MODE = 0o600


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bitcoin vanity generator: P2PKH (1…), P2SH (3…), native SegWit (bc1…).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--prefix", type=str, default="1", help="Address must start with this string.")
    parser.add_argument("--suffix", type=str, default="", help="Address must end with this string.")
    parser.add_argument(
        "--address-type",
        choices=ADDRESS_TYPES,
        default=None,
        help="Address format (default: auto-detect from prefix: 1/3/bc1).",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=500,
        help="Keys each worker checks between progress reports and stop checks",
    )
    parser.add_argument("--output", type=str, default="btc_addrs.jsonl", help="Output base filename (.jsonl)")
    parser.add_argument(
        "--per-file",
        type=int,
        default=0,
        help="Rotate output after N matches per file. 0 = single file.",
    )
    parser.add_argument("--count", type=int, default=1, help="Matches required before stopping")
    parser.add_argument(
        "--strength",
        type=int,
        default=256,
        choices=ALLOWED_STRENGTHS,
        help="Entropy bits for random key generation",
    )
    parser.add_argument(
        "--workers",
        "--pool-workers",
        dest="workers",
        type=int,
        default=default_workers(),
        help="Worker processes; each generates and checks keys on its own (default: CPU count)",
    )
    parser.add_argument("--pool", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--mnemonic", action="store_true", help="BIP39 + BIP32 derivation")
    parser.add_argument(
        "--index-search",
        action="store_true",
        help="With --mnemonic: one phrase per worker, scan the last path index (fast). "
        "The found path is saved with the result.",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="BIP32 path (--mnemonic). Default follows address type (44'/49'/84').",
    )
    parser.add_argument("--testnet", action="store_true", help="Testnet (m/n/2/tb1…)")
    parser.add_argument(
        "--no-private-key",
        action="store_true",
        help="Do not write private_key/WIF/mnemonic to output",
    )
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    return parser.parse_args()


def split_output_name(path: str) -> tuple[str, str]:
    root, ext = os.path.splitext(path)
    return root, ext or ".jsonl"


def secure_chmod(path: str) -> None:
    try:
        os.chmod(path, OUTPUT_MODE)
    except OSError:
        pass


def build_record(
    addr: str,
    priv: bytes,
    mnemonic: str | None,
    *,
    include_secrets: bool,
    testnet: bool,
    address_type: AddressType,
    path: str | None = None,
) -> dict:
    rec: dict = {"address": addr, "address_type": address_type}
    if include_secrets:
        rec["private_key"] = priv.hex()
        rec["wif"] = privkey_to_wif(priv, testnet=testnet)
        if mnemonic:
            rec["mnemonic"] = mnemonic
    if path:
        rec["path"] = path
    return rec


def resolve_address_type(args: argparse.Namespace) -> AddressType:
    if args.address_type:
        return args.address_type
    detected = detect_address_type(args.prefix, testnet=args.testnet)
    return detected or "p2pkh"


def main() -> None:
    args = parse_args()
    if args.version:
        print(f"btc-vanity {VERSION}")
        return

    address_type = resolve_address_type(args)
    derivation_path = args.path or DEFAULT_PATHS[address_type]
    if args.workers < 1 or args.batch < 1:
        print("❌ --workers and --batch must be >= 1")
        sys.exit(1)
    if args.index_search and not args.mnemonic:
        print("❌ --index-search needs --mnemonic")
        sys.exit(1)
    mode = ("index" if args.index_search else "mnemonic") if args.mnemonic else "key"

    try:
        validate_pattern(args.prefix, args.suffix, address_type=address_type, testnet=args.testnet)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    diff = estimate_difficulty(
        args.prefix, args.suffix, address_type=address_type, testnet=args.testnet
    )
    out_root, _ = split_output_name(args.output)
    include_secrets = not args.no_private_key
    testnet = args.testnet

    start = time.time()
    last_log = start
    found_count = 0
    current_part = 1
    written_in_part = 0

    def make_part_path(part_idx: int) -> str:
        if args.per_file > 0:
            return f"{out_root}_{part_idx:03d}.jsonl"
        return f"{out_root}.jsonl"

    current_path = make_part_path(current_part)
    os.makedirs(os.path.dirname(current_path) or ".", exist_ok=True)
    out_f = open(current_path, "a", encoding="utf-8")
    secure_chmod(current_path)

    def rotate_if_needed() -> None:
        nonlocal current_part, current_path, out_f, written_in_part
        if args.per_file <= 0 or written_in_part < args.per_file:
            return
        out_f.flush()
        out_f.close()
        current_part += 1
        current_path = make_part_path(current_part)
        out_f = open(current_path, "a", encoding="utf-8")
        secure_chmod(current_path)
        written_in_part = 0
        print(f"\n📁 Rotated output → {current_path}")

    def handle_match(found: dict) -> bool:
        nonlocal found_count, written_in_part
        rec = build_record(
            found["address"], bytes.fromhex(found["private_key"]), found.get("mnemonic"),
            include_secrets=include_secrets, testnet=testnet, address_type=address_type,
            path=found.get("path"),
        )
        out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        found_count += 1
        written_in_part += 1
        rotate_if_needed()
        print(f"\n✅ Found! {found_count}/{args.count}")
        print(f"🔗 {rec['address']}")
        if include_secrets:
            print(f"🔑 WIF: {rec['wif']}")
        if rec.get("path"):
            print(f"📍 Path: {rec['path']}")
        return found_count >= args.count

    engine: SearchEngine | None = None

    def on_interrupt(_sig, _frame) -> None:
        if mp.current_process().name != "MainProcess":
            return
        if engine is not None:
            engine.stop()
        attempts = engine.attempts if engine is not None else 0
        elapsed = time.time() - start
        print(f"\n🛑 Interrupted. Attempts: {attempts:,}, found: {found_count}")
        if elapsed > 0:
            print(f"⚡ {attempts / elapsed:,.0f} keys/sec")
        sys.exit(0)  # the finally block below stops the workers and closes the output

    signal.signal(signal.SIGINT, on_interrupt)

    type_labels = {"p2pkh": "P2PKH (1…)", "p2sh": "P2SH-P2WPKH (3…)", "p2wpkh": "Native SegWit (bc1…)"}
    net = "testnet" if testnet else "mainnet"
    print(f"🚀 Bitcoin vanity search — {type_labels[address_type]}")
    print(f"🔹 Network : {net}")
    print(f"🔹 Prefix  : {args.prefix}")
    print(f"🔹 Suffix  : {args.suffix or '(none)'}")
    print(f"🔹 Target  : {args.count:,} match(es)")
    if args.mnemonic:
        print(f"🔹 Path    : {derivation_path}" + (" (last index scanned)" if mode == "index" else ""))
    print(f"🧵 Workers : {args.workers} · mode: {mode} · curve backend: {secp.BACKEND}")
    print(f"💾 Output  : {out_root}*.jsonl (per_file={args.per_file})")
    if diff.constrained_chars == 0:
        print("📊 Difficulty: trivial")
    else:
        print(
            f"📊 Difficulty: ~{diff.expected_attempts:,.0f} attempts "
            f"({diff.constrained_chars} char(s), alphabet×{diff.charset_size})"
        )
        if diff.overlap_warning:
            print("   ⚠️  Prefix/suffix overlap — estimate may be optimistic.")
    print()

    job = Job(
        matcher=make_matcher(args.prefix, args.suffix, address_type=address_type, testnet=testnet),
        mode=mode,
        strength=args.strength,
        path=derivation_path,
        report_every=args.batch,
    )
    try:
        engine = SearchEngine(job, args.workers).start()
        start = time.time()
        while found_count < args.count:
            try:
                found = engine.next_match(timeout=0.5)
            except RuntimeError as e:
                print(f"\n❌ Worker failed: {e}")
                sys.exit(1)
            if found and handle_match(found):
                break
            if not engine.alive():
                print("\n❌ All workers exited unexpectedly")
                sys.exit(1)
            now = time.time()
            if now - last_log >= 1:
                attempts = engine.attempts
                elapsed = now - start
                speed = attempts / elapsed if elapsed > 0 else 0.0
                print(
                    f"\r🔄 {attempts:,} keys | ⚡ {speed:,.0f}/s | found {found_count}/{args.count}",
                    end="", flush=True,
                )
                last_log = now
    finally:
        if engine is not None:
            engine.stop()
        if not out_f.closed:
            out_f.flush()
            out_f.close()

    print(f"\n💾 Done. {found_count} address(es) → {out_root}*.jsonl")


if __name__ == "__main__":
    mp.freeze_support()
    main()
