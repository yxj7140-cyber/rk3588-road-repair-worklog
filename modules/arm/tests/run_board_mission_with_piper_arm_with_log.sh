#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p logs

if [[ ! -f ./piper_can_interface.env ]]; then
    echo "No piper_can_interface.env found; running check_board_can.sh first."
    bash ./check_board_can.sh
fi

source ./piper_can_interface.env

if [[ ! -d ./mission_runtime ]]; then
    echo "Missing ./mission_runtime. Deploy Road_Repair mission runtime first."
    exit 2
fi

ts="$(date +%Y%m%d_%H%M%S)"
log="logs/mission_with_piper_arm_${ts}.log"

echo "Log: $log"
PYTHONPATH="$PWD:$PWD/mission_runtime" \
python3 run_road_repair_mission_with_piper_arm.py \
    --interface socketcan \
    --channel "$PIPER_CAN" \
    --bitrate "$PIPER_CAN_BITRATE" \
    "$@" | tee "$log"
