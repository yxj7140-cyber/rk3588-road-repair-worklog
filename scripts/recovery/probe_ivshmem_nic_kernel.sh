#!/usr/bin/env bash
set -u

DEV="${1:-0000:ff:05.0}"
LOG_DIR="/home/rock/images"
PROBE_LOG="${LOG_DIR}/ivshmem_nic_kernel_probe_$(date +%Y%m%d_%H%M%S).log"
PID_FILE="${LOG_DIR}/ivshmem_net_keepalive.pid"

{
    echo "== probe kernel ivshmem_nic =="
    date
    echo "dev=${DEV}"

    echo "== stop userspace pvb-net if running =="
    if [ -s "${PID_FILE}" ]; then
        old_pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
        if [ -n "${old_pid}" ]; then
            kill "${old_pid}" 2>/dev/null || true
        fi
    fi
    pkill -x ivshmem-net 2>/dev/null || true
    sleep 0.5
    ip link set tap0 down 2>/dev/null || true
    ip tuntap del dev tap0 mode tap 2>/dev/null || true
    ip link set br0 down 2>/dev/null || true
    ip link del br0 type bridge 2>/dev/null || true

    echo "== before =="
    lspci -nnk -s "${DEV}" || true
    ip -br link || true

    echo "== bind kernel ivshmem_nic =="
    if [ -e "/sys/bus/pci/devices/${DEV}/driver/unbind" ]; then
        echo "${DEV}" > "/sys/bus/pci/devices/${DEV}/driver/unbind" 2>/dev/null || true
    fi
    modprobe ivshmem_nic 2>/dev/null || true
    if [ -d /sys/bus/pci/drivers/ivsh ]; then
        echo "1af4 1110" > /sys/bus/pci/drivers/ivsh/new_id 2>/dev/null || true
        echo "${DEV}" > /sys/bus/pci/drivers/ivsh/bind 2>/dev/null || true
    fi
    sleep 3

    echo "== after =="
    lspci -nnk -s "${DEV}" || true
    ip -br link || true
    ip -br addr || true
    ls -l /sys/bus/pci/devices/"${DEV}"/driver 2>/dev/null || true

    echo "== bring candidate interface up =="
    for ifc in $(ls /sys/class/net); do
        case "${ifc}" in
            lo|enP*|wl*|wlan*|can*|docker*|br*|tap*)
                continue
                ;;
        esac
        echo "candidate=${ifc}"
        ip link set "${ifc}" up 2>/dev/null || true
        ip addr add 10.10.10.1/24 dev "${ifc}" 2>/dev/null || true
        ip -br addr show "${ifc}" || true
        ping -I "${ifc}" -c 3 -W 1 10.10.10.30 || true
    done

    echo "== dmesg ivsh tail =="
    dmesg | grep -i ivsh | tail -80 || true

    echo "probe_log=${PROBE_LOG}"
} | tee "${PROBE_LOG}"
