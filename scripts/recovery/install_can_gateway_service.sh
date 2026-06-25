#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="can-gateway.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"
GATEWAY_SCRIPT="/home/rock/images/can_gateway_service.py"
LOG_DIR="/home/rock/images/logs"
ENABLE_SERVICE="${ENABLE_SERVICE:-0}"
START_SERVICE="${START_SERVICE:-0}"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: run this installer with sudo"
    exit 2
fi

if [ ! -f "${GATEWAY_SCRIPT}" ]; then
    echo "ERROR: gateway script not found: ${GATEWAY_SCRIPT}"
    exit 3
fi

mkdir -p "${LOG_DIR}"
chmod 755 "${LOG_DIR}"
chmod +x "${GATEWAY_SCRIPT}"

cat > "${SERVICE_PATH}" <<EOF
[Unit]
Description=Safe USB-CAN chassis gateway for RK3588 vmRT
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/rock/images
ExecStart=/usr/bin/python3 ${GATEWAY_SCRIPT} --iface can0 --setup-can --no-shm --udp --udp-bind 0.0.0.0 --udp-port 15550 --udp-command-timeout 0.25 --require-rt-ping 10.10.10.30 --rt-ping-iface enp255s5 --rt-ping-timeout 90 --require-udp-peer-timeout 90 --send-before-feedback --log-period 1.0
Restart=on-failure
RestartSec=5
StandardOutput=append:${LOG_DIR}/can_gateway_service.log
StandardError=append:${LOG_DIR}/can_gateway_service.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
if [ "${ENABLE_SERVICE}" = "1" ]; then
    systemctl enable "${SERVICE_NAME}"
else
    systemctl disable "${SERVICE_NAME}" >/dev/null 2>&1 || true
fi

if [ "${START_SERVICE}" = "1" ]; then
    systemctl restart "${SERVICE_NAME}"
else
    systemctl stop "${SERVICE_NAME}" >/dev/null 2>&1 || true
fi

echo "== ${SERVICE_NAME} installed =="
echo "ENABLE_SERVICE=${ENABLE_SERVICE} START_SERVICE=${START_SERVICE}"
systemctl --no-pager --full status "${SERVICE_NAME}" || true
echo
echo "Recent log:"
tail -40 "${LOG_DIR}/can_gateway_service.log" || true
