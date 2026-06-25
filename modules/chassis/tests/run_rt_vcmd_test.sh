#!/usr/bin/env bash
set -euo pipefail

SUDO_PASSWORD="${SUDO_PASSWORD:-rock}"
LOG_DIR="${LOG_DIR:-/home/rock/images/logs}"
LOG_PREFIX="${LOG_PREFIX:-rt_vcmd_test}"
RT_IP="${RT_IP:-10.10.10.30}"
RT_IFACE="${RT_IFACE:-enp255s5}"

FORWARD_RPM=0
STRAFE_RPM=0
ROTATE_RPM=0
DURATION=0.5
PERIOD=0.02
GATEWAY_SECONDS=10
ENABLE_CURRENT=0
CURRENT_LIMIT=0

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --forward-rpm N
  --strafe-rpm N
  --rotate-rpm N
  --duration SEC
  --period SEC
  --current-limit N     RT-side current clamp; 0 keeps the RT default
  --gateway-seconds SEC
  --log-prefix NAME
  --enable-current

Default mode is safe: the gateway logs RT requests but sends zero current.
--enable-current adds the two explicit dangerous-test switches to the gateway.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --forward-rpm)
            FORWARD_RPM="$2"; shift 2 ;;
        --strafe-rpm)
            STRAFE_RPM="$2"; shift 2 ;;
        --rotate-rpm)
            ROTATE_RPM="$2"; shift 2 ;;
        --duration)
            DURATION="$2"; shift 2 ;;
        --period)
            PERIOD="$2"; shift 2 ;;
        --current-limit)
            CURRENT_LIMIT="$2"; shift 2 ;;
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
}
trap cleanup EXIT INT TERM

cleanup

GATEWAY_ARGS=(
    python3 /home/rock/images/can_gateway_service.py
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
echo "vcmd forward=${FORWARD_RPM} strafe=${STRAFE_RPM} rotate=${ROTATE_RPM} duration=${DURATION} period=${PERIOD} current_limit=${CURRENT_LIMIT}"

(
    cd /home/rock/images
    sudo_if_needed timeout "${GATEWAY_SECONDS}s" "${GATEWAY_ARGS[@]}"
) > "${LOG}" 2>&1 &
GW_PID=$!

sleep 3
python3 /home/rock/images/send_vcmd.py \
    --forward-rpm "${FORWARD_RPM}" \
    --strafe-rpm "${STRAFE_RPM}" \
    --rotate-rpm "${ROTATE_RPM}" \
    --duration "${DURATION}" \
    --period "${PERIOD}" \
    --current-limit "${CURRENT_LIMIT}"

wait "${GW_PID}" || true
cleanup

echo "== log tail =="
tail -100 "${LOG}" || true

echo "== final state =="
systemctl is-active can-gateway.service 2>/dev/null || true
pgrep -af can_gateway_service.py || true
ip -details -statistics link show can0 || true
