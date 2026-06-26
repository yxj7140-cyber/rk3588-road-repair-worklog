# Procedure: New Board Self-Check Plan

This is the checklist for the future self-check script to run after the replacement board is booted and reachable.

The script should be safe: it must not send real motion commands.

## Inputs

```text
Board IP
SSH key path
Known hosts path
Expected HyperBoot MD5
```

Defaults:

```text
SSH key: E:\BaiduNetdiskDownload\rt\board_ssh\rock5b_ed25519
Expected HyperBoot MD5: 44ac4e9524aa40bccfc602f21c1c35a7
Web port: 8080
```

## Checks

1. SSH reachable:

   ```bash
   hostname; id; ip -br addr; ip route
   ```

2. Boot image:

   ```bash
   md5sum /boot/HyperBoot.bin
   ```

3. Required directories:

   ```bash
   ls -ld /home/rock/road_repair_web_remote
   ls -ld /home/rock/road_repair_chassis_migration
   ```

4. Web remote service:

   ```bash
   systemctl is-enabled road-repair-web-remote.service
   systemctl is-active road-repair-web-remote.service
   systemctl status road-repair-web-remote.service --no-pager
   ```

5. Web remote API:

   ```bash
   python3 - <<'PY'
import urllib.request
print(urllib.request.urlopen('http://127.0.0.1:8080/api/status', timeout=3).read().decode())
PY
   ```

6. Safe-lock:

   - API must indicate current is disabled or safe-lock is active.
   - If not, stop and investigate before motion tests.

7. CAN device visibility:

   ```bash
   ip -br link
   ip -details link show can0 || true
   ```

8. Formal package selfcheck:

   ```bash
   cd /home/rock/road_repair_chassis_migration
   bash ./run_road_repair_migration_selfcheck.sh
   ```

## Expected Output

The future script should print a compact PASS/FAIL table:

```text
SSH              PASS
HyperBoot MD5    PASS
Web service      PASS
Safe-lock        PASS
Formal package   PASS
CAN visible      PASS/WARN
Motion allowed   NO
```

## Safety

The self-check script must never:

- unlock web remote
- enable current
- start chassis motion
- move the arm
- enable the pump

Motion remains a separate user-confirmed test phase.
