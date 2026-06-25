# System Architecture

The road-repair vehicle is organized as five main hardware modules plus integration logic.

## Main Modules

1. Chassis
   - Responsible for vehicle movement.
   - Current path: USB-CAN on Linux, Linux gateway, RT side for real-time chassis execution.
   - Must keep safe-lock behavior for manual web remote.

2. Depth Camera
   - Mounted on or near the arm.
   - Responsible for RGB-D, point cloud, crack/pothole observation, and repair trajectory feedback.
   - Development files live under `modules/camera/`.

3. Arm
   - Piper arm.
   - Responsible for reaching repair pose and aligning tool/camera/pump outlet.
   - J5 joint issue remains a known hardware/vendor-support item.

4. Peristaltic Pump
   - Responsible for cement delivery.
   - Must be controlled with safety interlocks tied to arm pose and task state.

5. Lidar
   - Responsible for navigation support, map/path sensing, or environment awareness.
   - Pedestrian avoidance is currently not required, but lidar interfaces should remain modular.

6. IMU
   - Supports chassis straight-line correction through yaw feedback.
   - Current hardware: WT901C-TTL, auto-detected at 9600 baud during PC testing.

## Integration Layer

The integration layer coordinates the competition task:

1. Patrol the preset road.
2. Detect pothole or crack.
3. Move chassis to repair pose.
4. Use camera/arm feedback to align the repair path.
5. Enable pump only when the arm and chassis state are safe.
6. Record task result and return to patrol.

## Safety Rules

- RT/chassis motion tests require explicit user safety confirmation.
- Web remote must start locked.
- Board-resident temporary test scripts should be removed after use, but backed up on PC/VM.
- Large vendor SDKs and images are tracked by path, not committed.
