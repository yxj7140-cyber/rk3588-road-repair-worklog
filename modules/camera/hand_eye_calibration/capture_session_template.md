# Hand-Eye Capture Session Template

Copy this file for each real calibration session.

## Session

```text
date:
operator:
camera model:
camera serial:
camera mount description:
target type:
target square size:
raw image folder:
robot pose source:
robot rotation assumption:
notes:
```

## Pre-Check

- Camera is rigidly mounted on the Piper arm.
- Calibration target is fixed and will not move.
- OrbbecViewer can show stable color/depth.
- Piper state can be read.
- Arm workspace is clear.
- No automatic motion will be run in the first pass.

## Sample Naming

Use this pattern:

```text
handeye_001
handeye_002
...
handeye_025
```

For each sample, save:

```text
images/handeye_001_color.png
pose log from Piper capture_current_pose script
target_to_camera pose from checkerboard/marker detection
one row in samples CSV
```

## Sample Checklist

For every pose:

1. Move arm to a safe pose where the full target is visible.
2. Wait until the camera image is stable.
3. Save color image in OrbbecViewer.
4. Capture Piper pose without moving the arm.
5. Record `captured_flange_pose`.
6. Detect target pose in the image.
7. Add one CSV row.
8. Mark sample as good/bad.

## Pose Diversity Checklist

Collect samples with:

- camera left of target
- camera right of target
- camera above target
- camera below target
- camera closer
- camera farther
- wrist rotated clockwise
- wrist rotated counter-clockwise
- at least 12 good samples, preferably 18 to 25

Avoid:

- nearly identical poses
- target near image edge
- blurred images
- target moved during session
- arm pose captured after moving away

## Result

```text
result file:
sample count:
method:
robot rotation format used:
validation observation:
accepted: yes/no
reason:
```
