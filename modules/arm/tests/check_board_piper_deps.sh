#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "== Python =="
python3 --version

echo "== Piper Python imports =="
python3 - <<'PY'
import importlib
import sys

missing = []
for name in ("can", "pyAgxArm"):
    try:
        mod = importlib.import_module(name)
        print(f"{name}: OK {getattr(mod, '__version__', '')}")
    except Exception as exc:
        print(f"{name}: MISSING {exc}")
        missing.append(name)

if missing:
    sys.exit(1)
PY
