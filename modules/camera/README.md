# Camera Module

Scope:

- Depth camera bring-up.
- RGB-D and point cloud processing.
- Crack/pothole perception.
- Camera-on-arm calibration and coordinate transform notes.

Large Orbbec SDK folders stay local and are recorded in `docs/large-files-index.md`.

## Current Calibration Work

Hand-eye calibration lives in:

```text
modules/camera/hand_eye_calibration/
```

Current direction:

- Treat the Orbbec camera as eye-in-hand on the Piper arm.
- First pass is manual/static for safety.
- Use OrbbecViewer to verify and save images.
- Use Piper read-only pose capture for matching flange poses.
- Solve `gripper_T_camera` offline before deploying anything to RK3588.

Do not mix raw large image sets into Git. Keep raw captures local and commit only the final small calibration JSON after validation.
