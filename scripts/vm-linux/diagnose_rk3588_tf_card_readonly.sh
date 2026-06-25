#!/usr/bin/env bash
set -u

LOG_DIR="/mnt/hgfs/rt/vm_logs"
if [ ! -d /mnt/hgfs/rt ]; then
  LOG_DIR="$HOME/Desktop/rt_vm_logs"
fi
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
LOG="$LOG_DIR/tf_card_readonly_diag_${TS}.log"
MNT_BASE="/tmp/rk3588_tf_diag_${TS}"

exec > >(tee "$LOG") 2>&1

section() {
  echo
  echo "========== $* =========="
}

run() {
  echo
  echo "+ $*"
  "$@" || true
}

cleanup() {
  sync || true
  if mountpoint -q "$MNT_BASE/boot"; then
    sudo umount "$MNT_BASE/boot" || true
  fi
  if mountpoint -q "$MNT_BASE/root"; then
    sudo umount "$MNT_BASE/root" || true
  fi
}
trap cleanup EXIT

section "Start"
echo "Log: $LOG"
echo "Mode: read-only diagnostics. No repair, no format, no write mount."
date
id

section "Kernel And Block Devices"
run uname -a
run lsblk -o NAME,KNAME,PATH,TRAN,HOTPLUG,RM,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
run sudo blkid
run sudo fdisk -l
run dmesg -T

section "Find Candidate TF Card"
ROOT_DISK="$(lsblk -ndo PKNAME "$(findmnt -n -o SOURCE /)" 2>/dev/null || true)"
echo "Root disk parent: ${ROOT_DISK:-unknown}"

mapfile -t CANDIDATES < <(
  lsblk -ndo NAME,TYPE,TRAN,RM,SIZE,MODEL |
    awk -v root="$ROOT_DISK" '
      $2=="disk" && $1!=root {
        if ($3=="usb" || $4=="1") print "/dev/"$1
      }
    '
)

if [ "${#CANDIDATES[@]}" -eq 0 ]; then
  echo "No removable/USB disk candidate found inside VM."
  echo "If the TF card is still attached to Windows, connect it to VMware first:"
  echo "VMware Workstation -> VM -> Removable Devices -> Generic STORAGE DEVICE -> Connect (Disconnect from Host)."
  exit 10
fi

printf 'Candidates:\n'
printf '  %s\n' "${CANDIDATES[@]}"

CARD="${CANDIDATES[0]}"
if [ "${#CANDIDATES[@]}" -gt 1 ]; then
  echo "Multiple candidates found; using first candidate only: $CARD"
fi
echo "Selected card: $CARD"

section "Selected Card Partition Detail"
run lsblk -f "$CARD"
run sudo parted -s "$CARD" unit s print
run sudo sgdisk -p "$CARD"

BOOT_PART=""
ROOT_PART=""
while read -r part fstype label; do
  case "$fstype" in
    vfat|fat16|fat32|msdos)
      [ -z "$BOOT_PART" ] && BOOT_PART="$part"
      ;;
    ext2|ext3|ext4)
      [ -z "$ROOT_PART" ] && ROOT_PART="$part"
      ;;
  esac
done < <(lsblk -lnpo NAME,FSTYPE,LABEL "$CARD" | awk 'NF>=2 {print $1,$2,$3}')

echo "Detected boot partition: ${BOOT_PART:-none}"
echo "Detected root partition: ${ROOT_PART:-none}"

section "Read-only Filesystem Checks"
if [ -n "$BOOT_PART" ]; then
  run sudo fsck.vfat -n "$BOOT_PART"
fi
if [ -n "$ROOT_PART" ]; then
  run sudo e2fsck -fn "$ROOT_PART"
fi

section "Read-only Mount"
mkdir -p "$MNT_BASE/boot" "$MNT_BASE/root"
if [ -n "$BOOT_PART" ]; then
  run sudo mount -o ro "$BOOT_PART" "$MNT_BASE/boot"
fi
if [ -n "$ROOT_PART" ]; then
  run sudo mount -o ro,noload "$ROOT_PART" "$MNT_BASE/root"
fi

section "Boot Partition Contents"
if mountpoint -q "$MNT_BASE/boot"; then
  run sudo find "$MNT_BASE/boot" -maxdepth 3 -printf '%M %s %TY-%Tm-%Td %TH:%TM %p\n'
  for f in HyperBoot.bin boot.scr extlinux/extlinux.conf uEnv.txt config.txt cmdline.txt; do
    if [ -e "$MNT_BASE/boot/$f" ]; then
      echo
      echo "--- boot/$f ---"
      if [ -f "$MNT_BASE/boot/$f" ]; then
        sudo file "$MNT_BASE/boot/$f" || true
        sudo md5sum "$MNT_BASE/boot/$f" || true
        case "$f" in
          *.conf|*.txt|uEnv.txt|cmdline.txt)
            sudo sed -n '1,160p' "$MNT_BASE/boot/$f" || true
            ;;
        esac
      fi
    fi
  done
else
  echo "Boot partition not mounted."
fi

section "Rootfs Important Files"
if mountpoint -q "$MNT_BASE/root"; then
  for p in \
    etc/os-release \
    etc/fstab \
    etc/hostname \
    etc/hosts \
    etc/NetworkManager/NetworkManager.conf \
    etc/netplan \
    etc/systemd/network \
    etc/NetworkManager/system-connections \
    etc/hostapd \
    etc/dnsmasq.conf \
    etc/systemd/system \
    home/rock
  do
    if [ -e "$MNT_BASE/root/$p" ]; then
      echo
      echo "--- root/$p ---"
      sudo find "$MNT_BASE/root/$p" -maxdepth 2 -printf '%M %s %TY-%Tm-%Td %TH:%TM %p\n' 2>/dev/null || true
      if [ -f "$MNT_BASE/root/$p" ]; then
        sudo sed -n '1,200p' "$MNT_BASE/root/$p" || true
      fi
    fi
  done

  section "Search Board Startup And Project Files"
  run sudo find "$MNT_BASE/root/etc/systemd/system" "$MNT_BASE/root/lib/systemd/system" -maxdepth 2 \
    \( -iname '*chassis*' -o -iname '*can*' -o -iname '*web*' -o -iname '*road*' -o -iname '*hostapd*' -o -iname '*dnsmasq*' -o -iname '*NetworkManager*' \) \
    -printf '%M %s %TY-%Tm-%Td %TH:%TM %p\n'
  run sudo find "$MNT_BASE/root/home/rock" -maxdepth 4 \
    \( -iname '*chassis*' -o -iname '*can*' -o -iname '*web*' -o -iname '*road*' -o -iname '*imu*' -o -iname '*.py' -o -iname '*.service' \) \
    -printf '%M %s %TY-%Tm-%Td %TH:%TM %p\n'
else
  echo "Rootfs partition not mounted."
fi

section "Done"
echo "Log saved: $LOG"
