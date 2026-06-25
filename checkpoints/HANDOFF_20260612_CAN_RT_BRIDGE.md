# HANDOFF 2026-06-12: RK3588 RT CAN Bridge

## Goal

Main line: USB-CAN + Linux gateway + RT control through a dedicated raw ivshmem shared-memory channel.

Safety rule: keep default zero-current output. Do not enable non-zero motor current unless the operator explicitly confirms the robot is safe to move.

## Current Known State

- Board is bootable and previously confirmed normal after flashing earlier HyperBoot.
- Current board image known before today's raw-ivshmem edit: `HyperBoot.bin md5 = f7c12d0ad9bf3cf886ace2589922e566`.
- USB-CAN + Linux gateway path has been validated before: CAN bus feedback frames `0x201` to `0x204` were received, with 15165 frames observed.
- Previous attempts on `shm@2` / `0000:ff:05.0` only found `vNET`, not `CANB`.
- Important discovery today: official 32G configs had a commented raw ivshmem pair on `shm@1`.
- Important BDF correction: raw `shm@1` Linux side should be `0000:ff:04.0`; `0000:ff:05.0` is the existing ivshmem-net `shm@2` path.

## Files Changed Today

- `codex_remote_src/HyperSDK/flavor/N-U6_N-R2_CAR_NPU_32G/vm_linux.yaml`
  Enabled active Linux raw ivshmem device `pcie_ivshmem@1`, backend `shm@1`, BDF `0xff20`, class `0x0500`.

- `codex_remote_src/HyperSDK/flavor/N-U6_N-R2_CAR_NPU_32G/vm_rtt.yaml`
  Enabled active RT raw ivshmem device `pcie_ivshmem@2`, backend `shm@1`, BDF `0x0020`, class `0x0500`.

- `vm_scripts/try_enable_ivshmem_raw_bridge.sh`
  Now patches the VM HyperSDK 32G YAML files to enable the same raw `shm@1` pair, then builds RT with `RT_USING_DRIVER_IVSHMEM` enabled and `RT_USING_IVSHMEM_NET` disabled.

- `vm_scripts/rebuild_hyperboot_with_local_rtt.sh`
  Now snapshots `vm_linux.yaml`, `vm_rtt.yaml`, and `raw_ivshmem_config.txt` into each build output folder so the generated `HyperBoot.bin` can be audited.

- `board_tools/bind_uio_and_scan_canb.sh`
  Default scan target changed to `0000:ff:04.0`; it now finds the actual `/dev/uioX` from the PCI device instead of assuming `/dev/uio0`.

- `board_tools/scan_uio_canb.py`
  Supports `UIO` and `UIO_MAP_INDEX` environment variables.

- `board_tools/read_uio_canb.py`
  Supports `UIO` and `UIO_MAP_INDEX` environment variables.

- `board_tools/can_gateway_service.py`
  Default shared memory selection is now `--uio auto --pci-dev 0000:ff:04.0`, resolving the actual `/dev/uioX` from PCI sysfs.

- `board_tools/install_can_gateway_service.sh`
  Service now attempts to bind raw ivshmem `0000:ff:04.0` to `uio_ivshmem` before starting the CAN gateway. Failure is non-fatal and falls back to CAN-only safe mode.

## Verification Done

- Static grep confirmed active raw ivshmem config in local `codex_remote_src` YAML files:
  - Linux `pcie_ivshmem@1`, `backend=string,shm@1`, `class=16u,0x0500`
  - RT `pcie_ivshmem@2`, `backend=string,shm@1`, `class=16u,0x0500`
- Python scripts were syntax-checked by source compilation with bundled Python:
  - `board_tools/scan_uio_canb.py`
  - `board_tools/scan_uio_markers.py`
  - `board_tools/read_uio_canb.py`
  - `board_tools/can_gateway_service.py`
- Bash syntax check was not run on Windows because local `bash` is not installed. Run `bash -n` in the VM tomorrow.

## Tomorrow First Commands

Run in Ubuntu VM:

```bash
bash -n /mnt/hgfs/rt/vm_scripts/try_enable_ivshmem_raw_bridge.sh
bash -n /mnt/hgfs/rt/vm_scripts/rebuild_hyperboot_with_local_rtt.sh
cd ~/Desktop/rock_ws/sdk/rockchip-hypercar/software/RK3588
bash /mnt/hgfs/rt/vm_scripts/try_enable_ivshmem_raw_bridge.sh
```

If RT build finishes with status `0`, run:

```bash
bash /mnt/hgfs/rt/vm_scripts/rebuild_hyperboot_with_local_rtt.sh
```

Expected output folder pattern:

```text
/mnt/hgfs/rt/build_outputs/local_rtt_32G_YYYYMMDD_HHMMSS
```

Check that this folder contains:

- `HyperBoot.bin`
- `rtthread.bin`
- `md5.txt`
- `raw_ivshmem_config.txt`
- `vm_linux.yaml`
- `vm_rtt.yaml`

## Tomorrow Board Test After Flashing New HyperBoot

After copying the new board tools to `/home/rock/images` and flashing the newly built `HyperBoot.bin`, test raw shared memory first:

```bash
sudo bash /home/rock/images/bind_uio_and_scan_canb.sh
```

Expected positive sign:

```text
Using 0000:ff:04.0 -> /dev/uioX map1
CANB_offsets=0x0
magic=0x43414e42
rt_hb increases over time
```

If `CANB` appears, reinstall/restart gateway:

```bash
sudo bash /home/rock/images/install_can_gateway_service.sh
sudo journalctl -u can-gateway.service -n 80 --no-pager
tail -80 /home/rock/images/logs/can_gateway_service.log
```

## Safe Shutdown Tonight

On board, if SSH is available:

```bash
sync
sudo poweroff
```

In the VM:

```bash
sync
sudo poweroff
```

After both are powered off, disconnect robot power / CAN / USB-CAN if needed. Tomorrow reconnect in a calm order: board power, Ethernet/SSH, USB-CAN, then motor power only when ready to observe.

## Do Not Forget

- Do not test non-zero motor current yet.
- Do not use `0000:ff:05.0` for CANB scanning unless intentionally debugging the ivshmem-net path.
- If raw `shm@1` still does not expose CANB, fallback path is RT-to-Linux over ivshmem-net UDP/TCP, with Linux still acting as the CAN gateway.
