#!/usr/bin/env bash
set -u

LOG=/tmp/rk3588_cleanup_restore_mounts.log
exec >"$LOG" 2>&1

echo "== cleanup stale RK3588 restore mounts =="
date
echo "== mounts before =="
mount | grep rk3588_32g_restore || true

echo "== related processes before =="
ps -ef | grep -E 'restore_32g_tf|tar -C /tmp/rk3588_32g_restore|rk3588_32g_restore' | grep -v grep || true

echo "== fuser before =="
for m in $(mount | awk '/rk3588_32g_restore/{print $3}' | sort -r); do
  echo "-- $m"
  fuser -vm "$m" || true
done

echo "== kill stale restore/tar processes =="
pkill -f 'tar -C /tmp/rk3588_32g_restore' || true
pkill -f 'restore_32g_tf_to_0618.sh' || true
sleep 1

echo "== unmount stale restore mounts =="
for m in $(mount | awk '/rk3588_32g_restore/{print $3}' | sort -r); do
  echo "umount $m"
  umount "$m" || {
    echo "normal umount failed, lazy umount $m"
    umount -l "$m" || true
  }
done

echo "== mounts after =="
mount | grep rk3588_32g_restore || true

echo "== lsblk after =="
lsblk -o NAME,KNAME,PATH,TRAN,HOTPLUG,RM,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINT,MODEL

echo "== done =="
