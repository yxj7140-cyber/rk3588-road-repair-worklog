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
log="logs/piper_micro_motion_${PIPER_CAN}_${ts}.log"

echo "Log: $log"
python3 run_piper_micro_motion.py \
    --interface socketcan \
    --channel "$PIPER_CAN" \
    --bitrate "$PIPER_CAN_BITRATE" \
    "$@" | tee "$log"
