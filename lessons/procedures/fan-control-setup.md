# Procedure: Fan-Control Setup

Status: required gap for the repaired/replacement board.

The user explicitly requested:

```text
After the new board arrives, first rewrite/fix the fan program, then restore the 2026-06-18 state.
```

## What We Know

- The previous conversation established that fan behavior must be fixed before normal project restore.
- A mature final fan script has not been found in the saved workspace or repository.
- Do not pretend this step is already automated.

## First Actions When Board Arrives

1. Boot the board with a known-good image.
2. Observe fan behavior during idle and light load.
3. Inspect likely control paths:

   ```bash
   ls /sys/class/hwmon
   find /sys -iname '*fan*' -o -iname '*pwm*'
   systemctl list-units --type=service | grep -Ei 'fan|thermal|pwm' || true
   ps aux | grep -Ei 'fan|thermal|pwm' | grep -v grep || true
   ```

4. Check whether the vendor image already has a fan service or script.
5. If no suitable service exists, create a small conservative fan-control service.

## Required Result

The final fan fix must be saved in two places:

```text
scripts/recovery/
lessons/procedures/fan-control-setup.md
```

Record:

- exact board path
- service name
- enable/start commands
- how to verify it survived reboot
- any temperature threshold used

## Safety Notes

- Do not stress-test the board before the fan behavior is known.
- Prefer conservative fan-on behavior over silent overheating.
- If the fan pin/control path is unknown, document the blocker and do not continue heavy build/runtime work on the board.

## Verification Template

Fill this in after the new board is tested:

```text
Date:
Board:
Image:
Fan control path:
Service:
Enabled on boot:
Idle observation:
Load observation:
Reboot verification:
Notes:
```
