# 2026-06-21 32G TF Card Restore To 2026-06-18 State

## Goal

Restore the original 32G TF card to the stable chassis state around 2026-06-18 after the RK3588 board stopped booting normally.

This operation targeted the original 32G card only, not the later 64G card.

## VM And Device Facts

- VMware VM: `D:\robot\robot.vmx`
- VM user: `yx`
- VM shared folder: `/mnt/hgfs/rt`
- Card detected in VM as `/dev/sdb`
- Boot partition: `/dev/sdb1`, vfat, label `boot`, 512M
- Rootfs partition: `/dev/sdb2`, ext4, label `rootfs`, about 29.2G

Always verify these with `lsblk` before writing. Do not assume the device name will always be `/dev/sdb`.

## Restored State

- Restored RT boot image:
  - Source: `E:\BaiduNetdiskDownload\rt\build_outputs\local_rtt_32G_20260614_143025\HyperBoot.bin`
  - Target: TF boot partition `/HyperBoot.bin`
  - Verified MD5: `44ac4e9524aa40bccfc602f21c1c35a7`
- Restored hotspot startup script:
  - Target: `/usr/local/bin/start_ap.sh`
  - Important fix: accepts both `wlan*` and `wl*` wireless interface names.
- Restored browser remote package:
  - Target: `/home/rock/road_repair_web_remote`
  - Systemd service: `/etc/systemd/system/road-repair-web-remote.service`
  - Enabled symlink: `/etc/systemd/system/multi-user.target.wants/road-repair-web-remote.service`
  - Service starts in safe-lock mode. Real movement still requires explicit unlock in the webpage.
- Restored formal chassis migration package:
  - Target: `/home/rock/road_repair_chassis_migration`
- Restored/enabled AP service symlink:
  - `/etc/systemd/system/multi-user.target.wants/rockchip-ap.service`

## Logs And Backups

- Main restore log:
  - `E:\BaiduNetdiskDownload\rt\vm_logs\restore_32g_tf_to_0618_20260621_183144.log`
- Final verification log:
  - `E:\BaiduNetdiskDownload\rt\vm_logs\verify_32g_tf_restore_latest.log`
- Metadata fix log:
  - `E:\BaiduNetdiskDownload\rt\vm_logs\fix_32g_tf_restore_metadata_latest.log`
- Stale mount cleanup log:
  - `E:\BaiduNetdiskDownload\rt\vm_logs\rk3588_cleanup_restore_mounts.log`
- Card pre-restore backup:
  - `E:\BaiduNetdiskDownload\rt\rk3588_migration\tf_card_recovery\32g_restore_20260621_183144`

## Key Lessons

1. If the VM cannot see `/mnt/hgfs/rt`, remount VMware shared folders:

   ```bash
   sudo mkdir -p /mnt/hgfs
   sudo vmhgfs-fuse .host:/ /mnt/hgfs -o allow_other
   ```

2. Before restoring, identify the TF card by size, transport, partition labels, and root disk exclusion. Never write to a disk only because it is named `/dev/sdb`.

3. Do not tar the whole `/home/rock` directory during recovery. It can contain `.nx` socket/runtime files, and tar may hang for a long time. Use targeted backups only:

   - `/usr/local/bin/start_ap.sh`
   - `/etc/systemd/system/rockchip-ap.service`
   - `/etc/systemd/system/road-repair-web-remote.service`
   - `/etc/NetworkManager/system-connections/ROCK.nmconnection`
   - `/home/rock/images`
   - `/home/rock/road_repair_web_remote`
   - `/home/rock/road_repair_chassis_migration`

4. `e2fsck -fy` exit code `1` means filesystem errors were corrected. Treat `0` and `1` as acceptable for this recovery workflow; other codes need investigation.

5. If restore is stuck, check for stale restore mounts and tar processes:

   ```bash
   mount | grep rk3588_32g_restore
   sudo fuser -vm /tmp/rk3588_32g_restore_*/root
   ps -ef | grep -E 'restore_32g_tf|tar -C /tmp/rk3588_32g_restore'
   ```

6. After every card operation, run `sync`, unmount all card partitions, and verify no `/dev/sdb*` or `rk3588_32g_*` mount remains before removing the card.

7. Keep module boundaries clean:

   - Chassis files stay in `road_repair_chassis_migration` and `road_repair_web_remote`.
   - Arm files stay in the Piper/arm folders.
   - IMU files stay in `imu_dev`.
   - TF-card recovery records stay in `rk3588_migration/tf_card_recovery`.

## Repeat Procedure

1. Connect the 32G card reader to the VM.
2. Ensure `/mnt/hgfs/rt` is mounted.
3. Run:

   ```bash
   echo 000000 | sudo -S bash /mnt/hgfs/rt/vm_scripts/restore_32g_tf_to_0618.sh
   echo 000000 | sudo -S bash /mnt/hgfs/rt/vm_scripts/fix_32g_tf_restore_metadata.sh
   echo 000000 | sudo -S bash /mnt/hgfs/rt/vm_scripts/verify_32g_tf_restore.sh
   ```

4. Confirm verification reports:

   - `HyperBoot.bin` MD5 is `44ac4e9524aa40bccfc602f21c1c35a7`
   - `start_ap.sh` includes both `wlan` and `^wl`
   - `road-repair-web-remote.service` exists and is enabled
   - `road_repair_web_remote` and `road_repair_chassis_migration` exist

5. Disconnect/eject the card from the VM, insert it into RK3588, power on, wait 60-90 seconds, then check the hotspot and SSH.
