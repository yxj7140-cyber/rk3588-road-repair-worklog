# Road Repair Chassis Migration Package

This directory is the formal chassis-migration package for the RK3588 board.
It is separated from the web-remote/debug package on purpose.

## Main Files

```text
can_gateway_service.py
chassis_vcmd_client.py
chassis_control.py
road_repair_vcmd_adapter.py
road_repair_3508_model.py
road_repair_chassis_task.py
road_repair_competition_behavior.py
road_repair_competition_plan.py
road_repair_competition_api.py
road_repair_competition_scenario.py
road_repair_virtual_devices.py
road_repair_virtual_mission.py
road_repair_topic1_runner.py
test_chassis_migration_core.py
test_road_repair_migration.py
run_road_repair_chassis_task_test.sh
run_road_repair_virtual_mission_test.sh
run_road_repair_migration_selfcheck.sh
sample_road_repair_plan.txt
sample_road_repair_scenario.json
```

## Safe Commands

Dry-run core check:

```bash
python3 test_chassis_migration_core.py
```

Full non-motion self-check:

```bash
bash ./run_road_repair_migration_selfcheck.sh
```

Dry-run Road_Repair gamepad adapter through the shell runner:

```bash
bash ./run_road_repair_chassis_task_test.sh --dry-run --lx 127 --ly 112 --rx 127 --duration 0.35 --current-limit 1200
```

Dry-run inspection mission:

```bash
python3 road_repair_competition_api.py --inspection-repair --dry-run
```

Dry-run Topic 1 competition entrypoint:

```bash
python3 road_repair_topic1_runner.py --dry-run --current-limit 1200 --pump-duration 0.2
```

Dry-run virtual mission through the shell runner:

```bash
bash ./run_road_repair_virtual_mission_test.sh --dry-run --current-limit 1200 --mission-arg --pump-duration --mission-arg 0.2
```

Dry-run behavior sequence:

```bash
python3 road_repair_competition_behavior.py --sequence "forward:0.18:0.6,stop:0:0.2,strafe-right:0.16:0.35,rotate-right:0.2:0.25" --current-limit 1200 --dry-run
```

## Safety Rules

```text
Do not enable real current output here unless the operator explicitly says safe.
Do not leave temporary test scripts on the board.
Do not mix this directory with road_repair_web_remote.
Use runner-level --dry-run before any current-enabled test.
Logs must stay under /home/rock/road_repair_chassis_migration/logs.
Do not reintroduce /home/rock/images references into this formal package.
```

## Current Acceptance

```text
board core regression: PASS all 5 formal chassis migration core checks
six-direction current-enabled acceptance: PASS, moved_motors=4/4 for all directions
virtual mission current-enabled link/safety: PASS communication and final zero-current
Topic 1 runner dry-run: PASS, default mode is safe preview
final safe state after tests: can-gateway.service inactive, can0 DOWN
```

## Board Path

```text
/home/rock/road_repair_chassis_migration
```

Manual/debug web remote remains separate:

```text
/home/rock/road_repair_web_remote
```
