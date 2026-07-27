#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
BUILD_DIR="$PROJECT_ROOT/.build/appimage"
APPDIR="$BUILD_DIR/Snappix.AppDir"
APP_VERSION="${1:-0.1.0}"

if ! command -v appimagetool >/dev/null 2>&1; then
  echo "appimagetool not found. Install it first."
  exit 1
fi

echo "[snappix] Preparing AppDir..."
rm -rf "$BUILD_DIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/snappix"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"

echo "[snappix] Copying application files..."
rsync -a \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude ".build" \
  --exclude "dist" \
  --exclude "__pycache__" \
  "$PROJECT_ROOT/" "$APPDIR/usr/share/snappix/"

# The AppImage's squashfs is mounted read-only at runtime, so run.py's own
# uv/venv bootstrap (which writes into the project root) cannot work here.
# Bundle the pinned requirements as a vendored PYTHONPATH directory instead,
# so PySide6 et al. are already importable and that bootstrap path is never hit.
echo "[snappix] Vendoring Python dependencies..."
VENDOR_DIR="$APPDIR/usr/share/snappix/vendor"
python3 -m pip install --no-cache-dir --target "$VENDOR_DIR" -r "$PROJECT_ROOT/requirements.txt"

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec "$APPDIR/usr/bin/snappix" "$@"
EOF
chmod 0755 "$APPDIR/AppRun"

cat > "$APPDIR/usr/bin/snappix" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$APPDIR/usr/share/snappix/vendor${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "$APPDIR/usr/share/snappix/run.py" "$@"
EOF
chmod 0755 "$APPDIR/usr/bin/snappix"

cat > "$APPDIR/snappix.desktop" <<'EOF'
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

cp "$APPDIR/snappix.desktop" "$APPDIR/usr/share/applications/snappix.desktop"
cp "$PROJECT_ROOT/assets/snappix-red.svg" "$APPDIR/snappix.svg"
cp "$PROJECT_ROOT/assets/snappix-red.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/snappix.svg"
cp "$PROJECT_ROOT/assets/snappix.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/snappix-editor.svg"

mkdir -p "$DIST_DIR"
OUTPUT_FILE="$DIST_DIR/Snappix-${APP_VERSION}-x86_64.AppImage"
echo "[snappix] Building AppImage: $OUTPUT_FILE"
ARCH=x86_64 appimagetool "$APPDIR" "$OUTPUT_FILE"
echo "[snappix] Done."
