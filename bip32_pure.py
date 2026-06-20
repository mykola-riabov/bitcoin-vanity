"""Minimal pure-Python BIP32 (secp256k1) for mnemonic derivation."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

import ecdsa
from ecdsa import SECP256k1

_CURVE = SECP256k1
_CURVE_ORDER = _CURVE.order


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


def _point(privkey: bytes) -> bytes:
    sk = ecdsa.SigningKey.from_string(privkey, curve=_CURVE)
    vk = sk.get_verifying_key()
    pub_raw = vk.to_string()
    return (b"\x02" + pub_raw[:32]) if (pub_raw[-1] % 2 == 0) else (b"\x03" + pub_raw[:32])


def from_seed(seed: bytes) -> "BIP32":
    digest = _hmac_sha512(b"Bitcoin seed", seed)
    return BIP32(_Node(digest[:32], digest[32:]))


class BIP32:
    def __init__(self, node: _Node) -> None:
        self._node = node

    @classmethod
    def from_seed(cls, seed: bytes) -> "BIP32":
        return from_seed(seed)

    def get_privkey_from_path(self, path: list[int]) -> bytes:
        node = self._node
        for index in path:
            node = _derive_child(node, index)
        priv_int = _parse256(node.privkey)
        if not (1 <= priv_int < _CURVE_ORDER):
            raise ValueError("Invalid derived private key")
        return node.privkey


def _derive_child(node: _Node, index: int) -> _Node:
    hardened = index >= 0x80000000
    if hardened:
        data = b"\x00" + node.privkey + index.to_bytes(4, "big")
    else:
        data = _point(node.privkey) + index.to_bytes(4, "big")

    digest = _hmac_sha512(node.chain_code, data)
    child_int = (_parse256(digest[:32]) + _parse256(node.privkey)) % _CURVE_ORDER
    if child_int == 0:
        raise ValueError("Invalid child key")
    return _Node(_ser256(child_int), digest[32:])
