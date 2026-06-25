#!/usr/bin/env python3
"""Road_Repair task-level arm control.

The arm is treated as a Linux-side task actuator. This module stays separate
from the validated chassis RT path and only depends on the Piper adapter.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from road_repair_piper_arm import (
    DEFAULT_BITRATE,
    DEFAULT_FIRMWARE,
    PiperArmController,
    PiperConnectionConfig,
    PiperMotionProfile,
    load_motion_profiles,
    save_motion_profiles,
)


DEFAULT_ENV_FILE = "piper_can_interface.env"
ACTION_TO_PROFILE = {
    "current_safe": "current_safe",
    "safe_home": "task_home",
    "task_home": "task_home",
    "observe": "inspection_observe",
    "prepose": "repair_prepose",
    "approach": "repair_approach",
    "retract": "repair_retract",
}
DEFAULT_REPAIR_SEQUENCE = ["task_home", "prepose", "approach", "retract", "task_home"]


@dataclass(frozen=True)
class RepairArmPoseResult:
    name: str
    ok: bool
    execute: bool = False
    note: str = ""
    profile: dict[str, Any] | None = None
    snapshot_before: dict[str, Any] | None = None
    snapshot_after: dict[str, Any] | None = None
    enabled_before: list[bool] | None = None
    enabled_after: list[bool] | None = None
    motion_wait: dict[str, Any] | None = None
    disabled_after: bool | dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_piper_env(path: str | Path | None = None) -> dict[str, str]:
    env_path = Path(path) if path else Path.cwd() / DEFAULT_ENV_FILE
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def profile_to_dict(profile: PiperMotionProfile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "description": profile.description,
        "joints": list(profile.joints),
        "speed_percent": int(profile.speed_percent),
    }


class RoadRepairArmController:
    def __init__(
        self,
        interface: str | None = None,
        channel: str | None = None,
        bitrate: int | None = None,
        firmware: str = DEFAULT_FIRMWARE,
        timeout: float = 1.0,
        profiles_path: str | Path | None = None,
        env_path: str | Path | None = None,
    ):
        env = load_piper_env(env_path)
        resolved_channel = channel or env.get("PIPER_CAN")
        resolved_bitrate = int(bitrate or env.get("PIPER_CAN_BITRATE") or DEFAULT_BITRATE)
        self.connection = PiperConnectionConfig(
            interface=interface,
            channel=resolved_channel,
            bitrate=resolved_bitrate,
            firmware=firmware,
            timeout=timeout,
        )
        self.profiles = load_motion_profiles(profiles_path)
        self.arm = PiperArmController(self.connection)

    def __enter__(self) -> "RoadRepairArmController":
        self.arm.connect()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.arm.disconnect()

    def snapshot(self) -> dict[str, Any]:
        return self.arm.snapshot()

    def profile_summary(self) -> dict[str, dict[str, Any]]:
        return {name: profile_to_dict(profile) for name, profile in self.profiles.items()}

    def capture_current_profile(
        self,
        name: str,
        description: str = "",
        speed_percent: int = 5,
        profiles_path: str | Path | None = None,
    ) -> dict[str, Any]:
        snapshot = self.arm.snapshot()
        joint_data = snapshot.get("get_joint_angles")
        if not isinstance(joint_data, dict):
            raise RuntimeError(f"joint angles unavailable: {joint_data!r}")
        joints = joint_data.get("msg")
        if not isinstance(joints, list) or len(joints) != 6:
            raise RuntimeError(f"joint angles malformed: {joints!r}")

        profile = PiperMotionProfile(
            name=name,
            description=description,
            joints=[float(value) for value in joints],
            speed_percent=int(speed_percent),
        )
        profile.validate()
        self.profiles[name] = profile
        save_motion_profiles(self.profiles, profiles_path)
        return {
            "captured": profile_to_dict(profile),
            "snapshot": snapshot,
        }

    def goto_profile(
        self,
        profile_name: str,
        execute: bool = False,
        settle_s: float = 2.0,
        disable_after: bool = False,
    ) -> RepairArmPoseResult:
        if profile_name not in self.profiles:
            raise KeyError(f"unknown profile {profile_name!r}")
        profile = self.profiles[profile_name]
        profile_data = profile_to_dict(profile)
        if not execute:
            return RepairArmPoseResult(
                name=profile.name,
                ok=True,
                execute=False,
                note="dry-run",
                profile=profile_data,
            )

        before = self.arm.snapshot()
        enabled_before = self.arm.joints_enabled()
        after: dict[str, Any] | None = None
        enabled_after: list[bool] | None = None
        motion_wait: dict[str, Any] | None = None
        disabled_after: bool | dict[str, str] | None = None
        try:
            motion_wait = self.arm.move_profile(profile)
            time.sleep(max(0.0, float(settle_s)))
            after = self.arm.snapshot()
            enabled_after = self.arm.joints_enabled()
        finally:
            if disable_after:
                try:
                    disabled_after = self.arm.disable()
                except Exception as exc:
                    disabled_after = {"error": str(exc)}

        return RepairArmPoseResult(
            name=profile.name,
            ok=True,
            execute=True,
            note="executed",
            profile=profile_data,
            snapshot_before=before,
            snapshot_after=after,
            enabled_before=enabled_before,
            enabled_after=enabled_after,
            motion_wait=motion_wait,
            disabled_after=disabled_after,
        )

    def run_action(
        self,
        action: str,
        execute: bool = False,
        settle_s: float = 2.0,
        disable_after: bool = False,
    ) -> RepairArmPoseResult:
        if action not in ACTION_TO_PROFILE:
            raise KeyError(f"unknown action {action!r}; available={sorted(ACTION_TO_PROFILE)}")
        return self.goto_profile(
            ACTION_TO_PROFILE[action],
            execute=execute,
            settle_s=settle_s,
            disable_after=disable_after,
        )

    def safe_home(self, execute: bool = False) -> RepairArmPoseResult:
        return self.run_action("task_home", execute=execute)

    def inspection_observe(self, execute: bool = False) -> RepairArmPoseResult:
        return self.run_action("observe", execute=execute)

    def repair_prepose(self, execute: bool = False) -> RepairArmPoseResult:
        return self.run_action("prepose", execute=execute)

    def repair_approach(self, execute: bool = False) -> RepairArmPoseResult:
        return self.run_action("approach", execute=execute)

    def repair_retract(self, execute: bool = False) -> RepairArmPoseResult:
        return self.run_action("retract", execute=execute)
