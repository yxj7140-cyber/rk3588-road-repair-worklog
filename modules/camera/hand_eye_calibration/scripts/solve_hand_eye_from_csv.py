#!/usr/bin/env python3
"""Solve eye-in-hand calibration from paired robot and camera target poses.

CSV inputs:
  base_to_gripper_* : robot flange/end-effector pose in base frame
  target_to_cam_*   : OpenCV solvePnP pose, X_camera = R * X_target + t

Output:
  gripper_T_camera, usable as:
    base_T_camera = base_T_gripper @ gripper_T_camera
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np


REQUIRED_COLUMNS = [
    "sample_id",
    "base_to_gripper_x_m",
    "base_to_gripper_y_m",
    "base_to_gripper_z_m",
    "base_to_gripper_rx_rad",
    "base_to_gripper_ry_rad",
    "base_to_gripper_rz_rad",
    "target_to_cam_x_m",
    "target_to_cam_y_m",
    "target_to_cam_z_m",
    "target_to_cam_rx_rad",
    "target_to_cam_ry_rad",
    "target_to_cam_rz_rad",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Solve Piper-Orbbec eye-in-hand calibration from CSV poses.")
    parser.add_argument("--samples", required=True, help="CSV file containing paired robot/camera target poses.")
    parser.add_argument("--output", required=True, help="JSON output path.")
    parser.add_argument(
        "--robot-rotation-format",
        choices=["rpy_xyz", "rpy_zyx", "rotvec"],
        default="rpy_xyz",
        help="Interpretation of base_to_gripper_rx/ry/rz.",
    )
    parser.add_argument(
        "--camera-rotation-format",
        choices=["rotvec", "rpy_xyz", "rpy_zyx"],
        default="rotvec",
        help="Interpretation of target_to_cam_rx/ry/rz. OpenCV solvePnP uses rotvec.",
    )
    parser.add_argument(
        "--method",
        choices=["Tsai", "Park", "Horaud", "Andreff", "Daniilidis"],
        default="Tsai",
        help="OpenCV hand-eye method.",
    )
    parser.add_argument("--min-samples", type=int, default=8)
    return parser.parse_args()


def require_float(row: dict[str, str], key: str) -> float:
    text = (row.get(key) or "").strip()
    if not text:
        raise ValueError(f"missing {key}")
    return float(text)


def rot_x(rad: float) -> np.ndarray:
    c = math.cos(rad)
    s = math.sin(rad)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]], dtype=float)


def rot_y(rad: float) -> np.ndarray:
    c = math.cos(rad)
    s = math.sin(rad)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=float)


def rot_z(rad: float) -> np.ndarray:
    c = math.cos(rad)
    s = math.sin(rad)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=float)


def rotation_from_triplet(rx: float, ry: float, rz: float, fmt: str) -> np.ndarray:
    if fmt == "rotvec":
        rotation, _ = cv2.Rodrigues(np.array([rx, ry, rz], dtype=float).reshape(3, 1))
        return rotation
    if fmt == "rpy_xyz":
        return rot_x(rx) @ rot_y(ry) @ rot_z(rz)
    if fmt == "rpy_zyx":
        return rot_z(rz) @ rot_y(ry) @ rot_x(rx)
    raise ValueError(f"unsupported rotation format: {fmt}")


def make_transform(translation: Iterable[float], rotation: np.ndarray) -> np.ndarray:
    transform = np.eye(4, dtype=float)
    transform[:3, :3] = rotation
    transform[:3, 3] = np.array(list(translation), dtype=float)
    return transform


def method_constant(name: str) -> int:
    return {
        "Tsai": cv2.CALIB_HAND_EYE_TSAI,
        "Park": cv2.CALIB_HAND_EYE_PARK,
        "Horaud": cv2.CALIB_HAND_EYE_HORAUD,
        "Andreff": cv2.CALIB_HAND_EYE_ANDREFF,
        "Daniilidis": cv2.CALIB_HAND_EYE_DANIILIDIS,
    }[name]


def load_samples(path: Path, robot_fmt: str, camera_fmt: str) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [name for name in REQUIRED_COLUMNS if name not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"missing columns: {missing}")
        samples: list[dict[str, object]] = []
        for row in reader:
            sample_id = (row.get("sample_id") or "").strip()
            if not sample_id:
                continue
            try:
                base_t_gripper = np.array(
                    [
                        require_float(row, "base_to_gripper_x_m"),
                        require_float(row, "base_to_gripper_y_m"),
                        require_float(row, "base_to_gripper_z_m"),
                    ],
                    dtype=float,
                ).reshape(3, 1)
                base_r_gripper = rotation_from_triplet(
                    require_float(row, "base_to_gripper_rx_rad"),
                    require_float(row, "base_to_gripper_ry_rad"),
                    require_float(row, "base_to_gripper_rz_rad"),
                    robot_fmt,
                )
                target_t_cam = np.array(
                    [
                        require_float(row, "target_to_cam_x_m"),
                        require_float(row, "target_to_cam_y_m"),
                        require_float(row, "target_to_cam_z_m"),
                    ],
                    dtype=float,
                ).reshape(3, 1)
                target_r_cam = rotation_from_triplet(
                    require_float(row, "target_to_cam_rx_rad"),
                    require_float(row, "target_to_cam_ry_rad"),
                    require_float(row, "target_to_cam_rz_rad"),
                    camera_fmt,
                )
            except ValueError as exc:
                raise ValueError(f"sample {sample_id}: {exc}") from exc
            samples.append(
                {
                    "sample_id": sample_id,
                    "base_R_gripper": base_r_gripper,
                    "base_t_gripper": base_t_gripper,
                    "target_R_cam": target_r_cam,
                    "target_t_cam": target_t_cam,
                    "notes": row.get("notes", ""),
                }
            )
        return samples


def as_list(matrix: np.ndarray) -> list[list[float]]:
    return [[float(value) for value in row] for row in matrix]


def main() -> int:
    args = parse_args()
    samples_path = Path(args.samples)
    output_path = Path(args.output)
    samples = load_samples(samples_path, args.robot_rotation_format, args.camera_rotation_format)
    if len(samples) < args.min_samples:
        raise SystemExit(f"need at least {args.min_samples} samples, got {len(samples)}")

    rotations_gripper_to_base = [sample["base_R_gripper"] for sample in samples]
    translations_gripper_to_base = [sample["base_t_gripper"] for sample in samples]
    rotations_target_to_cam = [sample["target_R_cam"] for sample in samples]
    translations_target_to_cam = [sample["target_t_cam"] for sample in samples]

    # OpenCV returns R_cam2gripper/t_cam2gripper, i.e. ^gripper T_camera.
    gripper_r_camera, gripper_t_camera = cv2.calibrateHandEye(
        rotations_gripper_to_base,
        translations_gripper_to_base,
        rotations_target_to_cam,
        translations_target_to_cam,
        method=method_constant(args.method),
    )

    gripper_t_camera = make_transform(gripper_t_camera.reshape(3), gripper_r_camera)
    result = {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "samples_csv": str(samples_path),
        "sample_count": len(samples),
        "sample_ids": [str(sample["sample_id"]) for sample in samples],
        "method": args.method,
        "robot_rotation_format": args.robot_rotation_format,
        "camera_rotation_format": args.camera_rotation_format,
        "transform_name": "gripper_T_camera",
        "gripper_T_camera": as_list(gripper_t_camera),
        "translation_m": [float(value) for value in gripper_t_camera[:3, 3]],
        "rotation_matrix": as_list(gripper_r_camera),
        "usage": "base_T_camera = base_T_gripper @ gripper_T_camera",
        "notes": [
            "Verify robot rotation format before using this result.",
            "Hand-eye result does not include pump/nozzle offset.",
            "Do not deploy to board until projection/pose validation passes.",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
