#!/usr/bin/env bash
set -euo pipefail

SUDO_PASSWORD="${SUDO_PASSWORD:-rock}"
LOG_PREFIX="${LOG_PREFIX:-road_repair_chassis_task_test}"
RT_IP="${RT_IP:-10.10.10.30}"
RT_IFACE="${RT_IFACE:-enp255s5}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-${SCRIPT_DIR}}"
LOG_DIR="${LOG_DIR:-${APP_DIR}/logs}"

LX=127
LY=127
RX=127
LT=0
RT=0
DURATION=0.4
GATEWAY_SECONDS=10
CURRENT_LIMIT=1200
ENABLE_CURRENT=0
DISCONNECTED=0
NOT_XBOX360=0
DRY_RUN=0

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --lx N               Road_Repair gamepad LX byte, default 127
  --ly N               Road_Repair gamepad LY byte, default 127
  --rx N               Road_Repair gamepad RX byte, default 127
  --lt N               Road_Repair gamepad LT byte, default 0
  --rt N               Road_Repair gamepad RT byte, default 0
  --duration SEC
  --current-limit N    RT-side current clamp, default 1200
  --gateway-seconds SEC
  --log-prefix NAME
  --disconnected       Simulate missing gamepad; should command stop
  --not-xbox360        Simulate unsupported gamepad; should command stop
  --dry-run            Preview converted axes/rpm only. Does not start CAN gateway.
  --enable-current

Default mode is safe-lock: gateway logs RT requests but sends zero current.
--enable-current adds the two explicit dangerous-test switches to the gateway.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --lx)
            LX="$2"; shift 2 ;;
        --ly)
            LY="$2"; shift 2 ;;
        --rx)
            RX="$2"; shift 2 ;;
        --lt)
            LT="$2"; shift 2 ;;
        --rt)
            RT="$2"; shift 2 ;;
        --duration)
            DURATION="$2"; shift 2 ;;
        --current-limit)
            CURRENT_LIMIT="$2"; shift 2 ;;
        --gateway-seconds)
            GATEWAY_SECONDS="$2"; shift 2 ;;
        --log-prefix)
            LOG_PREFIX="$2"; shift 2 ;;
        --disconnected)
            DISCONNECTED=1; shift ;;
        --not-xbox360)
            NOT_XBOX360=1; shift ;;
        --dry-run)
            DRY_RUN=1; shift ;;
        --enable-current)
            ENABLE_CURRENT=1; shift ;;
        -h|--help)
            usage; exit 0 ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage >&2
            exit 2 ;;
    esac
done

sudo_if_needed() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif sudo -n true 2>/dev/null; then
        sudo "$@"
    else
        printf '%s\n' "${SUDO_PASSWORD}" | sudo -S "$@"
    fi
}

mkdir -p "${LOG_DIR}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/${LOG_PREFIX}_${STAMP}.log"

cleanup() {
    set +e
    sudo_if_needed systemctl stop can-gateway.service >/dev/null 2>&1
    sudo_if_needed pkill -f '[c]an_gateway_service.py' >/dev/null 2>&1
    sudo_if_needed ip link set can0 down >/dev/null 2>&1
}
trap cleanup EXIT INT TERM

cleanup

GATEWAY_ARGS=(
    python3 "${APP_DIR}/can_gateway_service.py"
    --iface can0 --setup-can --no-shm --udp
    --udp-bind 0.0.0.0 --udp-port 15550
    --udp-command-timeout 0.25
    --require-rt-ping "${RT_IP}" --rt-ping-iface "${RT_IFACE}"
    --rt-ping-timeout 20 --require-udp-peer-timeout 20
    --send-before-feedback --log-period 0.2
)

if [ "${ENABLE_CURRENT}" = "1" ]; then
    GATEWAY_ARGS+=(--allow-nonzero-current --i-understand-this-can-move-motors)
fi

TASK_ARGS=(
    python3 "${APP_DIR}/road_repair_chassis_task.py"
    --lx "${LX}" --ly "${LY}" --rx "${RX}" --lt "${LT}" --rt "${RT}"
    --duration "${DURATION}"
    --current-limit "${CURRENT_LIMIT}"
)

if [ "${DISCONNECTED}" = "1" ]; then
    TASK_ARGS+=(--disconnected)
fi
if [ "${NOT_XBOX360}" = "1" ]; then
    TASK_ARGS+=(--not-xbox360)
fi
if [ "${DRY_RUN}" = "1" ]; then
    TASK_ARGS+=(--dry-run)
    echo "== dry-run =="
    echo "app_dir=${APP_DIR}"
    echo "log_dir=${LOG_DIR}"
    "${TASK_ARGS[@]}"
    exit 0
fi

echo "== run =="
echo "log=${LOG}"
echo "mode=$([ "${ENABLE_CURRENT}" = "1" ] && echo current-enabled || echo safe-lock)"
echo "gamepad lx=${LX} ly=${LY} rx=${RX} lt=${LT} rt=${RT} disconnected=${DISCONNECTED} not_xbox360=${NOT_XBOX360}"
echo "duration=${DURATION} current_limit=${CURRENT_LIMIT}"

(
    cd "${APP_DIR}"
    sudo_if_needed timeout "${GATEWAY_SECONDS}s" "${GATEWAY_ARGS[@]}"
) > "${LOG}" 2>&1 &
GW_PID=$!

sleep 3
"${TASK_ARGS[@]}"

wait "${GW_PID}" || true
cleanup

echo "== log tail =="
tail -100 "${LOG}" || true

echo "== final state =="
systemctl is-active can-gateway.service 2>/dev/null || true
pgrep -af can_gateway_service.py || true
ip -details -statistics link show can0 || true
