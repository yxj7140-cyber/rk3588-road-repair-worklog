# New Board Restore Plan

This file is now a short entry point. The detailed, command-oriented runbook is:

```text
lessons/procedures/restore-new-board-to-0618.md
```

Before operating on the replacement board, also read:

```text
docs/new-board-first-hour-checklist.md
docs/project-timeline-20260626.md
docs/known-pitfalls-and-rules.md
lessons/procedures/connect-board-wireless.md
lessons/procedures/connect-vm-from-windows.md
lessons/procedures/vmware-shared-folder.md
```

Non-negotiable order:

1. Confirm the board can boot a known-good image.
2. Redo/confirm the fan-control fix first.
3. Establish stable SSH/network access.
4. Restore the 2026-06-18 baseline.
5. Verify web remote safe-lock and CAN/RT link.
6. Run motion only after explicit safety confirmation.

After SSH is reachable, run the safe self-check script:

```powershell
powershell -ExecutionPolicy Bypass -File "E:\BaiduNetdiskDownload\rt\github_work\rk3588-road-repair-worklog\scripts\host-windows\new_board_safe_selfcheck.ps1" -BoardIp <BOARD_IP>
```

This self-check intentionally does not unlock current, move the chassis, move the arm, or enable the pump.
