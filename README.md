# bitcoin-vanity

CPU vanity address generator for **Bitcoin** with desktop GUI and balance scanner.

| Type | Mainnet prefix | BIP path (mnemonic) |
|------|----------------|---------------------|
| P2PKH (legacy) | `1…` | `m/44'/0'/0'/0/0` |
| P2SH-P2WPKH (nested SegWit) | `3…` | `m/49'/0'/0'/0/0` |
| Native SegWit (P2WPKH) | `bc1…` | `m/84'/0'/0'/0/0` |

## Install

```bash
cd bitcoin-vanity
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Debian package

```bash
./scripts/build-deb.sh
sudo apt install ./dist/bitcoin-vanity_*.deb
```

Installed commands: `btc-vanity-gui`, `btc-vanity`, `btc-scan`

## GUI

```bash
btc-vanity-gui
```

Two pages:

- **Generator** — vanity search with themes, bulk mode, per-file rotation
- **Balance Scanner** — checks generated wallets via [Blockstream Esplora](https://blockstream.info)

### Workspace folder

Choose one **workspace** in the sidebar (saved between sessions). Everything lives under it:

```
~/bitcoin-vanity/          ← default workspace (change via Choose…)
├── generated/             ← generator output (*.jsonl)
│   └── btc_addrs.jsonl
├── found_wallets/         ← scanner: addresses with balance
└── checked_cache.json     ← scanner resume cache
```

Generator and scanner paths stay in sync — no separate file pickers.

## CLI

```bash
# P2PKH — address starting with 1Love…
btc-vanity --prefix 1Love --count 1

# P2SH nested SegWit — addresses starting with 3…
btc-vanity --address-type p2sh --prefix 3Hello --count 1

# Native SegWit — bc1q…
btc-vanity --address-type p2wpkh --prefix bc1q --count 1

# Multiprocessing + split 500k addresses per file
btc-vanity --prefix 1 --suffix x --count 1000000 --per-file 500000 --pool --pool-workers 4

# Scan balances (Blockstream API)
btc-scan
INPUT_GLOB=~/btc_addrs*.jsonl btc-scan
```

## Output

JSONL records (one object per line):

```json
{"address": "bc1q…", "address_type": "p2wpkh", "private_key": "…hex…", "wif": "K…"}
```

Use `--no-private-key` for address-only output.

## Difficulty

- **Base58** (`1…`, `3…`): each extra character × ~58
- **Bech32** (`bc1…`): each extra character × ~32 (after the `bc1` HRP)

## Scope

- CPU only — for long patterns consider [VanitySearch](https://github.com/JeanLucPons/VanitySearch) (GPU)
- Taproot `bc1p…` not supported yet

## License

MIT
