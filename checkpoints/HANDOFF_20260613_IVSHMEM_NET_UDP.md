# HANDOFF 2026-06-13: RK3588 ivshmem-net + Linux USB-CAN Gateway

## Current safe state

- Board is booted with the stable ivshmem-net baseline image:
  - `/boot/HyperBoot.bin` MD5: `cfef785eec7e1064bbaa5c4742e136a6`
  - Source copy on board: `/home/rock/images/HyperBoot_clean_ivshmem_net_20260613_211619.bin`
- `can-gateway.service` is disabled and inactive, so Linux is not continuously sending CAN commands.
- Latest UDP experiment image is preserved but not active:
  - `/home/rock/images/HyperBoot_clean_ivshmem_net_udp_20260613_213423.bin`
  - MD5: `2c1f0c9b6e21c25bd5e1390376a69f7b`
- Known fallback backups on board:
  - `/boot/HyperBoot.bin.bak_20260613_133530_cfef785e`
  - `/boot/HyperBoot.bin.bak_20260613_131803_af9eea73`
  - `/boot/HyperBoot.bin.good_original`

## What worked today

- A clean RT image with official `ivshmem_net` and no raw CANB driver was built and flashed.
- After a physical power cycle, Linux `enp255s5=10.10.10.31/24` successfully pinged RT `10.10.10.30`.
- Linux USB-CAN path is healthy:
  - `can0` is `ERROR-ACTIVE`, 1 Mbps.
  - Motor feedback IDs `0x201-0x204` were observed continuously.
- Linux gateway was updated to support UDP:
  - Listens on UDP `0.0.0.0:15550`.
  - Keeps non-zero motor currents disabled unless both explicit safety flags are passed.
  - Defaults to `--no-shm --udp --send-before-feedback`.

## What did not work yet

- The first UDP RT image started `can_udp_gateway_app.c` after only 5 seconds.
- With that image, `enp255s5` came up but never reached `LOWER_UP`; ping to `10.10.10.30` failed.
- Rolling back to the known-good `cfef785e` image via soft reboot did not restore ping. Earlier, a physical power cycle did restore ping, so the ivshmem-net link appears sensitive to cold-start state after UIO/hot-rebind experiments.
- Hot unbind/rebind of `ivshmem_nic` did not restore the link.

## Code changes made

- `board_tools/can_gateway_service.py`
  - Added UDP command receive and feedback transmit protocol.
  - Command magic: `RCAN`.
  - Feedback magic: `FCAN`.
  - Non-zero currents remain blocked unless both safety flags are set.
- `board_tools/install_can_gateway_service.sh`
  - Removed forced UIO rebind of `0000:ff:05.0`, because this breaks the kernel `ivshmem_nic` network path.
  - Starts gateway with UDP and `--no-shm`.
- `codex_remote_src/RK3588/applications/can_udp_gateway_app.c`
  - New RT UDP heartbeat/zero-current app.
  - Start delay changed from 5 seconds to 30 seconds after the first failed experiment.
- `vm_scripts/try_clean_ivshmem_net_only.sh`
  - Copies `can_udp_gateway_app.c` into the RT applications folder when building.
  - Keeps raw CANB bridge disabled.

## Next recommended steps

1. Physically power-cycle the board while it is on the `cfef785e` baseline image and `can-gateway.service` is disabled.
2. After boot, verify:
   ```bash
   md5sum /boot/HyperBoot.bin
   ip -br addr show enp255s5
   ping -I enp255s5 -c 3 -W 1 10.10.10.30
   ```
3. If ping works, rebuild a new UDP image with the 30-second delay and flash it.
4. Keep `can-gateway.service` disabled until after `10.10.10.30` ping succeeds, then start it manually:
   ```bash
   sudo systemctl start can-gateway.service
   tail -f /home/rock/images/logs/can_gateway_service.log
   ```
5. Expected success sign:
   ```text
   udp=peer:10.10.10.30:15551
   ```

## Safety reminder

Do not enable non-zero current output yet. The Linux gateway intentionally clamps output to four zero currents unless launched with both:

```bash
--allow-nonzero-current --i-understand-this-can-move-motors
```
