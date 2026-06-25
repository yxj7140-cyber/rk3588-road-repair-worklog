#!/usr/bin/env python3
"""Stable competition-side chassis API for the RK3588 Road_Repair port.

This is the import surface for upper-layer competition code. It intentionally
wraps the validated behavior/plan modules instead of reimplementing strategy,
vision, CAN, PID, or wheel mixing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from chassis_control import ChassisCommandResult, DEFAULT_CHASSIS_CURRENT_LIMIT
from chassis_vcmd_client import DEFAULT_PERIOD_S, DEFAULT_PORT, DEFAULT_TARGET
from road_repair_competition_behavior import (
    DEFAULT_BEHAVIOR_DURATION_S,
    DEFAULT_BEHAVIOR_MAGNITUDE,
    RoadRepairBehaviorStep,
    RoadRepairCompetitionBehaviorRunner,
    behavior_axes,
    parse_behavior_sequence,
    parse_behavior_step,
)
from road_repair_competition_plan import load_plan_file
from road_repair_vcmd_adapter import RoadRepairAxisCommand


@dataclass(frozen=True)
class RoadRepairActionPreview:
    step: int
    behavior: str
    magnitude: float
    duration_s: float
    forward_rpm: int
    strafe_rpm: int
    rotate_rpm: int
    current_limit: int


@dataclass(frozen=True)
class RoadRepairDefectObservation:
    """Minimal perception result needed by the current chassis-only task flow."""

    kind: str = "pothole"
    distance_m: float = 0.80
    lateral_offset_m: float = 0.16
    yaw_error_deg: float = -4.0


DEFAULT_INSPECT_MAGNITUDE = 0.18
DEFAULT_ALIGN_MAGNITUDE = 0.16
DEFAULT_ROTATE_MAGNITUDE = 0.20
DEFAULT_PUMP_DURATION_S = 0.80
DEFAULT_LATERAL_DEADBAND_M = 0.03
DEFAULT_YAW_DEADBAND_DEG = 2.0


def build_inspection_repair_steps(
    defect: RoadRepairDefectObservation = RoadRepairDefectObservation(),
    inspect_magnitude: float = DEFAULT_INSPECT_MAGNITUDE,
    align_magnitude: float = DEFAULT_ALIGN_MAGNITUDE,
    rotate_magnitude: float = DEFAULT_ROTATE_MAGNITUDE,
    pump_duration_s: float = DEFAULT_PUMP_DURATION_S,
    lateral_deadband_m: float = DEFAULT_LATERAL_DEADBAND_M,
    yaw_deadband_deg: float = DEFAULT_YAW_DEADBAND_DEG,
    include_resume: bool = True,
) -> list[RoadRepairBehaviorStep]:
    """Build the no-avoidance Topic-1 chassis flow from one virtual defect.

    Non-chassis hardware is represented by bounded stop durations. Real depth
    camera, arm, and pump modules can later replace the data source/effectors
    without changing the validated chassis command path.
    """

    steps = [
        RoadRepairBehaviorStep("forward", inspect_magnitude, 0.60),
        RoadRepairBehaviorStep("forward", inspect_magnitude, 0.50),
        RoadRepairBehaviorStep("stop", 0.0, 0.20),
    ]

    if defect.lateral_offset_m > lateral_deadband_m:
        steps.append(RoadRepairBehaviorStep("strafe-right", align_magnitude, 0.35))
    elif defect.lateral_offset_m < -lateral_deadband_m:
        steps.append(RoadRepairBehaviorStep("strafe-left", align_magnitude, 0.35))

    if defect.yaw_error_deg < -yaw_deadband_deg:
        steps.append(RoadRepairBehaviorStep("rotate-right", rotate_magnitude, 0.25))
    elif defect.yaw_error_deg > yaw_deadband_deg:
        steps.append(RoadRepairBehaviorStep("rotate-left", rotate_magnitude, 0.25))

    steps.extend(
        [
            RoadRepairBehaviorStep("forward", inspect_magnitude, 0.45),
            RoadRepairBehaviorStep("stop", 0.0, 0.40),
            RoadRepairBehaviorStep("stop", 0.0, pump_duration_s),
            RoadRepairBehaviorStep("stop", 0.0, 0.30),
        ]
    )

    if include_resume:
        steps.extend(
            [
                RoadRepairBehaviorStep("forward", inspect_magnitude, 0.40),
                RoadRepairBehaviorStep("stop", 0.0, 0.30),
            ]
        )

    return steps


def preview_steps(
    steps: list[RoadRepairBehaviorStep],
    current_limit: int = DEFAULT_CHASSIS_CURRENT_LIMIT,
    max_speed_rpm: int | None = None,
    max_rotate_rpm: int | None = None,
) -> list[RoadRepairActionPreview]:
    previews: list[RoadRepairActionPreview] = []
    for index, step in enumerate(steps, start=1):
        forward, strafe, rotate = behavior_axes(step.behavior, step.magnitude)
        vcmd = RoadRepairAxisCommand(
            forward=forward,
            strafe=strafe,
            rotate=rotate,
            current_limit=current_limit,
            **{
                key: value
                for key, value in {
                    "max_speed_rpm": max_speed_rpm,
                    "max_rotate_rpm": max_rotate_rpm,
                }.items()
                if value is not None
            },
        ).to_vcmd()
        previews.append(
            RoadRepairActionPreview(
                step=index,
                behavior=step.behavior,
                magnitude=step.magnitude,
                duration_s=step.duration_s,
                forward_rpm=vcmd.forward_rpm,
                strafe_rpm=vcmd.strafe_rpm,
                rotate_rpm=vcmd.rotate_rpm,
                current_limit=vcmd.current_limit,
            )
        )
    return previews


class RoadRepairCompetitionChassis:
    """Small facade for competition decisions to command the chassis."""

    def __init__(
        self,
        target: str = DEFAULT_TARGET,
        port: int = DEFAULT_PORT,
        period_s: float = DEFAULT_PERIOD_S,
        current_limit: int = DEFAULT_CHASSIS_CURRENT_LIMIT,
        max_speed_rpm: int | None = None,
        max_rotate_rpm: int | None = None,
    ):
        self.current_limit = int(current_limit)
        self.max_speed_rpm = max_speed_rpm
        self.max_rotate_rpm = max_rotate_rpm
        self.runner = RoadRepairCompetitionBehaviorRunner(
            target=target,
            port=port,
            period_s=period_s,
            current_limit=self.current_limit,
            max_speed_rpm=self.max_speed_rpm,
            max_rotate_rpm=self.max_rotate_rpm,
        )

    def close(self) -> None:
        self.runner.close()

    def __enter__(self) -> "RoadRepairCompetitionChassis":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
        self.close()

    def preview_behavior(
        self,
        behavior: str,
        magnitude: float = DEFAULT_BEHAVIOR_MAGNITUDE,
        duration_s: float = DEFAULT_BEHAVIOR_DURATION_S,
    ) -> RoadRepairActionPreview:
        return preview_steps(
            [RoadRepairBehaviorStep(behavior=behavior, magnitude=magnitude, duration_s=duration_s)],
            current_limit=self.current_limit,
            max_speed_rpm=self.max_speed_rpm,
            max_rotate_rpm=self.max_rotate_rpm,
        )[0]

    def preview_sequence(self, sequence: str) -> list[RoadRepairActionPreview]:
        return preview_steps(
            parse_behavior_sequence(sequence),
            current_limit=self.current_limit,
            max_speed_rpm=self.max_speed_rpm,
            max_rotate_rpm=self.max_rotate_rpm,
        )

    def preview_plan_file(self, plan_path: str | Path) -> list[RoadRepairActionPreview]:
        return preview_steps(
            load_plan_file(plan_path),
            current_limit=self.current_limit,
            max_speed_rpm=self.max_speed_rpm,
            max_rotate_rpm=self.max_rotate_rpm,
        )

    def run_behavior(
        self,
        behavior: str,
        magnitude: float = DEFAULT_BEHAVIOR_MAGNITUDE,
        duration_s: float = DEFAULT_BEHAVIOR_DURATION_S,
        final_stop: bool = True,
    ) -> ChassisCommandResult:
        return self.runner.run(
            behavior=behavior,
            magnitude=magnitude,
            duration_s=duration_s,
            final_stop=final_stop,
        )

    def run_steps(
        self,
        steps: list[RoadRepairBehaviorStep],
        final_stop: bool = True,
    ) -> list[ChassisCommandResult]:
        return self.runner.run_sequence(steps, final_stop=final_stop)

    def run_sequence(self, sequence: str, final_stop: bool = True) -> list[ChassisCommandResult]:
        return self.run_steps(parse_behavior_sequence(sequence), final_stop=final_stop)

    def run_plan_file(
        self,
        plan_path: str | Path,
        final_stop: bool = True,
    ) -> list[ChassisCommandResult]:
        return self.run_steps(load_plan_file(plan_path), final_stop=final_stop)

    def preview_inspection_repair(
        self,
        defect: RoadRepairDefectObservation = RoadRepairDefectObservation(),
        inspect_magnitude: float = DEFAULT_INSPECT_MAGNITUDE,
        align_magnitude: float = DEFAULT_ALIGN_MAGNITUDE,
        rotate_magnitude: float = DEFAULT_ROTATE_MAGNITUDE,
        pump_duration_s: float = DEFAULT_PUMP_DURATION_S,
        include_resume: bool = True,
    ) -> list[RoadRepairActionPreview]:
        return preview_steps(
            build_inspection_repair_steps(
                defect=defect,
                inspect_magnitude=inspect_magnitude,
                align_magnitude=align_magnitude,
                rotate_magnitude=rotate_magnitude,
                pump_duration_s=pump_duration_s,
                include_resume=include_resume,
            ),
            current_limit=self.current_limit,
            max_speed_rpm=self.max_speed_rpm,
            max_rotate_rpm=self.max_rotate_rpm,
        )

    def run_inspection_repair(
        self,
        defect: RoadRepairDefectObservation = RoadRepairDefectObservation(),
        inspect_magnitude: float = DEFAULT_INSPECT_MAGNITUDE,
        align_magnitude: float = DEFAULT_ALIGN_MAGNITUDE,
        rotate_magnitude: float = DEFAULT_ROTATE_MAGNITUDE,
        pump_duration_s: float = DEFAULT_PUMP_DURATION_S,
        include_resume: bool = True,
        final_stop: bool = True,
    ) -> list[ChassisCommandResult]:
        return self.run_steps(
            build_inspection_repair_steps(
                defect=defect,
                inspect_magnitude=inspect_magnitude,
                align_magnitude=align_magnitude,
                rotate_magnitude=rotate_magnitude,
                pump_duration_s=pump_duration_s,
                include_resume=include_resume,
            ),
            final_stop=final_stop,
        )

    def stop(self) -> None:
        self.runner.stop()


def _print_previews(previews: list[RoadRepairActionPreview]) -> None:
    for preview in previews:
        print(
            f"  step={preview.step} behavior={preview.behavior} "
            f"magnitude={preview.magnitude:.3f} duration={preview.duration_s:.3f}s "
            f"rpm={preview.forward_rpm},{preview.strafe_rpm},{preview.rotate_rpm} "
            f"current_limit={preview.current_limit}"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Road_Repair competition chassis API preview.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--behavior")
    source.add_argument("--sequence")
    source.add_argument("--plan")
    source.add_argument("--inspection-repair", action="store_true")
    parser.add_argument("--magnitude", type=float, default=DEFAULT_BEHAVIOR_MAGNITUDE)
    parser.add_argument("--duration", type=float, default=DEFAULT_BEHAVIOR_DURATION_S)
    parser.add_argument("--current-limit", type=int, default=DEFAULT_CHASSIS_CURRENT_LIMIT)
    parser.add_argument("--max-speed-rpm", type=int, default=None)
    parser.add_argument("--max-rotate-rpm", type=int, default=None)
    parser.add_argument("--defect-kind", default="pothole")
    parser.add_argument("--defect-distance", type=float, default=0.80)
    parser.add_argument("--defect-lateral-offset", type=float, default=0.16)
    parser.add_argument("--defect-yaw-error", type=float, default=-4.0)
    parser.add_argument("--inspect-magnitude", type=float, default=DEFAULT_INSPECT_MAGNITUDE)
    parser.add_argument("--align-magnitude", type=float, default=DEFAULT_ALIGN_MAGNITUDE)
    parser.add_argument("--rotate-magnitude", type=float, default=DEFAULT_ROTATE_MAGNITUDE)
    parser.add_argument("--pump-duration", type=float, default=DEFAULT_PUMP_DURATION_S)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    if not args.dry_run:
        raise SystemExit("ERROR: road_repair_competition_api.py CLI only supports --dry-run")

    if args.behavior:
        steps = [
            parse_behavior_step(
                f"{args.behavior}:{args.magnitude}:{args.duration}",
                default_magnitude=args.magnitude,
                default_duration_s=args.duration,
            )
        ]
    elif args.sequence:
        steps = parse_behavior_sequence(args.sequence)
    elif args.plan:
        steps = load_plan_file(args.plan)
    else:
        steps = build_inspection_repair_steps(
            defect=RoadRepairDefectObservation(
                kind=args.defect_kind,
                distance_m=args.defect_distance,
                lateral_offset_m=args.defect_lateral_offset,
                yaw_error_deg=args.defect_yaw_error,
            ),
            inspect_magnitude=args.inspect_magnitude,
            align_magnitude=args.align_magnitude,
            rotate_magnitude=args.rotate_magnitude,
            pump_duration_s=args.pump_duration,
            include_resume=not args.no_resume,
        )

    previews = preview_steps(
        steps,
        current_limit=args.current_limit,
        max_speed_rpm=args.max_speed_rpm,
        max_rotate_rpm=args.max_rotate_rpm,
    )
    print(f"dry-run RoadRepairCompetitionChassis steps={len(previews)}")
    _print_previews(previews)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
