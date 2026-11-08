"""secp256k1 public keys through the system libsecp256k1 (ctypes), with a pure-Python fallback.

libsecp256k1 is the library Bitcoin Core uses; it is tens of times faster than the pure-Python
`ecdsa` package. When the shared library is missing, the module falls back to `ecdsa` so the
program still works, only slower. `BACKEND` tells which one is in use.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os

import ecdsa

CURVE_ORDER = ecdsa.SECP256k1.order

# Library names tried in order: whatever the linker finds, then the sonames of known Ubuntu/Debian releases.
_LIBRARY_NAMES = ("secp256k1",)
_SONAMES = ("libsecp256k1.so.6", "libsecp256k1.so.2", "libsecp256k1.so.1", "libsecp256k1.so.0")
_ENV_LIBRARY = "SECP256K1_LIBRARY"
_ENV_DISABLE = "SECP256K1_DISABLE"

_CONTEXT_NONE = 1  # SECP256K1_FLAGS_TYPE_CONTEXT
_EC_COMPRESSED = (1 << 1) | (1 << 8)
_EC_UNCOMPRESSED = 1 << 1


def _load() -> ctypes.CDLL | None:
    if os.environ.get(_ENV_DISABLE):
        return None
    names = [os.environ[_ENV_LIBRARY]] if os.environ.get(_ENV_LIBRARY) else []
    names += [ctypes.util.find_library(n) for n in _LIBRARY_NAMES]
    names += list(_SONAMES)
    for name in names:
        if not name:
            continue
        try:
            lib = ctypes.CDLL(name)
        except OSError:
            continue
        lib.secp256k1_context_create.restype = ctypes.c_void_p
        lib.secp256k1_context_create.argtypes = [ctypes.c_uint]
        lib.secp256k1_context_randomize.restype = ctypes.c_int
        lib.secp256k1_context_randomize.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.secp256k1_ec_pubkey_create.restype = ctypes.c_int
        lib.secp256k1_ec_pubkey_create.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        lib.secp256k1_ec_pubkey_serialize.restype = ctypes.c_int
        lib.secp256k1_ec_pubkey_serialize.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        return lib
    return None


_LIB = _load()
_CTX = None
if _LIB is not None:
    _CTX = _LIB.secp256k1_context_create(_CONTEXT_NONE)
    _LIB.secp256k1_context_randomize(_CTX, os.urandom(32))

BACKEND = "libsecp256k1" if _LIB is not None else "python-ecdsa"


def rerandomize() -> None:
    """Fresh side-channel blinding for this process (call once in each forked worker)."""
    if _LIB is not None:
        _LIB.secp256k1_context_randomize(_CTX, os.urandom(32))


def _pubkey_lib(priv: bytes, flags: int, size: int) -> bytes:
    raw = ctypes.create_string_buffer(64)
    if len(priv) != 32 or not _LIB.secp256k1_ec_pubkey_create(_CTX, raw, priv):
        raise ValueError("Invalid secp256k1 private key")
    out = ctypes.create_string_buffer(size)
    out_len = ctypes.c_size_t(size)
    _LIB.secp256k1_ec_pubkey_serialize(_CTX, out, ctypes.byref(out_len), raw, flags)
    return out.raw[: out_len.value]


def _pubkey_py(priv: bytes) -> bytes:
    sk = ecdsa.SigningKey.from_string(priv, curve=ecdsa.SECP256k1)
    return sk.get_verifying_key().to_string()


def pubkey_compressed(priv: bytes) -> bytes:
    """33-byte SEC1 compressed public key."""
    if _LIB is not None:
        return _pubkey_lib(priv, _EC_COMPRESSED, 33)
    raw = _pubkey_py(priv)
    return (b"\x02" if raw[-1] % 2 == 0 else b"\x03") + raw[:32]


def pubkey_xy(priv: bytes) -> bytes:
    """64-byte uncompressed public key without the 0x04 marker (X || Y)."""
    if _LIB is not None:
        return _pubkey_lib(priv, _EC_UNCOMPRESSED, 65)[1:]
    return _pubkey_py(priv)
