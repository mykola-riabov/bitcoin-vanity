"""Tests for Bitcoin address derivation."""

import ecdsa

from bitcoin_address import (
    ADDRESS_TYPES,
    detect_address_type,
    estimate_difficulty,
    privkey_to_address,
    privkey_to_p2pkh,
    privkey_to_p2sh_p2wpkh,
    privkey_to_p2wpkh,
    privkey_to_wif,
    try_match_privkey,
    validate_pattern,
)


def test_known_p2pkh_vector() -> None:
    priv_hex = "e9873d79c6d87dc0fb6a5778635280c7c4fc6f5efb762a7f5b73aab822614547"
    priv = bytes.fromhex(priv_hex)
    assert privkey_to_p2pkh(priv) == "14wBKZ5xbXq84vspSpS1toFqRWEwAHdpkE"
    assert privkey_to_wif(priv) == "L53fCHmQhbNp1B4JipfEiPbpkL9SUFFJRwarEQwBF1tiRkhjTz6W"


def test_p2sh_and_p2wpkh_from_same_key() -> None:
    priv_hex = "e9873d79c6d87dc0fb6a5778635280c7c4fc6f5efb762a7f5b73aab822614547"
    priv = bytes.fromhex(priv_hex)
    p2sh = privkey_to_p2sh_p2wpkh(priv)
    p2wpkh = privkey_to_p2wpkh(priv)
    assert p2sh.startswith("3")
    assert p2wpkh.startswith("bc1q")
    assert len(p2sh) >= 34
    assert len(p2wpkh) >= 42


def test_bip84_mnemonic_vector() -> None:
    from bip32_pure import BIP32
    from mnemonic import Mnemonic

    words = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    seed = Mnemonic("english").to_seed(words)
    bip32 = BIP32.from_seed(seed)
    priv84 = bip32.get_privkey_from_path(
        [84 + 0x80000000, 0 + 0x80000000, 0 + 0x80000000, 0, 0]
    )
    assert privkey_to_p2wpkh(priv84) == "bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu"


def test_detect_address_type() -> None:
    assert detect_address_type("1Love") == "p2pkh"
    assert detect_address_type("3Hello") == "p2sh"
    assert detect_address_type("bc1q") == "p2wpkh"
    assert detect_address_type("tb1q", testnet=True) == "p2wpkh"


def test_validate_rejects_invalid_base58() -> None:
    try:
        validate_pattern("1Oops", "", address_type="p2pkh")
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "Base58" in str(e)


def test_try_match_prefix() -> None:
    priv_hex = "e9873d79c6d87dc0fb6a5778635280c7c4fc6f5efb762a7f5b73aab822614547"
    priv = bytes.fromhex(priv_hex)
    addr = privkey_to_p2pkh(priv)
    assert try_match_privkey(priv, addr[:4], "", address_type="p2pkh") == addr


def test_estimate_difficulty_bech32() -> None:
    d = estimate_difficulty("bc1q", "", address_type="p2wpkh")
    assert d.charset_size == 32
    assert d.expected_attempts == 32**1


def test_random_key_on_curve() -> None:
    from bitcoin_address import random_privkey_from_entropy

    priv = random_privkey_from_entropy(256)
    assert len(priv) == 32
    n = int.from_bytes(priv, "big")
    assert 1 <= n < ecdsa.SECP256k1.order
    for t in ADDRESS_TYPES:
        addr = privkey_to_address(priv, t)
        assert addr
