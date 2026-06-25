#!/usr/bin/env bash
set -u

UIO_DEV="${1:-/dev/uio0}"
LOG_DIR="/home/rock/images"
CONSOLE_SH="${LOG_DIR}/GuestSystem_Linux_Test_V0.13.0-RC1-9-G08484AC_ROCKPI5B_2025-11-28-153015/bin/ivshmem-pvb-console.sh"
PID_FILE="${LOG_DIR}/ivshmem_console_keepalive.pid"
RUNTIME_LOG="${LOG_DIR}/ivshmem_console_keepalive.log"
PROBE_LOG="${LOG_DIR}/rt_console_probe_$(date +%Y%m%d_%H%M%S).log"
TTY_DEV="/dev/ttyRTOS0"

mkdir -p "${LOG_DIR}"

{
    echo "== start rt console probe =="
    date
    echo "uio=${UIO_DEV}"

    if [ ! -e "${UIO_DEV}" ]; then
        echo "ERROR: ${UIO_DEV} does not exist"
        exit 2
    fi

    if [ ! -x "${CONSOLE_SH}" ]; then
        echo "ERROR: ${CONSOLE_SH} does not exist or is not executable"
        exit 3
    fi

    echo "== stop old console process =="
    if [ -s "${PID_FILE}" ]; then
        old_pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
        if [ -n "${old_pid}" ]; then
            kill "${old_pid}" 2>/dev/null || true
        fi
    fi
    pkill -x ivshmem-console 2>/dev/null || true
    sleep 0.3

    rm -f /dev/ttyRTOS* /tmp/ivshmem-console
    : > "${RUNTIME_LOG}"

    echo "== launch official ivshmem console =="
    cd /tmp || exit 4
    nohup sh "${CONSOLE_SH}" "${UIO_DEV}" ptmx > "${RUNTIME_LOG}" 2>&1 &
    console_pid="$!"
    echo "${console_pid}" > "${PID_FILE}"

    sleep 2

    echo "== process =="
    ps -p "${console_pid}" -o pid,ppid,stat,cmd || true

    echo "== devices =="
    ls -l /dev/uio* /dev/ttyRTOS* 2>/dev/null || true
    if [ -e "${TTY_DEV}" ]; then
        target="$(readlink "${TTY_DEV}" 2>/dev/null || true)"
        echo "${TTY_DEV} -> ${target}"
        ls -l "${target}" 2>/dev/null || true
    fi

    echo "== console runtime log =="
    sed -n '1,120p' "${RUNTIME_LOG}" || true

    echo "== rt shell probe =="
    if [ ! -e "${TTY_DEV}" ]; then
        echo "ERROR: ${TTY_DEV} was not created"
        exit 5
    fi

    stty -F "${TTY_DEV}" 115200 raw -echo -echoe -echok -echoctl -echoke min 0 time 5 2>/dev/null || true

    READ_TMP="/tmp/rt_shell_probe_read.txt"
    rm -f "${READ_TMP}"
    timeout 4s cat "${TTY_DEV}" > "${READ_TMP}" 2>/dev/null &
    cat_pid="$!"
    sleep 0.4

    # Only harmless shell queries. Do not send CAN commands here.
    printf '\r\nhelp\r\nlist_thread\r\nversion\r\n' > "${TTY_DEV}" 2>/dev/null || true
    sleep 2.5
    kill "${cat_pid}" 2>/dev/null || true
    wait "${cat_pid}" 2>/dev/null || true

    echo "== rt shell output =="
    if [ -s "${READ_TMP}" ]; then
        sed -n '1,200p' "${READ_TMP}"
    else
        echo "No RT Shell text captured yet."
    fi

    echo "== keepalive =="
    ps -p "${console_pid}" -o pid,ppid,stat,cmd || true
    echo "pid_file=${PID_FILE}"
    echo "runtime_log=${RUNTIME_LOG}"
    echo "probe_log=${PROBE_LOG}"
} | tee "${PROBE_LOG}"
