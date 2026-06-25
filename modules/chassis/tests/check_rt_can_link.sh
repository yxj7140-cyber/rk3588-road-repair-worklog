#!/usr/bin/env bash
set -euo pipefail

RT_IP="${RT_IP:-10.10.10.30}"
RT_IFACE="${RT_IFACE:-enp255s5}"
SERVICE="${SERVICE:-can-gateway.service}"

echo "== image =="
md5sum /boot/HyperBoot.bin || true

echo "== service =="
systemctl is-enabled "${SERVICE}" 2>/dev/null || true
systemctl is-active "${SERVICE}" 2>/dev/null || true

echo "== virtual network =="
ip -br addr show "${RT_IFACE}" || true
ip link show "${RT_IFACE}" || true
ping -I "${RT_IFACE}" -c 5 -W 1 "${RT_IP}"

echo "== can =="
ip -details -statistics link show can0 || true

echo "== recent gateway success lines =="
grep -aE 'udp=peer|Safety:|ERROR:|stopped; final zero-current' \
    /home/rock/images/logs/can_gateway_service.log 2>/dev/null | tail -n 40 || true
