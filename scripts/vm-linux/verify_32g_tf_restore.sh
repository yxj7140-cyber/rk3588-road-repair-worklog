#!/usr/bin/env bash
set -euo pipefail

LOG=/tmp/verify_32g_tf_restore.log
exec >"$LOG" 2>&1

echo "== verify 32G TF card restore =="
date

ROOT_SRC="$(findmnt -n -o SOURCE / || true)"
ROOT_DISK="$(lsblk -ndo PKNAME "$ROOT_SRC" 2>/dev/null || true)"
mapfile -t CANDIDATES < <(
  lsblk -b -ndo NAME,TYPE,TRAN,RM,SIZE |
    awk -v root="$ROOT_DISK" '
      $2=="disk" && $1!=root && ($3=="usb" || $4=="1") && $5>=28000000000 && $5<=35000000000 {
        print "/dev/"$1
      }
    '
)
if [ "${#CANDIDATES[@]}" -ne 1 ]; then
  echo "ERROR: expected one 32G card, found ${#CANDIDATES[@]}"
  printf '%s\n' "${CANDIDATES[@]:-}"
  exit 3
fi

CARD="${CANDIDATES[0]}"
BOOT_PART="$(lsblk -lnpo PATH,FSTYPE "$CARD" | awk '$2=="vfat" || $2=="fat32" || $2=="fat16" {print $1; exit}')"
ROOT_PART="$(lsblk -lnpo PATH,FSTYPE "$CARD" | awk '$2=="ext4" {print $1; exit}')"
MNT=/tmp/rk3588_32g_verify
rm -rf "$MNT"
mkdir -p "$MNT/root" "$MNT/boot"
cleanup() {
  set +e
  mountpoint -q "$MNT/boot" && umount "$MNT/boot"
  mountpoint -q "$MNT/root" && umount "$MNT/root"
}
trap cleanup EXIT

mount "$ROOT_PART" "$MNT/root"
mount "$BOOT_PART" "$MNT/boot"

echo "== HyperBoot md5 =="
md5sum "$MNT/boot/HyperBoot.bin"

echo "== restored files =="
for p in \
  "$MNT/root/usr/local/bin/start_ap.sh" \
  "$MNT/root/etc/systemd/system/road-repair-web-remote.service" \
  "$MNT/root/etc/systemd/system/multi-user.target.wants/road-repair-web-remote.service" \
  "$MNT/root/etc/systemd/system/multi-user.target.wants/rockchip-ap.service" \
  "$MNT/root/home/rock/road_repair_web_remote/road_repair_web_remote.py" \
  "$MNT/root/home/rock/road_repair_chassis_migration/road_repair_topic1_runner.py"; do
  if [ -e "$p" ]; then
    ls -l "$p"
  else
    echo "MISSING: $p"
    exit 4
  fi
done

echo "== AP script wl/wlan support =="
grep -En 'wlan|\^wl' "$MNT/root/usr/local/bin/start_ap.sh" || {
  echo "ERROR: AP script does not include wlan/wl interface matching"
  exit 5
}

echo "== service safety parameters =="
grep -n -- '--host\\|--web-port\\|--current-limit\\|--max-speed-rpm\\|--straight-assist\\|safe' "$MNT/root/etc/systemd/system/road-repair-web-remote.service" || true

echo "== package file counts =="
find "$MNT/root/home/rock/road_repair_web_remote" -maxdepth 1 -type f | wc -l
find "$MNT/root/home/rock/road_repair_chassis_migration" -maxdepth 1 -type f | wc -l

sync
echo "== verify done =="
