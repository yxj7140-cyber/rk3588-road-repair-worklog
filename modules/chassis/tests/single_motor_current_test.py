#!/usr/bin/env python3
"""Short single-motor SocketCAN current test for DJI 3508/C620 bring-up.

This is a Linux-side diagnostic tool. It does not depend on RT-Thread and does
not modify HyperBoot. The tool always sends repeated zero-current frames before
exit and can optionally bring can0 down for a safe post-test state.
"""

from __future__ import annotations

import argparse
import signal
import socket
import struct
import subprocess
import sys
import time
from dataclasses import dataclass


CMD_ID = 0x200
MOTOR_IDS = (0x201, 0x202, 0x203, 0x204)
MAX_TEST_CURRENT = 5000

running = True


@dataclass
class Feedback:
    angle: int = 0
    rpm: int = 0
    current: int = 0
    temperature: int = 0
    count: int = 0
    last_time: float = 0.0


def handle_signal(_signum, _frame) -> None:
    global running
    running = False


def run_cmd(args: list[str], check: bool = True) -> None:
    subprocess.run(args, check=check)


def setup_can(iface: str, bitrate: int) -> None:
    run_cmd(["ip", "link", "set", iface, "down"], check=False)
    run_cmd(["ip", "link", "set", iface, "type", "can", "bitrate", str(bitrate), "restart-ms", "100"])
    run_cmd(["ip", "link", "set", iface, "up"])


def pack_current(currents: list[int]) -> bytes:
    return struct.pack(">hhhh", *currents)


def send_currents(sock: socket.socket, currents: list[int]) -> None:
    frame = struct.pack("=IB3x8s", CMD_ID, 8, pack_current(currents))
    sock.send(frame)


def send_zero(sock: socket.socket) -> None:
    for _ in range(20):
        send_currents(sock, [0, 0, 0, 0])
        time.sleep(0.002)


def drain_feedback(sock: socket.socket, feedback: dict[int, Feedback]) -> None:
    while True:
        try:
            frame = sock.recv(16)
        except BlockingIOError:
            return

        can_id, dlc, data = struct.unpack("=IB3x8s", frame)
        can_id &= socket.CAN_EFF_MASK
        if can_id not in feedback or dlc < 8:
            continue

        angle = struct.unpack(">H", data[0:2])[0]
        rpm = struct.unpack(">h", data[2:4])[0]
        current = struct.unpack(">h", data[4:6])[0]
        temperature = data[6]
        item = feedback[can_id]
        item.angle = angle
        item.rpm = rpm
        item.current = current
        item.temperature = temperature
        item.count += 1
        item.last_time = time.monotonic()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iface", default="can0")
    parser.add_argument("--bitrate", type=int, default=1_000_000)
    parser.add_argument("--motor", type=int, required=True, choices=(1, 2, 3, 4))
    parser.add_argument("--current", type=int, required=True)
    parser.add_argument("--duration", type=float, default=0.8)
    parser.add_argument("--period", type=float, default=0.01)
    parser.add_argument("--print-period", type=float, default=0.1)
    parser.add_argument("--keep-can-up", action="store_true")
    args = parser.parse_args()
    if not -MAX_TEST_CURRENT <= args.current <= MAX_TEST_CURRENT:
        parser.error(f"--current must be within +/-{MAX_TEST_CURRENT}")
    if args.duration <= 0 or args.period <= 0:
        parser.error("--duration and --period must be positive")
    return args


def main() -> int:
    args = parse_args()
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    currents = [0, 0, 0, 0]
    currents[args.motor - 1] = args.current
    feedback = {motor_id: Feedback() for motor_id in MOTOR_IDS}
    target_can_id = 0x200 + args.motor

    print(
        f"single_motor_current_test iface={args.iface} motor={args.motor} "
        f"current={args.current} duration={args.duration}s"
    )
    print("Safety: chassis must be lifted. Sending zero current on exit.")

    sock: socket.socket | None = None
    try:
        setup_can(args.iface, args.bitrate)
        sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        sock.bind((args.iface,))
        sock.setblocking(False)

        start = time.monotonic()
        next_print = start
        while running and (time.monotonic() - start) < args.duration:
            drain_feedback(sock, feedback)
            send_currents(sock, currents)
            now = time.monotonic()
            if now >= next_print:
                item = feedback[target_can_id]
                if item.count:
                    age_ms = int((now - item.last_time) * 1000)
                    print(
                        f"motor={args.motor} req={args.current} "
                        f"rpm={item.rpm:6d} fb_current={item.current:6d} "
                        f"angle={item.angle:5d} temp={item.temperature:3d} "
                        f"count={item.count:5d} age_ms={age_ms:4d}"
                    )
                else:
                    print(f"motor={args.motor} req={args.current} feedback=none")
                next_print = now + args.print_period
            time.sleep(args.period)
    finally:
        if sock is not None:
            print("Sending zero current...")
            send_zero(sock)
            sock.close()
        if not args.keep_can_up:
            run_cmd(["ip", "link", "set", args.iface, "down"], check=False)
        print("single_motor_current_test stopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
