"""Bitcoin vanity address generation — P2PKH, P2SH-P2WPKH, native SegWit (CPU)."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Literal

from functools import partial
from typing import Callable

import base58
from bech32 import encode as bech32_segwit_encode
from bip32_pure import BIP32, parse_path
from mnemonic import Mnemonic

import secp

VERSION = "0.4.0"
HARDENED_OFFSET = 0x80000000
ALLOWED_STRENGTHS = [128, 160, 192, 224, 256]
AddressType = Literal["p2pkh", "p2sh", "p2wpkh"]

ADDRESS_TYPES: tuple[AddressType, ...] = ("p2pkh", "p2sh", "p2wpkh")
DEFAULT_PATHS: dict[AddressType, str] = {
    "p2pkh": "m/44'/0'/0'/0/0",
    "p2sh": "m/49'/0'/0'/0/0",
    "p2wpkh": "m/84'/0'/0'/0/0",
}

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BECH32_ALPHABET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BASE58_CHARSET_SIZE = 58
BECH32_CHARSET_SIZE = 32

_MAINNET_P2PKH = 0x00
_TESTNET_P2PKH = 0x6F
_MAINNET_P2SH = 0x05
_TESTNET_P2SH = 0xC4
_WIF_MAINNET = 0x80
_WIF_TESTNET = 0xEF

_CURVE_ORDER = secp.CURVE_ORDER
_MNEMO = Mnemonic("english")


def _ripemd160(data: bytes) -> bytes:
    try:
        return hashlib.new("ripemd160", data).digest()
    except ValueError:
        from Crypto.Hash import RIPEMD160

        return RIPEMD160.new(data).digest()


def _double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def _base58check(version: int, payload: bytes) -> str:
    body = bytes([version]) + payload
    return base58.b58encode(body + _double_sha256(body)[:4]).decode("ascii")


def _hrp(testnet: bool) -> str:
    return "tb" if testnet else "bc"


@dataclass(frozen=True)
class DifficultyEstimate:
    prefix_chars: int
    suffix_chars: int
    constrained_chars: int
    expected_attempts: float
    overlap_warning: bool
    charset_size: int


def invalid_base58_chars(part: str) -> list[str]:
    return [ch for ch in part if ch not in BASE58_ALPHABET]


def invalid_bech32_chars(part: str) -> list[str]:
    part_lower = part.lower()
    if part_lower != part and part.upper() != part:
        return list({c for c in part if c != c.lower() and c != c.upper()})
    return [ch for ch in part.lower() if ch not in BECH32_ALPHABET]


def detect_address_type(prefix: str, *, testnet: bool = False) -> AddressType | None:
    if not prefix:
        return None
    p = prefix.lower()
    if testnet:
        if p.startswith("tb1") or p.startswith("bcrt1"):
            return "p2wpkh"
        if p.startswith(("2", "m", "n")):
            return "p2pkh" if p[0] in "mn" else "p2sh"
        return None
    if p.startswith("bc1"):
        return "p2wpkh"
    if p.startswith("3"):
        return "p2sh"
    if p.startswith("1"):
        return "p2pkh"
    return None


def validate_pattern(
    prefix: str,
    suffix: str,
    *,
    address_type: AddressType | None = None,
    testnet: bool = False,
) -> None:
    addr_type = address_type or detect_address_type(prefix, testnet=testnet) or "p2pkh"
    if addr_type == "p2wpkh":
        hrp = _hrp(testnet)
        for part in (prefix, suffix):
            if not part:
                continue
            body = _strip_bech32_hrp(part, hrp)
            bad = invalid_bech32_chars(body)
            if bad:
                raise ValueError(
                    f"Invalid Bech32 character(s): {', '.join(sorted(set(bad)))}. "
                    f"Allowed: {BECH32_ALPHABET}"
                )
        return

    bad = set(invalid_base58_chars(prefix) + invalid_base58_chars(suffix))
    if bad:
        raise ValueError(
            f"Invalid Base58 character(s): {', '.join(sorted(bad))}. "
            "Base58 excludes 0, O, I, l."
        )


def _compressed_pubkey(priv_bytes: bytes) -> bytes:
    return secp.pubkey_compressed(priv_bytes)


def _pubkey_hash(priv_bytes: bytes) -> bytes:
    return _ripemd160(hashlib.sha256(_compressed_pubkey(priv_bytes)).digest())


def privkey_to_p2pkh(priv_bytes: bytes, *, testnet: bool = False) -> str:
    version = _TESTNET_P2PKH if testnet else _MAINNET_P2PKH
    return _base58check(version, _pubkey_hash(priv_bytes))


def privkey_to_p2sh_p2wpkh(priv_bytes: bytes, *, testnet: bool = False) -> str:
    """P2SH-P2WPKH nested SegWit (mainnet addresses start with 3)."""
    pubkey_hash = _pubkey_hash(priv_bytes)
    redeem_script = bytes([0x00, 0x14]) + pubkey_hash
    script_hash = _ripemd160(redeem_script)
    version = _TESTNET_P2SH if testnet else _MAINNET_P2SH
    return _base58check(version, script_hash)


def _strip_bech32_hrp(part: str, hrp: str) -> str:
    pl = part.lower()
    marker = f"{hrp.lower()}1"
    if pl.startswith(marker):
        return pl[len(marker) :]
    if pl.startswith(hrp.lower()):
        return pl[len(hrp) :]
    return pl


def privkey_to_p2wpkh(priv_bytes: bytes, *, testnet: bool = False) -> str:
    """Native SegWit v0 P2WPKH (mainnet bc1q…)."""
    pubkey_hash = _pubkey_hash(priv_bytes)
    hrp = _hrp(testnet)
    encoded = bech32_segwit_encode(hrp, 0, pubkey_hash)
    if encoded is None:
        raise ValueError("Failed to encode Bech32 address")
    return encoded


def privkey_to_address(
    priv_bytes: bytes,
    address_type: AddressType,
    *,
    testnet: bool = False,
) -> str:
    if address_type == "p2pkh":
        return privkey_to_p2pkh(priv_bytes, testnet=testnet)
    if address_type == "p2sh":
        return privkey_to_p2sh_p2wpkh(priv_bytes, testnet=testnet)
    return privkey_to_p2wpkh(priv_bytes, testnet=testnet)


def privkey_to_wif(priv_bytes: bytes, *, testnet: bool = False, compressed: bool = True) -> str:
    payload = bytes([_WIF_TESTNET if testnet else _WIF_MAINNET]) + priv_bytes
    if compressed:
        payload += b"\x01"
    return base58.b58encode(payload + _double_sha256(payload)[:4]).decode("ascii")


def matches_vanity(addr: str, prefix: str, suffix: str) -> bool:
    if prefix.lower().startswith(("bc1", "tb1")) or suffix.lower().startswith(("bc1", "tb1")):
        addr, prefix, suffix = addr.lower(), prefix.lower(), suffix.lower()
    return addr.startswith(prefix) and addr.endswith(suffix)


def try_match_privkey(
    priv_bytes: bytes,
    prefix: str,
    suffix: str,
    *,
    address_type: AddressType,
    testnet: bool = False,
) -> str | None:
    try:
        addr = privkey_to_address(priv_bytes, address_type, testnet=testnet)
    except Exception:
        return None
    return addr if matches_vanity(addr, prefix, suffix) else None


def estimate_difficulty(
    prefix: str,
    suffix: str,
    *,
    address_type: AddressType | None = None,
    testnet: bool = False,
) -> DifficultyEstimate:
    addr_type = address_type or detect_address_type(prefix, testnet=testnet) or "p2pkh"
    charset = BECH32_CHARSET_SIZE if addr_type == "p2wpkh" else BASE58_CHARSET_SIZE

    if addr_type == "p2wpkh":
        hrp = _hrp(testnet)
        prefix_body = _strip_bech32_hrp(prefix, hrp)
        suffix_body = _strip_bech32_hrp(suffix, hrp)
    else:
        prefix_body = prefix
        suffix_body = suffix

    prefix_len = len(prefix_body)
    suffix_len = len(suffix_body)
    overlap = prefix_len + suffix_len > 0 and prefix.endswith(suffix) and suffix_len > 0
    constrained = prefix_len + suffix_len
    expected = float(charset**constrained) if constrained else 1.0
    return DifficultyEstimate(
        prefix_chars=prefix_len,
        suffix_chars=suffix_len,
        constrained_chars=constrained,
        expected_attempts=expected,
        overlap_warning=overlap and len(prefix) > len(suffix),
        charset_size=charset,
    )


def random_privkey_from_entropy(strength_bits: int) -> bytes:
    if strength_bits not in ALLOWED_STRENGTHS:
        raise ValueError("Invalid strength_bits")
    nbytes = strength_bits // 8
    while True:
        raw = os.urandom(nbytes)
        if len(raw) != 32:
            raw = hashlib.sha256(raw).digest()
        priv_int = int.from_bytes(raw, "big")
        if 1 <= priv_int < _CURVE_ORDER:
            return raw


def mnemonic_to_privkey(strength_bits: int, derivation_path: str) -> tuple[bytes, str]:
    entropy_bytes = os.urandom(strength_bits // 8)
    words = _MNEMO.to_mnemonic(entropy_bytes)
    seed = _MNEMO.to_seed(words)
    bip32 = BIP32.from_seed(seed)
    return bip32.get_privkey_from_path(parse_path(derivation_path)), words


def generate_keys_batch(
    batch_size: int,
    strength_bits: int,
    *,
    mnemonic: bool = False,
    derivation_path: str = "m/44'/0'/0'/0/0",
) -> tuple[list[bytes], list[str] | None]:
    if mnemonic:
        keys: list[bytes] = []
        mnemonics: list[str] = []
        for _ in range(batch_size):
            privkey, words = mnemonic_to_privkey(strength_bits, derivation_path)
            keys.append(privkey)
            mnemonics.append(words)
        return keys, mnemonics
    return [random_privkey_from_entropy(strength_bits) for _ in range(batch_size)], None


def check_key_indexed(
    item: tuple[int, bytes, str, str, AddressType, bool],
) -> tuple[int, str | None]:
    idx, priv_bytes, prefix, suffix, address_type, testnet = item
    return idx, try_match_privkey(
        priv_bytes, prefix, suffix, address_type=address_type, testnet=testnet
    )


def make_matcher(
    prefix: str,
    suffix: str,
    *,
    address_type: AddressType,
    testnet: bool = False,
) -> Callable[[bytes], str | None]:
    """Picklable `priv -> address or None` for the search engine."""
    return partial(
        try_match_privkey, prefix=prefix, suffix=suffix, address_type=address_type, testnet=testnet
    )
