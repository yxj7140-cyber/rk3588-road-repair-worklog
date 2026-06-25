#!/usr/bin/env python3
"""
Zero-current-safe USB-CAN gateway skeleton for DJI 3508 style chassis motors.

This script runs on Linux. It receives motor feedback frames 0x201-0x204 and
periodically sends a zero-current command frame 0x200. Non-zero current output
is intentionally not implemented here; keep this as the safe bring-up tool.
"""

import argparse
import signal
import socket
import struct
import sys
import time


MOTOR_IDS = (0x201, 0x202, 0x203, 0x204)
CMD_ID = 0x200
CAN_EFF_FLAG = 0x80000000
CAN_RTR_FLAG = 0x40000000
CAN_ERR_FLAG = 0x20000000
CAN_SFF_MASK = 0x000007FF


def pack_can_frame(can_id, payload):
    payload = bytes(payload)
    if len(payload) > 8:
        raise ValueError("CAN payload too long")
    return struct.pack("=IB3x8s", can_id, len(payload), payload.ljust(8, b"\x00"))


def unpack_can_frame(frame):
    can_id, dlc, data = struct.unpack("=IB3x8s", frame)
    return can_id, dlc, data[:dlc]


def parse_motor_feedback(data):
    if len(data) < 7:
        return None
    angle = (data[0] << 8) | data[1]
    speed_rpm = struct.unpack(">h", data[2:4])[0]
    current_raw = struct.unpack(">h", data[4:6])[0]
    temperature = data[6]
    return angle, speed_rpm, current_raw, temperature


def send_zero_current(sock):
    sock.send(pack_can_frame(CMD_ID, b"\x00" * 8))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iface", default="can0")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--zero-period", type=float, default=0.02)
    args = parser.parse_args()

    stop = False

    def handle_signal(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    sock.bind((args.iface,))
    sock.setblocking(False)

    stats = {can_id: {"count": 0, "last": None} for can_id in MOTOR_IDS}
    start = time.monotonic()
    next_zero = start
    next_print = start

    print(f"can_gateway_zero_safe: iface={args.iface} duration={args.duration}s")
    print("Safety: command frame 0x200 is always eight zero bytes.")

    while not stop and time.monotonic() - start < args.duration:
        now = time.monotonic()
        if now >= next_zero:
            send_zero_current(sock)
            next_zero += args.zero_period

        try:
            frame = sock.recv(16)
        except BlockingIOError:
            time.sleep(0.001)
            continue

        can_id, dlc, data = unpack_can_frame(frame)
        if can_id & (CAN_EFF_FLAG | CAN_RTR_FLAG | CAN_ERR_FLAG):
            continue
        std_id = can_id & CAN_SFF_MASK
        if std_id not in stats:
            continue

        parsed = parse_motor_feedback(data)
        if parsed is None:
            continue
        stats[std_id]["count"] += 1
        stats[std_id]["last"] = parsed

        if now >= next_print:
            next_print = now + 1.0
            parts = []
            for motor_id in MOTOR_IDS:
                item = stats[motor_id]
                if item["last"] is None:
                    parts.append(f"{motor_id:03x}:no-data")
                else:
                    angle, speed, current, temp = item["last"]
                    parts.append(
                        f"{motor_id:03x}:cnt={item['count']} angle={angle} "
                        f"rpm={speed} cur={current} temp={temp}"
                    )
            print(" | ".join(parts))

    send_zero_current(sock)
    print("done; final zero-current frame sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
