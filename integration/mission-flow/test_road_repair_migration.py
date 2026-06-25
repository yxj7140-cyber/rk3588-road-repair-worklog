#!/usr/bin/env python3
"""Lightweight regression checks for the Road_Repair RK3588 migration."""

from __future__ import annotations

from pathlib import Path

from road_repair_3508_model import (
    MOTOR_COMMAND_CAN_ID,
    OLD_LINUX_REFERENCE_PID_CONFIGS,
    ROAD_REPAIR_PID_CONFIGS,
    MotorFeedback,
    PidConfig,
    RoadRepairGamepadState,
    RoadRepairPidController,
    RoadRepairWheelSpeeds,
    calculate_pid_currents,
    mix_current_rt_reference,
    mix_road_repair_reference,
    normalized_axes_to_rpm,
    pack_motor_command,
    parse_motor_feedback,
)
from road_repair_competition_api import (
    RoadRepairDefectObservation,
    build_inspection_repair_steps,
    preview_steps,
)
from road_repair_competition_scenario import build_scenario_steps, load_scenario_file
from road_repair_virtual_devices import VirtualDepthCamera, VirtualRoadDefect
from road_repair_virtual_mission import RoadRepairVirtualMissionPlanner, actions_to_steps
from road_repair_web_remote import HTML_PAGE, build_web_vcmd
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


def test_gamepad_normalization() -> None:
    forward, strafe, rotate, speed_scale, slow_scale = RoadRepairGamepadState(
        lx=127,
        ly=0,
        rx=127,
        lt=0,
        rt=0,
    ).normalized_axes()
    assert_tuple_close((forward, strafe, rotate), (1.0, 0.0, 0.0), "forward gamepad axes")
    assert_equal(round(speed_scale, 2), 0.85, "base speed scale")
    assert_equal(round(slow_scale, 2), 1.0, "base slow scale")

    forward, strafe, rotate, speed_scale, slow_scale = RoadRepairGamepadState(
        lx=254,
        ly=127,
        rx=0,
        lt=255,
        rt=255,
    ).normalized_axes()
    assert_equal(round(forward, 3), 0.0, "centered forward axis")
    assert_equal(round(strafe, 3), 1.0, "right strafe axis")
    assert_equal(round(rotate, 3), 1.0, "left rotate axis")
    assert_equal(round(speed_scale, 2), 1.20, "max speed scale")
    assert_equal(round(slow_scale, 2), 0.30, "slow trigger scale")


def test_axis_to_vcmd() -> None:
    vcmd = RoadRepairAxisCommand(
        forward=0.18,
        strafe=0.16,
        rotate=-0.20,
        current_limit=1200,
    ).to_vcmd()
    assert_equal(
        (vcmd.forward_rpm, vcmd.strafe_rpm, vcmd.rotate_rpm, vcmd.current_limit),
        (684, 608, -640, 1200),
        "mission axis to VCMD rpm",
    )

    assert_equal(
        normalized_axes_to_rpm(0.18, 0.16, -0.20),
        (684, 608, -640),
        "model normalized axes to rpm",
    )


def test_reference_mixers_are_traceable() -> None:
    original = mix_road_repair_reference(684, 608, -640).as_tuple()
    current = mix_current_rt_reference(684, 608, -640).as_tuple()
    assert_tuple_close(original, (-652.0, 564.0, 716.0, 1932.0), "original FreeRTOS mixer")
    assert_tuple_close(current, (652.0, -564.0, -716.0, -1932.0), "current validated RT mixer")


def test_can_format() -> None:
    payload = pack_motor_command(1, -2, 300, -400)
    assert_equal(MOTOR_COMMAND_CAN_ID, 0x200, "motor command CAN id")
    assert_equal(payload.hex(), "0001fffe012cfE70".lower(), "motor command payload")

    feedback = parse_motor_feedback(0x201, bytes.fromhex("1234ff38006419"))
    assert_equal(
        feedback,
        MotorFeedback(
            rotor_angle=0x1234,
            rotor_speed=-200,
            actual_torque_current=100,
            motor_temperature=25,
        ),
        "motor feedback parse",
    )


def test_pid_model() -> None:
    controller = RoadRepairPidController(PidConfig(kp=1.8, ki=0.0, kd=0.0))
    assert_equal(int(controller.calculate(600.0, 100.0, 0.01)), 900, "pure P PID output")
    assert_equal(round(controller.integral, 2), 5.0, "pure P still tracks integral state")

    saturated = RoadRepairPidController(PidConfig(kp=10.0, ki=1.0, kd=0.0, output_max=100.0, output_min=-100.0))
    assert_equal(int(saturated.calculate(1000.0, 0.0, 0.01)), 100, "PID output upper saturation")
    assert_equal(round(saturated.integral, 2), 0.0, "anti-windup keeps integral unchanged at saturated same-sign error")
    assert_equal(int(saturated.calculate(-1000.0, 0.0, 0.01)), -100, "PID output lower saturation")
    assert_equal(round(saturated.integral, 2), 0.0, "anti-windup keeps integral unchanged at lower saturation")


