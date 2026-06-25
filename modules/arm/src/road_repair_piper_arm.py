#!/usr/bin/env python3
"""Piper arm adapter for the Road_Repair RK3588 migration.

The arm remains a Linux/Windows-side task actuator. RT continues to own only
the validated chassis real-time loop. This module keeps the Piper SDK boundary
small so the same high-level task code can run on Windows now and on the board
later.
"""

from __future__ import annotations

import json
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_BITRATE = 1_000_000
DEFAULT_WINDOWS_INTERFACE = "agx_cando"
DEFAULT_WINDOWS_CHANNEL = "0"
DEFAULT_LINUX_INTERFACE = "socketcan"
DEFAULT_LINUX_CHANNEL = "can1"
DEFAULT_FIRMWARE = "default"
DEFAULT_SPEED_PERCENT = 10
DEFAULT_MOTION_TIMEOUT_S = 8.0
DEFAULT_MOTION_POLL_INTERVAL_S = 0.1
DEFAULT_JOINT_TARGET_TOLERANCE_RAD = 0.03


INSTALL_HINT = """Install Piper SDK dependencies first:
  pip install python-can
  pip install "git+https://github.com/agilexrobotics/python-can-agx-cando.git"
  pip install "git+https://github.com/agilexrobotics/pyAgxArm.git"

Windows default: interface=agx_cando channel=0
Board/Linux final: interface=socketcan channel=can1
"""


@dataclass(frozen=True)
class PiperConnectionConfig:
    firmware: str = DEFAULT_FIRMWARE
    interface: str | None = None
    channel: str | None = None
    bitrate: int = DEFAULT_BITRATE
    timeout: float = 1.0
    speed_percent: int = DEFAULT_SPEED_PERCENT
    receive_own_messages: bool = False
    local_loopback: bool = False

    def resolved_interface(self) -> str:
        if self.interface:
            return self.interface
        return DEFAULT_WINDOWS_INTERFACE if platform.system() == "Windows" else DEFAULT_LINUX_INTERFACE

    def resolved_channel(self) -> str:
        if self.channel:
            return self.channel
        return DEFAULT_WINDOWS_CHANNEL if platform.system() == "Windows" else DEFAULT_LINUX_CHANNEL


@dataclass(frozen=True)
class PiperMotionProfile:
    name: str
    description: str = ""
    joints: list[float] = field(default_factory=list)
    speed_percent: int = DEFAULT_SPEED_PERCENT

    def validate(self) -> None:
        if len(self.joints) != 6:
            raise ValueError(f"profile {self.name!r} must contain exactly 6 joint angles")
        if not 1 <= int(self.speed_percent) <= 100:
            raise ValueError(f"profile {self.name!r} speed_percent must be 1..100")


def default_piper_profiles_path() -> Path:
    return Path(__file__).with_name("piper_motion_profiles.json")


def load_motion_profiles(path: str | Path | None = None) -> dict[str, PiperMotionProfile]:
    profile_path = Path(path) if path else default_piper_profiles_path()
    raw = json.loads(profile_path.read_text(encoding="utf-8"))
    profiles = {}
    for item in raw.get("profiles", []):
        profile = PiperMotionProfile(
            name=str(item["name"]),
            description=str(item.get("description", "")),
            joints=[float(value) for value in item.get("joints", [])],
            speed_percent=int(item.get("speed_percent", DEFAULT_SPEED_PERCENT)),
        )
        profile.validate()
        profiles[profile.name] = profile
    return profiles


def save_motion_profiles(profiles: dict[str, PiperMotionProfile], path: str | Path | None = None) -> None:
    profile_path = Path(path) if path else default_piper_profiles_path()
    data = {
        "profiles": [
            {
                "name": profile.name,
                "description": profile.description,
                "joints": profile.joints,
                "speed_percent": int(profile.speed_percent),
            }
            for profile in profiles.values()
        ]
    }
    profile_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _import_pyagxarm() -> Any:
    try:
        import pyAgxArm  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local SDK install
        raise RuntimeError(INSTALL_HINT) from exc
    return pyAgxArm


