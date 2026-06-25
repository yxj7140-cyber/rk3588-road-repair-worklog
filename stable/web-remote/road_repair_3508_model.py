#!/usr/bin/env python3
"""Road_Repair 3508 control-core model for the RK3588 migration.

This module captures the portable parts of:

    Road_Repair_freertos/User/TASKs/3508ctrtask.c
    Road_Repair_freertos/User/moto/3508_motor.c
    Road_Repair_freertos/User/moto/pid.c

It is intentionally a model/reference layer. The active runtime path still uses
the validated RT VCMD controller and Linux USB-CAN gateway.
"""

from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass


MOTOR_COUNT = 4
MOTOR_COMMAND_CAN_ID = 0x200
MOTOR_FEEDBACK_FIRST_CAN_ID = 0x201
MOTOR_FEEDBACK_LAST_CAN_ID = 0x204

ROAD_REPAIR_GAMEPAD_CENTER = 127.0
ROAD_REPAIR_TRIGGER_MAX = 255.0
ROAD_REPAIR_AXIS_DEADBAND = 0.05
ROAD_REPAIR_MAX_SPEED_RPM = 3800.0
ROAD_REPAIR_MAX_ROTATE_RPM = 3200.0
ROAD_REPAIR_BASE_SPEED_SCALE = 0.85
ROAD_REPAIR_TRIGGER_SPEED_GAIN = 0.35
ROAD_REPAIR_TRIGGER_SLOW_GAIN = 0.70
ROAD_REPAIR_MIN_SLOW_SCALE = 0.15
ROAD_REPAIR_MAX_SPEED_SCALE = 1.20

MOTOR_PID_OUTPUT_LIMIT = 6500.0
MOTOR_PID_INTEGRAL_LIMIT = 2500.0
MOTOR_CONTROL_PERIOD_S = 0.01
MOTOR_TELEMETRY_PERIOD_MS = 50


def clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def clamp_byte(value: int) -> int:
    return max(0, min(255, int(value)))


def apply_axis_deadband(axis: float, deadband: float = ROAD_REPAIR_AXIS_DEADBAND) -> float:
    axis = clamp_float(axis, -1.0, 1.0)
    if -deadband < axis < deadband:
        return 0.0
    return axis


@dataclass(frozen=True)
class RoadRepairGamepadState:
    """Subset of the Road_Repair Xbox360 state used by Motor3508CtrTask."""

    lx: int = 127
    ly: int = 127
    rx: int = 127
    lt: int = 0
    rt: int = 0
    connected: bool = True
    xbox360: bool = True

    def normalized_axes(self) -> tuple[float, float, float, float, float]:
        """Return forward, strafe, rotate, speed_scale, slow_scale."""

        if not self.connected or not self.xbox360:
            return 0.0, 0.0, 0.0, 1.0, 1.0

        lx = float(clamp_byte(self.lx))
        ly = float(clamp_byte(self.ly))
        rx = float(clamp_byte(self.rx))
        lt = float(clamp_byte(self.lt))
        rt = float(clamp_byte(self.rt))

        forward = (ROAD_REPAIR_GAMEPAD_CENTER - ly) / ROAD_REPAIR_GAMEPAD_CENTER
        strafe = (lx - ROAD_REPAIR_GAMEPAD_CENTER) / ROAD_REPAIR_GAMEPAD_CENTER
        rotate = (ROAD_REPAIR_GAMEPAD_CENTER - rx) / ROAD_REPAIR_GAMEPAD_CENTER
        speed_scale = ROAD_REPAIR_BASE_SPEED_SCALE + (rt / ROAD_REPAIR_TRIGGER_MAX) * ROAD_REPAIR_TRIGGER_SPEED_GAIN
        slow_scale = 1.0 - (lt / ROAD_REPAIR_TRIGGER_MAX) * ROAD_REPAIR_TRIGGER_SLOW_GAIN
        slow_scale = max(slow_scale, ROAD_REPAIR_MIN_SLOW_SCALE)
        speed_scale = min(speed_scale, ROAD_REPAIR_MAX_SPEED_SCALE)
        return forward, strafe, rotate, speed_scale, slow_scale


