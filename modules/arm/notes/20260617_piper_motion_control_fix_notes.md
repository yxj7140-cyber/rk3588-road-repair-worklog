# 2026-06-17 Piper motion-control fix notes

## Problem
- Real Piper task execution was brittle because motion completion was not waited on.
- Normal task flow also defaulted to disabling the arm after each motion, which is unsafe for a raised arm and can make re-enable behavior flaky.

## Fix
- Added `wait_motion_done()` based on `get_arm_status().msg.motion_status == 0`.
- `move_profile()` now blocks until motion completes or times out.
- Default task execution now keeps the arm enabled unless `--disable-after` is explicitly requested.
- Structured result now records enable state, motion wait status, and snapshots.

## Next verification
- Deploy to board.
- Run status-only check.
- Run one dry-run task.
- If executing real motion, prefer `--keep-enabled`.
