#!/usr/bin/env python3
"""Virtual full-task mission for Road_Repair chassis migration.

Only the chassis is real at this stage. Depth camera, arm, and pump are
simulated as scripted events so we can validate the competition flow through the
already validated chassis API. Lidar/pedestrian avoidance remains available as
an optional scenario, but the default ground-test path excludes avoidance.
"""

from __future__ import annotations

import argparse

from chassis_control import DEFAULT_CHASSIS_CURRENT_LIMIT
from chassis_vcmd_client import DEFAULT_PERIOD_S, DEFAULT_PORT, DEFAULT_TARGET
from road_repair_competition_api import (
    DEFAULT_ALIGN_MAGNITUDE as API_DEFAULT_ALIGN_MAGNITUDE,
    DEFAULT_INSPECT_MAGNITUDE as API_DEFAULT_INSPECT_MAGNITUDE,
    DEFAULT_PUMP_DURATION_S,
    DEFAULT_ROTATE_MAGNITUDE as API_DEFAULT_ROTATE_MAGNITUDE,
    RoadRepairCompetitionChassis,
    RoadRepairDefectObservation,
    build_inspection_repair_steps,
    preview_steps,
)
from road_repair_competition_behavior import RoadRepairBehaviorStep
from road_repair_competition_scenario import build_scenario_steps, load_scenario_file
from road_repair_virtual_devices import (
    CementPumpDevice,
    DepthCameraDevice,
    LidarDevice,
    RepairArmDevice,
    VirtualArm,
    VirtualDepthCamera,
    VirtualLidar,
    VirtualMissionAction,
    VirtualPedestrian,
    VirtualPump,
    VirtualRoadDefect,
)


DEFAULT_INSPECT_MAGNITUDE = API_DEFAULT_INSPECT_MAGNITUDE
DEFAULT_AVOID_MAGNITUDE = 0.25
DEFAULT_ALIGN_MAGNITUDE = API_DEFAULT_ALIGN_MAGNITUDE
DEFAULT_ROTATE_MAGNITUDE = API_DEFAULT_ROTATE_MAGNITUDE


def _step(behavior: str, magnitude: float, duration_s: float) -> RoadRepairBehaviorStep:
    return RoadRepairBehaviorStep(behavior, max(0.0, min(1.0, magnitude)), max(0.0, duration_s))


