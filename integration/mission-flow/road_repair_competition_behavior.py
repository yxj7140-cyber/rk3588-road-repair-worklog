#!/usr/bin/env python3
"""Minimal competition-side behavior entry for the Road_Repair RK3588 port.

This file is intentionally small. It does not implement strategy, vision, CAN,
or PID. It only gives upper-layer competition code a stable, bounded way to call
the already validated chassis path:

    behavior name -> normalized chassis axes -> ChassisController -> RT VCMD
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from chassis_control import ChassisCommandResult, ChassisController, DEFAULT_CHASSIS_CURRENT_LIMIT
from chassis_vcmd_client import DEFAULT_PERIOD_S, DEFAULT_PORT, DEFAULT_TARGET
from road_repair_vcmd_adapter import RoadRepairAxisCommand, clamp_float


DEFAULT_BEHAVIOR_MAGNITUDE = 0.35
DEFAULT_BEHAVIOR_DURATION_S = 0.6


@dataclass(frozen=True)
class RoadRepairBehavior:
    name: str
    forward: float = 0.0
    strafe: float = 0.0
    rotate: float = 0.0


@dataclass(frozen=True)
class RoadRepairBehaviorStep:
    behavior: str
    magnitude: float
    duration_s: float


BEHAVIORS: dict[str, RoadRepairBehavior] = {
    "stop": RoadRepairBehavior("stop"),
    "forward": RoadRepairBehavior("forward", forward=1.0),
    "back": RoadRepairBehavior("back", forward=-1.0),
    "strafe-right": RoadRepairBehavior("strafe-right", strafe=1.0),
    "strafe-left": RoadRepairBehavior("strafe-left", strafe=-1.0),
    "rotate-left": RoadRepairBehavior("rotate-left", rotate=1.0),
    "rotate-right": RoadRepairBehavior("rotate-right", rotate=-1.0),
}


def behavior_axes(name: str, magnitude: float) -> tuple[float, float, float]:
    if name not in BEHAVIORS:
        raise ValueError(f"unknown behavior: {name}")

    behavior = BEHAVIORS[name]
    if behavior.name == "stop":
        return 0.0, 0.0, 0.0

    scale = clamp_float(abs(magnitude), 0.0, 1.0)
    return behavior.forward * scale, behavior.strafe * scale, behavior.rotate * scale


def parse_behavior_step(
    text: str,
    default_magnitude: float = DEFAULT_BEHAVIOR_MAGNITUDE,
    default_duration_s: float = DEFAULT_BEHAVIOR_DURATION_S,
) -> RoadRepairBehaviorStep:
    """Parse one behavior sequence item.

    Format: behavior[:magnitude[:duration_s]]
    Example: forward:0.35:0.4
    """

    parts = [part.strip() for part in text.split(":")]
    if not parts or not parts[0]:
        raise ValueError("empty behavior step")
    if len(parts) > 3:
        raise ValueError(f"invalid behavior step: {text!r}")

    behavior = parts[0]
    if behavior not in BEHAVIORS:
        raise ValueError(f"unknown behavior: {behavior}")

    magnitude = default_magnitude
    if len(parts) >= 2 and parts[1]:
        magnitude = float(parts[1])

    duration_s = default_duration_s
    if len(parts) >= 3 and parts[2]:
        duration_s = float(parts[2])

    return RoadRepairBehaviorStep(
        behavior=behavior,
        magnitude=clamp_float(abs(magnitude), 0.0, 1.0),
        duration_s=max(0.0, duration_s),
    )


def parse_behavior_sequence(
    text: str,
    default_magnitude: float = DEFAULT_BEHAVIOR_MAGNITUDE,
    default_duration_s: float = DEFAULT_BEHAVIOR_DURATION_S,
) -> list[RoadRepairBehaviorStep]:
    steps = [
        parse_behavior_step(item, default_magnitude, default_duration_s)
        for item in text.split(",")
        if item.strip()
    ]
    if not steps:
        raise ValueError("empty behavior sequence")
    return steps


class RoadRepairCompetitionBehaviorRunner:
    """Runs short, bounded chassis behaviors for competition-side code."""

    def __init__(
        self,
        controller: ChassisController | None = None,
        target: str = DEFAULT_TARGET,
        port: int = DEFAULT_PORT,
        period_s: float = DEFAULT_PERIOD_S,
        current_limit: int = DEFAULT_CHASSIS_CURRENT_LIMIT,
        max_speed_rpm: int | None = None,
        max_rotate_rpm: int | None = None,
    ):
        self.controller = controller or ChassisController(
            target=target,
            port=port,
            period_s=period_s,
            current_limit=current_limit,
            max_speed_rpm=max_speed_rpm,
            max_rotate_rpm=max_rotate_rpm,
        )
        self._owns_controller = controller is None

    def close(self) -> None:
        if self._owns_controller:
            self.controller.close()

    def __enter__(self) -> "RoadRepairCompetitionBehaviorRunner":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
        self.close()

    def run(
        self,
        behavior: str,
        magnitude: float = DEFAULT_BEHAVIOR_MAGNITUDE,
        duration_s: float = DEFAULT_BEHAVIOR_DURATION_S,
        final_stop: bool = True,
    ) -> ChassisCommandResult:
        forward, strafe, rotate = behavior_axes(behavior, magnitude)
        return self.controller.set_velocity(
            forward=forward,
            strafe=strafe,
            rotate=rotate,
            duration_s=duration_s,
            final_stop=final_stop,
        )

    def run_sequence(
        self,
        steps: list[RoadRepairBehaviorStep],
        final_stop: bool = True,
    ) -> list[ChassisCommandResult]:
        results: list[ChassisCommandResult] = []
        for step in steps:
            results.append(
                self.run(
                    behavior=step.behavior,
                    magnitude=step.magnitude,
                    duration_s=step.duration_s,
                    final_stop=final_stop,
                )
            )
        return results

    def stop(self) -> None:
        self.controller.stop()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a bounded Road_Repair competition chassis behavior.")
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--behavior", choices=sorted(BEHAVIORS), default="stop")
    parser.add_argument("--magnitude", type=float, default=DEFAULT_BEHAVIOR_MAGNITUDE)
    parser.add_argument("--duration", type=float, default=DEFAULT_BEHAVIOR_DURATION_S)
    parser.add_argument(
        "--sequence",
        default="",
        help="Comma-separated behavior[:magnitude[:duration]] steps. Overrides --behavior.",
    )
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD_S)
    parser.add_argument("--current-limit", type=int, default=DEFAULT_CHASSIS_CURRENT_LIMIT)
    parser.add_argument("--max-speed-rpm", type=int, default=None)
    parser.add_argument("--max-rotate-rpm", type=int, default=None)
    parser.add_argument("--no-final-stop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    if args.sequence:
        steps = parse_behavior_sequence(
            args.sequence,
            default_magnitude=args.magnitude,
            default_duration_s=args.duration,
        )

        if args.dry_run:
            print(
                "dry-run RoadRepairCompetitionBehavior sequence "
                f"steps={len(steps)} current_limit={args.current_limit}"
            )
            for index, step in enumerate(steps, start=1):
                forward, strafe, rotate = behavior_axes(step.behavior, step.magnitude)
                axis_command = RoadRepairAxisCommand(
                    forward=forward,
                    strafe=strafe,
                    rotate=rotate,
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
                print(
                    f"  step={index} behavior={step.behavior} "
                    f"magnitude={step.magnitude:.3f} duration={step.duration_s:.3f}s "
                    f"axes={forward:.3f},{strafe:.3f},{rotate:.3f} "
                    f"rpm={vcmd.forward_rpm},{vcmd.strafe_rpm},{vcmd.rotate_rpm}"
                )
            return 0

        with RoadRepairCompetitionBehaviorRunner(
            target=args.target,
            port=args.port,
            period_s=args.period,
            current_limit=args.current_limit,
            max_speed_rpm=args.max_speed_rpm,
            max_rotate_rpm=args.max_rotate_rpm,
        ) as runner:
            results = runner.run_sequence(steps, final_stop=not args.no_final_stop)

        print(
            f"sent RoadRepairCompetitionBehavior sequence steps={len(steps)} "
            f"packets={sum(result.packets for result in results)} "
            f"current_limit={args.current_limit}"
        )
        for index, (step, result) in enumerate(zip(steps, results), start=1):
            print(
                f"  step={index} behavior={step.behavior} "
                f"magnitude={step.magnitude:.3f} duration={step.duration_s:.3f}s "
                f"rpm={result.forward_rpm},{result.strafe_rpm},{result.rotate_rpm} "
                f"packets={result.packets}"
            )
        return 0

    forward, strafe, rotate = behavior_axes(args.behavior, args.magnitude)
    axis_command = RoadRepairAxisCommand(
        forward=forward,
        strafe=strafe,
        rotate=rotate,
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
            "dry-run RoadRepairCompetitionBehavior "
            f"behavior={args.behavior} magnitude={clamp_float(abs(args.magnitude), 0.0, 1.0):.3f} "
            f"axes={forward:.3f},{strafe:.3f},{rotate:.3f} "
            f"duration={args.duration:.3f}s -> "
            f"rpm={vcmd.forward_rpm},{vcmd.strafe_rpm},{vcmd.rotate_rpm} "
            f"current_limit={vcmd.current_limit}"
        )
        return 0

    with RoadRepairCompetitionBehaviorRunner(
        target=args.target,
        port=args.port,
        period_s=args.period,
        current_limit=args.current_limit,
        max_speed_rpm=args.max_speed_rpm,
        max_rotate_rpm=args.max_rotate_rpm,
    ) as runner:
        result = runner.run(
            behavior=args.behavior,
            magnitude=args.magnitude,
            duration_s=args.duration,
            final_stop=not args.no_final_stop,
        )

    print(
        f"sent RoadRepairCompetitionBehavior behavior={args.behavior} "
        f"packets={result.packets} "
        f"rpm={result.forward_rpm},{result.strafe_rpm},{result.rotate_rpm} "
        f"current_limit={result.current_limit}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
