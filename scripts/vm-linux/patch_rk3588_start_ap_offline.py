#!/usr/bin/env python3
"""Offline patch RK3588 rootfs /usr/local/bin/start_ap.sh on a TF card.

This performs one narrow write:

- Verify the target file, size, MD5, and ext4 extent.
- Backup the original file bytes and original full data block.
- Overwrite only the existing file payload bytes in-place.

It does not modify partition tables, inode metadata, fsck state, or any other
files. The replacement is padded with shell comments to the original byte size
so the ext4 inode size does not need to change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from read_ext4_rootfs_readonly import Ext4Reader


TARGET_PATH = "/usr/local/bin/start_ap.sh"
EXPECTED_OLD_MD5 = "1d6215e43a042b5edede86dab098993d"

PATCH_BODY = """#!/bin/bash
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
"""


def padded_patch(size: int) -> bytes:
    data = PATCH_BODY.encode("utf-8")
    if len(data) > size:
        raise ValueError(f"patch is {len(data)} bytes, exceeds old file size {size}")
    pad_len = size - len(data)
    if pad_len:
        filler = "\n" + ("#" * max(0, pad_len - 2)) + "\n"
        filler_bytes = filler.encode("ascii")
        if len(filler_bytes) > pad_len:
            filler_bytes = b"\n" * pad_len
        data += filler_bytes
        data += b"\n" * (size - len(data))
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch RK3588 start_ap.sh in-place on ext4 rootfs.")
    parser.add_argument("--device", default=r"\\.\Harddisk2Partition2")
    parser.add_argument("--backup-dir", default=r"E:\BaiduNetdiskDownload\rt\rk3588_migration\tf_card_recovery")
    parser.add_argument("--yes", action="store_true", help="Actually write. Omit for dry-run.")
    args = parser.parse_args()

    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    reader = Ext4Reader(args.device)
    try:
        inode = reader.resolve(TARGET_PATH)
        old_data = reader.read_file_inode(inode)
        old_md5 = hashlib.md5(old_data).hexdigest()
        extents = reader.extent_blocks(inode)
        print(json.dumps({
            "target": TARGET_PATH,
            "inode": inode.ino,
            "mode": oct(inode.mode),
            "size": inode.size,
            "old_md5": old_md5,
            "extents": extents,
            "block_size": reader.block_size,
        }, ensure_ascii=False, indent=2))

        if old_md5 != EXPECTED_OLD_MD5:
            raise SystemExit(f"Refuse to patch: old MD5 mismatch, expected {EXPECTED_OLD_MD5}, got {old_md5}")
        if not inode.is_regular:
            raise SystemExit("Refuse to patch: target is not a regular file")
        if inode.size != 880:
            raise SystemExit(f"Refuse to patch: expected size 880, got {inode.size}")
        if len(extents) != 1 or extents[0][0] != 0 or extents[0][2] < 1:
            raise SystemExit(f"Refuse to patch: unexpected extents {extents}")

        logical, physical, block_count = extents[0]
        block_offset = physical * reader.block_size
        file_offset = block_offset
        original_block = reader.read_at(block_offset, reader.block_size)
        new_data = padded_patch(inode.size)
        new_md5 = hashlib.md5(new_data).hexdigest()

        block_write = new_data + original_block[len(new_data) :]
        print(json.dumps({
            "patch_size": len(new_data),
            "patch_md5": new_md5,
            "write_offset": file_offset,
            "write_length": len(block_write),
            "file_payload_length": len(new_data),
            "dry_run": not args.yes,
        }, ensure_ascii=False, indent=2))

        if not args.yes:
            print("Dry-run only. Re-run with --yes to write.")
            return 0

        stamp = os.environ.get("TF_PATCH_TIMESTAMP")
        if not stamp:
            from datetime import datetime
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        old_file_path = backup_dir / f"start_ap.sh.before_{stamp}.bin"
        old_block_path = backup_dir / f"start_ap.sh.block_{physical}.before_{stamp}.bin"
        new_file_path = backup_dir / f"start_ap.sh.after_{stamp}.bin"
        meta_path = backup_dir / f"start_ap_patch_{stamp}.json"
        old_file_path.write_bytes(old_data)
        old_block_path.write_bytes(original_block)
        new_file_path.write_bytes(new_data)

        fd = os.open(args.device, os.O_RDWR | os.O_BINARY)
        try:
            os.lseek(fd, file_offset, os.SEEK_SET)
            written = os.write(fd, block_write)
            os.fsync(fd)
        finally:
            os.close(fd)
        if written != len(block_write):
            raise SystemExit(f"Short write: {written}/{len(block_write)}")

        # Verify using a fresh reader.
        verifier = Ext4Reader(args.device)
        try:
            verify_inode = verifier.resolve(TARGET_PATH)
            verify_data = verifier.read_file_inode(verify_inode)
            verify_md5 = hashlib.md5(verify_data).hexdigest()
        finally:
            verifier.close()

        meta = {
            "target": TARGET_PATH,
            "device": args.device,
            "inode": inode.ino,
            "mode": oct(inode.mode),
            "size": inode.size,
            "old_md5": old_md5,
            "new_md5": new_md5,
            "verify_md5": verify_md5,
            "physical_block": physical,
            "write_offset": file_offset,
            "write_length": len(block_write),
            "file_payload_length": len(new_data),
            "backup_old_file": str(old_file_path),
            "backup_old_block": str(old_block_path),
            "backup_new_file": str(new_file_path),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        if verify_md5 != new_md5:
            raise SystemExit("Patch verification failed")
        print("PATCH_OK")
        return 0
    finally:
        reader.close()


if __name__ == "__main__":
    raise SystemExit(main())
