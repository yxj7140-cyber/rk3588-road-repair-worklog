#!/usr/bin/env python3
"""Core-only regression checks for the formal chassis migration package."""

from __future__ import annotations

from road_repair_3508_model import (
    MOTOR_COMMAND_CAN_ID,
    ROAD_REPAIR_PID_CONFIGS,
    MotorFeedback,
    RoadRepairGamepadState,
    RoadRepairWheelSpeeds,
    calculate_pid_currents,
    mix_current_rt_reference,
    normalized_axes_to_rpm,
    pack_motor_command,
    parse_motor_feedback,
)
from road_repair_competition_api import RoadRepairDefectObservation, build_inspection_repair_steps, preview_steps
from road_repair_competition_behavior import behavior_axes, parse_behavior_sequence
from road_repair_topic1_runner import build_arg_parser
from road_repair_vcmd_adapter import RoadRepairAxisCommand


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_tuple_close(actual, expected, message: str, tolerance: float = 1e-6) -> None:
    if len(actual) != len(expected):
        raise AssertionError(f"{message}: length mismatch")
    for index, (left, right) in enumerate(zip(actual, expected), start=1):
        if abs(left - right) > tolerance:
            raise AssertionError(f"{message}: item {index} expected {right!r}, got {left!r}")


def test_gamepad_axis_and_vcmd_mapping() -> None:
    forward, strafe, rotate, speed_scale, slow_scale = RoadRepairGamepadState(
        lx=254,
        ly=0,
        rx=0,
        lt=0,
        rt=0,
    ).normalized_axes()
    assert_equal((round(forward, 3), round(strafe, 3), round(rotate, 3)), (1.0, 1.0, 1.0), "axes")
    assert_equal(round(speed_scale, 2), 0.85, "base speed scale")
    assert_equal(round(slow_scale, 2), 1.0, "base slow scale")

    vcmd = RoadRepairAxisCommand(forward=0.18, strafe=0.16, rotate=-0.20, current_limit=1200).to_vcmd()
    assert_equal((vcmd.forward_rpm, vcmd.strafe_rpm, vcmd.rotate_rpm, vcmd.current_limit), (684, 608, -640, 1200), "VCMD")
    assert_equal(normalized_axes_to_rpm(0.18, 0.16, -0.20), (684, 608, -640), "axis-to-rpm")


def test_current_validated_mixer_and_pid() -> None:
    current_mix = mix_current_rt_reference(684, 608, -640).as_tuple()
    assert_tuple_close(current_mix, (652.0, -564.0, -716.0, -1932.0), "validated RT mixer")

    target = RoadRepairWheelSpeeds(600.0, 600.0, -600.0, -600.0)
    feedback = RoadRepairWheelSpeeds(0.0, 0.0, 0.0, 0.0)
    assert_equal(calculate_pid_currents(target, feedback, ROAD_REPAIR_PID_CONFIGS), (1080, 1080, -1080, -1080), "PID currents")


def test_can_frame_semantics() -> None:
    assert_equal(MOTOR_COMMAND_CAN_ID, 0x200, "CAN command ID")
    assert_equal(pack_motor_command(1, -2, 300, -400).hex(), "0001fffe012cfe70", "CAN payload")
    feedback = parse_motor_feedback(0x201, bytes.fromhex("1234ff38006419"))
    assert_equal(
        feedback,
        MotorFeedback(rotor_angle=0x1234, rotor_speed=-200, actual_torque_current=100, motor_temperature=25),
        "feedback parse",
    )


def test_competition_chassis_flow() -> None:
    steps = build_inspection_repair_steps(
        RoadRepairDefectObservation(kind="pothole", distance_m=0.80, lateral_offset_m=0.16, yaw_error_deg=-4.0)
    )
    assert_equal(len(steps), 11, "inspection repair step count")
    assert_equal(
        [step.behavior for step in steps[:6]],
        ["forward", "forward", "stop", "strafe-right", "rotate-right", "forward"],
        "inspection leading behaviors",
    )
    previews = preview_steps(steps, current_limit=1200)
    assert_equal((previews[0].forward_rpm, previews[3].strafe_rpm, previews[4].rotate_rpm), (684, 608, -640), "preview rpm")

    sequence = parse_behavior_sequence("forward:0.18:0.6,stop:0:0.2,strafe-right:0.16:0.35")
    assert_equal([behavior_axes(step.behavior, step.magnitude) for step in sequence], [(0.18, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.16, 0.0)], "sequence axes")


def test_topic1_runner_default_is_safe_preview() -> None:
    args = build_arg_parser().parse_args([])
    assert_equal(args.dry_run, True, "Topic1 runner defaults to dry-run")
    assert_equal(args.execute, False, "Topic1 runner does not execute by default")


def main() -> int:
    tests = [
        test_gamepad_axis_and_vcmd_mapping,
        test_current_validated_mixer_and_pid,
        test_can_frame_semantics,
        test_competition_chassis_flow,
        test_topic1_runner_default_is_safe_preview,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS all {len(tests)} formal chassis migration core checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
