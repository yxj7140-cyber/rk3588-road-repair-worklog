#!/usr/bin/env python3
"""Replaceable virtual devices for the Road_Repair RK3588 migration.

The chassis is the only real actuator in the current bench setup. These small
interfaces keep the competition task flow shaped like the final robot while the
depth camera, arm, pump, and lidar are still simulated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from road_repair_competition_behavior import RoadRepairBehaviorStep
from road_repair_competition_api import RoadRepairDefectObservation


@dataclass(frozen=True)
class VirtualRoadDefect:
    kind: str
    distance_m: float
    lateral_offset_m: float
    yaw_error_deg: float = 0.0

    def to_observation(self) -> RoadRepairDefectObservation:
        return RoadRepairDefectObservation(
            kind=self.kind,
            distance_m=self.distance_m,
            lateral_offset_m=self.lateral_offset_m,
            yaw_error_deg=self.yaw_error_deg,
        )


@dataclass(frozen=True)
class VirtualPedestrian:
    distance_m: float
    side: str = "center"


@dataclass(frozen=True)
class VirtualMissionAction:
    source: str
    message: str
    step: RoadRepairBehaviorStep | None = None


class DepthCameraDevice(Protocol):
    def detect_defect(self) -> VirtualRoadDefect:
        ...


class LidarDevice(Protocol):
    def detect_pedestrian(self) -> VirtualPedestrian:
        ...


class RepairArmDevice(Protocol):
    def align(self, defect: VirtualRoadDefect) -> str:
        ...

    def retract(self) -> str:
        ...


class CementPumpDevice(Protocol):
    def dispense(self, duration_s: float) -> str:
        ...


class VirtualDepthCamera:
    """Scripted depth-camera detections for current chassis-only testing."""

    def __init__(self, defect: VirtualRoadDefect | None = None):
        self.defect = defect or VirtualRoadDefect(
            kind="pothole",
            distance_m=0.80,
            lateral_offset_m=0.16,
            yaw_error_deg=-4.0,
        )

    def detect_defect(self) -> VirtualRoadDefect:
        return self.defect

    def scripted_defect(self) -> VirtualRoadDefect:
        return self.detect_defect()


class VirtualLidar:
    """Scripted lidar pedestrian event for optional avoidance-path testing."""

    def __init__(self, pedestrian: VirtualPedestrian | None = None):
        self.pedestrian = pedestrian or VirtualPedestrian(distance_m=0.65, side="center")

    def detect_pedestrian(self) -> VirtualPedestrian:
        return self.pedestrian

    def scripted_pedestrian(self) -> VirtualPedestrian:
        return self.detect_pedestrian()


class VirtualArm:
    def align(self, defect: VirtualRoadDefect) -> str:
        return (
            "arm align virtual "
            f"target={defect.kind} offset={defect.lateral_offset_m:.2f}m "
            f"yaw={defect.yaw_error_deg:.1f}deg"
        )

    def retract(self) -> str:
        return "arm retract virtual"


class VirtualPump:
    def dispense(self, duration_s: float) -> str:
        return f"pump dispense cement virtual duration={duration_s:.2f}s"
