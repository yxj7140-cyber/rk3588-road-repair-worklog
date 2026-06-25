#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ]; then
    echo "Usage: $0 <source-hyperboot> <expected-md5> <backup-tag> [--reboot]"
    exit 2
fi

SRC="$1"
EXPECTED_MD5="$2"
BACKUP_TAG="$3"
DO_REBOOT="${4:-}"

BOOT="/boot/HyperBoot.bin"
BACKUP_DIR="/home/rock/images"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="${BACKUP_DIR}/HyperBoot_before_${BACKUP_TAG}_${STAMP}.bin"

echo "== install HyperBoot safely =="
date
echo "source=${SRC}"
echo "boot=${BOOT}"
echo "backup=${BACKUP}"

if [ ! -f "${SRC}" ]; then
    echo "ERROR: source image does not exist: ${SRC}"
    exit 3
fi

actual_md5="$(md5sum "${SRC}" | awk '{print $1}')"
echo "${actual_md5}  ${SRC}"
if [ "${actual_md5}" != "${EXPECTED_MD5}" ]; then
    echo "ERROR: source md5 mismatch, expected ${EXPECTED_MD5}"
    exit 4
fi

current_md5="$(md5sum "${BOOT}" | awk '{print $1}')"
echo "${current_md5}  ${BOOT}"

cp -a "${BOOT}" "${BACKUP}"
echo "== backup created =="
md5sum "${BACKUP}"

cp -f "${SRC}" "${BOOT}"
sync

echo "== installed =="
md5sum "${BOOT}"
ls -lh "${BOOT}" "${BACKUP}"

if [ "${DO_REBOOT}" = "--reboot" ]; then
    echo "== rebooting =="
    reboot
else
    echo "== no reboot requested =="
fi
