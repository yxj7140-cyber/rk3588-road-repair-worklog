# New Board Restore Plan

This is the fast recovery checklist for a replacement RK3588 board.

## Goal

Bring a fresh board back to the stable state reached around 2026-06-18.

## High-Level Order

1. Confirm board boots a known-good base image.
2. Apply the fan-control fix first, using the same method as the previous board.
3. Restore the 6.18-target RT image and Linux-side files.
4. Verify hotspot / SSH connectivity.
5. Verify web remote starts in safe-lock mode.
6. Verify chassis CAN gateway and RT communication before any real movement.
7. Only run motion tests after explicit safety confirmation.

## 6.18 Restore Components

- Stable `HyperBoot.bin`:
  - `E:\BaiduNetdiskDownload\rt\build_outputs\local_rtt_32G_20260614_143025\HyperBoot.bin`
  - MD5: `44ac4e9524aa40bccfc602f21c1c35a7`
- Fixed hotspot script:
  - `/usr/local/bin/start_ap.sh`
  - Must support both `wlan*` and `wl*` interface names.
- Browser remote:
  - Board path: `/home/rock/road_repair_web_remote`
  - Must start in safe-lock mode.
- Formal chassis migration package:
  - Board path: `/home/rock/road_repair_chassis_migration`
- Systemd:
  - `road-repair-web-remote.service`
  - `rockchip-ap.service`

## Existing Recovery Scripts

Keep these scripts available for the replacement board workflow:

- `E:\BaiduNetdiskDownload\rt\vm_scripts\restore_32g_tf_to_0618.sh`
- `E:\BaiduNetdiskDownload\rt\vm_scripts\fix_32g_tf_restore_metadata.sh`
- `E:\BaiduNetdiskDownload\rt\vm_scripts\verify_32g_tf_restore.sh`
- `E:\BaiduNetdiskDownload\rt\board_tools\restore_after_reflash_from_pc.ps1`

## Safety Rule

Do not run real chassis motion until:

- CAN device mapping is confirmed.
- RT communication is alive.
- Web remote is in safe-lock mode.
- User confirms the chassis is safe.
