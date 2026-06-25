#!/usr/bin/env bash
set -euo pipefail

SRC="/home/rock/images/HyperBoot_raw_shm1_20260613_201937.bin"
EXPECTED_MD5="50cfd76d6a151678a5a0daf10f7659fc"
BOOT="/boot/HyperBoot.bin"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="/boot/HyperBoot.bin.bak_before_raw_shm1_${STAMP}"

echo "== Verify source image =="
if [ ! -f "${SRC}" ]; then
    echo "Missing source image: ${SRC}"
    exit 1
fi

ACTUAL_MD5="$(md5sum "${SRC}" | awk '{print $1}')"
echo "${ACTUAL_MD5}  ${SRC}"
if [ "${ACTUAL_MD5}" != "${EXPECTED_MD5}" ]; then
    echo "MD5 mismatch, expected ${EXPECTED_MD5}"
    exit 1
fi

echo "== Backup current HyperBoot =="
sudo cp -a "${BOOT}" "${BACKUP}"
sudo md5sum "${BACKUP}"

echo "== Install new HyperBoot =="
sudo cp -f "${SRC}" "${BOOT}"
sync

echo "== Verify installed HyperBoot =="
md5sum "${BOOT}"
ls -lh "${BOOT}" "${BACKUP}"
echo "Backup: ${BACKUP}"
