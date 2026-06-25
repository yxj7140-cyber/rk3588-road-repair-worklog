#!/usr/bin/env bash
set -euo pipefail

IMG="/mnt/hgfs/rt/image_work/rockpi_car_32G.img"
LOG="/tmp/analyze_rockpi_image_ext4_offset.log"
exec >"$LOG" 2>&1

echo "== analyze image ext4 by byte offset =="
date
echo "image=$IMG"

START_B="$(parted -sm "$IMG" unit B print | awk -F: '$1=="2"{gsub(/B/,"",$2); print $2}')"
END_B="$(parted -sm "$IMG" unit B print | awk -F: '$1=="2"{gsub(/B/,"",$3); print $3}')"
SIZE_B="$(parted -sm "$IMG" unit B print | awk -F: '$1=="2"{gsub(/B/,"",$4); print $4}')"

echo "root_start_bytes=$START_B"
echo "root_end_bytes=$END_B"
echo "root_size_bytes=$SIZE_B"

LOOP="$(echo 000000 | sudo -S losetup --show -f -r -o "$START_B" --sizelimit "$SIZE_B" "$IMG")"
echo "loop=$LOOP"
cleanup() {
  set +e
  echo 000000 | sudo -S losetup -d "$LOOP" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== blkid =="
echo 000000 | sudo -S blkid "$LOOP" || true

echo "== e2fsck readonly =="
echo 000000 | sudo -S e2fsck -fn "$LOOP" || true

echo "== dumpe2fs =="
echo 000000 | sudo -S dumpe2fs -h "$LOOP" 2>/dev/null | grep -E 'Block count|Reserved block count|Free blocks|Block size|Filesystem state'

echo "== minimum blocks =="
echo 000000 | sudo -S resize2fs -P "$LOOP"

echo "== done =="