@dataclass(frozen=True)
class RoadRepairWheelSpeeds:
    motor1: float
    motor2: float
    motor3: float
    motor4: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.motor1, self.motor2, self.motor3, self.motor4


@dataclass(frozen=True)
class MotorFeedback:
    rotor_angle: int
    rotor_speed: int
    actual_torque_current: int
    motor_temperature: int


@dataclass(frozen=True)
class PidConfig:
    kp: float = 1.80
    ki: float = 0.0
    kd: float = 0.0
    output_max: float = MOTOR_PID_OUTPUT_LIMIT
    output_min: float = -MOTOR_PID_OUTPUT_LIMIT
    integral_max: float = MOTOR_PID_INTEGRAL_LIMIT
    integral_min: float = -MOTOR_PID_INTEGRAL_LIMIT


@dataclass
class RoadRepairPidController:
    """Stateful port of Road_Repair_freertos/User/moto/pid.c."""

    config: PidConfig
    target_value: float = 0.0
    actual_value: float = 0.0
    error: float = 0.0
    last_error: float = 0.0
    prev_error: float = 0.0
    integral: float = 0.0
    derivative: float = 0.0
    output: float = 0.0

    def calculate(self, target_value: float, actual_value: float, dt: float) -> float:
        if dt <= 0.0:
            dt = 0.001

        self.target_value = float(target_value)
        self.actual_value = float(actual_value)
        self.prev_error = self.last_error
        self.last_error = self.error
        self.error = self.target_value - self.actual_value
        self.derivative = (self.error - self.last_error) / dt

        new_integral = self.integral + self.error * dt
        new_integral = clamp_float(
            new_integral,
            self.config.integral_min,
            self.config.integral_max,
        )

        output = (
            self.config.kp * self.error
            + self.config.ki * new_integral
            + self.config.kd * self.derivative
        )
        output = clamp_float(output, self.config.output_min, self.config.output_max)

        if (
            (output < self.config.output_max and output > self.config.output_min)
            or (output == self.config.output_max and self.error < 0.0)
            or (output == self.config.output_min and self.error > 0.0)
        ):
            self.integral = new_integral

        self.output = output
        return self.output


ROAD_REPAIR_PID_CONFIGS: tuple[PidConfig, PidConfig, PidConfig, PidConfig] = (
    PidConfig(),
    PidConfig(),
    PidConfig(),
    PidConfig(),
)

OLD_LINUX_REFERENCE_PID_CONFIGS: tuple[PidConfig, PidConfig, PidConfig, PidConfig] = (
    PidConfig(kp=2.0, ki=0.35),
    PidConfig(kp=2.0, ki=0.30),
    PidConfig(kp=2.0, ki=0.40),
    PidConfig(kp=2.0, ki=0.60),
)


def road_repair_scale(speed_scale: float = 1.0, slow_scale: float = 1.0) -> float:
    speed = clamp_float(speed_scale, 0.0, ROAD_REPAIR_MAX_SPEED_SCALE)
    slow = clamp_float(slow_scale, ROAD_REPAIR_MIN_SLOW_SCALE, 1.0)
    return speed * slow


