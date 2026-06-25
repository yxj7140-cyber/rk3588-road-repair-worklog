#!/usr/bin/env bash
set -euo pipefail

SHARE="/mnt/hgfs/rt"
SRC="$SHARE/image_work/rockpi_car_32G.img"
LOCAL_DIR="/home/yx/Desktop/rock_ws/image_work"
TS="$(date +%Y%m%d_%H%M%S)"
LOCAL="$LOCAL_DIR/rockpi_car_32G_shrink_work_${TS}.img"
OUT="$SHARE/image_work/rockpi_car_32G_shrunk_31_18GB_${TS}.img"
LOG_DIR="$SHARE/vm_logs"
LOG="$LOG_DIR/shrink_rockpi_car_32g_${TS}.log"

# The current card reported by Windows is 31,268,536,320 bytes.
TARGET_CARD_BYTES=31268536320

# 60,900,000 sectors * 512 = 31,180,800,000 bytes.
# This leaves about 87 MB margin for the user's current 32G card.
NEW_DISK_SECTORS=60900000
SECTOR_SIZE=512
ALIGN_SECTORS=8

mkdir -p "$LOG_DIR" "$LOCAL_DIR" "$SHARE/image_work"
exec > >(tee "$LOG") 2>&1

section() {
  echo
  echo "========== $* =========="
}

run() {
  echo "+ $*"
  "$@"
}

fsck_rw() {
  local dev="$1"
  set +e
  e2fsck -fy "$dev"
  local rc=$?
  set -e
  echo "e2fsck exit code: $rc"
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
    echo "ERROR: e2fsck failed on $dev with code $rc"
    exit "$rc"
  fi
}

section "Start"
date
echo "source: $SRC"
echo "local work: $LOCAL"
echo "output: $OUT"
echo "target card bytes: $TARGET_CARD_BYTES"
echo "new disk sectors: $NEW_DISK_SECTORS"
echo "new disk bytes: $((NEW_DISK_SECTORS * SECTOR_SIZE))"

if [ ! -f "$SRC" ]; then
  echo "ERROR: source image not found: $SRC"
  exit 2
fi
if [ "$((NEW_DISK_SECTORS * SECTOR_SIZE))" -ge "$TARGET_CARD_BYTES" ]; then
  echo "ERROR: requested new image is not smaller than target card."
  exit 3
fi

section "Copy source image to VM local disk"
run ls -lh "$SRC"
run df -h "$LOCAL_DIR" "$SHARE/image_work"
run cp --sparse=always "$SRC" "$LOCAL"
run sync
run ls -lh "$LOCAL"

section "Read partition table"
run fdisk -l "$LOCAL"
run parted -s "$LOCAL" unit B print
run sgdisk -v "$LOCAL"

PARTED_S="$(parted -sm "$LOCAL" unit s print)"
echo "$PARTED_S"
ROOT_START_S="$(printf '%s\n' "$PARTED_S" | awk -F: '$1=="2"{gsub(/s/,"",$2); print $2}')"
ROOT_END_S="$(printf '%s\n' "$PARTED_S" | awk -F: '$1=="2"{gsub(/s/,"",$3); print $3}')"
if [ -z "$ROOT_START_S" ] || [ -z "$ROOT_END_S" ]; then
  echo "ERROR: could not parse rootfs partition from image."
  exit 4
fi

ROOT_START_B=$((ROOT_START_S * SECTOR_SIZE))
OLD_ROOT_SECTORS=$((ROOT_END_S - ROOT_START_S + 1))
OLD_ROOT_SIZE_B=$((OLD_ROOT_SECTORS * SECTOR_SIZE))

NEW_LAST_USABLE_S=$((NEW_DISK_SECTORS - 34))
NEW_ROOT_SECTORS=$((((NEW_LAST_USABLE_S - ROOT_START_S + 1) / ALIGN_SECTORS) * ALIGN_SECTORS))
NEW_ROOT_END_S=$((ROOT_START_S + NEW_ROOT_SECTORS - 1))
NEW_ROOT_BLOCKS=$((NEW_ROOT_SECTORS / 8))
NEW_ROOT_SIZE_B=$((NEW_ROOT_SECTORS * SECTOR_SIZE))
NEW_DISK_BYTES=$((NEW_DISK_SECTORS * SECTOR_SIZE))

echo "root_start_sector=$ROOT_START_S"
echo "root_end_sector_old=$ROOT_END_S"
echo "root_start_bytes=$ROOT_START_B"
echo "old_root_sectors=$OLD_ROOT_SECTORS"
echo "old_root_size_bytes=$OLD_ROOT_SIZE_B"
echo "new_last_usable_sector=$NEW_LAST_USABLE_S"
echo "new_root_sectors=$NEW_ROOT_SECTORS"
echo "new_root_end_sector=$NEW_ROOT_END_S"
echo "new_root_blocks_4k=$NEW_ROOT_BLOCKS"
echo "new_root_size_bytes=$NEW_ROOT_SIZE_B"
echo "new_disk_bytes=$NEW_DISK_BYTES"

