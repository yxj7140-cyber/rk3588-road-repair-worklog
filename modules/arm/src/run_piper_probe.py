#!/usr/bin/env python3
"""Read-only Piper probe for the Road_Repair migration."""

from __future__ import annotations

import argparse
import json
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
    parser = argparse.ArgumentParser(description="Probe a Piper arm without moving it.")
    parser.add_argument("--interface", default="socketcan")
    parser.add_argument("--channel", default="can1")
    parser.add_argument("--firmware", default=DEFAULT_FIRMWARE)
    parser.add_argument("--bitrate", type=int, default=DEFAULT_BITRATE)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--profiles", default=str(Path(__file__).with_name("piper_motion_profiles.json")))
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    cfg = PiperConnectionConfig(
        firmware=args.firmware,
        interface=args.interface,
        channel=args.channel,
        bitrate=args.bitrate,
        timeout=args.timeout,
    )

    profiles = load_motion_profiles(args.profiles)
    with PiperArmController(cfg) as arm:
        snapshot = arm.snapshot()
        profile_summary = {
            name: {
                "description": profile.description,
                "speed_percent": profile.speed_percent,
                "joints": profile.joints,
            }
            for name, profile in profiles.items()
        }
        result = {
            "connection": {
                "interface": cfg.resolved_interface(),
                "channel": cfg.resolved_channel(),
                "bitrate": cfg.bitrate,
                "firmware": cfg.firmware,
            },
            "snapshot": snapshot,
            "profiles": profile_summary,
        }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("Piper probe OK")
        print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

