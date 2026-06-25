# Procedure: Connect To Board Wirelessly

Use this when there is no Ethernet cable and the board must be recovered through its hotspot.

## Known Paths

Two connection paths have been used:

1. Wired Ethernet path
   - PC and board connected by network cable.
   - Use Windows network sharing or direct SSH depending on current network.
   - Prefer this when available.

2. Hotspot short-switch path
   - Temporarily connect PC Wi-Fi to board hotspot, usually `rockchip_xxxxxx`.
   - Board hotspot IP: `192.168.1.1`.
   - Use this to recover board Wi-Fi configuration when normal LAN access is not available.

## Hotspot Short-Switch Recovery

1. Keep this Codex/chat connection available if possible through another network.
2. Switch PC Wi-Fi to board hotspot.
3. Test:

   ```powershell
   ping 192.168.1.1
   ssh rock@192.168.1.1 "hostname && ip addr"
   ```

4. If SSH works, recover the board's normal Wi-Fi/LAN configuration.
5. Switch PC back to the normal internet network.
6. Verify the board's new IP from the normal network.

## Important Lessons

- Do not keep rediscovering this path from scratch.
- If the board hotspot does not appear, inspect `start_ap.sh` and Wi-Fi interface naming.
- The fixed AP script must match both `wlan*` and `wl*`.
- Do not assume `rock-5b.local` resolves. Use IP first, mDNS second.

## Useful Commands

```powershell
ping 192.168.1.1
ssh rock@192.168.1.1 "hostname; ip route; ip addr"
ssh rock@192.168.1.1 "systemctl status rockchip-ap --no-pager"
ssh rock@192.168.1.1 "systemctl status road-repair-web-remote --no-pager"
```

## Safety

Do not run chassis motion commands just because SSH works. First verify CAN mapping, service state, safe-lock mode, and user safety confirmation.
