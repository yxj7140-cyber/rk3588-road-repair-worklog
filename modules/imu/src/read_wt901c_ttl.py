#!/usr/bin/env python3
"""Read WIT Motion WT901C-TTL IMU data from a USB-TTL serial port.

This is a Windows-first acceptance tool. It does not touch RK3588, RT-Thread,
chassis CAN, laser radar, or any existing board service.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

try:
    import serial
    from serial.tools import list_ports
except Exception as exc:  # pragma: no cover - local dependency check
    raise SystemExit("pyserial is required. Install with: pip install -r requirements-windows.txt") from exc


FRAME_HEADER = 0x55
FRAME_LEN = 11
DEFAULT_BAUDS = [9600, 115200, 57600, 38400]


@dataclass
class ImuSample:
    timestamp_s: float
    port: str
    baud: int
    roll_deg: float | None = None
    pitch_deg: float | None = None
    yaw_deg: float | None = None
    gyro_x_dps: float | None = None
    gyro_y_dps: float | None = None
    gyro_z_dps: float | None = None
    acc_x_g: float | None = None
    acc_y_g: float | None = None
    acc_z_g: float | None = None
    temp_c: float | None = None


class WitParser:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.last_acc: tuple[float, float, float, float] | None = None
        self.last_gyro: tuple[float, float, float, float] | None = None

    @staticmethod
    def _i16(lo: int, hi: int) -> int:
        value = lo | (hi << 8)
        if value >= 0x8000:
            value -= 0x10000
        return value

    @staticmethod
    def _checksum_ok(frame: bytes) -> bool:
        return (sum(frame[:10]) & 0xFF) == frame[10]

    def feed(self, data: bytes, port: str, baud: int) -> Iterable[ImuSample]:
        self.buffer.extend(data)
        while len(self.buffer) >= FRAME_LEN:
            if self.buffer[0] != FRAME_HEADER:
                del self.buffer[0]
                continue
            frame = bytes(self.buffer[:FRAME_LEN])
            if not self._checksum_ok(frame):
                del self.buffer[0]
                continue
            del self.buffer[:FRAME_LEN]
            sample = self._parse_frame(frame, port, baud)
            if sample is not None:
                yield sample

    def _parse_frame(self, frame: bytes, port: str, baud: int) -> ImuSample | None:
        kind = frame[1]
        values = [self._i16(frame[i], frame[i + 1]) for i in range(2, 10, 2)]
        now = time.time()

        if kind == 0x51:
            ax = values[0] / 32768.0 * 16.0
            ay = values[1] / 32768.0 * 16.0
            az = values[2] / 32768.0 * 16.0
            temp = values[3] / 100.0
            self.last_acc = (ax, ay, az, temp)
            return None

        if kind == 0x52:
            gx = values[0] / 32768.0 * 2000.0
            gy = values[1] / 32768.0 * 2000.0
            gz = values[2] / 32768.0 * 2000.0
            temp = values[3] / 100.0
            self.last_gyro = (gx, gy, gz, temp)
            return None

        if kind == 0x53:
            roll = values[0] / 32768.0 * 180.0
            pitch = values[1] / 32768.0 * 180.0
            yaw = values[2] / 32768.0 * 180.0
            temp = values[3] / 100.0
            sample = ImuSample(timestamp_s=now, port=port, baud=baud, roll_deg=roll, pitch_deg=pitch, yaw_deg=yaw, temp_c=temp)
            if self.last_gyro is not None:
                sample.gyro_x_dps, sample.gyro_y_dps, sample.gyro_z_dps, _ = self.last_gyro
            if self.last_acc is not None:
                sample.acc_x_g, sample.acc_y_g, sample.acc_z_g, _ = self.last_acc
            return sample

        return None


def list_serial_ports() -> list[str]:
    ports = [port.device for port in list_ports.comports()]
    return sorted(ports)


def detect_port_and_baud(port: str | None, bauds: list[int], timeout_s: float) -> tuple[str, int]:
    ports = [port] if port else list_serial_ports()
    if not ports:
        raise SystemExit("No serial ports found. Plug in the USB-TTL adapter and retry.")

    for candidate_port in ports:
        for baud in bauds:
            parser = WitParser()
            try:
                with serial.Serial(candidate_port, baudrate=baud, timeout=0.1) as ser:
                    deadline = time.monotonic() + timeout_s
                    while time.monotonic() < deadline:
                        samples = list(parser.feed(ser.read(256), candidate_port, baud))
                        if samples:
                            return candidate_port, baud
            except Exception:
                continue
    raise SystemExit(f"Could not detect WT901C frames on ports={ports}, bauds={bauds}")


def _angle_delta_deg(now: float, start: float) -> float:
    delta = now - start
    while delta > 180.0:
        delta -= 360.0
    while delta < -180.0:
        delta += 360.0
    return delta


def run(args: argparse.Namespace) -> int:
    bauds = args.baud or DEFAULT_BAUDS
    port, baud = detect_port_and_baud(args.port, bauds, args.detect_timeout_s)
    print(f"Detected WT901C-TTL: port={port}, baud={baud}")

    output_path = Path(args.output) if args.output else None
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    parser = WitParser()
    start = time.monotonic()
    first_yaw: float | None = None
    last_print = 0.0
    sample_count = 0

    csv_file = output_path.open("w", newline="", encoding="utf-8") if output_path else None
    writer = None
    try:
        if csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=list(asdict(ImuSample(0, "", 0)).keys()))
            writer.writeheader()

        with serial.Serial(port, baudrate=baud, timeout=0.1) as ser:
            while time.monotonic() - start < args.duration_s:
                for sample in parser.feed(ser.read(256), port, baud):
                    sample_count += 1
                    if sample.yaw_deg is not None and first_yaw is None:
                        first_yaw = sample.yaw_deg
                    if writer:
                        writer.writerow(asdict(sample))
                    now = time.monotonic()
                    if now - last_print >= args.print_interval_s:
                        last_print = now
                        drift = None if first_yaw is None or sample.yaw_deg is None else _angle_delta_deg(sample.yaw_deg, first_yaw)
                        print(
                            "yaw={:.2f} deg pitch={:.2f} roll={:.2f} gyro_z={:.2f} dps drift={}".format(
                                sample.yaw_deg if sample.yaw_deg is not None else math.nan,
                                sample.pitch_deg if sample.pitch_deg is not None else math.nan,
                                sample.roll_deg if sample.roll_deg is not None else math.nan,
                                sample.gyro_z_dps if sample.gyro_z_dps is not None else math.nan,
                                "n/a" if drift is None else f"{drift:.2f} deg",
                            )
                        )
    finally:
        if csv_file:
            csv_file.close()

    summary = {
        "port": port,
        "baud": baud,
        "duration_s": args.duration_s,
        "sample_count": sample_count,
        "output": str(output_path) if output_path else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if sample_count > 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read WT901C-TTL WIT 0x55 serial IMU frames.")
    parser.add_argument("--port", help="Serial port, e.g. COM7. Omit to auto-detect.")
    parser.add_argument("--baud", type=int, action="append", help="Try a baud rate. Can be repeated.")
    parser.add_argument("--duration-s", type=float, default=30.0)
    parser.add_argument("--detect-timeout-s", type=float, default=1.5)
    parser.add_argument("--print-interval-s", type=float, default=0.5)
    parser.add_argument("--output", help="Optional CSV output path.")
    return parser


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
