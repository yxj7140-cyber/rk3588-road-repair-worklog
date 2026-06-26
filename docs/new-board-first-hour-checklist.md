# New Board First-Hour Checklist

Use this checklist the moment the repaired or replacement RK3588 board arrives.

Goal: restore the project to the stable 2026-06-18 chassis baseline quickly, without repeating the long discovery process.

## Before Power-On

- Confirm boot medium is known-good and fully seated.
- Connect serial console if available.
- Keep chassis wheels off the ground if motor power is connected.
- Do not connect arm, pump, lidar, and camera all at once during first boot. Bring back one subsystem at a time.
- Keep the stable HyperBoot path ready:

  ```text
  E:\BaiduNetdiskDownload\rt\build_outputs\local_rtt_32G_20260614_143025\HyperBoot.bin
  MD5: 44ac4e9524aa40bccfc602f21c1c35a7
  ```

## Step 1: Boot Health

Pass condition:

- DDR init succeeds.
- SPL does not stop at `Card did not respond to voltage select`.
- Linux boots or the bootloader continues normally.

Stop condition:

```text
Trying to boot from MMC1
Card did not respond to voltage select!
SPL: failed to boot from all boot devices
```

If the stop condition appears on the repaired board, do not restore project files yet. Treat it as boot-medium or board-side eMMC/boot-chain failure.

## Step 2: Fan Fix First

The user explicitly requested this order:

```text
fan-control fix first, then restore 2026-06-18 project state
```

Current gap:

- The final fan-control script was not found in the saved project files.
- The first new-board session must recover or recreate it.

Save the final result in:

```text
lessons/procedures/fan-control-setup.md
scripts/recovery/
```

## Step 3: Network Path

Do not guess. Use this order:

1. Same WLAN if the board has joined it.
2. Wired Ethernet if the user says cable is connected.
3. Board hotspot short-switch only as recovery.

Known board access patterns:

```text
WLAN historical IPs: 10.11.198.140, 10.21.50.12
Hotspot: 192.168.1.1
Wired/ICS historical board IP: 192.168.137.152
User: rock
Password used historically: rock
SSH key: E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519
```

Verify:

```powershell
ping <BOARD_IP>
ssh -i "E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519" rock@<BOARD_IP> "hostname; ip -br addr; ip route"
```

If key login is missing after reflash:

```powershell
Get-Content "E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519.pub" |
ssh rock@<BOARD_IP> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

## Step 4: Restore 2026-06-18 Baseline

Preferred when the board boots and SSH works:

```powershell
powershell -ExecutionPolicy Bypass -File "E:\BaiduNetdiskDownload\rt\board_tools\restore_after_reflash_from_pc.ps1" -BoardIp <BOARD_IP>
```

This should restore:

- `/boot/HyperBoot.bin`
- `/home/rock/road_repair_web_remote`
- `/home/rock/road_repair_chassis_migration`
- `road-repair-web-remote.service`
- safe-lock web remote startup

## Step 5: Safe Verification Only

These checks must not move the chassis:

```powershell
curl http://<BOARD_IP>:8080/api/status
ssh -i "E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519" rock@<BOARD_IP> "md5sum /boot/HyperBoot.bin; systemctl is-active road-repair-web-remote; systemctl is-enabled road-repair-web-remote"
```

Expected:

- HyperBoot MD5 is `44ac4e9524aa40bccfc602f21c1c35a7`.
- Web remote responds.
- Web remote is locked or current-disabled by default.
- No motion happens during verification.

## Step 6: CAN / RT Link Without Motion

Check device visibility and service logs before any movement:

```bash
ip -br link
ip -details link show can0 || true
systemctl status road-repair-web-remote --no-pager
```

Use safe preflight scripts only:

```text
modules/chassis/tests/check_rt_can_link.sh
modules/chassis/tests/competition_preflight.sh
```

## Step 7: Motion Requires Explicit Safety Confirmation

Only after the user confirms safety:

- Prefer suspended-wheel chassis testing first.
- Use short low-current pulses first.
- Use logs/RPM feedback to judge whether motors moved.
- Remove board-side temporary scripts after each test.
- Keep the source/test script in Git or PC/VM workspace.

## Fast Pass Definition

The first-hour restore is complete when:

- Board boots normally.
- Fan fix is redone or clearly documented as blocked.
- SSH key login works.
- Stable HyperBoot MD5 matches.
- Web remote service is active and safe-locked.
- Chassis migration package exists.
- CAN/RT link is verified without motion.

Do not continue new feature development until these pass.