class RoadRepairVirtualMissionPlanner:
    """Maps virtual task events to bounded chassis behavior steps."""

    def __init__(
        self,
        inspect_magnitude: float = DEFAULT_INSPECT_MAGNITUDE,
        avoid_magnitude: float = DEFAULT_AVOID_MAGNITUDE,
        align_magnitude: float = DEFAULT_ALIGN_MAGNITUDE,
        rotate_magnitude: float = DEFAULT_ROTATE_MAGNITUDE,
        pump_duration_s: float = DEFAULT_PUMP_DURATION_S,
        depth_camera: DepthCameraDevice | None = None,
        lidar: LidarDevice | None = None,
        arm: RepairArmDevice | None = None,
        pump: CementPumpDevice | None = None,
    ):
        self.inspect_magnitude = inspect_magnitude
        self.avoid_magnitude = avoid_magnitude
        self.align_magnitude = align_magnitude
        self.rotate_magnitude = rotate_magnitude
        self.pump_duration_s = pump_duration_s
        self.depth_camera = depth_camera or VirtualDepthCamera()
        self.lidar = lidar or VirtualLidar()
        self.arm = arm or VirtualArm()
        self.pump = pump or VirtualPump()

    def build_inspection_repair(self, include_avoidance: bool = False) -> list[VirtualMissionAction]:
        defect = self.depth_camera.detect_defect()

        actions: list[VirtualMissionAction] = [
            VirtualMissionAction(
                "mission",
                "start preset road inspection",
                _step("forward", self.inspect_magnitude, 0.6),
            ),
        ]

        if include_avoidance:
            pedestrian = self.lidar.detect_pedestrian()
            actions.extend(
                [
                    VirtualMissionAction(
                        "lidar",
                        (
                            f"pedestrian detected distance={pedestrian.distance_m:.2f}m "
                            f"side={pedestrian.side}"
                        ),
                        _step("stop", 0.0, 0.2),
                    ),
                    VirtualMissionAction(
                        "decision",
                        "avoid pedestrian: strafe right",
                        _step("strafe-right", self.avoid_magnitude, 0.45),
                    ),
                    VirtualMissionAction(
                        "decision",
                        "pass obstacle slowly",
                        _step("forward", self.inspect_magnitude, 0.45),
                    ),
                    VirtualMissionAction(
                        "decision",
                        "return to inspection lane",
                        _step("strafe-left", self.avoid_magnitude, 0.45),
                    ),
                ]
            )

        actions.extend(
            [
                VirtualMissionAction(
                    "mission",
                    "continue preset road inspection",
                    _step("forward", self.inspect_magnitude, 0.5),
                ),
                VirtualMissionAction(
                    "depth_camera",
                    (
                        f"{defect.kind} detected distance={defect.distance_m:.2f}m "
                        f"offset={defect.lateral_offset_m:.2f}m yaw={defect.yaw_error_deg:.1f}deg"
                    ),
                    _step("stop", 0.0, 0.2),
                ),
            ]
        )

        if defect.lateral_offset_m > 0.03:
            actions.append(
                VirtualMissionAction(
                    "decision",
                    "align chassis to defect: strafe right",
                    _step("strafe-right", self.align_magnitude, 0.35),
                )
            )
        elif defect.lateral_offset_m < -0.03:
            actions.append(
                VirtualMissionAction(
                    "decision",
                    "align chassis to defect: strafe left",
                    _step("strafe-left", self.align_magnitude, 0.35),
                )
            )

        if defect.yaw_error_deg < -2.0:
            actions.append(
                VirtualMissionAction(
                    "decision",
                    "fine yaw alignment: rotate right",
                    _step("rotate-right", self.rotate_magnitude, 0.25),
                )
            )
        elif defect.yaw_error_deg > 2.0:
            actions.append(
                VirtualMissionAction(
                    "decision",
                    "fine yaw alignment: rotate left",
                    _step("rotate-left", self.rotate_magnitude, 0.25),
                )
            )

        actions.extend(
            [
                VirtualMissionAction(
                    "decision",
                    "approach repair point",
                    _step("forward", self.inspect_magnitude, 0.45),
                ),
                VirtualMissionAction(
                    "arm",
                    self.arm.align(defect),
                    _step("stop", 0.0, 0.4),
                ),
                VirtualMissionAction(
                    "pump",
                    self.pump.dispense(self.pump_duration_s),
                    _step("stop", 0.0, self.pump_duration_s),
                ),
                VirtualMissionAction(
                    "arm",
                    self.arm.retract(),
                    _step("stop", 0.0, 0.3),
                ),
                VirtualMissionAction(
                    "mission",
                    "repair complete; resume inspection briefly",
                    _step("forward", self.inspect_magnitude, 0.4),
                ),
                VirtualMissionAction(
                    "mission",
                    "mission segment complete",
                    _step("stop", 0.0, 0.3),
                ),
            ]
        )

        if not include_avoidance:
            expected_steps = build_inspection_repair_steps(
                defect=defect.to_observation(),
                inspect_magnitude=self.inspect_magnitude,
                align_magnitude=self.align_magnitude,
                rotate_magnitude=self.rotate_magnitude,
                pump_duration_s=self.pump_duration_s,
            )
            actual_steps = [action.step for action in actions if action.step is not None]
            if actual_steps != expected_steps:
                raise AssertionError("virtual mission chassis steps drifted from competition API")
        return actions

    def build_from_scenario_file(self, scenario_file: str) -> list[VirtualMissionAction]:
        scenario = load_scenario_file(scenario_file)
        steps = build_scenario_steps(
            scenario,
            align_magnitude=self.align_magnitude,
            rotate_magnitude=self.rotate_magnitude,
        )
        actions: list[VirtualMissionAction] = []
        detect_stop_index = len(scenario.pre_defect_segments) + 1
        for index, step in enumerate(steps, start=1):
            if step.behavior == "stop" and index == detect_stop_index:
                source = "depth_camera"
                message = (
                    f"{scenario.defect.kind} detected distance={scenario.defect.distance_m:.2f}m "
                    f"offset={scenario.defect.lateral_offset_m:.2f}m "
                    f"yaw={scenario.defect.yaw_error_deg:.1f}deg"
                )
            elif step.behavior == "stop" and index > 3:
                source = "virtual_device"
                message = "virtual repair hold"
            else:
                source = "scenario"
                message = f"{scenario.name} step {index}"
            actions.append(VirtualMissionAction(source, message, step))
        return actions


