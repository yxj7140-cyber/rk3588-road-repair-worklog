#!/usr/bin/env bash
set -u

LOG=/tmp/check_vm_shared_paths.log
exec >"$LOG" 2>&1

echo "== check VM shared paths =="
date
echo "user=$(id)"

echo "== mount hgfs if needed =="
if ! mountpoint -q /mnt/hgfs; then
  echo 000000 | sudo -S mkdir -p /mnt/hgfs
  echo 000000 | sudo -S vmhgfs-fuse .host:/ /mnt/hgfs -o allow_other
fi

echo "== /mnt/hgfs =="
ls -la /mnt/hgfs || true

echo "== candidate image paths =="
for p in \
  /mnt/hgfs/D/rockpi_car_32G.img \
  /mnt/hgfs/rt/rockpi_car_32G.img \
  "/mnt/hgfs/rt/image_work/rockpi_car_32G.img" \
  "/mnt/hgfs/rt/虚拟/v1.1.0（新版拓展板）/images/rockpi_car_32G.img"
do
  echo "-- $p"
  ls -lh "$p" || true
done

echo "== disk free =="
df -h / /mnt/hgfs /mnt/hgfs/rt 2>/dev/null || true

echo "== tools =="
for t in fdisk parted losetup e2fsck resize2fs dumpe2fs truncate sgdisk gdisk partprobe; do
  printf '%-10s ' "$t"
  command -v "$t" || true
done

echo "== done =="
