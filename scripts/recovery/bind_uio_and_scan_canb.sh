#!/usr/bin/env bash
set -u

DEV="${1:-0000:ff:04.0}"

echo "== bind ivshmem_uio =="
if [ -e "/sys/bus/pci/devices/${DEV}/driver/unbind" ]; then
    echo "${DEV}" > "/sys/bus/pci/devices/${DEV}/driver/unbind" 2>/dev/null || true
fi

modprobe ivshmem_uio 2>/dev/null || true
echo "1af4 1110" > /sys/bus/pci/drivers/uio_ivshmem/new_id 2>/dev/null || true
echo "${DEV}" > /sys/bus/pci/drivers/uio_ivshmem/bind 2>/dev/null || true
sleep 0.2

UIO_DIR="$(find "/sys/bus/pci/devices/${DEV}/uio" -mindepth 1 -maxdepth 1 -type d -name 'uio[0-9]*' 2>/dev/null | head -n 1)"
if [ -z "${UIO_DIR}" ]; then
    echo "No UIO device found for ${DEV}. Current ivshmem PCI devices:"
    lspci -Dnn | grep -i "1af4:1110" || true
    exit 1
fi

UIO_NAME="$(basename "${UIO_DIR}")"
export UIO="/dev/${UIO_NAME}"
export UIO_MAP_INDEX="${UIO_MAP_INDEX:-1}"
echo "Using ${DEV} -> ${UIO} map${UIO_MAP_INDEX}"

echo "== uio maps =="
for map_dir in "/sys/class/uio/${UIO_NAME}"/maps/map*; do
    [ -d "${map_dir}" ] || continue
    printf "%s " "${map_dir}"
    cat "${map_dir}/name" "${map_dir}/addr" "${map_dir}/size" 2>/dev/null | xargs echo
done

echo "== scan CANB =="
python3 /home/rock/images/scan_uio_markers.py
python3 /home/rock/images/scan_uio_canb.py

echo "== read CANB heartbeat =="
python3 /home/rock/images/read_uio_canb.py
