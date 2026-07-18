#!/usr/bin/env bash
set -euo pipefail

APP_NAME="winvclipboard"
DISPLAY_NAME="WinV Clipboard"
VERSION="${VERSION:-0.1.1}"
MAINTAINER="${MAINTAINER:-Luthi <github.com/FORDDIVEN>}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCH="$(dpkg --print-architecture)"
PACKAGE_DIR="$(mktemp -d)"
PACKAGE_ROOT="$PACKAGE_DIR/${APP_NAME}_${VERSION}_${ARCH}"
OUTPUT="$ROOT_DIR/dist/${APP_NAME}_${VERSION}_${ARCH}.deb"

BIN_SOURCE="$ROOT_DIR/dist/$APP_NAME"
ICON_SOURCE="$ROOT_DIR/winvlogo.png"
DESKTOP_SOURCE="$ROOT_DIR/packaging/$APP_NAME.desktop"

if [[ ! -x "$BIN_SOURCE" ]]; then
    echo "Missing executable: $BIN_SOURCE" >&2
    echo "Build it first with: pyinstaller --noconfirm --onefile --windowed --name $APP_NAME main.py" >&2
    exit 1
fi

if [[ ! -f "$ICON_SOURCE" ]]; then
    echo "Missing icon: $ICON_SOURCE" >&2
    exit 1
fi

install -Dm755 "$BIN_SOURCE" "$PACKAGE_ROOT/usr/bin/$APP_NAME"
install -Dm644 "$DESKTOP_SOURCE" "$PACKAGE_ROOT/usr/share/applications/$APP_NAME.desktop"
install -Dm644 "$ICON_SOURCE" "$PACKAGE_ROOT/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png"

mkdir -p "$PACKAGE_ROOT/DEBIAN"
cat > "$PACKAGE_ROOT/DEBIAN/control" <<CONTROL
Package: $APP_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: $MAINTAINER
Depends: libc6, libx11-6, libxtst6
Description: Historial de portapapeles estilo Win+V para Linux
 $DISPLAY_NAME guarda textos e imagenes recientes del portapapeles
 y permite recuperarlos desde una ventana compacta.
CONTROL

dpkg-deb --build --root-owner-group "$PACKAGE_ROOT" "$OUTPUT"
echo "$OUTPUT"
