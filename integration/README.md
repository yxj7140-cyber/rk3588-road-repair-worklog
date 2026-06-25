# Integration

Cross-module mission logic belongs here.

Areas:

- `mission-flow/`: full topic task sequence.
- `topic1-runner/`: Reside topic 1 execution wrapper.
- `virtual-devices/`: simulated camera, lidar, arm, and pump inputs before hardware is ready.
- `safety-state-machine/`: global safety and priority logic.

Module-specific code should remain in `modules/`.
