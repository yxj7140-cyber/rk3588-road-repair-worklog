#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "== Python =="
python3 --version

echo "== Install board Piper dependencies =="
python3 -m pip install --user --upgrade pip
python3 -m pip install --user -r requirements-board.txt

echo "== Verify imports =="
python3 - <<'PY'
import importlib

for name in ("can", "pyAgxArm"):
    try:
        mod = importlib.import_module(name)
        print(f"{name}: OK {getattr(mod, '__version__', '')}")
    except Exception as exc:
        raise SystemExit(f"{name}: MISSING {exc}")
PY

echo "Board Piper environment OK."
