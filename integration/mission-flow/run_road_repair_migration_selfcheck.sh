#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-${SCRIPT_DIR}}"
LOG_DIR="${LOG_DIR:-${APP_DIR}/logs}"
LOG_PREFIX="${LOG_PREFIX:-road_repair_migration_selfcheck}"
SUDO_PASSWORD="${SUDO_PASSWORD:-rock}"

mkdir -p "${LOG_DIR}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/${LOG_PREFIX}_${STAMP}.log"

sudo_if_needed() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif sudo -n true 2>/dev/null; then
        sudo "$@"
    else
        printf '%s\n' "${SUDO_PASSWORD}" | sudo -S "$@"
    fi
}

{
    echo "== selfcheck =="
    echo "app_dir=${APP_DIR}"
    echo "log=${LOG}"
    echo "date=$(date -Is)"
    cd "${APP_DIR}"

    echo "== core regression =="
    python3 test_chassis_migration_core.py

    echo "== chassis runner dry-run =="
    bash ./run_road_repair_chassis_task_test.sh \
        --dry-run \
        --lx 127 --ly 112 --rx 127 \
        --duration 0.35 \
        --current-limit 1200 \
        --gateway-seconds 5 \
        --log-prefix selfcheck_chassis

    echo "== virtual mission runner dry-run =="
    bash ./run_road_repair_virtual_mission_test.sh \
        --dry-run \
        --current-limit 1200 \
        --log-prefix selfcheck_virtual_mission

    echo "== topic1 runner dry-run =="
    python3 ./road_repair_topic1_runner.py \
        --dry-run \
        --current-limit 1200 \
        --pump-duration 0.2

    echo "== path hygiene =="
    LEGACY_PATH="/home/rock/ima""ges"
    FOUND_LEGACY=0
    for file in ./*.py ./*.sh; do
        if [ "$(basename "${file}")" = "$(basename "$0")" ]; then
            continue
        fi
        if grep -n "${LEGACY_PATH}" "${file}" >/tmp/road_repair_legacy_path_hits.txt 2>/dev/null; then
            echo "legacy path found in ${file}:"
            cat /tmp/road_repair_legacy_path_hits.txt
            FOUND_LEGACY=1
        fi
    done
    rm -f /tmp/road_repair_legacy_path_hits.txt
    if [ "${FOUND_LEGACY}" -ne 0 ]; then
        echo "ERROR: legacy /home/rock/images path found in runtime files" >&2
        exit 1
    fi
    echo "OK: no legacy runtime path references"

    echo "== board safe-state =="
    systemctl is-active can-gateway.service 2>/dev/null || true
    ip -br link show can0 || true
} | tee "${LOG}"
