# Known Pitfalls And Project Rules

This file is the anti-repeat list from the long bring-up conversation.

## Do Not Guess Network Mode

We lost time by trying the wrong access path after reboots.

Use the decision tree:

- If the user says Ethernet is connected, try wired/ICS first.
- If the board is on the same WLAN, probe known WLAN IPs.
- If neither works, short-switch to the board hotspot at `192.168.1.1`.
- Do not assume `rock-5b.local` resolves.

Reference:

```text
lessons/procedures/connect-board-wireless.md
```

## Do Not Rebuild RT For Script-Level Tests

For Linux-side test scripts, web remote changes, and mission orchestration, deploy scripts to the board and run them.

Rebuild `rtthread.bin` / `HyperBoot.bin` only when changing RT-side code or boot packaging.

## Do Not Leave Temporary Scripts On The Board

Policy:

- Keep source scripts in Git/PC/VM.
- Copy to board only for the test.
- Run the test.
- Pull logs/results back.
- Delete board-side temporary files.

Reference:

```text
lessons/procedures/board-resident-test-script-policy.md
```

## Do Not Run Motion Without Safety Confirmation

Before any real chassis or arm motion:

- User confirms safety.
- Prefer suspended-wheel chassis testing first.
- Use low current and short duration first.
- Use logs/RPM/state feedback instead of relying only on visual observation.

## Web Remote Is Debug-Only

The web remote exists because there is no physical remote controller.

It must:

- start locked
- require explicit unlock for real motion
- have highest priority only inside the debug/control path
- not become a competition requirement dependency

## Chassis Mainline Is Preserved

Chosen chassis path:

```text
USB-CAN + Linux gateway + RT control
```

Reason:

- CAN feedback worked.
- It was the fastest reliable path.
- It preserves RT for chassis execution while allowing Linux to host gateway/debug tools.

## Keep Modules Separate

Do not mix files between:

- `modules/chassis`
- `modules/arm`
- `modules/camera`
- `modules/lidar`
- `modules/pump`
- `modules/imu`

Cross-module logic belongs in:

```text
integration/
```

## Arm J5 Is A Known Issue

Piper J5 showed repeated abnormal behavior.

Do not resume arm motion blindly. Wait for vendor guidance or a deliberate low-risk diagnostic plan.

## eMMC Failure Was Probably Board-Side

Windows could read the official eMMC, but the old board reported:

```text
Card did not respond to voltage select!
SPL: failed to boot from all boot devices
```

This points to board-side eMMC/boot-chain failure, not only an image problem.

## Large Files Stay Local

Do not commit:

- images
- SDKs
- logs
- virtualenvs
- Docker archives
- wheel/offline packages
- vendor installers

Track paths in:

```text
docs/large-files-index.md
```
