#!/usr/bin/env bash
# Snappix zero-Python launcher for Linux: fetches uv, provisions CPython 3.12,
# installs dependencies, then starts the app.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

RUNTIME_DIR="$ROOT/.snappix-runtime"
UV_DIR="$RUNTIME_DIR/uv"
UV_BIN="$UV_DIR/uv"
UV_VERSION="0.11.32"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) UV_ARCH="x86_64" ;;
  aarch64|arm64) UV_ARCH="aarch64" ;;
  *)
    echo "Snappix: unsupported architecture: $ARCH" >&2
    exit 1
    ;;
esac

UV_ASSET="uv-${UV_ARCH}-unknown-linux-gnu.tar.gz"
UV_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${UV_ASSET}"

if [[ ! -x "$UV_BIN" ]]; then
  echo "Snappix: downloading uv toolchain..."
  mkdir -p "$UV_DIR"
  TMP_ARCHIVE="$(mktemp)"
  TMP_EXTRACT="$(mktemp -d)"
  cleanup() {
    rm -f "$TMP_ARCHIVE"
    rm -rf "$TMP_EXTRACT"
  }
  trap cleanup EXIT
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$UV_URL" -o "$TMP_ARCHIVE"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP_ARCHIVE" "$UV_URL"
  else
    echo "Snappix: need curl or wget to download uv." >&2
    exit 1
  fi
  tar -xzf "$TMP_ARCHIVE" -C "$TMP_EXTRACT"
  FOUND="$(find "$TMP_EXTRACT" -type f -name uv | head -n 1)"
  if [[ -z "$FOUND" ]]; then
    echo "Snappix: uv binary missing in downloaded archive." >&2
    exit 1
  fi
  cp "$FOUND" "$UV_BIN"
  chmod +x "$UV_BIN"
  trap - EXIT
  cleanup
fi

export UV_CACHE_DIR="$RUNTIME_DIR/cache"
export UV_PYTHON_INSTALL_DIR="$RUNTIME_DIR/python"

echo "Snappix: ensuring Python 3.12 runtime..."
"$UV_BIN" python install 3.12

echo "Snappix: running dependency installer..."
"$UV_BIN" run --python 3.12 --no-project python install_dependencies.py

if [[ ! -x "$ROOT/.venv/bin/python" && ! -x "$ROOT/.venv/bin/python3" ]]; then
  echo "Snappix: .venv was not created." >&2
  exit 1
fi

VENV_PYTHON="$ROOT/.venv/bin/python3"
if [[ ! -x "$VENV_PYTHON" ]]; then
  VENV_PYTHON="$ROOT/.venv/bin/python"
fi

echo "Snappix: starting application..."
exec "$VENV_PYTHON" "$ROOT/run.py" "$@"
