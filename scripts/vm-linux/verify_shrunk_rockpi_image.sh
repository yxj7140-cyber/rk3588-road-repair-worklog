#!/usr/bin/env bash
set -euo pipefail

IMG="${1:-/mnt/hgfs/rt/image_work/rockpi_car_32G_shrunk_31_18GB_20260623_113526.img}"
LOG=/tmp/verify_shrunk_rockpi_image.log
exec >"$LOG" 2>&1

echo "== verify shrunk ROCKPI image =="
date
echo "image=$IMG"
ls -lh "$IMG"
stat -c 'size_bytes=%s' "$IMG"

echo "== partition table =="
fdisk -l "$IMG"
parted -s "$IMG" unit B print
sgdisk -v "$IMG"

START_B="$(parted -sm "$IMG" unit B print | awk -F: '$1=="2"{gsub(/B/,"",$2); print $2}')"
SIZE_B="$(parted -sm "$IMG" unit B print | awk -F: '$1=="2"{gsub(/B/,"",$4); print $4}')"
echo "root_start_bytes=$START_B"
echo "root_size_bytes=$SIZE_B"

LOOP="$(losetup --show -f -r -o "$START_B" --sizelimit "$SIZE_B" "$IMG")"
echo "loop=$LOOP"
cleanup() {
  set +e
  losetup -d "$LOOP" >/dev/null 2>&1 || true
}
trap cleanup EXIT

blkid "$LOOP"
e2fsck -fn "$LOOP"
dumpe2fs -h "$LOOP" 2>/dev/null | grep -E 'Filesystem state|Block count|Free blocks|Block size'

echo "== done =="
