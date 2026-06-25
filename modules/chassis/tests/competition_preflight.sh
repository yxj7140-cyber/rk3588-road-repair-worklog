#!/usr/bin/env bash
set -euo pipefail

RT_IP="${RT_IP:-10.10.10.30}"
RT_IFACE="${RT_IFACE:-enp255s5}"
SERVICE="${SERVICE:-can-gateway.service}"
LOG="${LOG:-/home/rock/images/logs/can_gateway_service.log}"
SUDO_PASSWORD="${SUDO_PASSWORD:-rock}"
START_GATEWAY=0
TAIL_LOG=0

usage() {
    cat <<EOF
Usage: $0 [--start-gateway] [--tail-log]

Checks the fragile RT/Linux ivshmem_net link before CAN is touched.
If the virtual link is unhealthy, the gateway is stopped and the script exits.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --start-gateway)
            START_GATEWAY=1
            ;;
        --tail-log)
            TAIL_LOG=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
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

fail_safe() {
    echo
    echo "ERROR: $*" >&2
    echo "Safe action: stopping ${SERVICE}; CAN gateway will not run." >&2
    sudo_if_needed systemctl stop "${SERVICE}" >/dev/null 2>&1 || true
    echo
    echo "Recovery recommendation:" >&2
    echo "  1. Do not judge the RT image by this soft-reboot state." >&2
    echo "  2. Physically remove board power for at least 10 seconds." >&2
    echo "  3. Reconnect power, wait for SSH, then rerun this preflight." >&2
    exit 20
}

echo "== image =="
md5sum /boot/HyperBoot.bin || true

echo "== service =="
systemctl is-enabled "${SERVICE}" 2>/dev/null || true
systemctl is-active "${SERVICE}" 2>/dev/null || true

echo "== virtual network =="
if ! ip link show "${RT_IFACE}" >/tmp/rt_if_link.txt 2>&1; then
    cat /tmp/rt_if_link.txt || true
    fail_safe "missing RT virtual interface: ${RT_IFACE}"
fi
cat /tmp/rt_if_link.txt

if ! grep -q "LOWER_UP" /tmp/rt_if_link.txt; then
    fail_safe "${RT_IFACE} is UP but not LOWER_UP; this is the known ivshmem_net stale-peer state"
fi

if ! ping -I "${RT_IFACE}" -c 5 -W 1 "${RT_IP}"; then
    fail_safe "RT IP ${RT_IP} is not reachable through ${RT_IFACE}"
fi

echo "== can device =="
ip -details -statistics link show can0 || true

echo "== gateway log tail =="
tail -40 "${LOG}" 2>/dev/null || true

if [ "${START_GATEWAY}" = "1" ]; then
    echo "== start safe gateway =="
    sudo_if_needed systemctl start "${SERVICE}"
    sleep 3
    systemctl --no-pager --full status "${SERVICE}" || true
    echo
    echo "== latest gateway log =="
    tail -80 "${LOG}" 2>/dev/null || true
fi

if [ "${TAIL_LOG}" = "1" ]; then
    echo "== follow gateway log; press Ctrl+C to stop watching =="
    tail -f "${LOG}"
fi

echo
echo "Preflight OK: ${RT_IFACE} has LOWER_UP and ${RT_IP} is reachable."
