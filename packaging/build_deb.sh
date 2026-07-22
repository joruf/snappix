#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
BUILD_DIR="$PROJECT_ROOT/.build/deb"
STAGING_DIR="$BUILD_DIR/staging"
PKG_NAME="snappix"
PKG_VERSION="${1:-0.1.0}"
ARCH="$(dpkg --print-architecture)"

echo "[snappix] Preparing Debian package build directories..."
rm -rf "$BUILD_DIR"
mkdir -p "$STAGING_DIR/DEBIAN"
mkdir -p "$STAGING_DIR/opt/$PKG_NAME"
mkdir -p "$STAGING_DIR/usr/bin"
mkdir -p "$STAGING_DIR/usr/share/applications"
mkdir -p "$STAGING_DIR/usr/share/icons/hicolor/scalable/apps"

echo "[snappix] Copying application files..."
rsync -a \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude ".build" \
  --exclude "dist" \
  --exclude "__pycache__" \
  "$PROJECT_ROOT/" "$STAGING_DIR/opt/$PKG_NAME/"

cat > "$STAGING_DIR/usr/bin/snappix" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec python3 /opt/snappix/run.py "$@"
EOF
chmod 0755 "$STAGING_DIR/usr/bin/snappix"

cat > "$STAGING_DIR/usr/share/applications/snappix.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Snappix
Comment=Screenshot and annotation tool
Exec=snappix
Icon=snappix
Terminal=false
Categories=Graphics;Utility;
StartupWMClass=snappix
EOF

cp "$PROJECT_ROOT/assets/snappix.svg" "$STAGING_DIR/usr/share/icons/hicolor/scalable/apps/snappix.svg"

cat > "$STAGING_DIR/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $PKG_VERSION
Section: graphics
Priority: optional
Architecture: $ARCH
Maintainer: Joachim Ruf <info@loresoft.de>
Depends: python3, python3-venv, python3-pip, xdotool, x11-utils
Description: Snappix screenshot editor
 Linux screenshot and annotation tool inspired by SnagIt.
EOF

mkdir -p "$DIST_DIR"
OUTPUT_DEB="$DIST_DIR/${PKG_NAME}_${PKG_VERSION}_${ARCH}.deb"
echo "[snappix] Building package: $OUTPUT_DEB"
dpkg-deb --build "$STAGING_DIR" "$OUTPUT_DEB"
echo "[snappix] Done."
