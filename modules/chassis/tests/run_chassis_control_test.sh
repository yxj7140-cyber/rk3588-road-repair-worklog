#!/usr/bin/env bash
set -euo pipefail

SUDO_PASSWORD="${SUDO_PASSWORD:-rock}"
LOG_DIR="${LOG_DIR:-/home/rock/images/logs}"
LOG_PREFIX="${LOG_PREFIX:-chassis_control_test}"
RT_IP="${RT_IP:-10.10.10.30}"
RT_IFACE="${RT_IFACE:-enp255s5}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-${SCRIPT_DIR}}"

FORWARD=0
STRAFE=0
ROTATE=0
DURATION=0.4
PERIOD=0.02
GATEWAY_SECONDS=10
CURRENT_LIMIT=0
ENABLE_CURRENT=0
MAX_SPEED_RPM=""
MAX_ROTATE_RPM=""

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --forward N          Normalized -1.0..1.0, + is forward
  --strafe N           Normalized -1.0..1.0, + is right
  --rotate N           Normalized -1.0..1.0, + is left / counterclockwise
  --duration SEC
  --period SEC
  --current-limit N    RT-side current clamp; 0 keeps RT default
  --max-speed-rpm N    Normalized forward/strafe scale; omitted keeps adapter default
  --max-rotate-rpm N   Normalized rotate scale; omitted keeps adapter default
  --gateway-seconds SEC
  --log-prefix NAME
  --enable-current

Default mode is safe-lock: gateway logs RT requests but sends zero current.
--enable-current adds the two explicit dangerous-test switches to the gateway.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --forward)
            FORWARD="$2"; shift 2 ;;
        --strafe)
            STRAFE="$2"; shift 2 ;;
        --rotate)
            ROTATE="$2"; shift 2 ;;
        --duration)
            DURATION="$2"; shift 2 ;;
        --period)
            PERIOD="$2"; shift 2 ;;
        --current-limit)
            CURRENT_LIMIT="$2"; shift 2 ;;
        --max-speed-rpm)
            MAX_SPEED_RPM="$2"; shift 2 ;;
        --max-rotate-rpm)
            MAX_ROTATE_RPM="$2"; shift 2 ;;
        --gateway-seconds)
            GATEWAY_SECONDS="$2"; shift 2 ;;
        --log-prefix)
            LOG_PREFIX="$2"; shift 2 ;;
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

echo "== run =="
echo "log=${LOG}"
echo "mode=$([ "${ENABLE_CURRENT}" = "1" ] && echo current-enabled || echo safe-lock)"
echo "axis forward=${FORWARD} strafe=${STRAFE} rotate=${ROTATE} duration=${DURATION} period=${PERIOD} current_limit=${CURRENT_LIMIT}"
echo "scale max_speed_rpm=${MAX_SPEED_RPM:-adapter-default} max_rotate_rpm=${MAX_ROTATE_RPM:-adapter-default}"

(
    cd /home/rock/images
    sudo_if_needed timeout "${GATEWAY_SECONDS}s" "${GATEWAY_ARGS[@]}"
) > "${LOG}" 2>&1 &
GW_PID=$!

sleep 3
CLIENT_ARGS=(
    python3 "${APP_DIR}/chassis_control.py"
    --forward "${FORWARD}"
    --strafe "${STRAFE}"
    --rotate "${ROTATE}"
    --duration "${DURATION}"
    --period "${PERIOD}"
    --current-limit "${CURRENT_LIMIT}"
)

if [ -n "${MAX_SPEED_RPM}" ]; then
    CLIENT_ARGS+=(--max-speed-rpm "${MAX_SPEED_RPM}")
fi
if [ -n "${MAX_ROTATE_RPM}" ]; then
    CLIENT_ARGS+=(--max-rotate-rpm "${MAX_ROTATE_RPM}")
fi

"${CLIENT_ARGS[@]}"

wait "${GW_PID}" || true
cleanup

echo "== log tail =="
tail -100 "${LOG}" || true

echo "== final state =="
systemctl is-active can-gateway.service 2>/dev/null || true
pgrep -af can_gateway_service.py || true
ip -details -statistics link show can0 || true
