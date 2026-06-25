#!/usr/bin/env bash
set -u

ROOT="$HOME/Desktop/rock_ws/sdk"
RTT_APP="$ROOT/rockchip-hypercar/software/RK3588"
HYPERSDK="$ROOT/HyperSDK"
if [ -d "$HOME/hgfs/rt" ]; then
    SHARE_ROOT="$HOME/hgfs/rt"
elif [ -d "/mnt/hgfs/rt" ]; then
    SHARE_ROOT="/mnt/hgfs/rt"
else
    echo "Cannot find shared folder at $HOME/hgfs/rt or /mnt/hgfs/rt"
    exit 1
fi
LOG_DIR="$SHARE_ROOT/vm_logs"
OUT_ROOT="$SHARE_ROOT/build_outputs"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="$OUT_ROOT/local_rtt_32G_$STAMP"
BACKUP_DIR="$HYPERSDK/codex_backup_$STAMP"

LOCAL_RTT="$RTT_APP/rtthread.bin"
TARGET_RTT="$HYPERSDK/target/rtthread.bin"
TARGET_HYPERBOOT="$HYPERSDK/target/HyperBoot.bin"
LOG="$LOG_DIR/hyper_rebuild_with_local_rtt_32G.log"
FLAVOR="N-U6_N-R2_CAR_NPU_32G"
VM_LINUX="$HYPERSDK/flavor/$FLAVOR/vm_linux.yaml"
VM_RTT="$HYPERSDK/flavor/$FLAVOR/vm_rtt.yaml"

mkdir -p "$LOG_DIR" "$OUT_DIR" "$BACKUP_DIR"

echo "== Verify local RT-Thread image =="
if [ ! -f "$LOCAL_RTT" ]; then
    echo "Cannot find local rtthread.bin: $LOCAL_RTT"
    exit 1
fi
ls -lh "$LOCAL_RTT"
md5sum "$LOCAL_RTT" | tee "$LOG_DIR/local_rtt_before_hyper_rebuild.md5"

echo "== Backup HyperSDK target images =="
if [ -f "$TARGET_RTT" ]; then
    cp -a "$TARGET_RTT" "$BACKUP_DIR/rtthread.bin.before"
fi
if [ -f "$TARGET_HYPERBOOT" ]; then
    cp -a "$TARGET_HYPERBOOT" "$BACKUP_DIR/HyperBoot.bin.before"
fi

echo "== Replace HyperSDK target rtthread.bin with local build =="
cp -a "$LOCAL_RTT" "$TARGET_RTT"
ls -lh "$TARGET_RTT"
md5sum "$TARGET_RTT" | tee "$LOG_DIR/hypersdk_target_rtt_after_replace.md5"

echo "== Snapshot HyperSDK VM configs =="
if [ -f "$VM_LINUX" ] && [ -f "$VM_RTT" ]; then
    cp -a "$VM_LINUX" "$OUT_DIR/vm_linux.yaml"
    cp -a "$VM_RTT" "$OUT_DIR/vm_rtt.yaml"
    grep -n "pcie_ivshmem@1\|pcie_ivshmem@2\|backend=string,shm@1\|class=16u,0x0500" \
        "$VM_LINUX" "$VM_RTT" | tee "$OUT_DIR/raw_ivshmem_config.txt" || true
else
    echo "HyperSDK VM config files not found, skip snapshot"
fi

echo "== Rebuild HyperBoot.bin for $FLAVOR =="
cd "$HYPERSDK" || exit 1
make run_rockpi5b DOCKER_TERM_OPTS=-i USR_CMD="make build FLAVOR=$FLAVOR" > "$LOG" 2>&1
status=$?

echo "== HyperSDK build finished with status $status =="
if [ -f "$TARGET_HYPERBOOT" ]; then
    cp -a "$TARGET_HYPERBOOT" "$OUT_DIR/HyperBoot.bin"
    cp -a "$TARGET_RTT" "$OUT_DIR/rtthread.bin"
    md5sum "$OUT_DIR/HyperBoot.bin" "$OUT_DIR/rtthread.bin" | tee "$OUT_DIR/md5.txt"
    ls -lh "$OUT_DIR"
else
    echo "HyperBoot.bin was not generated"
fi

echo "Log: $LOG"
echo "Output: $OUT_DIR"
echo "Backup: $BACKUP_DIR"
exit "$status"
