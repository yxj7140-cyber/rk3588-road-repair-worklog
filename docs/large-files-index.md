# Large Files Index

Large binaries are not committed to Git. This file records where they live locally and how they are used.

## Boot And System Images

| File | Local Path | Size | Purpose | Status |
|---|---|---:|---|---|
| `rockpi_car_32G.img` | `D:\rockpi_car_32G.img` | 31.9 GB | User-specified official base image source | Keep local only |
| `rockpi_car_32G.img` working copy | `E:\BaiduNetdiskDownload\rt\image_work\rockpi_car_32G.img` | 31.9 GB | Working copy used for shrink operation | Keep local only |
| `rockpi_car_32G_shrunk_31_18GB_20260623_113526.img` | `E:\BaiduNetdiskDownload\rt\image_work\rockpi_car_32G_shrunk_31_18GB_20260623_113526.img` | 31.18 GB | Shrunk image fitting 31.3 GB official eMMC | Keep local only |
| `rockpi_car_16G.img` | `E:\BaiduNetdiskDownload\rt\虚拟\v1.1.0（新版拓展板）\images\rockpi_car_16G.img` | 31.9 GB | Vendor image, filename says 16G but actual size matches 32G image | Keep local only |
| `rockpi_car_32G.img` | `E:\BaiduNetdiskDownload\rt\虚拟\v1.1.0（新版拓展板）\images\rockpi_car_32G.img` | 31.9 GB | Vendor car image | Keep local only |
| `rockpi_car.img` | `E:\BaiduNetdiskDownload\rt\虚拟化混合部署产品资料\images\rockpi_car.img` | 31.9 GB | Original vendor car image | Keep local only |
| `ubuntu-20.04.6-desktop-amd64.iso` | `E:\BaiduNetdiskDownload\rt\虚拟化混合部署产品资料\images\ubuntu-20.04.6-desktop-amd64.iso` | large | VM installer ISO | Keep local only |

## RT / HyperBoot Outputs

| File | Local Path | Purpose | Status |
|---|---|---|---|
| Stable 6.18-target `HyperBoot.bin` | `E:\BaiduNetdiskDownload\rt\build_outputs\local_rtt_32G_20260614_143025\HyperBoot.bin` | RT image used by restore-to-0618 workflow, MD5 `44ac4e9524aa40bccfc602f21c1c35a7` | Track hash and notes, binary may be copied only if needed |
| Original backup `HyperBoot.bin` | `E:\BaiduNetdiskDownload\rt\build_outputs\backup_original_HyperBoot.bin` | Vendor/original boot image backup | Keep local unless explicitly needed |
| Rollback HyperBoot files | `E:\BaiduNetdiskDownload\rt\rk3588_migration\rollback_keep\*.bin` | At least two rollback points for chassis RT experiments | Track metadata |

## SDKs And Toolchains

| File / Folder | Local Path | Purpose | Status |
|---|---|---|---|
| Vendor SDK | `E:\BaiduNetdiskDownload\rt\虚拟化混合部署产品资料\sdk` | Official virtualization mixed-deployment SDK | Do not commit |
| New board SDK copy | `E:\BaiduNetdiskDownload\rt\虚拟\v1.1.0（新版拓展板）\sdk` | Newer extension-board vendor SDK | Do not commit |
| Toolchain archive | `E:\BaiduNetdiskDownload\rt\虚拟化混合部署产品资料\sdk\x86_linux\toolchains\gcc-arm-10.2-2020.11-x86_64-aarch64-none-elf.tar.xz` | RT build toolchain | Do not commit |
| Docker image archive | `E:\BaiduNetdiskDownload\rt\虚拟化混合部署产品资料\sdk\x86_linux\hyperenv_rockpi5b.tar.xz` | Vendor build environment | Do not commit |

## Recovery Backups

| File / Folder | Local Path | Purpose | Status |
|---|---|---|---|
| 32G/eMMC restore backup | `E:\BaiduNetdiskDownload\rt\rk3588_migration\tf_card_recovery\32g_restore_20260621_183144` | Backup made before restoring 6.18-like state | Keep local; commit summary only |
| Stuck old full home backup | `E:\BaiduNetdiskDownload\rt\rk3588_migration\tf_card_recovery\32g_restore_20260621_182110\home_rock_before.tgz` | Old broad backup that hung on `.nx` socket files | Keep local only; avoid repeating |

## Vendor Tools And Device SDKs

| File / Folder | Local Path | Purpose | Status |
|---|---|---|---|
| Piper arm Windows tool | `E:\BaiduNetdiskDownload\rt\ArmRobotTool_V1.5.4.260414_release` | Piper arm vendor upper-computer tool | Keep local only |
| Piper offline packages | `E:\BaiduNetdiskDownload\rt\board_piper\offline_pkgs` | Offline Python wheels and source archives for board-side Piper install | Keep local only; do not commit wheels/zips |
| Orbbec SDK | `E:\BaiduNetdiskDownload\rt\OrbbecSDK_C_C++_v1.10.27_20250925_0549823cb_win_x64_release` | Depth camera SDK | Keep local only |
| Orbbec Viewer | `E:\BaiduNetdiskDownload\rt\OrbbecViewer_v1.10.27_202509252154_win_x64_release` | Depth camera viewer | Keep local only |
| IMU Windows venv | `E:\BaiduNetdiskDownload\rt\imu_dev\.venv` | Local Python environment for WT901C-TTL PC tests | Keep local only; recreate from requirements |

## Logs And Captures

| File / Folder | Local Path | Purpose | Status |
|---|---|---|---|
| VM logs | `E:\BaiduNetdiskDownload\rt\vm_logs` | VM script output and recovery logs | Keep local; commit only distilled lessons |
| Piper logs | `E:\BaiduNetdiskDownload\rt\board_piper\logs` | Arm bring-up, J5 issue, Wi-Fi probe, and install logs | Keep local; commit selected notes only |
| IMU captures | `E:\BaiduNetdiskDownload\rt\imu_dev\captures` | WT901C-TTL CSV captures | Keep local unless a small selected sample is needed |
| IMU logs | `E:\BaiduNetdiskDownload\rt\imu_dev\logs` | WT901C-TTL read logs | Keep local unless a small selected sample is needed |

## Notes

- Do not commit `.img`, `.iso`, `.tar`, `.tar.xz`, `.zip`, `.exe`, `.deb`, or large SDK directories.
- If a large file becomes necessary for release, use GitHub Releases or external storage, not normal Git history.
- Every image used for flashing must have a matching note under `images/` with size, hash if available, source path, and test status.
