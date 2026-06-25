#!/usr/bin/env python3
"""Dry-run Road_Repair mission with real Piper arm adapter injected."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from road_repair_piper_device import PiperArmDeviceConfig, PiperRepairArmDevice
from road_repair_virtual_devices import VirtualDepthCamera, VirtualRoadDefect, VirtualPump
from road_repair_virtual_mission import (
    RoadRepairVirtualMissionPlanner,
    actions_to_steps,
    print_actions,
)


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Road_Repair mission with Piper arm adapter injected.")
    parser.add_argument("--interface", default="socketcan")
    parser.add_argument("--channel")
    parser.add_argument("--bitrate", type=int)
    parser.add_argument("--firmware", default="default")
    parser.add_argument("--env-file", default=str(Path.cwd() / "piper_can_interface.env"))
    parser.add_argument("--profiles", default=str(Path(__file__).with_name("piper_motion_profiles.json")))
    parser.add_argument("--align-action", default="approach")
    parser.add_argument("--retract-action", default="current_safe")
    parser.add_argument("--settle-s", type=float, default=2.0)
    parser.add_argument("--execute-arm", action="store_true")
    parser.add_argument("--disable-after", action="store_true")
    parser.add_argument("--defect-kind", default="crack", choices=["pothole", "crack"])
    parser.add_argument("--defect-distance", type=float, default=0.75)
    parser.add_argument("--defect-lateral-offset", type=float, default=-0.12)
    parser.add_argument("--defect-yaw-error", type=float, default=5.0)
    parser.add_argument("--pump-duration", type=float, default=0.8)
    parser.add_argument("--current-limit", type=int, default=1200)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    defect = VirtualRoadDefect(
        kind=args.defect_kind,
        distance_m=args.defect_distance,
        lateral_offset_m=args.defect_lateral_offset,
        yaw_error_deg=args.defect_yaw_error,
    )
    arm = PiperRepairArmDevice(
        PiperArmDeviceConfig(
            interface=args.interface,
            channel=args.channel,
            bitrate=args.bitrate,
            firmware=args.firmware,
            env_path=args.env_file,
            profiles_path=args.profiles,
            execute=args.execute_arm,
            align_action=args.align_action,
            retract_action=args.retract_action,
            settle_s=args.settle_s,
            disable_after=bool(args.disable_after),
        )
    )
    planner = RoadRepairVirtualMissionPlanner(
        depth_camera=VirtualDepthCamera(defect),
        arm=arm,
        pump=VirtualPump(),
        pump_duration_s=args.pump_duration,
    )
    actions = planner.build_inspection_repair(include_avoidance=False)
    steps = actions_to_steps(actions)

    print_json({
        "execute_arm": bool(args.execute_arm),
        "execute_chassis": False,
        "defect": {
            "kind": defect.kind,
            "distance_m": defect.distance_m,
            "lateral_offset_m": defect.lateral_offset_m,
            "yaw_error_deg": defect.yaw_error_deg,
        },
        "arm": {
            "align_action": args.align_action,
            "retract_action": args.retract_action,
        },
        "arm_action_results": getattr(arm, "last_results", []),
        "summary": {
            "actions": len(actions),
            "chassis_steps": len(steps),
        },
    })
    print_actions(actions, current_limit=args.current_limit)
    if not args.execute_arm:
        print("DRY-RUN arm only. Chassis is never executed by this demo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
