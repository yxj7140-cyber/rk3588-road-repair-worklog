#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
exec bash ./check_board_can.sh "$@"
