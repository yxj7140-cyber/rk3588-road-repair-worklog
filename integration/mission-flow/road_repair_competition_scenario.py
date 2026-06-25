#!/usr/bin/env python3
"""Preset-road scenario model for the Road_Repair RK3588 migration."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from road_repair_competition_api import (
    DEFAULT_ALIGN_MAGNITUDE,
    DEFAULT_INSPECT_MAGNITUDE,
    DEFAULT_LATERAL_DEADBAND_M,
    DEFAULT_PUMP_DURATION_S,
    DEFAULT_ROTATE_MAGNITUDE,
    DEFAULT_YAW_DEADBAND_DEG,
    RoadRepairDefectObservation,
    preview_steps,
)
from road_repair_competition_behavior import BEHAVIORS, RoadRepairBehaviorStep


@dataclass(frozen=True)
class PresetRoadSegment:
    name: str
    behavior: str = "forward"
    magnitude: float = DEFAULT_INSPECT_MAGNITUDE
    duration_s: float = 0.5

    def to_step(self) -> RoadRepairBehaviorStep:
        if self.behavior not in BEHAVIORS:
            raise ValueError(f"unknown preset-road behavior: {self.behavior}")
        return RoadRepairBehaviorStep(
            behavior=self.behavior,
            magnitude=max(0.0, min(1.0, abs(float(self.magnitude)))),
            duration_s=max(0.0, float(self.duration_s)),
        )


@dataclass(frozen=True)
class RoadRepairScenario:
    name: str = "default_single_defect"
    defect: RoadRepairDefectObservation = field(default_factory=RoadRepairDefectObservation)
    pre_defect_segments: tuple[PresetRoadSegment, ...] = field(
        default_factory=lambda: (
            PresetRoadSegment("inspect_start", "forward", DEFAULT_INSPECT_MAGNITUDE, 0.60),
            PresetRoadSegment("inspect_continue", "forward", DEFAULT_INSPECT_MAGNITUDE, 0.50),
        )
    )
    approach_segment: PresetRoadSegment = field(
        default_factory=lambda: PresetRoadSegment(
            "approach_repair_point",
            "forward",
            DEFAULT_INSPECT_MAGNITUDE,
            0.45,
        )
    )
    post_repair_segments: tuple[PresetRoadSegment, ...] = field(
        default_factory=lambda: (
            PresetRoadSegment("resume_inspection", "forward", DEFAULT_INSPECT_MAGNITUDE, 0.40),
        )
    )
    detect_stop_s: float = 0.20
    arm_align_s: float = 0.40
    pump_duration_s: float = DEFAULT_PUMP_DURATION_S
    arm_retract_s: float = 0.30
    final_stop_s: float = 0.30


def build_scenario_steps(
    scenario: RoadRepairScenario,
    align_magnitude: float = DEFAULT_ALIGN_MAGNITUDE,
    rotate_magnitude: float = DEFAULT_ROTATE_MAGNITUDE,
    lateral_deadband_m: float = DEFAULT_LATERAL_DEADBAND_M,
    yaw_deadband_deg: float = DEFAULT_YAW_DEADBAND_DEG,
) -> list[RoadRepairBehaviorStep]:
    defect = scenario.defect
    steps = [segment.to_step() for segment in scenario.pre_defect_segments]
    steps.append(RoadRepairBehaviorStep("stop", 0.0, max(0.0, scenario.detect_stop_s)))

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
            scenario.approach_segment.to_step(),
            RoadRepairBehaviorStep("stop", 0.0, max(0.0, scenario.arm_align_s)),
            RoadRepairBehaviorStep("stop", 0.0, max(0.0, scenario.pump_duration_s)),
            RoadRepairBehaviorStep("stop", 0.0, max(0.0, scenario.arm_retract_s)),
        ]
    )
    steps.extend(segment.to_step() for segment in scenario.post_repair_segments)
    steps.append(RoadRepairBehaviorStep("stop", 0.0, max(0.0, scenario.final_stop_s)))
    return steps


def _read_segment(data: dict[str, Any], default_name: str) -> PresetRoadSegment:
    return PresetRoadSegment(
        name=str(data.get("name", default_name)),
        behavior=str(data.get("behavior", "forward")),
        magnitude=float(data.get("magnitude", DEFAULT_INSPECT_MAGNITUDE)),
        duration_s=float(data.get("duration_s", data.get("duration", 0.5))),
    )


def _read_segments(value: Any, default_prefix: str) -> tuple[PresetRoadSegment, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{default_prefix} must be a list")
    return tuple(
        _read_segment(item, f"{default_prefix}_{index}")
        for index, item in enumerate(value, start=1)
    )


def load_scenario_file(path: str | Path) -> RoadRepairScenario:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("scenario file must contain a JSON object")

    defect_data = data.get("defect", {})
    if not isinstance(defect_data, dict):
        raise ValueError("scenario defect must be a JSON object")

    return RoadRepairScenario(
        name=str(data.get("name", "scenario")),
        defect=RoadRepairDefectObservation(
            kind=str(defect_data.get("kind", "pothole")),
            distance_m=float(defect_data.get("distance_m", 0.80)),
            lateral_offset_m=float(defect_data.get("lateral_offset_m", 0.16)),
            yaw_error_deg=float(defect_data.get("yaw_error_deg", -4.0)),
        ),
        pre_defect_segments=_read_segments(data.get("pre_defect_segments"), "pre_defect"),
        approach_segment=_read_segment(data.get("approach_segment", {}), "approach_repair_point"),
        post_repair_segments=_read_segments(data.get("post_repair_segments"), "post_repair"),
        detect_stop_s=float(data.get("detect_stop_s", 0.20)),
        arm_align_s=float(data.get("arm_align_s", 0.40)),
        pump_duration_s=float(data.get("pump_duration_s", DEFAULT_PUMP_DURATION_S)),
        arm_retract_s=float(data.get("arm_retract_s", 0.30)),
        final_stop_s=float(data.get("final_stop_s", 0.30)),
    )


def scenario_to_dict(scenario: RoadRepairScenario) -> dict[str, Any]:
    def segment_to_dict(segment: PresetRoadSegment) -> dict[str, Any]:
        return {
            "name": segment.name,
            "behavior": segment.behavior,
            "magnitude": segment.magnitude,
            "duration_s": segment.duration_s,
        }

    return {
        "name": scenario.name,
        "defect": {
            "kind": scenario.defect.kind,
            "distance_m": scenario.defect.distance_m,
            "lateral_offset_m": scenario.defect.lateral_offset_m,
            "yaw_error_deg": scenario.defect.yaw_error_deg,
        },
        "pre_defect_segments": [segment_to_dict(segment) for segment in scenario.pre_defect_segments],
        "approach_segment": segment_to_dict(scenario.approach_segment),
        "post_repair_segments": [segment_to_dict(segment) for segment in scenario.post_repair_segments],
        "detect_stop_s": scenario.detect_stop_s,
        "arm_align_s": scenario.arm_align_s,
        "pump_duration_s": scenario.pump_duration_s,
        "arm_retract_s": scenario.arm_retract_s,
        "final_stop_s": scenario.final_stop_s,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview a Road_Repair preset-road scenario.")
    parser.add_argument("--scenario-file")
    parser.add_argument("--current-limit", type=int, default=1200)
    parser.add_argument("--max-speed-rpm", type=int, default=None)
    parser.add_argument("--max-rotate-rpm", type=int, default=None)
    parser.add_argument("--print-default-json", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    scenario = load_scenario_file(args.scenario_file) if args.scenario_file else RoadRepairScenario()

    if args.print_default_json:
        print(json.dumps(scenario_to_dict(scenario), indent=2))
        return 0

    steps = build_scenario_steps(scenario)
    previews = preview_steps(
        steps,
        current_limit=args.current_limit,
        max_speed_rpm=args.max_speed_rpm,
        max_rotate_rpm=args.max_rotate_rpm,
    )
    print(f"scenario={scenario.name} steps={len(steps)} defect={scenario.defect.kind}")
    for index, preview in enumerate(previews, start=1):
        print(
            f"  step={index} behavior={preview.behavior} "
            f"magnitude={preview.magnitude:.3f} duration={preview.duration_s:.3f}s "
            f"rpm={preview.forward_rpm},{preview.strafe_rpm},{preview.rotate_rpm} "
            f"current_limit={preview.current_limit}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
