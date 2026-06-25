#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PKG_DIR="./offline_pkgs"
if [[ ! -d "$PKG_DIR" ]]; then
    echo "Missing $PKG_DIR. Upload offline packages first."
    exit 2
fi

echo "== Python =="
python3 --version

echo "== Offline package files =="
ls -lh "$PKG_DIR"

echo "== Install wheels without internet =="
python3 -m pip install --user --no-index --find-links "$PKG_DIR" \
    "typing_extensions==4.13.2" \
    "wrapt==1.17.3" \
    "packaging==25.0" \
    "msgpack==1.1.1" \
    "python-can==4.5.0"

echo "== Install pyAgxArm from local source zip =="
python3 -m pip install --user --no-index --find-links "$PKG_DIR" \
    --no-build-isolation \
    --no-deps \
    "$PKG_DIR/pyAgxArm-master.zip"

echo "== Verify imports =="
bash ./check_board_piper_deps.sh
