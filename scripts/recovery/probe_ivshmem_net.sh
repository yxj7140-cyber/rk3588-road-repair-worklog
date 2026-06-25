#!/usr/bin/env bash
set -u

DEV="${1:-0000:ff:05.0}"
UIO="${2:-/dev/uio0}"
NET_ID="${3:-0}"
LOG_DIR="/home/rock/images"
NET_SH="${LOG_DIR}/GuestSystem_Linux_Test_V0.13.0-RC1-9-G08484AC_ROCKPI5B_2025-11-28-153015/bin/ivshmem-pvb-net.sh"
PID_FILE="${LOG_DIR}/ivshmem_net_keepalive.pid"
RUNTIME_LOG="${LOG_DIR}/ivshmem_net_keepalive.log"
PROBE_LOG="${LOG_DIR}/ivshmem_net_probe_$(date +%Y%m%d_%H%M%S).log"

{
    echo "== probe ivshmem net =="
    date
    echo "dev=${DEV}"
    echo "uio=${UIO}"

    echo "== current HyperBoot =="
    md5sum /boot/HyperBoot.bin 2>/dev/null || true

    echo "== stop old pvb net =="
    if [ -s "${PID_FILE}" ]; then
        old_pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
        if [ -n "${old_pid}" ]; then
            kill "${old_pid}" 2>/dev/null || true
        fi
    fi
    pkill -x ivshmem-net 2>/dev/null || true
    ip link set tap"${NET_ID}" down 2>/dev/null || true
    ip tuntap del dev tap"${NET_ID}" mode tap 2>/dev/null || true
    ip link set br0 down 2>/dev/null || true
    ip link del br0 type bridge 2>/dev/null || true
    sleep 0.5

    echo "== bind uio ivshmem =="
    if [ -e "/sys/bus/pci/devices/${DEV}/driver/unbind" ]; then
        echo "${DEV}" > "/sys/bus/pci/devices/${DEV}/driver/unbind" 2>/dev/null || true
    fi
    modprobe ivshmem_uio 2>/dev/null || true
    echo "1af4 1110" > /sys/bus/pci/drivers/uio_ivshmem/new_id 2>/dev/null || true
    echo "${DEV}" > /sys/bus/pci/drivers/uio_ivshmem/bind 2>/dev/null || true

    echo "== uio maps =="
    ls -l /dev/uio* 2>/dev/null || true
    for d in /sys/class/uio/uio*; do
        [ -d "$d" ] || continue
        echo "-- $d --"
        cat "$d/name" 2>/dev/null || true
        for m in "$d"/maps/map*; do
            [ -d "$m" ] || continue
            printf "%s " "$m"
            cat "$m/name" "$m/addr" "$m/size" 2>/dev/null | xargs echo
        done
    done

    echo "== launch official pvb net =="
    : > "${RUNTIME_LOG}"
    cd /tmp || exit 4
    nohup sh "${NET_SH}" "${UIO}" "${NET_ID}" br0 > "${RUNTIME_LOG}" 2>&1 &
    pvb_pid="$!"
    echo "${pvb_pid}" > "${PID_FILE}"

    sleep 4

    echo "== process =="
    ps -p "${pvb_pid}" -o pid,ppid,stat,cmd || true
    ps -ef | grep -E '[i]vshmem-net|[p]vb-net' || true

    echo "== runtime log =="
    sed -n '1,180p' "${RUNTIME_LOG}" || true

    echo "== links =="
    ip -br link || true
    ip -br addr || true

    echo "== set host side addresses =="
    ip addr add 10.10.10.1/24 dev tap"${NET_ID}" 2>/dev/null || true
    ip link set tap"${NET_ID}" up 2>/dev/null || true
    ip addr add 10.10.10.99/24 dev br0 2>/dev/null || true
    ip link set br0 up 2>/dev/null || true
    ip -br addr show tap"${NET_ID}" br0 2>/dev/null || true

    echo "== ping RT default ivshmem IP 10.10.10.30 =="
    ping -c 3 -W 1 10.10.10.30 || true

    echo "== final keepalive =="
    ps -p "${pvb_pid}" -o pid,ppid,stat,cmd || true
    echo "pid_file=${PID_FILE}"
    echo "runtime_log=${RUNTIME_LOG}"
    echo "probe_log=${PROBE_LOG}"
} | tee "${PROBE_LOG}"
