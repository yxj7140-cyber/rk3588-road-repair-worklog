#!/usr/bin/env python3
"""Minimal chassis-control API for competition-side code.

This module is the intended import surface for upper-layer logic. It deliberately
stays thin: Road_Repair-style input scaling is handled here, while RT keeps the
mecanum mixer, PID, current limiting, and failsafe behavior.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from chassis_vcmd_client import DEFAULT_PERIOD_S, DEFAULT_PORT, DEFAULT_TARGET, ChassisVcmdClient
from road_repair_vcmd_adapter import RoadRepairAxisCommand

DEFAULT_CHASSIS_CURRENT_LIMIT = 1200


@dataclass(frozen=True)
class ChassisCommandResult:
    packets: int
    forward_rpm: int
    strafe_rpm: int
    rotate_rpm: int
    current_limit: int


class ChassisController:
    """Small context-manager wrapper around the RT VCMD UDP client."""

    def __init__(
        self,
        target: str = DEFAULT_TARGET,
        port: int = DEFAULT_PORT,
        period_s: float = DEFAULT_PERIOD_S,
        current_limit: int = DEFAULT_CHASSIS_CURRENT_LIMIT,
        max_speed_rpm: int | None = None,
        max_rotate_rpm: int | None = None,
    ):
        self.period_s = float(period_s)
        self.current_limit = int(current_limit)
        self.max_speed_rpm = max_speed_rpm
        self.max_rotate_rpm = max_rotate_rpm
        self.client = ChassisVcmdClient(target, port)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "ChassisController":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
        self.close()

    def set_velocity(
        self,
        forward: float = 0.0,
        strafe: float = 0.0,
        rotate: float = 0.0,
        duration_s: float = 0.2,
        speed_scale: float = 1.0,
        slow_scale: float = 1.0,
        final_stop: bool = True,
    ) -> ChassisCommandResult:
        """Send normalized chassis velocity for a bounded duration.

        Axis convention:
          forward + = forward
          strafe  + = right
          rotate  + = left / counterclockwise
        """

        axis_command = RoadRepairAxisCommand(
            forward=forward,
            strafe=strafe,
            rotate=rotate,
            speed_scale=speed_scale,
            slow_scale=slow_scale,
            current_limit=self.current_limit,
            **{
                key: value
                for key, value in {
                    "max_speed_rpm": self.max_speed_rpm,
                    "max_rotate_rpm": self.max_rotate_rpm,
                }.items()
                if value is not None
            },
        )
        vcmd = axis_command.to_vcmd()
        packets = self.client.stream(
            vcmd,
            duration_s=duration_s,
            period_s=self.period_s,
            final_stop=final_stop,
        )
        return ChassisCommandResult(
            packets=packets,
            forward_rpm=vcmd.forward_rpm,
            strafe_rpm=vcmd.strafe_rpm,
            rotate_rpm=vcmd.rotate_rpm,
            current_limit=vcmd.current_limit,
        )

    def stop(self) -> None:
        self.client.stop(period_s=self.period_s)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal competition-side chassis-control API demo.")
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--forward", type=float, default=0.0)
    parser.add_argument("--strafe", type=float, default=0.0)
    parser.add_argument("--rotate", type=float, default=0.0)
    parser.add_argument("--duration", type=float, default=0.2)
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD_S)
    parser.add_argument("--speed-scale", type=float, default=1.0)
    parser.add_argument("--slow-scale", type=float, default=1.0)
    parser.add_argument("--current-limit", type=int, default=DEFAULT_CHASSIS_CURRENT_LIMIT)
    parser.add_argument("--max-speed-rpm", type=int, default=None)
    parser.add_argument("--max-rotate-rpm", type=int, default=None)
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
        current_limit=args.current_limit,
        **{
            key: value
            for key, value in {
                "max_speed_rpm": args.max_speed_rpm,
                "max_rotate_rpm": args.max_rotate_rpm,
            }.items()
            if value is not None
        },
    )
    vcmd = axis_command.to_vcmd()

    if args.dry_run:
        print(
            "dry-run ChassisController.set_velocity "
            f"axes={args.forward:.3f},{args.strafe:.3f},{args.rotate:.3f} "
            f"duration={args.duration:.3f}s period={args.period:.3f}s -> "
            f"rpm={vcmd.forward_rpm},{vcmd.strafe_rpm},{vcmd.rotate_rpm} "
            f"current_limit={vcmd.current_limit}"
        )
        return 0

    with ChassisController(
        target=args.target,
        port=args.port,
        period_s=args.period,
        current_limit=args.current_limit,
        max_speed_rpm=args.max_speed_rpm,
        max_rotate_rpm=args.max_rotate_rpm,
    ) as controller:
        result = controller.set_velocity(
            forward=args.forward,
            strafe=args.strafe,
            rotate=args.rotate,
            duration_s=args.duration,
            speed_scale=args.speed_scale,
            slow_scale=args.slow_scale,
            final_stop=not args.no_final_stop,
        )

    print(
        f"sent chassis velocity packets={result.packets} "
        f"rpm={result.forward_rpm},{result.strafe_rpm},{result.rotate_rpm} "
        f"current_limit={result.current_limit}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