def _sdk_constant(container: Any, name: str, fallback: str) -> Any:
    normalized = name.strip().upper().replace("-", "_")
    return getattr(container, normalized, fallback)


def build_pyagxarm_config(config: PiperConnectionConfig) -> dict[str, Any]:
    pyagxarm = _import_pyagxarm()
    arm_model = _sdk_constant(pyagxarm.ArmModel, "PIPER", "piper")
    firmware = _sdk_constant(pyagxarm.PiperFW, config.firmware, config.firmware)
    return pyagxarm.create_agx_arm_config(
        robot=arm_model,
        firmeware_version=firmware,
        interface=config.resolved_interface(),
        channel=config.resolved_channel(),
        bitrate=int(config.bitrate),
        timeout=float(config.timeout),
        receive_own_messages=bool(config.receive_own_messages),
        local_loopback=bool(config.local_loopback),
    )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if hasattr(value, "msg"):
        data = {
            "msg": _json_safe(getattr(value, "msg", None)),
            "hz": _json_safe(getattr(value, "hz", None)),
            "timestamp": _json_safe(getattr(value, "timestamp", None)),
        }
        return data
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return repr(value)


class PiperArmController:
    """Thin runtime wrapper around pyAgxArm Piper APIs."""

    def __init__(self, config: PiperConnectionConfig):
        self.config = config
        self.robot: Any | None = None

    def connect(self) -> None:
        pyagxarm = _import_pyagxarm()
        sdk_config = build_pyagxarm_config(self.config)
        self.robot = pyagxarm.AgxArmFactory.create_arm(sdk_config)
        self.robot.connect()

    def disconnect(self) -> None:
        if self.robot is not None and hasattr(self.robot, "disconnect"):
            self.robot.disconnect()
        self.robot = None

    def __enter__(self) -> "PiperArmController":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.disconnect()

    def _require_robot(self) -> Any:
        if self.robot is None:
            raise RuntimeError("Piper arm is not connected")
        return self.robot

    def snapshot(self) -> dict[str, Any]:
        robot = self._require_robot()
        fields: dict[str, Any] = {
            "interface": self.config.resolved_interface(),
            "channel": self.config.resolved_channel(),
            "firmware_config": self.config.firmware,
            "joint_nums": _json_safe(getattr(robot, "joint_nums", None)),
        }
        methods = [
            "is_ok",
            "has_comm_error",
            "get_comm_error",
            "get_fps",
            "get_firmware",
            "get_arm_status",
            "get_joint_angles",
            "get_flange_pose",
            "get_tcp_pose",
            "get_motor_states",
            "get_driver_states",
            "get_joints_enable_status_list",
        ]
        for method_name in methods:
            method = getattr(robot, method_name, None)
            if method is None:
                continue
            try:
                fields[method_name] = _json_safe(method())
            except Exception as exc:
                fields[method_name] = {"error": str(exc)}
        return fields

    def driver_faults(self) -> list[dict[str, Any]]:
        faults: list[dict[str, Any]] = []
        robot = self._require_robot()
        for joint_index in range(1, 7):
            method = getattr(robot, "get_driver_states", None)
            if method is None:
                continue
            try:
                state = method(joint_index)
            except Exception as exc:
                faults.append({
                    "joint": joint_index,
                    "error": str(exc),
                })
                continue
            if state is None:
                continue
            msg = getattr(state, "msg", None)
            foc_status = getattr(msg, "foc_status", None)
            if foc_status is None:
                continue
            flags = {
                "driver_enable_status": bool(getattr(foc_status, "driver_enable_status", False)),
                "driver_error_status": bool(getattr(foc_status, "driver_error_status", False)),
                "driver_overcurrent": bool(getattr(foc_status, "driver_overcurrent", False)),
                "driver_overheating": bool(getattr(foc_status, "driver_overheating", False)),
                "motor_overheating": bool(getattr(foc_status, "motor_overheating", False)),
                "stall_status": bool(getattr(foc_status, "stall_status", False)),
                "collision_status": bool(getattr(foc_status, "collision_status", False)),
                "voltage_too_low": bool(getattr(foc_status, "voltage_too_low", False)),
            }
            active_faults = {
                name: value
                for name, value in flags.items()
                if name != "driver_enable_status" and value
            }
            if active_faults:
                faults.append({
                    "joint": joint_index,
                    "active_faults": active_faults,
                    "foc_status_code": _json_safe(getattr(msg, "foc_status_code", None)),
                    "vol": _json_safe(getattr(msg, "vol", None)),
                    "bus_current": _json_safe(getattr(msg, "bus_current", None)),
                    "foc_temp": _json_safe(getattr(msg, "foc_temp", None)),
                    "motor_temp": _json_safe(getattr(msg, "motor_temp", None)),
                })
        return faults

    def assert_no_driver_faults(self) -> None:
        faults = self.driver_faults()
        if faults:
            raise RuntimeError(f"Piper driver fault blocks motion: {json.dumps(faults, ensure_ascii=False)}")

    def enable(self, timeout_s: float = 5.0, joint_index: int = 255) -> bool:
        robot = self._require_robot()
        deadline = time.monotonic() + max(0.1, float(timeout_s))
        while time.monotonic() < deadline:
            if joint_index == 255:
                current = self.joints_enabled() or [False] * 6
                if len(current) >= 6 and all(current[:6]):
                    return True
                for idx, is_enabled in enumerate(current[:6], start=1):
                    if is_enabled:
                        continue
                    try:
                        robot.enable(idx)
                    except Exception:
                        pass
                    if self._wait_joint_enabled(idx, deadline):
                        continue
                current = self.joints_enabled() or [False] * 6
                if len(current) >= 6 and all(current[:6]):
                    return True
                time.sleep(0.05)
                continue

            try:
                robot.enable(joint_index)
            except Exception:
                pass
            if self._wait_joint_enabled(joint_index, deadline):
                return True
            time.sleep(0.02)
        return False

    def _joint_enabled(self, joint_index: int) -> bool:
        enabled = self.joints_enabled()
        if not enabled:
            return False
        if not 1 <= int(joint_index) <= 6:
            return False
        return bool(enabled[int(joint_index) - 1])

    def _wait_joint_enabled(self, joint_index: int, deadline: float) -> bool:
        while time.monotonic() < deadline:
            if self._joint_enabled(joint_index):
                return True
            time.sleep(0.05)
        return self._joint_enabled(joint_index)

    def disable(self, timeout_s: float = 5.0, joint_index: int = 255) -> bool:
        robot = self._require_robot()
        deadline = time.monotonic() + max(0.1, float(timeout_s))
        while time.monotonic() < deadline:
            if bool(robot.disable(joint_index)):
                return True
            time.sleep(0.01)
        return False

    def joints_enabled(self) -> list[bool] | None:
        method = getattr(self._require_robot(), "get_joints_enable_status_list", None)
        if method is None:
            return None
        return [bool(value) for value in method()]

    def motion_status(self) -> Any:
        status = self._require_robot().get_arm_status()
        if status is None:
            return None
        msg = getattr(status, "msg", None)
        return getattr(msg, "motion_status", None)

    @staticmethod
    def _motion_status_is_done(status: Any) -> bool:
        if status == 0:
            return True
        try:
            return int(status) == 0
        except Exception:
            return False

    def wait_motion_done(
        self,
        target_joints: list[float] | None = None,
        timeout_s: float = DEFAULT_MOTION_TIMEOUT_S,
        poll_interval_s: float = DEFAULT_MOTION_POLL_INTERVAL_S,
        initial_delay_s: float = 0.5,
        joint_tolerance_rad: float = DEFAULT_JOINT_TARGET_TOLERANCE_RAD,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.1, float(timeout_s))
        time.sleep(max(0.0, float(initial_delay_s)))
        last_status: Any = None
        last_joint_error: float | None = None
        samples = 0
        while True:
            last_status = self.motion_status()
            if target_joints is not None:
                last_joint_error = self.max_joint_error(target_joints)
                if last_joint_error is not None and last_joint_error <= float(joint_tolerance_rad):
                    return {
                        "done": True,
                        "done_by": "joint_tolerance",
                        "last_motion_status": _json_safe(last_status),
                        "max_joint_error_rad": last_joint_error,
                        "joint_tolerance_rad": float(joint_tolerance_rad),
                        "samples": samples + 1,
                    }
            samples += 1
            if self._motion_status_is_done(last_status):
                return {
                    "done": True,
                    "done_by": "motion_status",
                    "last_motion_status": _json_safe(last_status),
                    "max_joint_error_rad": last_joint_error,
                    "samples": samples,
                }
            if time.monotonic() >= deadline:
                return {
                    "done": False,
                    "last_motion_status": _json_safe(last_status),
                    "max_joint_error_rad": last_joint_error,
                    "joint_tolerance_rad": float(joint_tolerance_rad),
                    "samples": samples,
                    "timeout_s": float(timeout_s),
                }
            time.sleep(max(0.01, float(poll_interval_s)))

    def current_joint_angles(self) -> list[float] | None:
        joint_data = self._require_robot().get_joint_angles()
        if joint_data is None:
            return None
        values = getattr(joint_data, "msg", None)
        if not isinstance(values, list) or len(values) != 6:
            return None
        return [float(value) for value in values]

    def max_joint_error(self, target_joints: list[float]) -> float | None:
        current = self.current_joint_angles()
        if current is None or len(target_joints) != 6:
            return None
        return max(abs(float(now) - float(target)) for now, target in zip(current, target_joints))

    def set_speed_percent(self, speed_percent: int) -> Any:
        robot = self._require_robot()
        speed_percent = max(1, min(100, int(speed_percent)))
        return robot.set_speed_percent(speed_percent)

    def move_j(self, joints: list[float]) -> None:
        if len(joints) != 6:
            raise ValueError("move_j requires exactly 6 joint angles")
        self._require_robot().move_j([float(value) for value in joints])

    def move_profile(
        self,
        profile: PiperMotionProfile,
        enable_timeout_s: float = 5.0,
        motion_timeout_s: float = DEFAULT_MOTION_TIMEOUT_S,
    ) -> dict[str, Any]:
        profile.validate()
        self.assert_no_driver_faults()
        if not self.enable(timeout_s=enable_timeout_s):
            raise RuntimeError("failed to enable Piper arm before motion")
        self.assert_no_driver_faults()
        self.set_speed_percent(profile.speed_percent)
        self.move_j(profile.joints)
        motion_wait = self.wait_motion_done(target_joints=profile.joints, timeout_s=motion_timeout_s)
        if not bool(motion_wait.get("done")):
            raise RuntimeError(f"Piper arm motion did not finish: {motion_wait}")
        enabled_after = self.joints_enabled()
        motion_wait["enabled_after"] = enabled_after
        if enabled_after is not None and len(enabled_after) >= 6 and not all(enabled_after[:6]):
            raise RuntimeError(
                "Piper arm joint disabled after motion: "
                f"{json.dumps(motion_wait, ensure_ascii=False)}"
            )
        return motion_wait

    def electronic_emergency_stop(self) -> Any:
        return self._require_robot().electronic_emergency_stop()


def print_json(data: Any) -> None:
    print(json.dumps(_json_safe(data), ensure_ascii=False, indent=2, sort_keys=True))

