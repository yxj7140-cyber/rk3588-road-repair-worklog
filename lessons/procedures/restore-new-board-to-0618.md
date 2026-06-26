# Procedure: Restore New Board To 2026-06-18 State

Use this when the repaired or replacement RK3588 board arrives.

The goal is to recover the project to the known-good chassis state reached around 2026-06-18 without rediscovering the network, VM, image, CAN, and web-remote steps.

## Current Truth

- The old board was sent back because it could not initialize the official eMMC from the board side.
- Windows could read the official eMMC through the reader, so the image and eMMC contents were not the only suspect.
- The SPL log line `Card did not respond to voltage select` meant the board did not initialize eMMC hardware.
- The replacement board must first prove that it can boot a known-good image before any project restore.
- The first project-specific action requested by the user is to redo the fan-control fix, then restore the 2026-06-18 project state.

## Hard Safety Rules

1. Do not run real chassis motion before explicit user safety confirmation.
2. Web remote must start in safe-lock mode.
3. Board-resident temporary test scripts must be deleted after use, but saved in this repo or local workspace first.
4. Do not guess the board network path. Follow `connect-board-wireless.md`.
5. Do not repeat VM/shared-folder discovery. Follow `connect-vm-from-windows.md` and `vmware-shared-folder.md`.
6. Do not commit large images, SDKs, logs, virtualenvs, or offline wheel packages.

## Local Paths That Matter

Workspace:

```text
E:\BaiduNetdiskDownload\rt
```

GitHub working copy:

```text
E:\BaiduNetdiskDownload\rt\github_work\rk3588-road-repair-worklog
```

Stable HyperBoot:

```text
E:\BaiduNetdiskDownload\rt\build_outputs\local_rtt_32G_20260614_143025\HyperBoot.bin
MD5: 44ac4e9524aa40bccfc602f21c1c35a7
```

Restore script from PC:

```text
E:\BaiduNetdiskDownload\rt\board_tools\restore_after_reflash_from_pc.ps1
```

VM scripts:

```text
E:\BaiduNetdiskDownload\rt\vm_scripts\restore_32g_tf_to_0618.sh
E:\BaiduNetdiskDownload\rt\vm_scripts\fix_32g_tf_restore_metadata.sh
E:\BaiduNetdiskDownload\rt\vm_scripts\verify_32g_tf_restore.sh
```

SSH key:

```text
E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519
```

## Phase 0: Confirm The Board And Boot Medium

Do this before restoring project files.

1. Insert known-good boot medium.
2. Power on.
3. Watch serial log.
4. Confirm the boot medium initializes.

Expected for a healthy board:

```text
DDR init succeeds
U-Boot SPL starts
MMC/eMMC init succeeds
Kernel or U-Boot proper continues
```

Bad eMMC-side symptom from the failed board:

```text
Trying to boot from MMC1
Card did not respond to voltage select!
SPL: failed to boot from all boot devices
```

If this appears again on the new board with official eMMC fully seated, stop and handle hardware/boot-firmware diagnosis before project restore.

## Phase 1: Fan-Control Fix

The user explicitly requested that the fan program/fix be redone first on the new board.

Current status:

- A mature fan-control script has not yet been found in the local project files.
- Existing search only found unrelated `thermal` header work from early RT compile attempts.
- Treat fan-control as a required first-task gap, not as an already automated step.

When the board arrives:

1. Inspect current fan behavior.
2. Locate the previous fix if available from user memory, board filesystem, or vendor docs.
3. Save the final fan procedure in:

   ```text
   lessons/procedures/fan-control-setup.md
   scripts/recovery/
   ```

4. Only after the fan fix is confirmed, continue to Phase 2.

Do not silently skip this step.

Procedure placeholder:

```text
lessons/procedures/fan-control-setup.md
```

## Phase 2: Establish Network Access

Use the decision rule from `connect-board-wireless.md`.

Preferred order:

1. Same WLAN/campus network if available.
2. Wired Ethernet if user says cable is connected.
3. Board hotspot short-switch only as recovery.

Known historical WLAN IPs:

```text
10.11.198.140
10.21.50.12
```

Historical wired recovery pattern:

```text
PC Ethernet/ICS: 192.168.137.1/24
Board Ethernet: 192.168.137.152/24
```

Board hotspot recovery:

```text
SSID: rockchip_decdfa or rockchip_xxxxxx
Board IP: 192.168.1.1
SSH: rock@192.168.1.1
```

Basic probe:

```powershell
ping <BOARD_IP>
ssh -i "E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519" `
  -o BatchMode=yes `
  -o ConnectTimeout=5 `
  -o StrictHostKeyChecking=no `
  rock@<BOARD_IP> "hostname; ip -br addr; ip route"
```

If key login fails after fresh image, use password login once, then restore authorized key.

## Phase 3: Restore SSH Key If Needed

If the new board was reflashed and key login is missing:

```powershell
Get-Content "E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519.pub" |
ssh rock@<BOARD_IP> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

Password historically used:

```text
rock
```

Verify:

```powershell
ssh -i "E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519" rock@<BOARD_IP> "hostname"
```

## Phase 4: Restore 2026-06-18 Project State From PC

Use this if the board is booted and reachable over SSH.

```powershell
powershell -ExecutionPolicy Bypass -File "E:\BaiduNetdiskDownload\rt\board_tools\restore_after_reflash_from_pc.ps1" -BoardIp <BOARD_IP>
```

This script restores:

- `/boot/HyperBoot.bin`
- `/home/rock/road_repair_web_remote`
- `/home/rock/road_repair_chassis_migration`
- `road-repair-web-remote.service`
- web remote safe-lock autostart

Expected script checks:

- HyperBoot MD5 matches `44ac4e9524aa40bccfc602f21c1c35a7`
- `road-repair-web-remote.service` is enabled and active
- `/api/status` is readable locally on the board
- formal migration selfcheck passes

## Phase 5: Restore 2026-06-18 State Offline Through VM

Use this if the boot medium is connected to the VM as a removable disk/eMMC reader and the board itself is not booted.

VM facts:

```text
VMX: D:\robot\robot.vmx
user: yx
password: 000000
shared folder: /mnt/hgfs/rt
```

Mount shared folder if missing:

```bash
sudo mkdir -p /mnt/hgfs
sudo vmhgfs-fuse .host:/ /mnt/hgfs -o allow_other
```

Run:

```bash
sudo bash /mnt/hgfs/rt/vm_scripts/restore_32g_tf_to_0618.sh
sudo bash /mnt/hgfs/rt/vm_scripts/fix_32g_tf_restore_metadata.sh
sudo bash /mnt/hgfs/rt/vm_scripts/verify_32g_tf_restore.sh
```

Important lessons:

- The restore script should detect exactly one 28-35 GB removable disk.
- Treat `e2fsck -fy` exit code `0` and `1` as acceptable; `1` means repaired.
- Do not tar the whole `/home/rock`; `.nx` socket files can hang tar.
- Verify no stale mount remains before removing the boot medium.

## Phase 6: Verify Web Remote Safe-Lock

Open:

```text
http://<BOARD_IP>:8080/
```

API:

```powershell
curl http://<BOARD_IP>:8080/api/status
```

Expected:

```text
service responds
safe-lock / enable_current=false
no motion until unlocked intentionally
```

Board-side:

```bash
systemctl status road-repair-web-remote --no-pager
systemctl is-enabled road-repair-web-remote
systemctl is-active road-repair-web-remote
```

## Phase 7: Verify CAN And RT Link Without Motion

Do not move the chassis yet.

Preferred host-side safe self-check:

```powershell
powershell -ExecutionPolicy Bypass -File "E:\BaiduNetdiskDownload\rt\github_work\rk3588-road-repair-worklog\scripts\host-windows\new_board_safe_selfcheck.ps1" -BoardIp <BOARD_IP>
```

Check:

```bash
ip -br link
ip -details link show can0
systemctl status road-repair-web-remote --no-pager
```

Use safe preflight scripts before real motion:

```text
modules/chassis/tests/check_rt_can_link.sh
modules/chassis/tests/competition_preflight.sh
```

Expected:

- CAN device exists.
- Gateway can start.
- RT ping/VCMD path works.
- Web remote still safe-locked.

## Phase 8: Motion Tests Only After User Safety Confirmation

Before any motion:

1. Ask user to confirm chassis is safe.
2. Prefer suspended-wheel chassis tests before ground tests.
3. Run low-current/short-duration tests first.
4. Use logs to judge motor RPM; do not rely only on visual observation.
5. Clean temporary scripts from board afterward.

Known result from previous work:

- Basic direction mapping was validated.
- Forward/back/strafe/rotate signs were corrected.
- Web remote worked, but straight-line correction still needed IMU yaw feedback for robust ground driving.

## Phase 9: Other Modules Are Separate

Do not mix these into chassis restore:

- Piper arm files stay under `modules/arm`.
- IMU files stay under `modules/imu`.
- Camera files stay under `modules/camera`.
- Lidar files stay under `modules/lidar`.
- Pump files stay under `modules/pump`.

Piper J5 remains a known hardware/vendor-support issue. Do not resume arm motion blindly.

## Fast Success Definition

The replacement board is considered restored to the old working baseline when:

- Fan fix is redone or explicitly documented as pending with reason.
- SSH key login works.
- `/boot/HyperBoot.bin` MD5 is `44ac4e9524aa40bccfc602f21c1c35a7`.
- `road-repair-web-remote.service` is enabled and active.
- Web remote responds at `http://<BOARD_IP>:8080/`.
- Web remote starts safe-locked.
- `/home/rock/road_repair_chassis_migration` exists and selfcheck passes.
- CAN/RT link is verified without real motion.

Only after this baseline should new development continue.
