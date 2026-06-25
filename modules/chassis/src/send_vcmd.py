#!/usr/bin/env python3
"""Low-level RT VCMD packet sender for bring-up tests.

For new upper-layer control code, prefer chassis_vcmd_client.py. This script is
kept as a minimal packet-format diagnostic tool.
"""

import argparse
import socket
import struct
import time


VCMD_MAGIC = b"VCMD"
VERSION = 1
VCMD_ENABLE = 1 << 0
PACKET = struct.Struct("<4sHHIhhhH")


def clamp_i16(value: int) -> int:
    return max(-32768, min(32767, int(value)))


def clamp_u16(value: int) -> int:
    return max(0, min(65535, int(value)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="10.10.10.30")
    parser.add_argument("--port", type=int, default=15551)
    parser.add_argument("--forward-rpm", type=int, default=0)
    parser.add_argument("--strafe-rpm", type=int, default=0)
    parser.add_argument("--rotate-rpm", type=int, default=0)
    parser.add_argument("--duration", type=float, default=0.5)
    parser.add_argument("--period", type=float, default=0.02)
    parser.add_argument(
        "--current-limit",
        type=int,
        default=0,
        help="RT current clamp for this VCMD. 0 keeps the RT default.",
    )
    parser.add_argument("--disable", action="store_true")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    flags = 0 if args.disable else VCMD_ENABLE
    deadline = time.monotonic() + max(0.0, args.duration)
    seq = 0

    while True:
        seq += 1
        packet = PACKET.pack(
            VCMD_MAGIC,
            VERSION,
            flags,
            seq,
            clamp_i16(args.forward_rpm),
            clamp_i16(args.strafe_rpm),
            clamp_i16(args.rotate_rpm),
            clamp_u16(args.current_limit),
        )
        sock.sendto(packet, (args.target, args.port))

        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.001, args.period))

    print(
        f"sent VCMD packets={seq} target={args.target}:{args.port} "
        f"flags={flags} forward={args.forward_rpm} strafe={args.strafe_rpm} "
        f"rotate={args.rotate_rpm} current_limit={args.current_limit}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
