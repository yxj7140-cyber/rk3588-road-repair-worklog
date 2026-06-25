#!/usr/bin/env python3
"""Road_Repair 3508 chassis task adapter for the RK3588 migration.

This module ports the useful part of Road_Repair_freertos/User/TASKs/
3508ctrtask.c to the validated RK3588 runtime path:

    gamepad-like input -> Road_Repair axis math -> ChassisController

It intentionally does not reimplement CAN, PID, or wheel mixing. Those now live
in the validated RT/Linux stack.
"""

from __future__ import annotations

import argparse

from chassis_control import ChassisCommandResult, ChassisController, DEFAULT_CHASSIS_CURRENT_LIMIT
from road_repair_3508_model import RoadRepairGamepadState, clamp_byte
from road_repair_vcmd_adapter import (
    RoadRepairAxisCommand,
)


class RoadRepairChassisTask:
    """Small Linux-side equivalent of Road_Repair's Motor3508CtrTask input layer."""

    def __init__(
        self,
        controller: ChassisController | None = None,
        current_limit: int = DEFAULT_CHASSIS_CURRENT_LIMIT,
    ):
        self.current_limit = int(current_limit)
        self.controller = controller or ChassisController(current_limit=self.current_limit)
        self._owns_controller = controller is None

    def close(self) -> None:
        if self._owns_controller:
            self.controller.close()

    def __enter__(self) -> "RoadRepairChassisTask":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
        self.close()

    def apply_gamepad_state(
        self,
        state: RoadRepairGamepadState,
        duration_s: float = 0.2,
        final_stop: bool = True,
    ) -> ChassisCommandResult:
        forward, strafe, rotate, speed_scale, slow_scale = state.normalized_axes()
        return self.controller.set_velocity(
            forward=forward,
            strafe=strafe,
            rotate=rotate,
            duration_s=duration_s,
            speed_scale=speed_scale,
            slow_scale=slow_scale,
            final_stop=final_stop,
        )

    def stop(self) -> None:
        self.controller.stop()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Road_Repair gamepad-to-chassis migration adapter.")
    parser.add_argument("--lx", type=int, default=127)
    parser.add_argument("--ly", type=int, default=127)
    parser.add_argument("--rx", type=int, default=127)
    parser.add_argument("--lt", type=int, default=0)
    parser.add_argument("--rt", type=int, default=0)
    parser.add_argument("--duration", type=float, default=0.2)
    parser.add_argument("--current-limit", type=int, default=DEFAULT_CHASSIS_CURRENT_LIMIT)
    parser.add_argument("--disconnected", action="store_true")
    parser.add_argument("--not-xbox360", action="store_true")
    parser.add_argument("--no-final-stop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    state = RoadRepairGamepadState(
        lx=args.lx,
        ly=args.ly,
        rx=args.rx,
        lt=args.lt,
        rt=args.rt,
        connected=not args.disconnected,
        xbox360=not args.not_xbox360,
    )
    forward, strafe, rotate, speed_scale, slow_scale = state.normalized_axes()
    axis_command = RoadRepairAxisCommand(
        forward=forward,
        strafe=strafe,
        rotate=rotate,
        speed_scale=speed_scale,
        slow_scale=slow_scale,
        current_limit=args.current_limit,
    )
    vcmd = axis_command.to_vcmd()

    if args.dry_run:
        print(
            "dry-run RoadRepairChassisTask "
            f"gamepad=lx:{clamp_byte(args.lx)} ly:{clamp_byte(args.ly)} "
            f"rx:{clamp_byte(args.rx)} lt:{clamp_byte(args.lt)} rt:{clamp_byte(args.rt)} "
            f"connected={int(state.connected)} xbox360={int(state.xbox360)} -> "
            f"axes={forward:.3f},{strafe:.3f},{rotate:.3f} "
            f"scale={speed_scale:.3f} slow={slow_scale:.3f} "
            f"rpm={vcmd.forward_rpm},{vcmd.strafe_rpm},{vcmd.rotate_rpm} "
            f"current_limit={vcmd.current_limit}"
        )
        return 0

    with RoadRepairChassisTask(current_limit=args.current_limit) as task:
        result = task.apply_gamepad_state(
            state,
            duration_s=args.duration,
            final_stop=not args.no_final_stop,
        )

    print(
        f"sent RoadRepairChassisTask packets={result.packets} "
        f"rpm={result.forward_rpm},{result.strafe_rpm},{result.rotate_rpm} "
        f"current_limit={result.current_limit}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
