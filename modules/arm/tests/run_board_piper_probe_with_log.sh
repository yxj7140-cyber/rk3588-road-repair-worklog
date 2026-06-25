#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p logs

if [[ ! -f ./piper_can_interface.env ]]; then
    echo "No piper_can_interface.env found; running check_board_can.sh first."
    bash ./check_board_can.sh
fi

source ./piper_can_interface.env

ts="$(date +%Y%m%d_%H%M%S)"
log="logs/piper_probe_${PIPER_CAN}_${ts}.json"

echo "Log: $log"
python3 run_piper_probe.py \
    --interface socketcan \
    --channel "$PIPER_CAN" \
    --bitrate "$PIPER_CAN_BITRATE" \
    --json | tee "$log"
