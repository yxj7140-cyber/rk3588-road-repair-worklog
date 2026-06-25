# Checkpoint 2026-06-13 Shutdown

## Safe Shutdown State

Before shutdown, the board was checked over SSH:

```text
Board: rock@192.168.137.152
/boot/HyperBoot.bin MD5: e99f0e47cff300f658989fa124e2df26
can-gateway.service: disabled / inactive
can0: DOWN
enp255s5: UP, no LOWER_UP
```

This is safe to power off. The CAN gateway is not running and CAN is not active.

## Key Experience From Today

The fragile part is not CAN itself. Linux USB-CAN and motor feedback are working. The fragile part is the official `ivshmem_net` virtual network after Linux soft reboot.

Known bad state:

```text
enp255s5: UP
no LOWER_UP
ping -I enp255s5 10.10.10.30 fails
```

Validated non-fixes:

```text
ip link set enp255s5 down/up
modprobe -r ivshmem_nic; modprobe ivshmem_nic
```

These did not restore the stale peer state. Do not rely on Linux-only recovery for competition.

## Current Robustness Policy

Use the validated mainline:

```text
RT control logic
  -> official ivshmem_net UDP
  -> Linux safe gateway
  -> USB-CAN can0
  -> chassis CAN motors
```

Protect it with:

- Physical cold boot before competition validation.
- Preflight before starting CAN gateway.
- `can-gateway.service` remains disabled by default.
- Gateway waits for RT ping and RT UDP peer before touching CAN.
- Gateway uses `--udp-command-timeout 0.25`, so stale RT commands become zero-current.
- Non-zero current is still locked behind explicit dangerous-test flags.

## Files Updated Today

- `E:\BaiduNetdiskDownload\rt\board_tools\can_gateway_service.py`
- `E:\BaiduNetdiskDownload\rt\board_tools\install_can_gateway_service.sh`
- `E:\BaiduNetdiskDownload\rt\board_tools\competition_preflight.sh`
- `E:\BaiduNetdiskDownload\rt\board_tools\run_competition_preflight.ps1`
- `E:\BaiduNetdiskDownload\rt\skills\rk3588-rt-can-gateway\SKILL.md`
- `E:\BaiduNetdiskDownload\rt\skills\rk3588-rt-can-gateway\references\current-state.md`
- `E:\BaiduNetdiskDownload\rt\skills\rk3588-rt-can-gateway\references\robustness-plan-zh.md`

Board-side installed files:

```text
/home/rock/images/can_gateway_service.py
/home/rock/images/install_can_gateway_service.sh
/home/rock/images/competition_preflight.sh
/etc/systemd/system/can-gateway.service
```

## Tomorrow Resume Steps

1. Power on the board with a physical cold boot.
2. Wait for SSH on `192.168.137.152`.
3. Run:

```powershell
powershell -ExecutionPolicy Bypass -File E:\BaiduNetdiskDownload\rt\board_tools\run_competition_preflight.ps1
```

4. If preflight passes, start the safe gateway:

```powershell
powershell -ExecutionPolicy Bypass -File E:\BaiduNetdiskDownload\rt\board_tools\run_competition_preflight.ps1 -StartGateway
```

5. Confirm success:

```text
enp255s5 has LOWER_UP
ping to 10.10.10.30 succeeds
gateway log shows udp=peer:10.10.10.30:15551
can0 is UP, LOWER_UP, ERROR-ACTIVE
motor feedback 0x201-0x204 appears
```

6. Do not enable non-zero current until the robot is physically safe and explicitly approved.

## Next Engineering Direction

Short-term competition path: keep cold boot + preflight + safe gateway.

Root-cause path: create an experimental RT image that patches `RK3588/driver/ivshmem/ivshmem_net.c` so the RT side can actively re-handshake after Linux soft reboot. This should be tested separately and rolled back immediately if it weakens the currently stable cold-boot path.
