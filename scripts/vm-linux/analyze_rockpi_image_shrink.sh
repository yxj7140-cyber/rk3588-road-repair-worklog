#!/usr/bin/env bash
set -euo pipefail

IMG="/mnt/hgfs/rt/image_work/rockpi_car_32G.img"
LOG="/tmp/analyze_rockpi_image_shrink.log"
exec >"$LOG" 2>&1

echo "== analyze ROCKPI image for shrink =="
date
echo "image=$IMG"

if [ ! -f "$IMG" ]; then
  echo "ERROR: image not found"
  exit 2
fi

ls -lh "$IMG"
stat -c 'size_bytes=%s' "$IMG"

echo "== fdisk =="
fdisk -l "$IMG"

echo "== parted bytes =="
parted -s "$IMG" unit B print

echo "== sgdisk verify =="
sgdisk -v "$IMG" || true

echo "== attach loop read-only =="
LOOP="$(echo 000000 | sudo -S losetup --show -Pf -r "$IMG")"
echo "loop=$LOOP"
cleanup() {
  set +e
  echo 000000 | sudo -S losetup -d "$LOOP" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== loop parts =="
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINT "$LOOP"

ROOT_PART=""
for p in "${LOOP}"p*; do
  [ -e "$p" ] || continue
  fs="$(lsblk -npo FSTYPE "$p" | head -n1 || true)"
  label="$(lsblk -npo LABEL "$p" | head -n1 || true)"
  if [ "$fs" = "ext4" ] && { [ "$label" = "rootfs" ] || [ -z "$ROOT_PART" ]; }; then
    ROOT_PART="$p"
  fi
done

if [ -z "$ROOT_PART" ]; then
  echo "ERROR: root ext4 partition not found"
  exit 3
fi
echo "root_part=$ROOT_PART"

echo "== ext4 usage =="
echo 000000 | sudo -S e2fsck -fn "$ROOT_PART" || true
echo "-- dumpe2fs important fields --"
echo 000000 | sudo -S dumpe2fs -h "$ROOT_PART" 2>/dev/null | grep -E 'Block count|Reserved block count|Free blocks|Block size|Filesystem state'

echo "== resize2fs minimum =="
echo 000000 | sudo -S resize2fs -P "$ROOT_PART"

echo "== done =="
