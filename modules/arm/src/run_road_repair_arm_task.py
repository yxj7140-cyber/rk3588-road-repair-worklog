#!/usr/bin/env python3
"""Board-side Road_Repair arm task entrypoint.

This is the formal Piper-side interface for the migration. It exposes
competition-level actions while keeping real motion behind an explicit
`--execute` flag.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from road_repair_arm_control import ACTION_TO_PROFILE, RoadRepairArmController


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Road_Repair Piper arm task interface.")
    parser.add_argument("--interface", default="socketcan")
    parser.add_argument("--channel")
    parser.add_argument("--bitrate", type=int)
    parser.add_argument("--firmware", default="default")
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--env-file", default=str(Path.cwd() / "piper_can_interface.env"))
    parser.add_argument("--profiles", default=str(Path(__file__).with_name("piper_motion_profiles.json")))

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Read current Piper status without motion.")
    subparsers.add_parser("profiles", help="List configured task profiles without motion.")

    capture_parser = subparsers.add_parser("capture", help="Capture current arm pose into profiles JSON.")
    capture_parser.add_argument("name")
    capture_parser.add_argument("--description", default="Captured current safe pose")
    capture_parser.add_argument("--speed-percent", type=int, default=5)

    action_parser = subparsers.add_parser("action", help="Run or dry-run a task action.")
    action_parser.add_argument("name", choices=sorted(ACTION_TO_PROFILE))
    action_parser.add_argument("--execute", action="store_true")
    action_parser.add_argument("--settle-s", type=float, default=2.0)
    action_parser.add_argument("--keep-enabled", action="store_true")
    action_parser.add_argument("--disable-after", action="store_true")
    return parser


def make_controller(args: argparse.Namespace) -> RoadRepairArmController:
    return RoadRepairArmController(
        interface=args.interface,
        channel=args.channel,
        bitrate=args.bitrate,
        firmware=args.firmware,
        timeout=args.timeout,
        profiles_path=args.profiles,
        env_path=args.env_file,
    )


def main() -> int:
    args = build_arg_parser().parse_args()

    if args.command == "profiles":
        controller = make_controller(args)
        print_json({
            "actions": ACTION_TO_PROFILE,
            "profiles": controller.profile_summary(),
        })
        return 0

    with make_controller(args) as controller:
        if args.command == "status":
            print_json({
                "connection": {
                    "interface": controller.connection.resolved_interface(),
                    "channel": controller.connection.resolved_channel(),
                    "bitrate": controller.connection.bitrate,
                    "firmware": controller.connection.firmware,
                },
                "snapshot": controller.snapshot(),
            })
            return 0

        if args.command == "capture":
            print_json(controller.capture_current_profile(
                name=args.name,
                description=args.description,
                speed_percent=args.speed_percent,
                profiles_path=args.profiles,
            ))
            return 0

        if args.command == "action":
            result = controller.run_action(
                args.name,
                execute=args.execute,
                settle_s=args.settle_s,
                disable_after=bool(args.disable_after and not args.keep_enabled),
            )
            print_json(result.to_dict())
            if not args.execute:
                print("DRY-RUN only. Add --execute only after confirming the arm workspace is safe.")
            return 0

    raise SystemExit(f"unknown command {args.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
