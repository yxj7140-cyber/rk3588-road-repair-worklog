# 2026-06-21 RK3588 TF Card Hotspot Offline Diagnosis

Current situation:

- Board hotspot `rockchip_decdfa` is not visible from Windows.
- TF card was inserted into Windows via USB card reader.
- Windows sees the card as `Disk 2`, GPT, about 64 GB physical size.
- Partitions are present:
  - Partition 1: 512 MB EFI/System boot partition.
  - Partition 2: about 31 GB Linux rootfs partition, ext4 label `rootfs`.
- ext4 superblock is readable and reports clean state.

Important finding:

- `/usr/local/bin/start_ap.sh` only detects wireless interfaces whose names match `^wlan`:

```bash
IFACE=$(iw dev | awk '$1=="Interface" && $2 ~ /^wlan/ {print $2; exit}')
```

- Our previously validated board Wi-Fi interface was `wlP2p33s0`, not `wlan0`.
- Therefore the AP init service can exit with `No wireless interface found`, and the hotspot will not appear.
- Existing `ROCK.nmconnection` also contains `interface-name=wlan0`, although `start_ap.sh` would normally repair it if it found an interface.

Conclusion:

The TF card is not obviously unreadable or filesystem-corrupt. The hotspot failure is much more likely caused by the AP startup script assuming a `wlan*` interface name. This may have been exposed or worsened by recent network/lidar development, but the root technical fault is interface-name matching.

Safe repair plan:

1. Backup the current TF card or at least rootfs critical files before writing anything.
2. Patch `/usr/local/bin/start_ap.sh` to select any real Wi-Fi interface from `iw dev`, preferably one matching `wl*` or `wlan*`.
3. Optionally remove or ignore stale `.start_ap.sh.swp` after confirming it is only a Vim swap file.
4. Boot the board and verify:
   - hotspot appears as `rockchip_decdfa` or generated `rockchip_xxxxxx`,
   - SSH works at `192.168.1.1`,
   - board WLAN/campus recovery still works,
   - chassis services are untouched.

Do not run fsck repair or format. Current evidence does not justify destructive recovery.
