# 2026-06-23 Shrink rockpi_car_32G.img For Smaller 32G TF Card

## Why

BalenaEtcher rejected the image because the official image was larger than the actual TF card capacity.

- Source image size: `31,914,983,424` bytes
- TF card size shown by Windows: `31,268,536,320` bytes
- Difference: about `646 MB`

This is a normal "32G card capacity differs by vendor" issue. Do not force-write the original image.

## Source And Output

- User-specified source image:
  - `D:\rockpi_car_32G.img`
- Working copy:
  - `E:\BaiduNetdiskDownload\rt\image_work\rockpi_car_32G.img`
- Shrunk output image:
  - `E:\BaiduNetdiskDownload\rt\image_work\rockpi_car_32G_shrunk_31_18GB_20260623_113526.img`
- Output image size:
  - `31,180,800,000` bytes
- Margin versus current TF card:
  - about `87 MB`

## What Was Changed

Only a copy of the source image was changed. The original `D:\rockpi_car_32G.img` was not modified.

The image layout after shrink:

- Partition 1: boot, FAT32, 512MB
- Partition 2: rootfs, ext4, about 30.63GB
- GPT backup header moved to the new end of the image

## Verification

Final verification log:

- `E:\BaiduNetdiskDownload\rt\vm_logs\verify_shrunk_rockpi_image.log`

Verification results:

- GPT: `No problems found`
- rootfs: `clean`
- rootfs block count: `7477327`
- rootfs free blocks: `3958784`
- image size is smaller than the target TF card

## Important Notes

This shrunk image is an official base image shrink, not yet the restored 2026-06-18 project state.

After the card boots, restore our project state again:

- 6.18 `HyperBoot.bin`
- fixed `/usr/local/bin/start_ap.sh`
- `road_repair_web_remote`
- `road_repair_chassis_migration`
- systemd autostart links

Use the previous recovery script once the card can be read by the VM:

```bash
echo 000000 | sudo -S bash /mnt/hgfs/rt/vm_scripts/restore_32g_tf_to_0618.sh
echo 000000 | sudo -S bash /mnt/hgfs/rt/vm_scripts/fix_32g_tf_restore_metadata.sh
echo 000000 | sudo -S bash /mnt/hgfs/rt/vm_scripts/verify_32g_tf_restore.sh
```

## Lessons

1. A "32G" TF card is not guaranteed to fit a "32G" image.
2. BalenaEtcher refusing "space too small" is protecting the card; do not force-write.
3. Shrink workflow should be:
   - copy source image
   - repair ext4 with `e2fsck -fy`
   - shrink ext4 with `resize2fs`
   - shrink GPT partition end
   - truncate image
   - move GPT backup header with `sgdisk -e`
   - verify GPT and ext4 read-only
4. Avoid doing risky writes directly on the original image.
5. Avoid long `md5sum` on huge files over VMware shared folders; verify structure first, and compute hashes on the host if needed.
