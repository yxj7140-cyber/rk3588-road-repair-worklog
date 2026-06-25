#!/usr/bin/env bash
set -euo pipefail

LOG=/tmp/fix_32g_tf_restore_metadata.log
exec >"$LOG" 2>&1

echo "== fix 32G TF restored file metadata =="
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
ROOT_PART="$(lsblk -lnpo PATH,FSTYPE "$CARD" | awk '$2=="ext4" {print $1; exit}')"
MNT=/tmp/rk3588_32g_fix_metadata
rm -rf "$MNT"
mkdir -p "$MNT/root"
cleanup() {
  set +e
  mountpoint -q "$MNT/root" && umount "$MNT/root"
}
trap cleanup EXIT

mount "$ROOT_PART" "$MNT/root"

chown 0:0 "$MNT/root/usr/local/bin/start_ap.sh"
chmod 755 "$MNT/root/usr/local/bin/start_ap.sh"
chown 0:0 "$MNT/root/etc/systemd/system/road-repair-web-remote.service"
chmod 644 "$MNT/root/etc/systemd/system/road-repair-web-remote.service"
chown -h 0:0 "$MNT/root/etc/systemd/system/multi-user.target.wants/road-repair-web-remote.service"
chown -h 0:0 "$MNT/root/etc/systemd/system/multi-user.target.wants/rockchip-ap.service" || true
chown -R 1000:1000 "$MNT/root/home/rock/road_repair_web_remote" "$MNT/root/home/rock/road_repair_chassis_migration"

sync
ls -l "$MNT/root/usr/local/bin/start_ap.sh"
ls -l "$MNT/root/etc/systemd/system/road-repair-web-remote.service"
echo "== done =="
