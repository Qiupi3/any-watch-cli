#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# Detect hatch binary
HATCH_BIN=""
if command -v hatch >/dev/null 2>&1; then
    HATCH_BIN="hatch"
elif [ -f "$ROOT_DIR/.venv/bin/hatch" ]; then
    HATCH_BIN="$ROOT_DIR/.venv/bin/hatch"
else
    echo "[!] 'hatch' not found. Installing hatch..."
    pip install hatch >/dev/null 2>&1 || uv pip install hatch >/dev/null 2>&1
    HATCH_BIN="hatch"
fi

mkdir -p "$ROOT_DIR/release"
rm -f "$ROOT_DIR/release/"*.whl

echo "=== Building any-watch-cli packages ==="
for pkg in any-watch-core any-watch-flix any-watch-anime any-watch-drama any-watch; do
    echo "[+] Building $pkg..."
    (cd "$ROOT_DIR/packages/$pkg" && rm -rf dist && "$HATCH_BIN" build --target wheel > /dev/null && mv dist/*.whl "$ROOT_DIR/release/")
done

echo ""
echo "[✓] Successfully built wheels in release/:"
ls -lh "$ROOT_DIR/release"
