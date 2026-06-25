#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

ALLOW_CAN0="${ALLOW_CAN0:-0}"
PREFER_CAN="${PREFER_CAN:-can1}"
BITRATE="${PIPER_CAN_BITRATE:-1000000}"

echo "== CAN links =="
ip -details link show type can || true

detect_args=(--prefer "$PREFER_CAN" --bitrate "$BITRATE")
if [[ "$ALLOW_CAN0" == "1" ]]; then
    detect_args+=(--allow-can0)
fi

echo "== Detect Piper CAN =="
python3 detect_board_can.py "${detect_args[@]}" --json
source ./piper_can_interface.env

echo "Selected Piper CAN: $PIPER_CAN"
ip -details link show "$PIPER_CAN"

if ip -details link show "$PIPER_CAN" | grep -q "state DOWN"; then
    echo "$PIPER_CAN is DOWN; bringing it up at ${PIPER_CAN_BITRATE} bps."
    sudo ip link set "$PIPER_CAN" down || true
    sudo ip link set "$PIPER_CAN" type can bitrate "$PIPER_CAN_BITRATE"
    sudo ip link set "$PIPER_CAN" up
fi

echo "Piper CAN ready:"
ip -details link show "$PIPER_CAN"

