# Project Timeline And Key Decisions Through 2026-06-26

This document condenses the long Codex conversation into a practical memory aid. Use it before resuming work on the repaired/replacement RK3588 board.

## 1. Original Goal

The project goal is to migrate `Road_Repair_freertos` style road-repair logic to an RK3588 board with mixed Linux/RT deployment.

Competition task:

1. Automatically patrol a preset road.
2. Detect potholes or cracks.
3. Move the chassis to the repair area.
4. Use the arm-mounted depth camera to align with the defect.
5. Start a peristaltic pump to inject cement.
6. Pedestrian avoidance was discussed but later removed from the current requirement.

Main hardware modules:

- Chassis
- Depth camera
- Piper arm
- Peristaltic pump
- Lidar
- IMU as chassis-assist hardware

## 2. Architecture Decision

The validated direction is:

```text
Linux side:
  USB-CAN gateway
  web remote debug tool
  perception/planning/integration
  arm/camera/lidar/pump high-level orchestration

RT side:
  chassis real-time execution path
  VCMD/runtime command handling
```

For the chassis specifically, the chosen mainline was:

```text
USB-CAN + Linux gateway + RT control
```

Reason:

- It was the fastest and lowest-risk path.
- CAN bus was already proven alive.
- Motor feedback from `0x201` to `0x204` had been observed.

## 3. VM And Development Environment

VM facts:

```text
VMX: D:\robot\robot.vmx
user: yx
password: 000000
shared folder: /mnt/hgfs/rt
Windows workspace: E:\BaiduNetdiskDownload\rt
```

Important VM lessons:

- `vmrun` often hides guest stdout, so write logs to `/tmp` and copy them back.
- `/mnt/hgfs/rt` can disappear after reboot.
- If `vmware-hgfsclient` lists `rt`, remount with:

```bash
sudo mkdir -p /mnt/hgfs
sudo vmhgfs-fuse .host:/ /mnt/hgfs -o allow_other
```

## 4. RT Build And HyperBoot

The stable RT boot artifact for the 2026-06-18 baseline is:

```text
E:\BaiduNetdiskDownload\rt\build_outputs\local_rtt_32G_20260614_143025\HyperBoot.bin
MD5: 44ac4e9524aa40bccfc602f21c1c35a7
```

Earlier build work involved:

- disabling/skipping micro-ROS for baseline RT build
- fixing header conflicts
- adding POSIX/header compatibility pieces
- rebuilding `HyperBoot.bin`

For normal board recovery, do not rebuild RT first. Use the stable `HyperBoot.bin` above.

## 5. Chassis Progress

Validated chassis work:

- USB-CAN communication worked.
- Motor feedback logs were usable to judge motion.
- Four 3508 motors were mapped.
- Direction mapping was iteratively corrected.
- Forward/back/strafe/rotate tests were performed both with wheels suspended and on the ground.
- Web remote could control the chassis after safe unlock.
- Safe-lock mode was added and made the default.
- Web remote was configured for autostart.
- Straight-line control using motor feedback was attempted.

Remaining chassis limitation:

- Ground straight-line driving still needs more robust yaw feedback.
- IMU yaw closed-loop correction is the preferred next improvement, but not a blocker for restoring the 2026-06-18 baseline.

## 6. Web Remote

Purpose:

```text
Manual debug tool because there is no physical remote controller.
Not part of the final competition task requirement.
```

Stable board path:

```text
/home/rock/road_repair_web_remote
```

Systemd service:

```text
road-repair-web-remote.service
```

Default behavior:

```text
safe-lock mode
enable_current=false
real motion requires explicit web unlock
```

Useful URL:

```text
http://<BOARD_IP>:8080/
http://<BOARD_IP>:8080/api/status
```

## 7. Network Lessons

Do not guess the connection mode.

Validated options:

1. Same WLAN/campus network
   - historical board IPs: `10.11.198.140`, `10.21.50.12`
   - preferred when it works because PC keeps internet

2. Wired Ethernet
   - use only if user explicitly says cable is connected
   - historical pattern: board around `192.168.137.152`

3. Board hotspot short-switch
   - recovery only
   - board IP: `192.168.1.1`
   - disconnects PC from normal internet

Procedure file:

```text
lessons/procedures/connect-board-wireless.md
```

## 8. Mechanical Arm

