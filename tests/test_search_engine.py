import os
import unittest

import ecdsa
from mnemonic import Mnemonic

import secp
from bip32_pure import BIP32, parse_path
from bitcoin_address import make_matcher, privkey_to_address
from search_engine import Job, SearchEngine

# BIP39 test phrase and the reference addresses from BIP44 / BIP84 test vectors.
_PHRASE = "abandon " * 11 + "about"
_P2PKH = ("m/44'/0'/0'/0/0", "1LqBGSKuX5yYUonjxT5qGfpUsXKYYWeabA")
_P2WPKH = ("m/84'/0'/0'/0/0", "bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu")


def _from_phrase(words: str, path: str) -> bytes:
    return BIP32.from_seed(Mnemonic("english").to_seed(words)).get_privkey_from_path(parse_path(path))


class TestCurve(unittest.TestCase):
    def test_backend_matches_python_ecdsa(self):
        for _ in range(50):
            priv = os.urandom(32)
            raw = ecdsa.SigningKey.from_string(priv, curve=ecdsa.SECP256k1).get_verifying_key().to_string()
            compressed = (b"\x02" if raw[-1] % 2 == 0 else b"\x03") + raw[:32]
            self.assertEqual(secp.pubkey_compressed(priv), compressed)


class TestDerivation(unittest.TestCase):
    def test_known_phrase(self):
        self.assertEqual(privkey_to_address(_from_phrase(_PHRASE, _P2PKH[0]), "p2pkh"), _P2PKH[1])
        self.assertEqual(privkey_to_address(_from_phrase(_PHRASE, _P2WPKH[0]), "p2wpkh"), _P2WPKH[1])

    def test_index_scanner_equals_full_derivation(self):
        root = BIP32.from_seed(Mnemonic("english").to_seed(_PHRASE))
        scanner = root.derive(parse_path("m/84'/0'/0'/0")).index_scanner()
        for i in (0, 1, 5, 1000):
            self.assertEqual(scanner.child(i), _from_phrase(_PHRASE, f"m/84'/0'/0'/0/{i}"))


class TestEngine(unittest.TestCase):
    def _run(self, mode: str, path: str) -> dict:
        job = Job(matcher=make_matcher("bc1qq", "", address_type="p2wpkh"), mode=mode, path=path, report_every=50)
        with SearchEngine(job, 2) as engine:
            for _ in range(600):
                rec = engine.next_match(timeout=0.1)
                if rec:
                    return rec
        self.fail(f"no match in mode {mode}")

    def test_key_mode(self):
        rec = self._run("key", "")
        self.assertTrue(rec["address"].startswith("bc1qq"))
        self.assertEqual(privkey_to_address(bytes.fromhex(rec["private_key"]), "p2wpkh"), rec["address"])

    def test_index_mode_is_recoverable_from_phrase(self):
        rec = self._run("index", _P2WPKH[0])
        priv = _from_phrase(rec["mnemonic"], rec["path"])
        self.assertEqual(privkey_to_address(priv, "p2wpkh"), rec["address"])


if __name__ == "__main__":
    unittest.main()
