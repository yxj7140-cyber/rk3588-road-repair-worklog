# CHECKPOINT 2026-06-13: RT UDP to Linux USB-CAN gateway link OK

## Result

The selected architecture is now validated at the zero-current safety stage:

- RT side sends UDP command packets over official `ivshmem_net`.
- Linux side receives RT UDP packets from `10.10.10.30:15551`.
- Linux USB-CAN gateway brings up `can0` at 1 Mbps.
- DJI motor feedback frames `0x201` to `0x204` are received continuously.
- Non-zero motor current is still blocked by the Linux gateway safety guard.

## Current flashed image

- Board: `rock@192.168.137.152`
- Active `/boot/HyperBoot.bin` MD5:
  `e99f0e47cff300f658989fa124e2df26`
- Image copied on board:
  `/home/rock/images/HyperBoot_clean_ivshmem_net_udp_30s_20260613_215051.bin`
- Stable fallback backup:
  `/boot/HyperBoot.bin.bak_20260613_135226_cfef785e`
- Previous known-good baseline MD5:
  `cfef785eec7e1064bbaa5c4742e136a6`

## Verified after physical cold boot

Linux virtual NIC:

```text
enp255s5: <BROADCAST,MULTICAST,UP,LOWER_UP>
Linux IP: 10.10.10.31/24
RT IP:    10.10.10.30
```

Ping result:

```text
ping -I enp255s5 -c 8 -W 1 10.10.10.30
8 packets transmitted, 8 received, 0% packet loss
```

USB-CAN:

```text
can0: <NOARP,UP,LOWER_UP,ECHO>
state ERROR-ACTIVE
bitrate 1000000
```

Gateway success sign:

```text
udp=peer:10.10.10.30:15551 age=0.00s cmd=...
```

Motor feedback observed:

```text
201: angle=4102 rpm=0 temp=27
202: angle=4229 rpm=0 temp=27
203: angle=4123 rpm=0 temp=27
204: angle=3341 rpm=0 temp=27
```

## Safety state

`can-gateway.service` is installed but disabled for boot:

```text
systemctl is-enabled can-gateway.service -> disabled
```

The tested service command does not include:

```text
--allow-nonzero-current
--i-understand-this-can-move-motors
```

So the Linux gateway clamps outgoing command current to zero.

## Next engineering step

Implement the real RT control protocol on top of the validated UDP link:

1. Keep the current Linux gateway safety lock.
2. Add a structured RT command source, replacing the heartbeat-only zero-current app.
3. First test only with zero current and feedback parsing.
4. Then test tiny bounded current commands only after the robot is physically lifted and the user explicitly confirms it is safe.

## Hardening added after validation

To reduce the fragility of the `ivshmem_net` link during development, the Linux gateway and service unit were hardened:

- `board_tools/can_gateway_service.py` now supports `--require-rt-ping`.
- `board_tools/can_gateway_service.py` now supports `--require-udp-peer-timeout`.
- `board_tools/install_can_gateway_service.sh` now installs the service disabled and stopped by default.
- The service unit no longer runs `modprobe ivshmem_uio`, avoiding accidental disruption of the kernel `ivshmem_nic` path.
- The service command now waits for `10.10.10.30` and UDP peer `10.10.10.30:15551` before setting up CAN.
- A board-side health-check script was added: `/home/rock/images/check_rt_can_link.sh`.

Validated hardened startup log:

```text
Waiting for RT network: target=10.10.10.30 iface=enp255s5 timeout=90.0s
RT network reachable: 10.10.10.30
UDP RT link listening on 0.0.0.0:15550
Waiting for RT UDP peer timeout=90.0s
RT UDP peer detected: 10.10.10.30:15551
can_gateway_service: iface=can0 bitrate=1000000
Safety: non-zero current output is disabled.
```

The service was stopped after this validation and remains inactive.

## Soft reboot retest

On 2026-06-13 22:23 CST, a normal Linux `reboot` was tested.

Result:

```text
/boot/HyperBoot.bin MD5: e99f0e47cff300f658989fa124e2df26
can-gateway.service: disabled/inactive
enp255s5: UP, but not LOWER_UP
ping -I enp255s5 10.10.10.30: 100% packet loss
```

This confirms the known `ivshmem_net` soft-reboot fragility.

The hardened gateway was then started during the broken-link state. It stayed at:

```text
Waiting for RT network: target=10.10.10.30 iface=enp255s5 timeout=90.0s
```

After stopping the service, `can0` remained DOWN/STOPPED, confirming the gateway did not enter CAN setup when RT was unreachable.

## Useful commands

Check board state:

```powershell
ssh -i E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519 rock@192.168.137.152 "md5sum /boot/HyperBoot.bin; systemctl is-enabled can-gateway.service || true; systemctl is-active can-gateway.service || true; ip -br addr"
```

Verify virtual RT network:

```powershell
ssh -i E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519 rock@192.168.137.152 "ping -I enp255s5 -c 5 -W 1 10.10.10.30"
```

Start safe zero-current gateway manually:

```powershell
ssh -i E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519 rock@192.168.137.152 "echo rock | sudo -S systemctl start can-gateway.service; tail -f /home/rock/images/logs/can_gateway_service.log"
```

Stop gateway:

```powershell
ssh -i E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519 rock@192.168.137.152 "echo rock | sudo -S systemctl stop can-gateway.service"
```
