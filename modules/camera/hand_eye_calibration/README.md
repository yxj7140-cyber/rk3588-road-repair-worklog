# Arm-Camera Hand-Eye Calibration

This folder contains the eye-in-hand calibration workflow for the Piper arm and Orbbec depth camera.

Current assumption:

```text
Camera is mounted on the Piper arm/end effector.
Calibration target is fixed in the world/chassis workspace.
We solve gripper_T_camera, also written as ^gripper T_camera.
```

## Goal

After calibration, a point measured by the camera can be transformed into the arm/base frame:

```text
base_T_camera = base_T_gripper * gripper_T_camera
point_base = base_T_camera * point_camera
```

This is the transform needed later for:

- crack/pothole 3D localization
- arm-mounted camera repair alignment
- pump/nozzle positioning relative to the detected defect

## Safety Policy

- First calibration pass should be manual/static.
- Do not run automatic arm motion until read-only pose capture and image capture are verified.
- Because Piper J5 had prior issues, prefer manual GUI positioning plus read-only pose capture.
- Close `ArmRobotTool_V1.5.4.260414_release.exe` before using Python/CAN scripts.
- Keep all calibration files off the board until the result is verified.

## Required Hardware

- Piper arm with camera rigidly mounted.
- Orbbec camera visible in OrbbecViewer.
- Flat calibration target.
- Accurate target square size measurement.

Recommended target:

```text
Checkerboard or ChArUco board, printed flat and fixed so it does not move.
```

If using the simple script path here, a normal checkerboard is enough as long as the entire board is visible in each image.

## Coordinate Frames

Use these names consistently:

```text
base      Piper robot base frame
gripper   Piper flange/end-effector frame used by captured_flange_pose
camera    Orbbec color/depth camera optical frame
target    printed checkerboard/marker target frame
```

Robot pose input:

```text
base_T_gripper
```

Camera target pose input:

```text
target_T_camera in OpenCV naming is usually target_to_cam:
X_camera = R_target_to_cam * X_target + t_target_to_cam
```

OpenCV `solvePnP` returns this `target_to_cam` pose.

## Data Collection Rules

Collect at least 12 valid samples. 18 to 25 is better.

Each sample must include:

- one saved camera image
- one robot flange pose captured at the same physical pose
- one detected calibration target pose in the camera frame

Good samples:

- target is sharp and fully visible
- arm poses vary in orientation, not just position
- camera sees the target from left/right/up/down and different wrist rotations
- target remains fixed during the whole session

Bad samples:

- target moved between captures
- only translation changed while wrist orientation stayed almost identical
- images are blurred
- board is too close to the image edge
- robot pose and image are not from the same arm pose

## Manual First-Pass Workflow

1. Mount camera rigidly on the arm.
2. Place and fix calibration target in the workspace.
3. Open OrbbecViewer:

   ```text
   C:\OrbbecViewer_v1.10.27_202509252154_win_x64_release\OrbbecViewer.exe
   ```

4. Verify color and depth streams are stable.
5. Move arm to a safe pose where the target is visible.
6. Save the color image.
7. Close ArmRobotTool if it is open.
8. Capture Piper pose with the existing read-only script.
9. Repeat for 12 to 25 poses.
10. Fill `samples_template.csv`.
11. Run `scripts/solve_hand_eye_from_csv.py`.

## Existing Piper Pose Capture

Existing read-only script:

```powershell
powershell -ExecutionPolicy Bypass -File E:\BaiduNetdiskDownload\rt\ArmRobotTool_V1.5.4.260414_release\piper_dev\capture_current_pose_with_log.ps1 -Name handeye_001 -Description "Hand-eye sample 001" -SpeedPercent 4
```

The useful values are:

```text
captured_flange_pose: [x, y, z, rx, ry, rz]
```

Important: confirm whether Piper pose rotation is Euler RPY or rotation-vector before trusting final calibration. The solver script supports both, but the correct interpretation must be verified.

## 2026-06-26 Windows Bring-Up Notes

- OrbbecViewer was recovered after fixing the Windows `ORBBEC Depth Sensor` Code 28 driver binding.
- Verified camera device: `Dabai DC1 SN: CC13653019J USB2.0`.
- Verified stream: color `640x480 MJPG 30`, checkerboard visible.
- Depth device is now `Status: OK` in Windows, but depth frame capture still needs a direct verification step before using depth in the repair pipeline.
- See `lessons/procedures/orbbec-windows-driver-code28.md` if the camera falls back to Code 28 again.
- Current Piper pose script default is `agx_cando`; if the adapter is detected as `candleLight USB to CAN adapter`, do not assume the old default will read the arm. Verify the correct CAN backend before collecting samples.

## Solve

Install requirements:

```powershell
python -m pip install -r E:\BaiduNetdiskDownload\rt\github_work\rk3588-road-repair-worklog\modules\camera\hand_eye_calibration\requirements-windows.txt
```

Run:

```powershell
python E:\BaiduNetdiskDownload\rt\github_work\rk3588-road-repair-worklog\modules\camera\hand_eye_calibration\scripts\solve_hand_eye_from_csv.py `
  --samples E:\BaiduNetdiskDownload\rt\github_work\rk3588-road-repair-worklog\modules\camera\hand_eye_calibration\samples_template.csv `
  --robot-rotation-format rpy_xyz `
  --camera-rotation-format rotvec `
  --output E:\BaiduNetdiskDownload\rt\github_work\rk3588-road-repair-worklog\modules\camera\hand_eye_calibration\outputs\hand_eye_result.json
```

If validation looks wrong, rerun with:

```powershell
--robot-rotation-format rotvec
```

## Result File

The result should be saved as:

```text
outputs/hand_eye_result.json
```

It must record:

- date
- camera model/serial if available
- target type and square size
- number of valid samples
- rotation-format assumption
- final `gripper_T_camera`
- validation notes

## Next Integration Step

After the transform is trusted:

1. Put the verified matrix into `modules/camera`.
2. Add a small adapter that converts Orbbec 3D points into Piper base coordinates.
3. Add pump/nozzle offset calibration separately. Hand-eye only gives camera-to-gripper, not pump-tip-to-camera.
