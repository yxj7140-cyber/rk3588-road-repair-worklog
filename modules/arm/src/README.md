# RK3588 Board Piper Arm Files

This folder is the board-side Piper workspace. It is intentionally separate
from chassis files.

## Boundary

```text
board_piper -> Piper arm only
board_tools -> chassis, RT gateway, web remote, and competition tools
```

Do not put chassis scripts in this folder. Do not modify the chassis CAN
gateway while testing Piper.

## CAN Layout

Final target:

```text
can0 -> chassis / RT path
can1 -> Piper arm
```

The Piper scripts default to:

```text
interface = socketcan
channel = can1
bitrate = 1000000
```

## Board Install

After copying this folder to the board, run:

```bash
cd ~/board_piper
bash check_board_piper_deps.sh
bash setup_board_piper_env.sh
```

If GitHub/PyPI is slow on the board, use the PC-prepared offline package set:

```bash
cd ~/board_piper
bash install_board_piper_offline.sh
```

On RK3588 boards that still use Python 3.8, the offline installer keeps build
isolation disabled for `pyAgxArm` so it can reuse the board's existing
`setuptools`/`wheel` pair. That avoids pulling a Python 3.9+ build toolchain
into the board by accident.

From Windows, deploy this folder without touching chassis files:

```powershell
powershell -ExecutionPolicy Bypass -File E:\BaiduNetdiskDownload\rt\board_piper\deploy_board_piper_to_board.ps1 -HostName 192.168.1.1
```

Then check CAN devices:

```bash
bash check_board_can.sh
```

Read-only probe:

```bash
bash run_board_piper_probe_with_log.sh
```

Formal Road_Repair arm task interface:

```bash
bash run_board_arm_task_with_log.sh status
bash run_board_arm_task_with_log.sh profiles
bash run_board_arm_task_with_log.sh action observe
bash run_board_arm_task_with_log.sh capture current_safe --description "Captured safe baseline"
```

Real Piper implementation of the virtual `RepairArmDevice` boundary:

```bash
bash run_board_piper_device_demo_with_log.sh
```

This demo calls `align(defect)` and `retract()` using virtual defect data. It is
also dry-run by default. Real movement requires `--execute`.

Mission dry-run with the Piper adapter injected into the Road_Repair virtual
task flow:

```powershell
powershell -ExecutionPolicy Bypass -File E:\BaiduNetdiskDownload\rt\board_piper\deploy_mission_runtime_to_board.ps1 -HostName 10.11.198.140
```

```bash
bash run_board_mission_with_piper_arm_with_log.sh
```

The `action` command is dry-run by default. Real motion requires an explicit
`--execute`:

```bash
bash run_board_arm_task_with_log.sh action observe --execute
```

Dry-run a profile:

```bash
python3 run_piper_safe_motion.py --profile safe_home
```

Or use the log wrapper:

```bash
bash run_board_piper_motion_with_log.sh safe_home
```

Real motion is only allowed after the workspace is clear:

```bash
python3 run_piper_safe_motion.py --profile safe_home --execute --snapshot-after
```

Equivalent logged command:

```bash
bash run_board_piper_motion_with_log.sh safe_home execute
```

## Safety

Start with read-only probe. Do not run `--execute` until:

```text
Piper is powered.
The arm workspace is clear.
The chassis is stopped.
can1 is confirmed as the Piper adapter.
If only one USB-CAN adapter is connected during Piper-only testing, it may be
detected as `can0`. In that temporary case, run:

```bash
ALLOW_CAN0=1 bash check_board_can.sh
```
The chassis CAN adapter remains on can0 or the existing chassis path.
```
