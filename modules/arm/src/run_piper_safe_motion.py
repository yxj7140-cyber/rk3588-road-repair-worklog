#!/usr/bin/env python3
"""Low-speed Piper profile runner.

Default behavior is dry-run. Add --execute only after the arm workspace is clear
and the official host tool is closed so the CAN adapter is not shared.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from road_repair_piper_arm import (
    DEFAULT_BITRATE,
    DEFAULT_FIRMWARE,
    PiperConnectionConfig,
    PiperArmController,
    load_motion_profiles,
    print_json,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one low-speed Piper profile.")
    parser.add_argument("--interface", default="socketcan")
    parser.add_argument("--channel", default="can1")
    parser.add_argument("--firmware", default=DEFAULT_FIRMWARE)
    parser.add_argument("--bitrate", type=int, default=DEFAULT_BITRATE)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--profiles", default=str(Path(__file__).with_name("piper_motion_profiles.json")))
    parser.add_argument("--profile", default="safe_home")
    parser.add_argument("--speed-percent", type=int, help="Override profile speed percent.")
    parser.add_argument("--enable-timeout", type=float, default=5.0)
    parser.add_argument("--settle-s", type=float, default=2.0)
    parser.add_argument(
        "--require-current-close-rad",
        type=float,
        help="Abort before motion if current joints are farther than this from the target profile.",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--snapshot-after", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    profiles = load_motion_profiles(args.profiles)
    if args.profile not in profiles:
        raise SystemExit(f"unknown profile {args.profile!r}; available={sorted(profiles)}")

    profile = profiles[args.profile]
    if args.speed_percent is not None:
        profile = type(profile)(
            name=profile.name,
            description=profile.description,
            joints=profile.joints,
            speed_percent=args.speed_percent,
        )
    profile.validate()

    cfg = PiperConnectionConfig(
        firmware=args.firmware,
        interface=args.interface,
        channel=args.channel,
        bitrate=args.bitrate,
        timeout=args.timeout,
        speed_percent=profile.speed_percent,
    )

    plan = {
        "execute": bool(args.execute),
        "connection": {
            "interface": cfg.resolved_interface(),
            "channel": cfg.resolved_channel(),
            "bitrate": cfg.bitrate,
            "firmware": cfg.firmware,
        },
        "profile": {
            "name": profile.name,
            "description": profile.description,
            "speed_percent": profile.speed_percent,
            "joints": profile.joints,
        },
    }
    print_json(plan)

    if not args.execute:
        print("DRY-RUN only. Add --execute after confirming the workspace is safe.")
        return 0

    with PiperArmController(cfg) as arm:
        if args.require_current_close_rad is not None:
            current_joints = arm.current_joint_angles()
            if current_joints is None:
                raise SystemExit("current joint angles unavailable; refusing guarded motion")
            max_error = arm.max_joint_error(profile.joints)
            preflight = {
                "preflight": "require_current_close",
                "max_joint_error_rad": max_error,
                "limit_rad": float(args.require_current_close_rad),
                "current_joints": current_joints,
                "target_joints": profile.joints,
            }
            print_json(preflight)
            if max_error is None or max_error > float(args.require_current_close_rad):
                raise SystemExit(
                    f"current pose is not close to target; refusing motion: "
                    f"max_error={max_error}, limit={args.require_current_close_rad}"
                )
        motion_wait = arm.move_profile(profile, enable_timeout_s=args.enable_timeout)
        print_json({"motion_wait": motion_wait})
        time.sleep(max(0.0, args.settle_s))
        if args.snapshot_after:
            print_json({"snapshot_after": arm.snapshot()})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

