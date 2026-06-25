#!/usr/bin/env python3
"""Road_Repair-style normalized input adapter for the RK3588 RT VCMD path.

This is the recommended bridge from competition/upper-layer logic to the
validated RT chassis controller. It keeps Road_Repair's input semantics
near the top of the stack:

    normalized axes -> deadband/limits -> ChassisVelocityCommand -> RT VCMD

The RT image still owns mecanum mixing, PID, current calculation, and the
command-boundary axis normalization that was already validated on the chassis.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from chassis_vcmd_client import (
    DEFAULT_PERIOD_S,
    DEFAULT_PORT,
    DEFAULT_TARGET,
    ChassisVcmdClient,
    ChassisVelocityCommand,
)
from road_repair_3508_model import (
    ROAD_REPAIR_AXIS_DEADBAND,
    ROAD_REPAIR_MAX_ROTATE_RPM,
    ROAD_REPAIR_MAX_SPEED_RPM,
    ROAD_REPAIR_MAX_SPEED_SCALE,
    ROAD_REPAIR_MIN_SLOW_SCALE,
    apply_axis_deadband,
    clamp_float,
)


@dataclass(frozen=True)
class RoadRepairAxisCommand:
    """Normalized user-facing chassis input.

    Conventions match the current RT command interface:
      forward + = forward
      strafe  + = right
      rotate  + = left / counterclockwise
    """

    forward: float = 0.0
    strafe: float = 0.0
    rotate: float = 0.0
    speed_scale: float = 1.0
    slow_scale: float = 1.0
    deadband: float = ROAD_REPAIR_AXIS_DEADBAND
    max_speed_rpm: int = ROAD_REPAIR_MAX_SPEED_RPM
    max_rotate_rpm: int = ROAD_REPAIR_MAX_ROTATE_RPM
    current_limit: int = 0

    def scale(self) -> float:
        speed = clamp_float(self.speed_scale, 0.0, ROAD_REPAIR_MAX_SPEED_SCALE)
        slow = clamp_float(self.slow_scale, ROAD_REPAIR_MIN_SLOW_SCALE, 1.0)
        return speed * slow

    def to_vcmd(self) -> ChassisVelocityCommand:
        scale = self.scale()
        max_speed_rpm = abs(int(self.max_speed_rpm))
        max_rotate_rpm = abs(int(self.max_rotate_rpm))
        forward_rpm = int(apply_axis_deadband(self.forward, self.deadband) * max_speed_rpm * scale)
        strafe_rpm = int(apply_axis_deadband(self.strafe, self.deadband) * max_speed_rpm * scale)
        rotate_rpm = int(apply_axis_deadband(self.rotate, self.deadband) * max_rotate_rpm * scale)
        forward_rpm = int(clamp_float(forward_rpm, -max_speed_rpm, max_speed_rpm))
        strafe_rpm = int(clamp_float(strafe_rpm, -max_speed_rpm, max_speed_rpm))
        rotate_rpm = int(clamp_float(rotate_rpm, -max_rotate_rpm, max_rotate_rpm))
        return ChassisVelocityCommand(
            forward_rpm=forward_rpm,
            strafe_rpm=strafe_rpm,
            rotate_rpm=rotate_rpm,
            current_limit=self.current_limit,
            enabled=True,
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert Road_Repair-style normalized axes to RT VCMD commands."
    )
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--forward", type=float, default=0.0, help="Normalized -1.0..1.0")
    parser.add_argument("--strafe", type=float, default=0.0, help="Normalized -1.0..1.0; + is right")
    parser.add_argument("--rotate", type=float, default=0.0, help="Normalized -1.0..1.0; + is left/CCW")
    parser.add_argument("--speed-scale", type=float, default=1.0)
    parser.add_argument("--slow-scale", type=float, default=1.0)
    parser.add_argument("--deadband", type=float, default=ROAD_REPAIR_AXIS_DEADBAND)
    parser.add_argument("--max-speed-rpm", type=int, default=ROAD_REPAIR_MAX_SPEED_RPM)
    parser.add_argument("--max-rotate-rpm", type=int, default=ROAD_REPAIR_MAX_ROTATE_RPM)
    parser.add_argument("--current-limit", type=int, default=0)
    parser.add_argument("--duration", type=float, default=0.2)
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD_S)
    parser.add_argument("--no-final-stop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    axis_command = RoadRepairAxisCommand(
        forward=args.forward,
        strafe=args.strafe,
        rotate=args.rotate,
        speed_scale=args.speed_scale,
        slow_scale=args.slow_scale,
        deadband=args.deadband,
        max_speed_rpm=args.max_speed_rpm,
        max_rotate_rpm=args.max_rotate_rpm,
        current_limit=args.current_limit,
    )
    vcmd = axis_command.to_vcmd()

    if args.dry_run:
        print(
            "dry-run RoadRepairAxisCommand "
            f"forward={axis_command.forward:.3f} strafe={axis_command.strafe:.3f} "
            f"rotate={axis_command.rotate:.3f} scale={axis_command.scale():.3f} "
            f"deadband={axis_command.deadband:.3f} -> "
            f"VCMD forward_rpm={vcmd.forward_rpm} strafe_rpm={vcmd.strafe_rpm} "
            f"rotate_rpm={vcmd.rotate_rpm} current_limit={vcmd.current_limit}"
        )
        return 0

    client = ChassisVcmdClient(args.target, args.port)
    try:
        count = client.stream(
            vcmd,
            duration_s=args.duration,
            period_s=args.period,
            final_stop=not args.no_final_stop,
        )
        print(
            f"sent RoadRepair VCMD packets={count} target={args.target}:{args.port} "
            f"forward={axis_command.forward:.3f} strafe={axis_command.strafe:.3f} "
            f"rotate={axis_command.rotate:.3f} -> "
            f"rpm={vcmd.forward_rpm},{vcmd.strafe_rpm},{vcmd.rotate_rpm} "
            f"current_limit={vcmd.current_limit}"
        )
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
