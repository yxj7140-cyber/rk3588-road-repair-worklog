#!/usr/bin/env python3
"""Runtime VCMD client for the RK3588 RT chassis controller.

This is the stable upper-layer entry point for the current migration path:

    upper-layer/Linux app -> VCMD UDP -> RT controller -> Linux CAN gateway

The axis convention is user-facing and matches the validated RT image:

    forward + = forward
    strafe  + = right
    rotate  + = left / counterclockwise

Do not invert strafe or rotate here. The current RT image performs the
command-boundary normalization before entering the physical wheel mixer.
"""

from __future__ import annotations

import argparse
import socket
import struct
import time
from dataclasses import dataclass


VCMD_MAGIC = b"VCMD"
VCMD_VERSION = 1
VCMD_ENABLE = 1 << 0
VCMD_PACKET = struct.Struct("<4sHHIhhhH")

DEFAULT_TARGET = "10.10.10.30"
DEFAULT_PORT = 15551
DEFAULT_PERIOD_S = 0.02


def clamp_i16(value: int) -> int:
    return max(-32768, min(32767, int(value)))


def clamp_u16(value: int) -> int:
    return max(0, min(65535, int(value)))


@dataclass(frozen=True)
class ChassisVelocityCommand:
    """User-facing chassis command in RPM-like RT target units."""

    forward_rpm: int = 0
    strafe_rpm: int = 0
    rotate_rpm: int = 0
    current_limit: int = 0
    enabled: bool = True

    def packet(self, seq: int) -> bytes:
        flags = VCMD_ENABLE if self.enabled else 0
        return VCMD_PACKET.pack(
            VCMD_MAGIC,
            VCMD_VERSION,
            flags,
            int(seq) & 0xFFFFFFFF,
            clamp_i16(self.forward_rpm),
            clamp_i16(self.strafe_rpm),
            clamp_i16(self.rotate_rpm),
            clamp_u16(self.current_limit),
        )


class ChassisVcmdClient:
    """Small UDP client used by Linux-side upper-layer code."""

    def __init__(self, target: str = DEFAULT_TARGET, port: int = DEFAULT_PORT):
        self.target = target
        self.port = int(port)
        self.seq = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def close(self) -> None:
        self.sock.close()

    def send(self, command: ChassisVelocityCommand) -> int:
        self.seq = (self.seq + 1) & 0xFFFFFFFF
        if self.seq == 0:
            self.seq = 1
        self.sock.sendto(command.packet(self.seq), (self.target, self.port))
        return self.seq

    def stream(
        self,
        command: ChassisVelocityCommand,
        duration_s: float,
        period_s: float = DEFAULT_PERIOD_S,
        final_stop: bool = True,
    ) -> int:
        """Send a command repeatedly so the RT 250 ms failsafe stays fed."""

        count = 0
        deadline = time.monotonic() + max(0.0, float(duration_s))
        period_s = max(0.001, float(period_s))

        while True:
            self.send(command)
            count += 1
            if time.monotonic() >= deadline:
                break
            time.sleep(period_s)

        if final_stop:
            self.stop(period_s=period_s)
        return count

    def stop(self, repeats: int = 8, period_s: float = DEFAULT_PERIOD_S) -> None:
        stop_cmd = ChassisVelocityCommand(enabled=False)
        for _ in range(max(1, int(repeats))):
            self.send(stop_cmd)
            time.sleep(max(0.001, float(period_s)))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send user-facing chassis VCMD packets to the RK3588 RT controller."
    )
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--forward-rpm", type=int, default=0)
    parser.add_argument("--strafe-rpm", type=int, default=0)
    parser.add_argument("--rotate-rpm", type=int, default=0)
    parser.add_argument(
        "--current-limit",
        type=int,
        default=0,
        help="RT PID output clamp. 0 keeps the RT default.",
    )
    parser.add_argument("--duration", type=float, default=0.2)
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD_S)
    parser.add_argument("--stop", action="store_true", help="Send disabled VCMD stop packets.")
    parser.add_argument("--no-final-stop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    if args.stop:
        command = ChassisVelocityCommand(enabled=False)
    else:
        command = ChassisVelocityCommand(
            forward_rpm=args.forward_rpm,
            strafe_rpm=args.strafe_rpm,
            rotate_rpm=args.rotate_rpm,
            current_limit=args.current_limit,
            enabled=True,
        )

    if args.dry_run:
        flags = VCMD_ENABLE if command.enabled else 0
        print(
            "dry-run VCMD "
            f"target={args.target}:{args.port} flags={flags} "
            f"forward={command.forward_rpm} strafe={command.strafe_rpm} "
            f"rotate={command.rotate_rpm} current_limit={command.current_limit} "
            "convention='forward+ forward, strafe+ right, rotate+ left'"
        )
        return 0

    client = ChassisVcmdClient(args.target, args.port)
    try:
        if args.stop:
            client.stop(period_s=args.period)
            count = 8
        else:
            count = client.stream(
                command,
                duration_s=args.duration,
                period_s=args.period,
                final_stop=not args.no_final_stop,
            )
        print(
            f"sent VCMD packets={count} target={args.target}:{args.port} "
            f"forward={command.forward_rpm} strafe={command.strafe_rpm} "
            f"rotate={command.rotate_rpm} current_limit={command.current_limit} "
            f"enabled={int(command.enabled)}"
        )
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
