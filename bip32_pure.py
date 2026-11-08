"""Minimal BIP32 (secp256k1) for mnemonic derivation, with a fast path for scanning address indexes."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from secp import CURVE_ORDER, pubkey_compressed

HARDENED_OFFSET = 0x80000000
MAX_NON_HARDENED = HARDENED_OFFSET - 1


@dataclass(frozen=True)
class _Node:
    privkey: bytes
    chain_code: bytes


def _hmac_sha512(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha512).digest()


def _parse256(data: bytes) -> int:
    return int.from_bytes(data, "big")


def _ser256(value: int) -> bytes:
    return value.to_bytes(32, "big")


def parse_path(path: str) -> list[int]:
    """`m/44'/118'/0'/0/0` -> list of child indexes (hardened ones offset by 2^31)."""
    parts = [p for p in path.strip().removeprefix("m").split("/") if p]
    out: list[int] = []
    for p in parts:
        hardened = p.endswith(("'", "h", "H"))
        value = int(p.rstrip("'hH"))
        if not 0 <= value <= MAX_NON_HARDENED:
            raise ValueError(f"Path index out of range: {p}")
        out.append(value + HARDENED_OFFSET if hardened else value)
    return out


def from_seed(seed: bytes) -> "BIP32":
    digest = _hmac_sha512(b"Bitcoin seed", seed)
    return BIP32(_Node(digest[:32], digest[32:]))


class BIP32:
    def __init__(self, node: _Node) -> None:
        self._node = node

    @classmethod
    def from_seed(cls, seed: bytes) -> "BIP32":
        return from_seed(seed)

    def derive(self, path: list[int]) -> "BIP32":
        node = self._node
        for index in path:
            node = _derive_child(node, index)
        return BIP32(node)

    def get_privkey_from_path(self, path: list[int]) -> bytes:
        priv = self.derive(path)._node.privkey
        if not (1 <= _parse256(priv) < CURVE_ORDER):
            raise ValueError("Invalid derived private key")
        return priv

    def index_scanner(self) -> "IndexScanner":
        """Fast non-hardened children of this node: one HMAC and no curve math per index."""
        return IndexScanner(self._node)


class IndexScanner:
    """Children i = 0, 1, 2… of one parent node. The parent public key is computed once."""

    def __init__(self, node: _Node) -> None:
        self._chain_code = node.chain_code
        self._parent_int = _parse256(node.privkey)
        self._parent_pub = pubkey_compressed(node.privkey)

    def child(self, index: int) -> bytes | None:
        """Private key of non-hardened child `index`, or None for the (astronomically rare) invalid one."""
        if not 0 <= index <= MAX_NON_HARDENED:
            raise ValueError("Index must be non-hardened")
        digest = _hmac_sha512(self._chain_code, self._parent_pub + index.to_bytes(4, "big"))
        tweak = _parse256(digest[:32])
        if tweak >= CURVE_ORDER:
            return None
        child_int = (tweak + self._parent_int) % CURVE_ORDER
        return _ser256(child_int) if child_int else None


def _derive_child(node: _Node, index: int) -> _Node:
    hardened = index >= HARDENED_OFFSET
    if hardened:
        data = b"\x00" + node.privkey + index.to_bytes(4, "big")
    else:
        data = pubkey_compressed(node.privkey) + index.to_bytes(4, "big")

    digest = _hmac_sha512(node.chain_code, data)
    tweak = _parse256(digest[:32])
    child_int = (tweak + _parse256(node.privkey)) % CURVE_ORDER
    if tweak >= CURVE_ORDER or child_int == 0:
        raise ValueError("Invalid child key")
    return _Node(_ser256(child_int), digest[32:])
