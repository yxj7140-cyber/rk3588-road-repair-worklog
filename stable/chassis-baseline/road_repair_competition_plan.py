#!/usr/bin/env python3
"""Tiny plan-file entry for Road_Repair competition chassis migration.

This module is intentionally only a file/CLI wrapper around the validated
RoadRepairCompetitionBehaviorRunner. It does not add strategy, vision, CAN, PID,
or navigation.

Plan file format:

    # behavior magnitude duration_s
    forward 0.35 0.3
    stop 0 0.2
    strafe-right 0.35 0.3

The compact behavior sequence format is also accepted per line:

    forward:0.35:0.3
"""

from __future__ import annotations

import argparse
from pathlib import Path

from chassis_control import DEFAULT_CHASSIS_CURRENT_LIMIT
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
from road_repair_vcmd_adapter import RoadRepairAxisCommand


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].strip()


def parse_plan_line(
    line: str,
    default_magnitude: float = DEFAULT_BEHAVIOR_MAGNITUDE,
    default_duration_s: float = DEFAULT_BEHAVIOR_DURATION_S,
) -> RoadRepairBehaviorStep | None:
    line = _strip_comment(line)
    if not line:
        return None

    if ":" in line and len(line.replace(",", " ").split()) == 1:
        return parse_behavior_step(line, default_magnitude, default_duration_s)

    parts = line.replace(",", " ").split()
    if len(parts) > 3:
        raise ValueError(f"invalid plan line: {line!r}")

    compact = ":".join(parts)
    return parse_behavior_step(compact, default_magnitude, default_duration_s)


def load_plan_file(
    plan_path: str | Path,
    default_magnitude: float = DEFAULT_BEHAVIOR_MAGNITUDE,
    default_duration_s: float = DEFAULT_BEHAVIOR_DURATION_S,
) -> list[RoadRepairBehaviorStep]:
    steps: list[RoadRepairBehaviorStep] = []
    path = Path(plan_path)

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                step = parse_plan_line(line, default_magnitude, default_duration_s)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
            if step is not None:
                steps.append(step)

    if not steps:
        raise ValueError(f"{path}: empty plan")
    return steps


def dry_run_steps(steps: list[RoadRepairBehaviorStep], current_limit: int) -> None:
    print(f"dry-run RoadRepairCompetitionPlan steps={len(steps)} current_limit={current_limit}")
    for index, step in enumerate(steps, start=1):
        forward, strafe, rotate = behavior_axes(step.behavior, step.magnitude)
        axis_command = RoadRepairAxisCommand(
            forward=forward,
            strafe=strafe,
            rotate=rotate,
            current_limit=current_limit,
        )
        vcmd = axis_command.to_vcmd()
        print(
            f"  step={index} behavior={step.behavior} "
            f"magnitude={step.magnitude:.3f} duration={step.duration_s:.3f}s "
            f"axes={forward:.3f},{strafe:.3f},{rotate:.3f} "
            f"rpm={vcmd.forward_rpm},{vcmd.strafe_rpm},{vcmd.rotate_rpm}"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Road_Repair competition chassis plan.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--plan", help="Path to a plain text behavior plan.")
    source.add_argument(
        "--sequence",
        help="Comma-separated behavior[:magnitude[:duration]] steps.",
    )
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--magnitude", type=float, default=DEFAULT_BEHAVIOR_MAGNITUDE)
    parser.add_argument("--duration", type=float, default=DEFAULT_BEHAVIOR_DURATION_S)
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD_S)
    parser.add_argument("--current-limit", type=int, default=DEFAULT_CHASSIS_CURRENT_LIMIT)
    parser.add_argument("--no-final-stop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    if args.plan:
        steps = load_plan_file(
            args.plan,
            default_magnitude=args.magnitude,
            default_duration_s=args.duration,
        )
    else:
        steps = parse_behavior_sequence(
            args.sequence,
            default_magnitude=args.magnitude,
            default_duration_s=args.duration,
        )

    if args.dry_run:
        dry_run_steps(steps, args.current_limit)
        return 0

    with RoadRepairCompetitionBehaviorRunner(
        target=args.target,
        port=args.port,
        period_s=args.period,
        current_limit=args.current_limit,
    ) as runner:
        results = runner.run_sequence(steps, final_stop=not args.no_final_stop)

    print(
        f"sent RoadRepairCompetitionPlan steps={len(steps)} "
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


if __name__ == "__main__":
    raise SystemExit(main())
