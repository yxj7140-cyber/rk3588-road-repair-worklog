#!/usr/bin/env python3
"""Tiny Piper motion smoke test.

This is intentionally much smaller than a named repair/inspection profile. It
reads the current joint angles, nudges one joint by a tiny delta, then returns
to the exact starting angles.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from road_repair_piper_arm import (
    DEFAULT_BITRATE,
    DEFAULT_FIRMWARE,
    DEFAULT_MOTION_TIMEOUT_S,
    PiperArmController,
    PiperConnectionConfig,
    print_json,
)


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def extract_joint_angles(snapshot: dict[str, Any]) -> list[float]:
    data = snapshot.get("get_joint_angles")
    if not isinstance(data, dict):
        raise RuntimeError(f"joint angles unavailable: {data!r}")
    values = data.get("msg")
    if not isinstance(values, list) or len(values) != 6:
        raise RuntimeError(f"joint angles malformed: {values!r}")
    return [float(value) for value in values]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a tiny Piper joint nudge and return.")
    parser.add_argument("--interface", default="socketcan")
    parser.add_argument("--channel")
    parser.add_argument("--firmware", default=DEFAULT_FIRMWARE)
    parser.add_argument("--bitrate", type=int)
    parser.add_argument("--joint", type=int, default=6, choices=range(1, 7))
    parser.add_argument("--delta", type=float, default=0.03)
    parser.add_argument("--speed-percent", type=int, default=3)
    parser.add_argument("--settle-s", type=float, default=0.8)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--enable-timeout", type=float, default=5.0)
    parser.add_argument("--motion-timeout", type=float, default=DEFAULT_MOTION_TIMEOUT_S)
    parser.add_argument("--disable-after", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    env_file = Path(__file__).with_name("piper_can_interface.env")
    cwd_env_file = Path.cwd() / "piper_can_interface.env"
    env = load_env_file(env_file)
    env.update(load_env_file(cwd_env_file))
    channel = args.channel or os.environ.get("PIPER_CAN") or env.get("PIPER_CAN") or "can1"
    bitrate = args.bitrate or int(os.environ.get("PIPER_CAN_BITRATE") or env.get("PIPER_CAN_BITRATE") or DEFAULT_BITRATE)

    if abs(args.delta) > 0.05:
        raise SystemExit("Refusing delta larger than 0.05 rad for micro motion.")
    if not 1 <= args.speed_percent <= 5:
        raise SystemExit("Refusing speed-percent outside 1..5 for micro motion.")

    cfg = PiperConnectionConfig(
        firmware=args.firmware,
        interface=args.interface,
        channel=channel,
        bitrate=bitrate,
        timeout=args.timeout,
        speed_percent=args.speed_percent,
    )

    with PiperArmController(cfg) as arm:
        before = arm.snapshot()
        start = extract_joint_angles(before)
        target = list(start)
        target[args.joint - 1] += float(args.delta)

        plan = {
            "execute": bool(args.execute),
            "connection": {
                "interface": cfg.resolved_interface(),
                "channel": cfg.resolved_channel(),
                "bitrate": cfg.bitrate,
                "firmware": cfg.firmware,
            },
            "motion": {
                "joint": args.joint,
                "delta_rad": args.delta,
                "speed_percent": args.speed_percent,
                "start": start,
                "target": target,
            },
            "snapshot_before": before,
        }
        print_json(plan)

        if not args.execute:
            print("DRY-RUN only. Add --execute after confirming the arm workspace is safe.")
            return 0

        disabled = None
        mid = None
        after = None
        enabled_before = None
        enabled_after_enable = None
        enabled_after = None
        target_motion_wait = None
        return_motion_wait = None
        try:
            enabled_before = arm.joints_enabled()
            if not arm.enable(timeout_s=args.enable_timeout):
                raise RuntimeError("failed to enable Piper arm")
            enabled_after_enable = arm.joints_enabled()
            if not enabled_after_enable or not all(enabled_after_enable[:6]):
                raise RuntimeError(f"arm did not reach fully enabled state: {enabled_after_enable}")
            arm.set_speed_percent(args.speed_percent)
            arm.move_j(target)
            target_motion_wait = arm.wait_motion_done(timeout_s=args.motion_timeout)
            if not bool(target_motion_wait.get("done")):
                raise RuntimeError(f"target motion did not finish: {target_motion_wait}")
            time.sleep(max(0.0, args.settle_s))
            mid = arm.snapshot()
            arm.move_j(start)
            return_motion_wait = arm.wait_motion_done(timeout_s=args.motion_timeout)
            if not bool(return_motion_wait.get("done")):
                raise RuntimeError(f"return motion did not finish: {return_motion_wait}")
            time.sleep(max(0.0, args.settle_s))
            after = arm.snapshot()
            enabled_after = arm.joints_enabled()
        finally:
            if args.disable_after:
                try:
                    disabled = arm.disable(timeout_s=args.enable_timeout)
                except Exception as exc:
                    disabled = {"error": str(exc)}

        print(json.dumps({
            "motion_result": {
                "enabled_before": enabled_before,
                "enabled_after_enable": enabled_after_enable,
                "enabled_after": enabled_after,
                "target_motion_wait": target_motion_wait,
                "return_motion_wait": return_motion_wait,
                "disabled_after": disabled,
                "snapshot_mid": mid,
                "snapshot_after": after,
            }
        }, ensure_ascii=False, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
