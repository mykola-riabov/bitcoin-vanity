#!/usr/bin/env bash
# Build a self-contained .deb with bundled Python venv, GUI launcher, and CLI tools.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PKG="bitcoin-vanity"
ARCH="all"
VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
MAINTAINER="Mykola Riabov <mykola-riabov@users.noreply.github.com>"

BUILD_DIR="$ROOT/build/deb"
STAGE="$BUILD_DIR/root"
VENV_DIR="$BUILD_DIR/venv"
OUT_DIR="$ROOT/dist"
DEB_FILE="$OUT_DIR/${PKG}_${VERSION}_${ARCH}.deb"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

need python3
need fakeroot
need dpkg-deb

if ! python3 -m venv -h >/dev/null 2>&1; then
  echo "python3-venv is required. Install: sudo apt install python3-venv" >&2
  exit 1
fi

echo "==> Building ${PKG} ${VERSION} (${ARCH})"

rm -rf "$BUILD_DIR"
mkdir -p "$STAGE/usr/lib/$PKG" "$STAGE/usr/bin" "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/icons/hicolor/scalable/apps" "$OUT_DIR"

echo "==> Creating virtualenv and installing Python package"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip wheel >/dev/null
"$VENV_DIR/bin/pip" install "$ROOT" >/dev/null

echo "==> Staging application files"
cp -a "$VENV_DIR" "$STAGE/usr/lib/$PKG/venv"

install -m 755 /dev/stdin "$STAGE/usr/bin/btc-vanity-gui" <<'EOF'
#!/bin/sh
exec /usr/lib/bitcoin-vanity/venv/bin/python3 -m gui "$@"
EOF

install -m 755 /dev/stdin "$STAGE/usr/bin/btc-vanity" <<'EOF'
#!/bin/sh
exec /usr/lib/bitcoin-vanity/venv/bin/btc-vanity "$@"
EOF

install -m 755 /dev/stdin "$STAGE/usr/bin/btc-scan" <<'EOF'
#!/bin/sh
exec /usr/lib/bitcoin-vanity/venv/bin/btc-scan "$@"
EOF

install -m 644 "$ROOT/debian/bitcoin-vanity.desktop" \
  "$STAGE/usr/share/applications/bitcoin-vanity.desktop"
install -m 644 "$ROOT/debian/icons/bitcoin-vanity.svg" \
  "$STAGE/usr/share/icons/hicolor/scalable/apps/bitcoin-vanity.svg"

mkdir -p "$STAGE/DEBIAN"
install -m 644 /dev/stdin "$STAGE/DEBIAN/control" <<EOF
Package: ${PKG}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.10), libxcb-cursor0
Recommends: libsecp256k1-6 | libsecp256k1-2 | libsecp256k1-1 | libsecp256k1-0
Maintainer: ${MAINTAINER}
Homepage: https://github.com/mykola-riabov/bitcoin-vanity
Description: Bitcoin vanity address generator (CPU)
 GUI and CLI for generating custom Bitcoin addresses
 (P2PKH, P2SH-P2WPKH, native SegWit).
 .
 Installed commands:
  - btc-vanity-gui  desktop GUI
  - btc-vanity      CLI generator
  - btc-scan        balance scanner for generated wallets
EOF

install -m 755 /dev/stdin "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
EOF

install -m 755 /dev/stdin "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
  fi
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
  fi
fi
EOF

echo "==> Building .deb package"
fakeroot dpkg-deb --root-owner-group -Zgzip -b "$STAGE" "$DEB_FILE"

echo
echo "Done: $DEB_FILE"
echo "Install: sudo apt install ./dist/${PKG}_${VERSION}_${ARCH}.deb"
echo "Launch GUI: btc-vanity-gui"
