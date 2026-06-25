#!/usr/bin/env bash
set -euo pipefail

SHARE="/mnt/hgfs/rt"
if [ ! -d "$SHARE" ]; then
  echo "ERROR: VMware shared folder not found: $SHARE"
  echo "Please enable shared folder rt first."
  exit 2
fi

LOG_DIR="$SHARE/vm_logs"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
LOG="$LOG_DIR/restore_32g_tf_to_0618_${TS}.log"
exec > >(tee "$LOG") 2>&1

echo "== restore 32G TF card to 2026-06-18 chassis state =="
echo "Log: $LOG"
date

if [ "$(id -u)" -eq 0 ]; then
  SUDO=()
else
  SUDO=(sudo)
fi

section() {
  echo
  echo "========== $* =========="
}

run() {
  echo "+ $*"
  "$@"
}

section "Block Devices"
LSBLK_COLS="NAME,KNAME,PATH,TRAN,HOTPLUG,RM,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINT,MODEL,SERIAL"
lsblk -o "$LSBLK_COLS"

ROOT_SRC="$(findmnt -n -o SOURCE / || true)"
ROOT_DISK="$(lsblk -ndo PKNAME "$ROOT_SRC" 2>/dev/null || true)"
echo "VM root source: ${ROOT_SRC:-unknown}"
echo "VM root disk parent: ${ROOT_DISK:-unknown}"

mapfile -t CANDIDATES < <(
  lsblk -b -ndo NAME,TYPE,TRAN,RM,SIZE |
    awk -v root="$ROOT_DISK" '
      $2=="disk" && $1!=root && ($3=="usb" || $4=="1") && $5>=28000000000 && $5<=35000000000 {
        print "/dev/"$1
      }
    '
)

if [ "${#CANDIDATES[@]}" -ne 1 ]; then
  echo "ERROR: expected exactly one removable/USB 32G disk candidate, found ${#CANDIDATES[@]}."
  printf 'Candidates:\n'
  printf '  %s\n' "${CANDIDATES[@]:-}"
  echo "If none: in VMware menu connect the USB card reader to the VM first."
  echo "If multiple: remove unrelated USB storage and retry."
  exit 3
fi

CARD="${CANDIDATES[0]}"
echo "Selected card: $CARD"

PARTS_JSON="$(lsblk -J -o NAME,PATH,FSTYPE,LABEL,SIZE,TYPE "$CARD")"
echo "$PARTS_JSON"

BOOT_PART="$(lsblk -lnpo PATH,FSTYPE "$CARD" | awk '$2=="vfat" || $2=="fat32" || $2=="fat16" {print $1; exit}')"
ROOT_PART="$(lsblk -lnpo PATH,FSTYPE,LABEL "$CARD" | awk '$2=="ext4" {print $1; exit}')"

if [ -z "${ROOT_PART:-}" ]; then
  echo "ERROR: ext4 rootfs partition not found on $CARD"
  exit 4
fi

echo "Boot partition: ${BOOT_PART:-none}"
echo "Root partition: $ROOT_PART"

section "Unmount desktop auto-mounts if present"
while read -r mountpoint; do
  if [ -n "$mountpoint" ]; then
    run "${SUDO[@]}" umount "$mountpoint"
  fi
done < <(lsblk -lnpo MOUNTPOINT "$CARD" | awk 'NF {print}')

section "Read-only checks"
if ! "${SUDO[@]}" e2fsck -fn "$ROOT_PART"; then
  echo "WARN: read-only fsck reported errors. Running repair fsck because this script is restoring a recovery card."
  set +e
  "${SUDO[@]}" e2fsck -fy "$ROOT_PART"
  FSCK_RC=$?
  set -e
  echo "e2fsck repair exit code: $FSCK_RC"
  if [ "$FSCK_RC" -ne 0 ] && [ "$FSCK_RC" -ne 1 ]; then
    echo "ERROR: e2fsck repair failed with exit code $FSCK_RC"
    exit "$FSCK_RC"
  fi
fi

MNT="/tmp/rk3588_32g_restore_${TS}"
mkdir -p "$MNT/root" "$MNT/boot"
cleanup() {
  set +e
  mountpoint -q "$MNT/root" && "${SUDO[@]}" umount "$MNT/root"
  mountpoint -q "$MNT/boot" && "${SUDO[@]}" umount "$MNT/boot"
}
trap cleanup EXIT

