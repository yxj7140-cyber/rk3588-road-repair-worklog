#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p logs

if [[ ! -f ./piper_can_interface.env ]]; then
    echo "No piper_can_interface.env found; running check_board_can.sh first."
    bash ./check_board_can.sh
fi

source ./piper_can_interface.env

cmd="${1:-status}"
if [[ "$#" -gt 0 ]]; then
    shift
fi

ts="$(date +%Y%m%d_%H%M%S)"
safe_cmd="${cmd//[^A-Za-z0-9_.-]/_}"
log="logs/arm_task_${safe_cmd}_${ts}.log"

echo "Log: $log"
python3 run_road_repair_arm_task.py \
    --interface socketcan \
    --channel "$PIPER_CAN" \
    --bitrate "$PIPER_CAN_BITRATE" \
    "$cmd" "$@" | tee "$log"
