#!/usr/bin/env python3
"""Real Piper implementation of the Road_Repair arm device boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from road_repair_arm_control import RoadRepairArmController


class DefectLike(Protocol):
    kind: str
    distance_m: float
    lateral_offset_m: float
    yaw_error_deg: float


@dataclass(frozen=True)
class PiperArmDeviceConfig:
    interface: str | None = "socketcan"
    channel: str | None = None
    bitrate: int | None = None
    firmware: str = "default"
    env_path: str | Path | None = None
    profiles_path: str | Path | None = None
    execute: bool = False
    align_action: str = "approach"
    retract_action: str = "current_safe"
    settle_s: float = 2.0
    disable_after: bool = False


class PiperRepairArmDevice:
    """Drop-in replacement for the virtual `RepairArmDevice`.

    Default mode is dry-run so it can be safely wired into the existing virtual
    mission flow before enabling real motion.
    """

    def __init__(self, config: PiperArmDeviceConfig | None = None):
        self.config = config or PiperArmDeviceConfig()
        self.last_results: list[dict[str, Any]] = []

    def _run_action(self, action: str) -> dict[str, Any]:
        with RoadRepairArmController(
            interface=self.config.interface,
            channel=self.config.channel,
            bitrate=self.config.bitrate,
            firmware=self.config.firmware,
            profiles_path=self.config.profiles_path,
            env_path=self.config.env_path,
        ) as controller:
            return controller.run_action(
                action,
                execute=self.config.execute,
                settle_s=self.config.settle_s,
                disable_after=self.config.disable_after,
            ).to_dict()

    def align(self, defect: DefectLike) -> str:
        result = self._run_action(self.config.align_action)
        self.last_results.append(
            {
                "op": "align",
                "action": self.config.align_action,
                "defect": {
                    "kind": defect.kind,
                    "distance_m": defect.distance_m,
                    "lateral_offset_m": defect.lateral_offset_m,
                    "yaw_error_deg": defect.yaw_error_deg,
                },
                "result": result,
            }
        )
        mode = "execute" if self.config.execute else "dry-run"
        return (
            f"piper arm align {mode} action={self.config.align_action} "
            f"target={defect.kind} offset={defect.lateral_offset_m:.2f}m "
            f"yaw={defect.yaw_error_deg:.1f}deg ok={result.get('ok')}"
        )

    def retract(self) -> str:
        result = self._run_action(self.config.retract_action)
        self.last_results.append(
            {
                "op": "retract",
                "action": self.config.retract_action,
                "result": result,
            }
        )
        mode = "execute" if self.config.execute else "dry-run"
        return (
            f"piper arm retract {mode} action={self.config.retract_action} "
            f"ok={result.get('ok')}"
        )