section "Mount rootfs read-write"
run "${SUDO[@]}" mount "$ROOT_PART" "$MNT/root"
if [ -n "${BOOT_PART:-}" ]; then
  run "${SUDO[@]}" mount "$BOOT_PART" "$MNT/boot"
fi

section "Backup existing card state"
BACKUP_ROOT="$SHARE/rk3588_migration/tf_card_recovery/32g_restore_${TS}"
mkdir -p "$BACKUP_ROOT"

backup_file() {
  local rel="$1"
  if [ -e "$MNT/root/$rel" ]; then
    mkdir -p "$BACKUP_ROOT/$(dirname "$rel")"
    run "${SUDO[@]}" cp -a "$MNT/root/$rel" "$BACKUP_ROOT/$rel"
  fi
}

backup_dir() {
  local rel="$1"
  if [ -d "$MNT/root/$rel" ]; then
    mkdir -p "$BACKUP_ROOT/$(dirname "$rel")"
    run "${SUDO[@]}" tar \
      --ignore-failed-read \
      --exclude='.nx' \
      --exclude='*.sock' \
      --exclude='*.socket' \
      -C "$MNT/root" \
      -czf "$BACKUP_ROOT/${rel//\//_}.tgz" \
      "$rel"
  fi
}

for p in \
  usr/local/bin/start_ap.sh \
  etc/systemd/system/rockchip-ap.service \
  etc/systemd/system/road-repair-web-remote.service \
  etc/NetworkManager/system-connections/ROCK.nmconnection
do
  backup_file "$p"
done
backup_dir home/rock/images
backup_dir home/rock/road_repair_web_remote
backup_dir home/rock/road_repair_chassis_migration
if mountpoint -q "$MNT/boot" && [ -f "$MNT/boot/HyperBoot.bin" ]; then
  run "${SUDO[@]}" cp -a "$MNT/boot/HyperBoot.bin" "$BACKUP_ROOT/HyperBoot.before.bin"
  md5sum "$BACKUP_ROOT/HyperBoot.before.bin" || true
fi

section "Restore HyperBoot"
HYPER="$SHARE/build_outputs/local_rtt_32G_20260614_143025/HyperBoot.bin"
if [ ! -f "$HYPER" ]; then
  echo "ERROR: HyperBoot not found: $HYPER"
  exit 5
fi
if mountpoint -q "$MNT/boot"; then
  run "${SUDO[@]}" cp -f "$HYPER" "$MNT/boot/HyperBoot.bin"
  sync
  md5sum "$HYPER" "$MNT/boot/HyperBoot.bin"
else
  echo "WARN: boot partition not mounted; HyperBoot not restored."
fi

section "Restore AP startup script"
run "${SUDO[@]}" tee "$MNT/root/usr/local/bin/start_ap.sh" >/dev/null <<'EOS'
#!/bin/bash
CON_NAME=ROCK
IFACE=$(iw dev | awk '$1=="Interface"&&($2~/^wlan/||$2~/^wl/){print $2;exit} $1=="Interface"&&f==""{f=$2} END{if(f!="")print f}')
[ -z "$IFACE" ] && echo "No Wi-Fi" && exit 1
if nmcli connection show "$CON_NAME" >/dev/null 2>&1; then
  echo "Fix AP iface: $IFACE"
  nmcli connection modify "$CON_NAME" connection.interface-name "$IFACE"
  nmcli connection up "$CON_NAME"
  exit 0
fi
MAC=$(cat /sys/class/net/$IFACE/address | awk -F: '{print $4$5$6}')
SSID="rockchip_${MAC}"
nmcli connection add type wifi con-name "$CON_NAME" autoconnect yes ssid "$SSID"
nmcli connection modify "$CON_NAME" connection.interface-name "$IFACE" 802-11-wireless.mode ap ipv4.method shared ipv4.addresses 192.168.1.1/24 wifi-sec.key-mgmt wpa-psk wifi-sec.psk "rockchip"
echo "Hotspot: $SSID $IFACE"
nmcli connection up "$CON_NAME"
EOS
run "${SUDO[@]}" chown 0:0 "$MNT/root/usr/local/bin/start_ap.sh"
run "${SUDO[@]}" chmod 755 "$MNT/root/usr/local/bin/start_ap.sh"

section "Restore web remote package"
WEB_DIR="$MNT/root/home/rock/road_repair_web_remote"
run "${SUDO[@]}" rm -rf "$WEB_DIR"
run "${SUDO[@]}" mkdir -p "$WEB_DIR/logs"
for f in \
  can_gateway_service.py \
  chassis_vcmd_client.py \
  road_repair_3508_model.py \
  road_repair_vcmd_adapter.py \
  road_repair_web_remote.py
