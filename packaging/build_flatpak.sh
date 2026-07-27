#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FLATPAK_DIR="$PROJECT_ROOT/packaging/flatpak"
DIST_DIR="$PROJECT_ROOT/dist"
BUILD_DIR="$PROJECT_ROOT/.build/flatpak"
APP_ID="io.github.joruf.Snappix"
RUNTIME_VERSION="6.9"
APP_VERSION="${1:-0.1.0}"

if ! command -v flatpak-builder >/dev/null 2>&1; then
  echo "flatpak-builder not found. Install it first (e.g. apt install flatpak-builder)."
  exit 1
fi

echo "[snappix] Ensuring Flathub remote and KDE runtime/SDK ${RUNTIME_VERSION}..."
flatpak remote-add --if-not-exists --user flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y --noninteractive flathub \
  "org.kde.Platform//${RUNTIME_VERSION}" "org.kde.Sdk//${RUNTIME_VERSION}"

echo "[snappix] Building with flatpak-builder..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
flatpak-builder --user --force-clean \
  --repo="$BUILD_DIR/repo" \
  "$BUILD_DIR/build" \
  "$FLATPAK_DIR/$APP_ID.yml"

mkdir -p "$DIST_DIR"
OUTPUT_FILE="$DIST_DIR/Snappix-${APP_VERSION}-x86_64.flatpak"
echo "[snappix] Building single-file bundle: $OUTPUT_FILE"
flatpak build-bundle "$BUILD_DIR/repo" "$OUTPUT_FILE" "$APP_ID"
echo "[snappix] Done."
