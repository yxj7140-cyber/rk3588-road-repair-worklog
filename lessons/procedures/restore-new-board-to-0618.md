# Procedure: Restore New Board To 2026-06-18 State

Use this when the repaired/replacement RK3588 board arrives.

## Strict Order

1. Boot a known-good base image.
2. Re-apply the fan-control fix first, using the same method as the previous board.
3. Verify SSH and stable network access.
4. Restore the 6.18-target RT and Linux-side packages.
5. Verify safe-lock web remote.
6. Verify CAN/RT communication.
7. Run chassis tests only after explicit safety confirmation.

## Restore Components

- `HyperBoot.bin`
  - Local path: `E:\BaiduNetdiskDownload\rt\build_outputs\local_rtt_32G_20260614_143025\HyperBoot.bin`
  - MD5: `44ac4e9524aa40bccfc602f21c1c35a7`
- Web remote package:
  - Board path: `/home/rock/road_repair_web_remote`
- Formal chassis migration package:
  - Board path: `/home/rock/road_repair_chassis_migration`
- Hotspot fix:
  - `/usr/local/bin/start_ap.sh`
  - Must support both `wlan*` and `wl*`.

## Main Scripts

VM-side image/card restore:

```bash
sudo bash /mnt/hgfs/rt/vm_scripts/restore_32g_tf_to_0618.sh
sudo bash /mnt/hgfs/rt/vm_scripts/fix_32g_tf_restore_metadata.sh
sudo bash /mnt/hgfs/rt/vm_scripts/verify_32g_tf_restore.sh
```

Windows/board-side restore after reflash:

```powershell
E:\BaiduNetdiskDownload\rt\board_tools\restore_after_reflash_from_pc.ps1
```

## Do Not Forget

- This project now treats the removable boot medium as eMMC if using the official module/reader.
- The previous SPL log `Card did not respond to voltage select` meant the board did not initialize eMMC hardware; it was not just an image issue.
- Do not run motion tests until the web remote is locked and the user confirms safety.
