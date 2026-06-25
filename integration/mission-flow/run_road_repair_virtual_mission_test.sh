#!/usr/bin/env bash
set -euo pipefail

SUDO_PASSWORD="${SUDO_PASSWORD:-rock}"
LOG_PREFIX="${LOG_PREFIX:-road_repair_virtual_mission}"
RT_IP="${RT_IP:-10.10.10.30}"
RT_IFACE="${RT_IFACE:-enp255s5}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-${SCRIPT_DIR}}"
LOG_DIR="${LOG_DIR:-${APP_DIR}/logs}"

PERIOD=0.02
GATEWAY_SECONDS=18
CURRENT_LIMIT=1200
ENABLE_CURRENT=0
DRY_RUN=0
MISSION_ARGS=()

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --period SEC          Default 0.02
  --current-limit N     RT-side current clamp, default 1200
  --gateway-seconds SEC Default 18
  --log-prefix NAME
  --enable-current
  --dry-run            Preview virtual mission only. Does not start CAN gateway.
  --mission-arg ARG     Pass one argument through to road_repair_virtual_mission.py.

Default mode is safe-lock: gateway logs RT requests but sends zero current.
EOF
}

while [ "$#" -gt 0 ]; do
    ARG="${1//$'\r'/}"
    case "${ARG}" in
        --enable-current)
            ENABLE_CURRENT=1; shift ;;
        --dry-run)
            DRY_RUN=1; shift ;;
        --period)
            PERIOD="$2"; shift 2 ;;
        --current-limit)
            CURRENT_LIMIT="$2"; shift 2 ;;
        --gateway-seconds)
            GATEWAY_SECONDS="$2"; shift 2 ;;
        --log-prefix)
            LOG_PREFIX="$2"; shift 2 ;;
        --mission-arg)
            MISSION_ARGS+=("$2"); shift 2 ;;
        -h|--help)
            usage; exit 0 ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage >&2
            exit 2 ;;
    esac
done

# Be tolerant of CRLF-contaminated arguments when invoked from Windows/SSH.
PERIOD="${PERIOD//$'\r'/}"
GATEWAY_SECONDS="${GATEWAY_SECONDS//$'\r'/}"
CURRENT_LIMIT="${CURRENT_LIMIT//$'\r'/}"
LOG_PREFIX="${LOG_PREFIX//$'\r'/}"

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

MISSION_CMD=(
    python3 "${APP_DIR}/road_repair_virtual_mission.py"
    --period "${PERIOD}"
    --current-limit "${CURRENT_LIMIT}"
)
if [ "${#MISSION_ARGS[@]}" -gt 0 ]; then
    MISSION_CMD+=("${MISSION_ARGS[@]}")
fi
if [ "${DRY_RUN}" = "1" ]; then
    MISSION_CMD+=(--dry-run)
    echo "== dry-run =="
    echo "app_dir=${APP_DIR}"
    echo "log_dir=${LOG_DIR}"
    echo "period=${PERIOD} current_limit=${CURRENT_LIMIT} mission_args=${MISSION_ARGS[*]:-}"
    "${MISSION_CMD[@]}"
    exit 0
fi

echo "== run =="
echo "log=${LOG}"
echo "mode=$([ "${ENABLE_CURRENT}" = "1" ] && echo current-enabled || echo safe-lock)"
echo "period=${PERIOD} current_limit=${CURRENT_LIMIT} mission_args=${MISSION_ARGS[*]:-}"

(
    sudo_if_needed timeout "${GATEWAY_SECONDS}s" "${GATEWAY_ARGS[@]}"
) > "${LOG}" 2>&1 &
GW_PID=$!

sleep 3
"${MISSION_CMD[@]}"

wait "${GW_PID}" || true
cleanup

echo "== log tail =="
tail -120 "${LOG}" || true

echo "== final state =="
systemctl is-active can-gateway.service 2>/dev/null || true
pgrep -af can_gateway_service.py || true
ip -br link show can0 || true