def normalized_axes_to_rpm(
    forward: float,
    strafe: float,
    rotate: float,
    speed_scale: float = 1.0,
    slow_scale: float = 1.0,
    deadband: float = ROAD_REPAIR_AXIS_DEADBAND,
    max_speed_rpm: float = ROAD_REPAIR_MAX_SPEED_RPM,
    max_rotate_rpm: float = ROAD_REPAIR_MAX_ROTATE_RPM,
) -> tuple[int, int, int]:
    scale = road_repair_scale(speed_scale, slow_scale)
    max_speed_rpm = abs(float(max_speed_rpm))
    max_rotate_rpm = abs(float(max_rotate_rpm))
    forward_rpm = int(apply_axis_deadband(forward, deadband) * max_speed_rpm * scale)
    strafe_rpm = int(apply_axis_deadband(strafe, deadband) * max_speed_rpm * scale)
    rotate_rpm = int(apply_axis_deadband(rotate, deadband) * max_rotate_rpm * scale)
    return (
        int(clamp_float(forward_rpm, -max_speed_rpm, max_speed_rpm)),
        int(clamp_float(strafe_rpm, -max_speed_rpm, max_speed_rpm)),
        int(clamp_float(rotate_rpm, -max_rotate_rpm, max_rotate_rpm)),
    )


def mix_road_repair_reference(
    forward_rpm: float,
    strafe_rpm: float,
    rotate_rpm: float,
    max_speed_rpm: float = ROAD_REPAIR_MAX_SPEED_RPM,
) -> RoadRepairWheelSpeeds:
    """Original FreeRTOS wheel-speed formula from 3508ctrtask.c.

    This is kept for migration traceability. Do not use it to override the
    current RT image's already validated physical axis mapping.
    """

    wheel = [
        -(forward_rpm + strafe_rpm) - rotate_rpm,
        -(forward_rpm - strafe_rpm) - rotate_rpm,
        (forward_rpm - strafe_rpm) - rotate_rpm,
        (forward_rpm + strafe_rpm) - rotate_rpm,
    ]
    peak = max(abs(value) for value in wheel)
    max_speed_rpm = abs(float(max_speed_rpm))
    if peak > max_speed_rpm and peak > 0:
        normalize = max_speed_rpm / peak
        wheel = [value * normalize for value in wheel]
    wheel = [clamp_float(value, -max_speed_rpm, max_speed_rpm) for value in wheel]
    return RoadRepairWheelSpeeds(*wheel)


def mix_current_rt_reference(
    forward_rpm: float,
    strafe_rpm: float,
    rotate_rpm: float,
    max_speed_rpm: float = ROAD_REPAIR_MAX_SPEED_RPM,
) -> RoadRepairWheelSpeeds:
    """Current validated RT wheel target sign model.

    This mirrors the sign-normalized RT image used in the current migration
    checkpoint and is useful for dry-run comparison only.
    """

    wheel = [
        (forward_rpm + strafe_rpm) + rotate_rpm,
        (forward_rpm - strafe_rpm) + rotate_rpm,
        -(forward_rpm - strafe_rpm) + rotate_rpm,
        -(forward_rpm + strafe_rpm) + rotate_rpm,
    ]
    peak = max(abs(value) for value in wheel)
    max_speed_rpm = abs(float(max_speed_rpm))
    if peak > max_speed_rpm and peak > 0:
        normalize = max_speed_rpm / peak
        wheel = [value * normalize for value in wheel]
    wheel = [clamp_float(value, -max_speed_rpm, max_speed_rpm) for value in wheel]
    return RoadRepairWheelSpeeds(*wheel)


def pack_motor_command(
    motor1_current: int,
    motor2_current: int,
    motor3_current: int,
    motor4_current: int,
) -> bytes:
    return struct.pack(
        ">hhhh",
        int(clamp_float(motor1_current, -32768, 32767)),
        int(clamp_float(motor2_current, -32768, 32767)),
        int(clamp_float(motor3_current, -32768, 32767)),
        int(clamp_float(motor4_current, -32768, 32767)),
    )