do
  run "${SUDO[@]}" cp -f "$SHARE/board_tools/$f" "$WEB_DIR/$f"
done

run "${SUDO[@]}" tee "$MNT/root/etc/systemd/system/road-repair-web-remote.service" >/dev/null <<'EOS'
[Unit]
Description=Road Repair browser remote safe-lock service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/rock/road_repair_web_remote
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 /home/rock/road_repair_web_remote/road_repair_web_remote.py --host 0.0.0.0 --web-port 8080 --current-limit 1800 --max-speed-rpm 2000 --max-strafe-rpm 1500 --max-rotate-rpm 1600 --forward-left-turn-compensation 0 --feedback-json /home/rock/road_repair_web_remote/logs/motor_feedback.json --feedback-json-period-s 0.05 --straight-assist --straight-assist-kp 0.35 --straight-assist-trim-limit 0.08 --straight-assist-max-feedback-age-s 0.3 --straight-assist-min-axis 0.12 --straight-assist-min-rpm 80 --rt-ping-timeout 90 --udp-peer-timeout 90 --gateway-log /home/rock/road_repair_web_remote/logs/web_remote_gateway.log
Restart=on-failure
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOS
run "${SUDO[@]}" chown 0:0 "$MNT/root/etc/systemd/system/road-repair-web-remote.service"
run "${SUDO[@]}" chmod 644 "$MNT/root/etc/systemd/system/road-repair-web-remote.service"

section "Restore formal chassis migration package"
FORMAL_DIR="$MNT/root/home/rock/road_repair_chassis_migration"
run "${SUDO[@]}" rm -rf "$FORMAL_DIR"
run "${SUDO[@]}" mkdir -p "$FORMAL_DIR/logs"
for f in \
  can_gateway_service.py \
  chassis_vcmd_client.py \
  chassis_control.py \
  road_repair_3508_model.py \
  road_repair_vcmd_adapter.py \
  road_repair_chassis_task.py \
  road_repair_competition_behavior.py \
  road_repair_competition_plan.py \
  road_repair_competition_api.py \
  road_repair_virtual_devices.py \
  road_repair_virtual_mission.py \
  road_repair_topic1_runner.py \
  sample_road_repair_plan.txt \
  sample_road_repair_scenario.json \
  test_chassis_migration_core.py \
  test_road_repair_migration.py \
  run_road_repair_chassis_task_test.sh \
  run_road_repair_virtual_mission_test.sh \
  run_road_repair_migration_selfcheck.sh
do
  if [ -f "$SHARE/board_tools/$f" ]; then
    run "${SUDO[@]}" cp -f "$SHARE/board_tools/$f" "$FORMAL_DIR/$f"
  else
    echo "WARN: missing optional formal file: $f"
  fi
done
run "${SUDO[@]}" chmod +x "$FORMAL_DIR"/*.sh

section "Enable services by symlink"
run "${SUDO[@]}" mkdir -p "$MNT/root/etc/systemd/system/multi-user.target.wants"
run "${SUDO[@]}" ln -sfn ../road-repair-web-remote.service "$MNT/root/etc/systemd/system/multi-user.target.wants/road-repair-web-remote.service"
if [ -f "$MNT/root/etc/systemd/system/rockchip-ap.service" ]; then
  run "${SUDO[@]}" ln -sfn ../rockchip-ap.service "$MNT/root/etc/systemd/system/multi-user.target.wants/rockchip-ap.service"
fi

section "Fix ownership and sync"
run "${SUDO[@]}" chown -R 1000:1000 "$MNT/root/home/rock/road_repair_web_remote" "$MNT/root/home/rock/road_repair_chassis_migration"
run "${SUDO[@]}" sync

section "Post-restore summary"
ls -l "$MNT/root/usr/local/bin/start_ap.sh"
ls -l "$MNT/root/etc/systemd/system/multi-user.target.wants/road-repair-web-remote.service" || true
ls -l "$MNT/root/etc/systemd/system/multi-user.target.wants/rockchip-ap.service" || true
find "$MNT/root/home/rock/road_repair_chassis_migration" -maxdepth 1 -type f -printf '%f\n' | sort
find "$MNT/root/home/rock/road_repair_web_remote" -maxdepth 1 -type f -printf '%f\n' | sort

section "Done"
echo "Backup: $BACKUP_ROOT"
echo "Log: $LOG"
echo "Now safely disconnect/eject the TF card, insert it into RK3588, and power on."
