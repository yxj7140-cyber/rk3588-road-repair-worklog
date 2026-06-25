# Modules

Each module keeps its own notes, tests, and implementation files.

- `chassis/`: chassis movement and CAN motor control.
- `arm/`: Piper arm development and safety.
- `camera/`: RGB-D/depth camera and defect perception.
- `lidar/`: lidar bring-up, network/config, and navigation support.
- `pump/`: peristaltic pump control and interlocks.
- `imu/`: IMU bring-up and yaw-based straight-line assist.

Do not mix hardware modules. Cross-module mission logic belongs in `integration/`.