def parse_motor_feedback(can_id: int, data: bytes) -> MotorFeedback:
    if can_id < MOTOR_FEEDBACK_FIRST_CAN_ID or can_id > MOTOR_FEEDBACK_LAST_CAN_ID:
        raise ValueError(f"unexpected 3508 feedback CAN id: 0x{can_id:x}")
    if len(data) < 7:
        raise ValueError("3508 feedback frame must contain at least 7 bytes")
    return MotorFeedback(
        rotor_angle=(data[0] << 8) | data[1],
        rotor_speed=struct.unpack(">h", data[2:4])[0],
        actual_torque_current=struct.unpack(">h", data[4:6])[0],
        motor_temperature=data[6],
    )


def calculate_pid_currents(
    target_wheel_rpm: RoadRepairWheelSpeeds,
    feedback_rpm: RoadRepairWheelSpeeds,
    configs: tuple[PidConfig, PidConfig, PidConfig, PidConfig] = ROAD_REPAIR_PID_CONFIGS,
    dt: float = MOTOR_CONTROL_PERIOD_S,
) -> tuple[int, int, int, int]:
    controllers = [RoadRepairPidController(config) for config in configs]
    return tuple(
        int(controller.calculate(target, actual, dt))
        for controller, target, actual in zip(
            controllers,
            target_wheel_rpm.as_tuple(),
            feedback_rpm.as_tuple(),
        )
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run Road_Repair 3508 migration model.")
    parser.add_argument("--forward", type=float, default=0.0)
    parser.add_argument("--strafe", type=float, default=0.0)
    parser.add_argument("--rotate", type=float, default=0.0)
    parser.add_argument("--speed-scale", type=float, default=1.0)
    parser.add_argument("--slow-scale", type=float, default=1.0)
    parser.add_argument("--max-speed-rpm", type=float, default=ROAD_REPAIR_MAX_SPEED_RPM)
    parser.add_argument("--max-rotate-rpm", type=float, default=ROAD_REPAIR_MAX_ROTATE_RPM)
    parser.add_argument("--gamepad", action="store_true")
    parser.add_argument("--lx", type=int, default=127)
    parser.add_argument("--ly", type=int, default=127)
    parser.add_argument("--rx", type=int, default=127)
    parser.add_argument("--lt", type=int, default=0)
    parser.add_argument("--rt", type=int, default=0)
    parser.add_argument("--disconnected", action="store_true")
    parser.add_argument("--not-xbox360", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    if args.gamepad:
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
    else:
        forward, strafe, rotate = args.forward, args.strafe, args.rotate
        speed_scale, slow_scale = args.speed_scale, args.slow_scale

    forward_rpm, strafe_rpm, rotate_rpm = normalized_axes_to_rpm(
        forward=forward,
        strafe=strafe,
        rotate=rotate,
        speed_scale=speed_scale,
        slow_scale=slow_scale,
        max_speed_rpm=args.max_speed_rpm,
        max_rotate_rpm=args.max_rotate_rpm,
    )
    rr_wheel = mix_road_repair_reference(forward_rpm, strafe_rpm, rotate_rpm, args.max_speed_rpm)
    rt_wheel = mix_current_rt_reference(forward_rpm, strafe_rpm, rotate_rpm, args.max_speed_rpm)

    print(
        "dry-run RoadRepair3508Model "
        f"axes={forward:.3f},{strafe:.3f},{rotate:.3f} "
        f"scale={road_repair_scale(speed_scale, slow_scale):.3f} "
        f"rpm={forward_rpm},{strafe_rpm},{rotate_rpm}"
    )
    print(
        "  original_freertos_wheel_rpm="
        f"{rr_wheel.motor1:.0f},{rr_wheel.motor2:.0f},{rr_wheel.motor3:.0f},{rr_wheel.motor4:.0f}"
    )
    print(
        "  current_validated_rt_wheel_rpm="
        f"{rt_wheel.motor1:.0f},{rt_wheel.motor2:.0f},{rt_wheel.motor3:.0f},{rt_wheel.motor4:.0f}"
    )
    print(
        "  can_command_id=0x200 feedback_ids=0x201..0x204 "
        "payload=big-endian int16 currents"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