Arm model:

```text
Piper
```

Development notes:

- Windows vendor upper-computer tool could read state.
- pyAgxArm and board-side Piper code were tested.
- Board-side arm files were kept separate from chassis files.
- Two USB-CAN adapters were recommended for final architecture: one for chassis, one for arm.
- J5 joint had repeated issues and was paused for vendor support.

Important safety decision:

- Do not resume arm motion blindly.
- Keep Piper work isolated under `modules/arm`.

## 9. IMU

IMU:

```text
WT901C-TTL
```

PC testing:

- Auto-detected baud rate: `9600`
- Static tests and manual rotation tests were performed.
- User confirmed clockwise orientation from top-down view.

Role:

- Use yaw for chassis straight-line assist.
- Linux can read and compute yaw correction.
- RT does not need to directly own the IMU for the current architecture.

## 10. Lidar, Camera, Pump

These modules are not yet developed to the same depth as chassis/arm.

Current boundaries:

- `modules/camera`: RGB-D, point cloud, defect recognition, hand-eye calibration
- `modules/lidar`: lidar networking, navigation/mapping/path support
- `modules/pump`: pump enable/flow timing and safety interlocks

Integration layer:

```text
integration/
```

Simulated devices should be used until hardware is ready.

## 11. eMMC / Image / Boot-Medium Lessons

The official eMMC was readable from Windows through the Genesys reader:

```text
Disk: Genesys UFD
GPT present
Partition 1: 512MB EFI/System
Partition 2: Linux filesystem
```

The old board still logged:

```text
Trying to boot from MMC1
Card did not respond to voltage select!
SPL: failed to boot from all boot devices
```

Conclusion:

- The old board did not initialize eMMC hardware.
- This was not simply an Etcher/image issue.
- The board was sent to the vendor for repair.

Image shrink lesson:

- The original `rockpi_car_32G.img` was larger than the official 31.3GB eMMC.
- A shrunk image was created:

```text
E:\BaiduNetdiskDownload\rt\image_work\rockpi_car_32G_shrunk_31_18GB_20260623_113526.img
size: 31,180,800,000 bytes
```

This file is local-only and tracked in `docs/large-files-index.md`.

## 12. Recovery Baseline

The intended restored board state is the 2026-06-18 chassis baseline:

```text
/boot/HyperBoot.bin
/home/rock/road_repair_web_remote
/home/rock/road_repair_chassis_migration
road-repair-web-remote.service enabled
rockchip-ap.service enabled
start_ap.sh supports wlan* and wl*
```

Main restore procedures:

```text
lessons/procedures/restore-new-board-to-0618.md
lessons/procedures/20260621_32g_restore_to_0618_summary.md
```

## 13. Fan-Control Gap

The user explicitly requested:

```text
New board first step: rewrite/fix fan program, then restore to 6.18 state.
```

Current status:

- No mature fan-control script was found in the current local files.
- The runbook marks this as Phase 1 and a required gap to fill when the new board arrives.

Do not skip this step during replacement-board bring-up.

## 14. GitHub Repository State

Repository:

```text
https://github.com/yxj7140-cyber/rk3588-road-repair-worklog
```

Local working copy:

```text
E:\BaiduNetdiskDownload\rt\github_work\rk3588-road-repair-worklog
```

Policy:

- GitHub stores small source, scripts, notes, and procedures.
- Large images, SDKs, VM artifacts, logs, wheels, zips, and virtualenvs stay local.
- Large files are tracked by local path in `docs/large-files-index.md`.

## 15. Next Work Before Board Arrives

Best next tasks:

1. Finish and review the new-board restore runbook.
2. Prepare a fan-control procedure placeholder and fill it when board arrives.
3. Build a board self-check script that verifies SSH, HyperBoot MD5, web service, safe-lock, CAN presence, and package paths.
4. Keep camera/lidar/pump interfaces modular and simulated until hardware is ready.

## 16. New Board First-Hour Objective

When the repaired board arrives, success means:

1. Board boots a known-good image.
2. Fan fix is applied or explicitly documented as blocked.
3. SSH works.
4. 2026-06-18 `HyperBoot.bin` is restored.
5. Web remote starts in safe-lock mode.
6. Chassis migration package exists and selfcheck passes.
7. CAN/RT link is verified without real motion.

Only then continue new development.
