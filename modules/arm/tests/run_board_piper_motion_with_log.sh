#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p logs

PROFILE="${1:-safe_home}"
MODE="${2:-dryrun}"
REQUIRE_CURRENT_CLOSE_RAD="${3:-}"

if [[ ! -f ./piper_can_interface.env ]]; then
    echo "No piper_can_interface.env found; running check_board_can.sh first."
    bash ./check_board_can.sh
fi

source ./piper_can_interface.env

ts="$(date +%Y%m%d_%H%M%S)"
log="logs/piper_motion_${PIPER_CAN}_${PROFILE}_${MODE}_${ts}.log"

args=(
    run_piper_safe_motion.py
    --interface socketcan
    --channel "$PIPER_CAN"
    --bitrate "$PIPER_CAN_BITRATE"
    --profile "$PROFILE"
)

if [[ "$MODE" == "execute" ]]; then
    args+=(--execute --snapshot-after)
    if [[ -n "$REQUIRE_CURRENT_CLOSE_RAD" ]]; then
        args+=(--require-current-close-rad "$REQUIRE_CURRENT_CLOSE_RAD")
    fi
else
    echo "Dry-run mode. Pass second arg 'execute' only after the arm workspace is clear."
fi

echo "Log: $log"
python3 "${args[@]}" | tee "$log"