if [ "$NEW_ROOT_END_S" -ge "$NEW_LAST_USABLE_S" ]; then
  echo "ERROR: computed rootfs end is too close to GPT backup area."
  exit 5
fi

section "Attach rootfs as offset loop and repair"
LOOP="$(losetup --show -f -o "$ROOT_START_B" --sizelimit "$OLD_ROOT_SIZE_B" "$LOCAL")"
echo "loop=$LOOP"
cleanup_loop() {
  set +e
  if [ -n "${LOOP:-}" ] && losetup "$LOOP" >/dev/null 2>&1; then
    losetup -d "$LOOP" || true
  fi
}
trap cleanup_loop EXIT

run blkid "$LOOP"
fsck_rw "$LOOP"

section "Filesystem size before shrink"
run dumpe2fs -h "$LOOP"
BEFORE_BLOCKS="$(dumpe2fs -h "$LOOP" 2>/dev/null | awk -F: '/Block count/{gsub(/ /,"",$2); print $2}')"
FREE_BLOCKS="$(dumpe2fs -h "$LOOP" 2>/dev/null | awk -F: '/Free blocks/{gsub(/ /,"",$2); print $2}')"
MIN_TEXT="$(resize2fs -P "$LOOP" 2>&1 || true)"
echo "$MIN_TEXT"
MIN_BLOCKS="$(printf '%s\n' "$MIN_TEXT" | awk '/minimum size/{print $NF}' || true)"
echo "before_blocks=$BEFORE_BLOCKS"
echo "free_blocks=$FREE_BLOCKS"
echo "resize2fs_min_blocks=${MIN_BLOCKS:-unknown}"

if [ -n "${MIN_BLOCKS:-}" ] && [ "$NEW_ROOT_BLOCKS" -le "$MIN_BLOCKS" ]; then
  echo "ERROR: new rootfs block count is below resize2fs minimum."
  exit 6
fi

section "Shrink ext4 rootfs"
run resize2fs "$LOOP" "$NEW_ROOT_BLOCKS"
fsck_rw "$LOOP"

section "Filesystem size after shrink"
run dumpe2fs -h "$LOOP"
AFTER_BLOCKS="$(dumpe2fs -h "$LOOP" 2>/dev/null | awk -F: '/Block count/{gsub(/ /,"",$2); print $2}')"
echo "after_blocks=$AFTER_BLOCKS"
if [ "$AFTER_BLOCKS" != "$NEW_ROOT_BLOCKS" ]; then
  echo "ERROR: resized block count mismatch."
  exit 7
fi

losetup -d "$LOOP"
LOOP=""
trap - EXIT

section "Shrink GPT partition and image file"
run sgdisk -d 2 -n "2:${ROOT_START_S}:${NEW_ROOT_END_S}" -t 2:8300 -c 2:rootfs "$LOCAL"
run truncate -s "$NEW_DISK_BYTES" "$LOCAL"
run sgdisk -e "$LOCAL"
run sgdisk -v "$LOCAL"
run fdisk -l "$LOCAL"
run parted -s "$LOCAL" unit B print
run ls -lh "$LOCAL"
stat -c 'local_size_bytes=%s' "$LOCAL"

section "Verify shrunk image rootfs"
LOOP="$(losetup --show -f -r -o "$ROOT_START_B" --sizelimit "$NEW_ROOT_SIZE_B" "$LOCAL")"
trap cleanup_loop EXIT
run blkid "$LOOP"
set +e
e2fsck -fn "$LOOP"
VERIFY_RC=$?
set -e
echo "readonly e2fsck exit code: $VERIFY_RC"
if [ "$VERIFY_RC" -ne 0 ]; then
  echo "ERROR: readonly verification fsck reported code $VERIFY_RC"
  exit "$VERIFY_RC"
fi
losetup -d "$LOOP"
LOOP=""
trap - EXIT

section "Copy final image back to shared folder"
run cp --sparse=always "$LOCAL" "$OUT"
run sync
run ls -lh "$OUT"
stat -c 'output_size_bytes=%s' "$OUT"
if [ "$(stat -c '%s' "$OUT")" -ge "$TARGET_CARD_BYTES" ]; then
  echo "ERROR: output image is still too large for the target card."
  exit 8
fi

section "Checksum"
md5sum "$OUT" | tee "${OUT}.md5"

section "Done"
echo "Output image: $OUT"
echo "Output md5: ${OUT}.md5"
echo "Log: $LOG"
