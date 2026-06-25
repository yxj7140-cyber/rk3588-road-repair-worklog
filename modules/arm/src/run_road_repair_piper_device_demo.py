#!/usr/bin/env python3
"""Exercise the real Piper arm device boundary with virtual defect data."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from road_repair_piper_device import PiperArmDeviceConfig, PiperRepairArmDevice


@dataclass(frozen=True)
class DemoDefect:
    kind: str = "crack"
    distance_m: float = 0.75
    lateral_offset_m: float = -0.12
    yaw_error_deg: float = 5.0


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Demo PiperRepairArmDevice align/retract.")
    parser.add_argument("--interface", default="socketcan")
    parser.add_argument("--channel")
    parser.add_argument("--bitrate", type=int)
    parser.add_argument("--firmware", default="default")
    parser.add_argument("--env-file", default=str(Path.cwd() / "piper_can_interface.env"))
    parser.add_argument("--profiles", default=str(Path(__file__).with_name("piper_motion_profiles.json")))
    parser.add_argument("--align-action", default="approach")
    parser.add_argument("--retract-action", default="current_safe")
    parser.add_argument("--settle-s", type=float, default=2.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--defect-kind", default="crack")
    parser.add_argument("--defect-distance", type=float, default=0.75)
    parser.add_argument("--defect-lateral-offset", type=float, default=-0.12)
    parser.add_argument("--defect-yaw-error", type=float, default=5.0)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    defect = DemoDefect(
        kind=args.defect_kind,
        distance_m=args.defect_distance,
        lateral_offset_m=args.defect_lateral_offset,
        yaw_error_deg=args.defect_yaw_error,
    )
    device = PiperRepairArmDevice(
        PiperArmDeviceConfig(
            interface=args.interface,
            channel=args.channel,
            bitrate=args.bitrate,
            firmware=args.firmware,
            env_path=args.env_file,
            profiles_path=args.profiles,
            execute=args.execute,
            align_action=args.align_action,
            retract_action=args.retract_action,
            settle_s=args.settle_s,
        )
    )
    result = {
        "execute": bool(args.execute),
        "defect": asdict(defect),
        "align": device.align(defect),
        "retract": device.retract(),
    }
    print_json(result)
    if not args.execute:
        print("DRY-RUN only. Add --execute only after confirming the arm workspace is safe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