def test_pid_current_reference_configs() -> None:
    target = RoadRepairWheelSpeeds(600.0, 600.0, -600.0, -600.0)
    feedback = RoadRepairWheelSpeeds(0.0, 0.0, 0.0, 0.0)
    current_rt = calculate_pid_currents(target, feedback, ROAD_REPAIR_PID_CONFIGS)
    old_linux = calculate_pid_currents(target, feedback, OLD_LINUX_REFERENCE_PID_CONFIGS)

    assert_equal(current_rt, (1080, 1080, -1080, -1080), "current RT PID reference currents")
    assert_equal(old_linux, (1202, 1201, -1202, -1203), "old Linux PID reference currents")


def test_competition_flow() -> None:
    steps = build_inspection_repair_steps(
        RoadRepairDefectObservation(
            kind="pothole",
            distance_m=0.80,
            lateral_offset_m=0.16,
            yaw_error_deg=-4.0,
        )
    )
    assert_equal(len(steps), 11, "inspection repair step count")
    assert_equal([step.behavior for step in steps[:6]], [
        "forward",
        "forward",
        "stop",
        "strafe-right",
        "rotate-right",
        "forward",
    ], "inspection repair leading behaviors")

    previews = preview_steps(steps, current_limit=1200)
    assert_equal(
        (previews[0].forward_rpm, previews[3].strafe_rpm, previews[4].rotate_rpm),
        (684, 608, -640),
        "inspection repair preview rpm",
    )


def test_defect_alignment_variants() -> None:
    left_crack = build_inspection_repair_steps(
        RoadRepairDefectObservation(
            kind="crack",
            distance_m=0.70,
            lateral_offset_m=-0.12,
            yaw_error_deg=5.0,
        )
    )
    assert_equal([step.behavior for step in left_crack[:6]], [
        "forward",
        "forward",
        "stop",
        "strafe-left",
        "rotate-left",
        "forward",
    ], "left crack alignment behaviors")

    centered = build_inspection_repair_steps(
        RoadRepairDefectObservation(
            kind="pothole",
            distance_m=0.60,
            lateral_offset_m=0.01,
            yaw_error_deg=1.0,
        )
    )
    assert_equal(len(centered), 9, "centered defect skips lateral and yaw alignment")
    assert_equal([step.behavior for step in centered[:4]], [
        "forward",
        "forward",
        "stop",
        "forward",
    ], "centered defect leading behaviors")


def test_virtual_mission_uses_replaceable_devices() -> None:
    defect = VirtualRoadDefect(
        kind="crack",
        distance_m=0.55,
        lateral_offset_m=-0.10,
        yaw_error_deg=6.0,
    )
    planner = RoadRepairVirtualMissionPlanner(depth_camera=VirtualDepthCamera(defect))
    actions = planner.build_inspection_repair()
    steps = actions_to_steps(actions)
    expected = build_inspection_repair_steps(defect.to_observation())

    assert_equal(steps, expected, "virtual mission steps match competition API for injected defect")
    assert_equal(
        [step.behavior for step in steps[:6]],
        ["forward", "forward", "stop", "strafe-left", "rotate-left", "forward"],
        "virtual mission injected defect behaviors",
    )
    assert_equal(
        any("crack detected" in action.message for action in actions),
        True,
        "virtual depth-camera message includes defect kind",
    )


def test_scenario_file_flow() -> None:
    scenario_path = Path(__file__).with_name("sample_road_repair_scenario.json")
    scenario = load_scenario_file(scenario_path)
    steps = build_scenario_steps(scenario)

    assert_equal(scenario.name, "topic1_single_crack_left_offset", "scenario name")
    assert_equal([step.behavior for step in steps[:6]], [
        "forward",
        "forward",
        "stop",
        "strafe-left",
        "rotate-left",
        "forward",
    ], "scenario leading behaviors")

    planner = RoadRepairVirtualMissionPlanner()
    actions = planner.build_from_scenario_file(str(scenario_path))
    assert_equal(actions_to_steps(actions), steps, "virtual mission scenario steps")
    assert_equal(
        any("crack detected" in action.message for action in actions),
        True,
        "scenario depth-camera event message",
    )


def test_web_remote_assets() -> None:
    assert_equal("Road Repair Remote" in HTML_PAGE, True, "web remote page title")
    assert_equal("/api/drive" in HTML_PAGE, True, "web remote drive endpoint")
    assert_equal("/api/enable_current" in HTML_PAGE, True, "web remote unlock endpoint")
    assert_equal("/api/safe_lock" in HTML_PAGE, True, "web remote safe-lock endpoint")
    vcmd = build_web_vcmd(
        forward=0.4,
        strafe=0.0,
        rotate=0.0,
    )
    strafe_vcmd = build_web_vcmd(
        forward=0.0,
        strafe=0.4,
        rotate=0.0,
    )
    assert_equal((vcmd.forward_rpm, vcmd.current_limit), (800, 1800), "web remote stronger forward rpm")
    assert_equal(strafe_vcmd.strafe_rpm, 600, "web remote 1.5x strafe rpm")


def main() -> int:
    tests = [
        test_gamepad_normalization,
        test_axis_to_vcmd,
        test_reference_mixers_are_traceable,
        test_can_format,
        test_pid_model,
        test_pid_current_reference_configs,
        test_competition_flow,
        test_defect_alignment_variants,
        test_virtual_mission_uses_replaceable_devices,
        test_scenario_file_flow,
        test_web_remote_assets,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS all {len(tests)} Road_Repair migration checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
