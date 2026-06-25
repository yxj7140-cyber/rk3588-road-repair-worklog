#!/usr/bin/env python3
"""Topic 1 task entrypoint for the RK3588 Road_Repair migration.

This is the formal competition-facing runner for the current chassis-only
stage. It keeps the task shape close to the final robot:

    preset road inspection -> defect detection -> chassis alignment ->
    arm/pump repair hold -> resume inspection

Depth camera, arm, pump, and lidar can still be virtual here. Real chassis
motion is only sent when this script is run without --dry-run and an external
runner has started the validated gateway path.
"""

from __future__ import annotations

import argparse

from chassis_control import DEFAULT_CHASSIS_CURRENT_LIMIT
from chassis_vcmd_client import DEFAULT_PERIOD_S, DEFAULT_PORT, DEFAULT_TARGET
from road_repair_competition_api import RoadRepairCompetitionChassis
from road_repair_virtual_mission import RoadRepairVirtualMissionPlanner, actions_to_steps, print_actions
from road_repair_virtual_devices import VirtualDepthCamera, VirtualRoadDefect


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or preview Road_Repair Topic 1 task flow.")
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD_S)
    parser.add_argument("--current-limit", type=int, default=DEFAULT_CHASSIS_CURRENT_LIMIT)
    parser.add_argument("--max-speed-rpm", type=int, default=None)
    parser.add_argument("--max-rotate-rpm", type=int, default=None)
    parser.add_argument("--scenario-file")
    parser.add_argument("--defect-kind", default="pothole", choices=["pothole", "crack"])
    parser.add_argument("--defect-distance", type=float, default=0.80)
    parser.add_argument("--defect-lateral-offset", type=float, default=0.16)
    parser.add_argument("--defect-yaw-error", type=float, default=-4.0)
    parser.add_argument("--inspect-magnitude", type=float, default=0.18)
    parser.add_argument("--align-magnitude", type=float, default=0.16)
    parser.add_argument("--rotate-magnitude", type=float, default=0.20)
    parser.add_argument("--pump-duration", type=float, default=0.80)
    parser.add_argument(
        "--include-avoidance",
        action="store_true",
        help="Include the optional virtual lidar/pedestrian avoidance segment.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview only. This is the default safety mode.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Send chassis commands. Requires the external gateway runner to be active.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    execute = bool(args.execute)
    dry_run = not execute

    planner = RoadRepairVirtualMissionPlanner(
        inspect_magnitude=args.inspect_magnitude,
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

    print("RoadRepairTopic1Runner")
    print(f"mode={'execute' if execute else 'dry-run'}")
    print(f"virtual_devices=depth_camera,arm,pump,lidar_optional real_devices=chassis")
    print_actions(
        actions,
        current_limit=args.current_limit,
        max_speed_rpm=args.max_speed_rpm,
        max_rotate_rpm=args.max_rotate_rpm,
    )

    if dry_run:
        return 0

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
        f"sent RoadRepairTopic1Runner chassis_steps={len(steps)} "
        f"packets={sum(result.packets for result in results)} "
        f"current_limit={args.current_limit}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
