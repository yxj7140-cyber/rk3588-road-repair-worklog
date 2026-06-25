# RK3588 Road Repair Worklog

This repository records the RK3588 road-repair vehicle migration work.

Current rule: keep large binary images, SDKs, vendor packages, and VM artifacts outside Git. Track them in `docs/large-files-index.md` with local paths, sizes, roles, and recovery notes.

## Layout

- `docs/`: procedures, bring-up notes, recovery guides, and status summaries.
- `modules/`: hardware/software modules separated by responsibility.
- `integration/`: competition-level mission flow and cross-module coordination.
- `scripts/test/`: temporary and repeatable test scripts.
- `scripts/recovery/`: recovery, reflashing, image repair, and restore scripts.
- `scripts/host-windows/`: Windows-side PowerShell helpers.
- `scripts/vm-linux/`: VM-side Linux scripts.
- `images/old-flashed/`: metadata for previously flashed images.
- `images/shrunk/`: metadata for resized images.
- `images/checksums/`: hash files and verification notes.
- `stable/`: mature deliverables and restore-ready files.
- `checkpoints/`: milestone summaries and selected lightweight snapshots.
- `lessons/`: debugging lessons and repeatable troubleshooting knowledge.
- `external-notes/`: external references, official docs links, and third-party notes.

## Module Boundaries

- `modules/chassis/`: chassis CAN gateway, motor model, RT/Linux bridge, web remote chassis logic, and chassis tests.
- `modules/arm/`: Piper arm control, CAN protocol notes, home pose, J5 issue tracking, and arm safety.
- `modules/camera/`: RGB-D/depth camera, point cloud, defect detection, and hand-eye calibration notes.
- `modules/lidar/`: lidar networking, localization/mapping/path support, and related diagnostics.
- `modules/pump/`: peristaltic pump control, flow/enable logic, and cement delivery safety interlocks.
- `modules/imu/`: WT901C-TTL IMU, yaw calibration, straight-line assist, and serial configuration.

Keep module-specific tests under `modules/<module>/tests/`. Put cross-module or full-mission tests under `scripts/test/` or `integration/`.