def actions_to_steps(actions: list[VirtualMissionAction]) -> list[RoadRepairBehaviorStep]:
    return [action.step for action in actions if action.step is not None]


def print_actions(
    actions: list[VirtualMissionAction],
    current_limit: int,
    max_speed_rpm: int | None = None,
    max_rotate_rpm: int | None = None,
) -> None:
    steps = actions_to_steps(actions)
    previews = preview_steps(
        steps,
        current_limit=current_limit,
        max_speed_rpm=max_speed_rpm,
        max_rotate_rpm=max_rotate_rpm,
    )
    preview_index = 0
    print(f"virtual mission actions={len(actions)} chassis_steps={len(steps)}")
    for index, action in enumerate(actions, start=1):
        if action.step is None:
            print(f"  action={index} source={action.source} event={action.message}")
            continue
        preview = previews[preview_index]
        preview_index += 1
        print(
            f"  action={index} source={action.source} event={action.message} -> "
            f"behavior={action.step.behavior} magnitude={action.step.magnitude:.3f} "
            f"duration={action.step.duration_s:.3f}s "
            f"rpm={preview.forward_rpm},{preview.strafe_rpm},{preview.rotate_rpm} "
            f"current_limit={preview.current_limit}"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a virtual Road_Repair full-task mission.")
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD_S)
    parser.add_argument("--current-limit", type=int, default=DEFAULT_CHASSIS_CURRENT_LIMIT)
    parser.add_argument("--inspect-magnitude", type=float, default=DEFAULT_INSPECT_MAGNITUDE)
    parser.add_argument("--avoid-magnitude", type=float, default=DEFAULT_AVOID_MAGNITUDE)
    parser.add_argument("--align-magnitude", type=float, default=DEFAULT_ALIGN_MAGNITUDE)
    parser.add_argument("--rotate-magnitude", type=float, default=DEFAULT_ROTATE_MAGNITUDE)
    parser.add_argument("--max-speed-rpm", type=int, default=None)
    parser.add_argument("--max-rotate-rpm", type=int, default=None)
    parser.add_argument("--pump-duration", type=float, default=DEFAULT_PUMP_DURATION_S)
    parser.add_argument("--scenario-file")
    parser.add_argument("--defect-kind", default="pothole", choices=["pothole", "crack"])
    parser.add_argument("--defect-distance", type=float, default=0.80)
    parser.add_argument("--defect-lateral-offset", type=float, default=0.16)
    parser.add_argument("--defect-yaw-error", type=float, default=-4.0)
    parser.add_argument(
        "--include-avoidance",
        action="store_true",
        help="Include the optional pedestrian/lidar avoidance segment. Default excludes it.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    planner = RoadRepairVirtualMissionPlanner(
        inspect_magnitude=args.inspect_magnitude,
        avoid_magnitude=args.avoid_magnitude,
        align_magnitude=args.align_magnitude,
        rotate_magnitude=args.rotate_magnitude,
        pump_duration_s=args.pump_duration,
        depth_camera=VirtualDepthCamera(
            VirtualRoadDefect(
                kind=args.defect_kind,
                distance_m=args.defect_distance,
                lateral_offset_m=args.defect_lateral_offset,
                yaw_error_deg=args.defect_yaw_error,
            )
        ),
    )
    actions = (
        planner.build_from_scenario_file(args.scenario_file)
        if args.scenario_file
        else planner.build_inspection_repair(include_avoidance=args.include_avoidance)
    )
    steps = actions_to_steps(actions)

    if args.dry_run:
        print_actions(
            actions,
            current_limit=args.current_limit,
            max_speed_rpm=args.max_speed_rpm,
            max_rotate_rpm=args.max_rotate_rpm,
        )
        return 0

    print_actions(
        actions,
        current_limit=args.current_limit,
        max_speed_rpm=args.max_speed_rpm,
        max_rotate_rpm=args.max_rotate_rpm,
    )
    with RoadRepairCompetitionChassis(
        target=args.target,
        port=args.port,
        period_s=args.period,
        current_limit=args.current_limit,
        max_speed_rpm=args.max_speed_rpm,
        max_rotate_rpm=args.max_rotate_rpm,
    ) as chassis:
        results = chassis.run_steps(steps)

    print(
        f"sent virtual mission chassis_steps={len(steps)} "
        f"packets={sum(result.packets for result in results)} "
        f"current_limit={args.current_limit}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
