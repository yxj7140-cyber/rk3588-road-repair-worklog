#!/usr/bin/env python3
"""
Linux USB-CAN gateway for the RK3588 vmRT chassis bring-up.

Default behavior is intentionally safe:
  - Receive DJI motor feedback frames 0x201-0x204.
  - Publish feedback into the optional CANB shared-memory block if RT creates it.
  - Send command frame 0x200 with four zero currents unless explicit non-zero
    output is enabled by two command-line switches.

Do not enable non-zero current output until the robot is lifted or otherwise
made safe and the operator explicitly approves motor movement.
"""

import argparse
import errno
import json
import mmap
import os
import signal
import socket
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


MOTOR_IDS = (0x201, 0x202, 0x203, 0x204)
CMD_ID = 0x200

CAN_EFF_FLAG = 0x80000000
CAN_RTR_FLAG = 0x40000000
CAN_ERR_FLAG = 0x20000000
CAN_SFF_MASK = 0x000007FF

CANB_MAGIC = 0x43414E42
CANB_VERSION = 1
CANB_RT_READY = 1 << 0
CANB_LINUX_READY = 1 << 1
CANB_CMD_ENABLE = 1 << 2

CANB_HEADER_SIZE = 32
CANB_STRUCT_MIN_SIZE = 176
CANB_CURRENT_OFFSET = 32
CANB_MOTOR_OFFSET = 48
CANB_MOTOR_SIZE = 16
CANB_TX_COUNT_OFFSET = 112
CANB_RX_COUNT_OFFSET = 116
CANB_ERROR_COUNT_OFFSET = 120

UDP_CMD_MAGIC = b"RCAN"
UDP_FEEDBACK_MAGIC = b"FCAN"
UDP_VERSION = 1
UDP_CMD_ENABLE = 1 << 0
UDP_CMD_STRUCT = struct.Struct("<4sHHIhhhh")
UDP_FEEDBACK_HEADER_STRUCT = struct.Struct("<4sHHII")
UDP_FEEDBACK_MOTOR_STRUCT = struct.Struct("<IHHhBBI")


@dataclass
class MotorFeedback:
    angle: int = 0
    speed_rpm: int = 0
    current_raw: int = 0
    temperature: int = 0
    count: int = 0
    update_seq: int = 0
    last_seen: float = 0.0


def pack_can_frame(can_id: int, payload: bytes) -> bytes:
    if len(payload) > 8:
        raise ValueError("CAN payload too long")
    return struct.pack("=IB3x8s", can_id, len(payload), payload.ljust(8, b"\x00"))


def unpack_can_frame(frame: bytes) -> Tuple[int, int, bytes]:
    can_id, dlc, data = struct.unpack("=IB3x8s", frame)
    return can_id, dlc, data[:dlc]


def parse_motor_feedback(data: bytes) -> Optional[Tuple[int, int, int, int]]:
    if len(data) < 7:
        return None
    angle = (data[0] << 8) | data[1]
    speed_rpm = struct.unpack(">h", data[2:4])[0]
    current_raw = struct.unpack(">h", data[4:6])[0]
    temperature = data[6]
    return angle, speed_rpm, current_raw, temperature


def pack_current_command(currents) -> bytes:
    clipped = []
    for value in currents:
        value = int(value)
        if value < -16384:
            value = -16384
        if value > 16384:
            value = 16384
        clipped.append(value)
    return struct.pack(">hhhh", *clipped)


def setup_can_interface(iface: str, bitrate: int) -> None:
    subprocess.run(["ip", "link", "set", iface, "down"], check=False)
    subprocess.run(
        [
            "ip",
            "link",
            "set",
            iface,
            "type",
            "can",
            "bitrate",
            str(bitrate),
            "restart-ms",
            "100",
        ],
        check=True,
    )
    subprocess.run(["ip", "link", "set", iface, "txqueuelen", "100"], check=False)
    subprocess.run(["ip", "link", "set", iface, "up"], check=True)


def wait_for_rt_ping(target: str, iface: str, timeout: float, interval: float) -> bool:
    deadline = time.monotonic() + timeout
    cmd = ["ping", "-c", "1", "-W", "1"]
    if iface:
        cmd.extend(["-I", iface])
    cmd.append(target)

    print(
        f"Waiting for RT network: target={target} iface={iface or 'default'} timeout={timeout:.1f}s",
        flush=True,
    )
    while True:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if result.returncode == 0:
            print(f"RT network reachable: {target}", flush=True)
            return True

        now = time.monotonic()
        if now >= deadline:
            print(f"ERROR: RT network not reachable before timeout: {target}", file=sys.stderr, flush=True)
            return False
        time.sleep(min(interval, max(0.05, deadline - now)))


def resolve_uio_device(requested: str, pci_dev: str) -> str:
    if requested != "auto":
        return requested

    uio_root = f"/sys/bus/pci/devices/{pci_dev}/uio"
    try:
        names = sorted(name for name in os.listdir(uio_root) if name.startswith("uio"))
    except FileNotFoundError:
        return "/dev/uio0"

    if not names:
        return "/dev/uio0"

    return f"/dev/{names[0]}"


class CanbSharedMemory:
    def __init__(self, uio: str, map_index: int, offset: int = -1):
        self.uio = uio
        self.map_index = map_index
        self.offset = offset
        self.fd = None
        self.mm = None
        self.size = 0
        self.linux_heartbeat = 0
        self.linux_feedback_seq = 0
        self.tx_count = 0
        self.rx_count = 0
        self.error_count = 0

    def open(self) -> bool:
        uio_name = os.path.basename(self.uio)
        size_path = f"/sys/class/uio/{uio_name}/maps/map{self.map_index}/size"
        if not os.path.exists(self.uio) or not os.path.exists(size_path):
            return False

        page_size = os.sysconf("SC_PAGE_SIZE")
        self.size = int(open(size_path, encoding="ascii").read(), 16)
        self.fd = os.open(self.uio, os.O_RDWR | os.O_SYNC)
        self.mm = mmap.mmap(
            self.fd,
            self.size,
            mmap.MAP_SHARED,
            mmap.PROT_READ | mmap.PROT_WRITE,
            offset=page_size * self.map_index,
        )
        if self.offset < 0:
            marker = struct.pack("<I", CANB_MAGIC)
            self.offset = self.mm.find(marker)
        if self.offset < 0 or self.offset + CANB_STRUCT_MIN_SIZE > self.size:
            return False
        return True

    def close(self) -> None:
        if self.mm is not None:
            self.mm.close()
            self.mm = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def is_rt_ready(self) -> bool:
        if self.mm is None or self.offset < 0 or self.offset + CANB_STRUCT_MIN_SIZE > self.size:
            return False
        magic, version, struct_size, flags = struct.unpack_from("<IIII", self.mm, self.offset)
        return magic == CANB_MAGIC and version == CANB_VERSION and struct_size >= CANB_STRUCT_MIN_SIZE and bool(flags & CANB_RT_READY)

    def publish_feedback(self, feedback: Dict[int, MotorFeedback]) -> None:
        if self.mm is None or not self.is_rt_ready():
            return

        base = self.offset
        magic, version, struct_size, flags = struct.unpack_from("<IIII", self.mm, base)
        flags |= CANB_LINUX_READY
        self.linux_heartbeat += 1
        self.linux_feedback_seq += 1

        struct.pack_into(
            "<IIIIIIII",
            self.mm,
            base,
            magic,
            version,
            struct_size,
            flags,
            struct.unpack_from("<I", self.mm, base + 16)[0],
            self.linux_heartbeat,
            struct.unpack_from("<I", self.mm, base + 24)[0],
            self.linux_feedback_seq,
        )

        for index, motor_id in enumerate(MOTOR_IDS):
            item = feedback[motor_id]
            offset = base + CANB_MOTOR_OFFSET + index * CANB_MOTOR_SIZE
            struct.pack_into(
                "<IHHhBBI",
                self.mm,
                offset,
                item.update_seq,
                item.angle & 0xFFFF,
                item.speed_rpm & 0xFFFF,
                item.current_raw,
                item.temperature & 0xFF,
                0,
                item.count,
            )

        struct.pack_into("<III", self.mm, base + CANB_TX_COUNT_OFFSET, self.tx_count, self.rx_count, self.error_count)

    def read_current_command(self) -> Optional[Tuple[int, int, int, int]]:
        if self.mm is None or not self.is_rt_ready():
            return None
        flags = struct.unpack_from("<I", self.mm, self.offset + 12)[0]
        if not (flags & CANB_CMD_ENABLE):
            return None
        return struct.unpack_from("<hhhh", self.mm, self.offset + CANB_CURRENT_OFFSET)


def open_can_socket(iface: str) -> socket.socket:
    sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    sock.bind((iface,))
    sock.setblocking(False)
    return sock


def format_stats(feedback: Dict[int, MotorFeedback]) -> str:
    parts = []
    now = time.monotonic()
    for motor_id in MOTOR_IDS:
        item = feedback[motor_id]
        age = now - item.last_seen if item.last_seen else -1.0
        if item.count == 0:
            parts.append(f"{motor_id:03x}:no-data")
        else:
            parts.append(
                f"{motor_id:03x}:cnt={item.count} angle={item.angle} "
                f"rpm={item.speed_rpm} cur={item.current_raw} temp={item.temperature} age={age:.2f}s"
            )
    return " | ".join(parts)


def write_feedback_json(
    path: str,
    feedback: Dict[int, MotorFeedback],
    feedback_seq: int,
    cmd_count: int,
) -> None:
    """Publish a small machine-readable feedback snapshot for Linux tools."""

    if not path:
        return

    wall_now = time.time()
    mono_now = time.monotonic()
    payload = {
        "time": wall_now,
        "feedback_seq": int(feedback_seq),
        "cmd_count": int(cmd_count),
        "motors": {},
    }
    for motor_id in MOTOR_IDS:
        item = feedback[motor_id]
        age = mono_now - item.last_seen if item.last_seen else None
        payload["motors"][f"0x{motor_id:03x}"] = {
            "angle": int(item.angle),
            "speed_rpm": int(item.speed_rpm),
            "current_raw": int(item.current_raw),
            "temperature": int(item.temperature),
            "count": int(item.count),
            "update_seq": int(item.update_seq),
            "age_s": age,
        }

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
    os.replace(temp_path, path)


class UdpRtLink:
    def __init__(self, bind_ip: str, port: int, tx_period: float, command_timeout: float):
        self.bind_ip = bind_ip
        self.port = port
        self.tx_period = tx_period
        self.command_timeout = command_timeout
        self.sock: Optional[socket.socket] = None
        self.peer: Optional[Tuple[str, int]] = None
        self.last_rx_time = 0.0
        self.cmd_count = 0
        self.feedback_seq = 0
        self.next_tx = time.monotonic()
        self.current_cmd = (0, 0, 0, 0)
        self.cmd_enabled = False

    def open(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.bind_ip, self.port))
        self.sock.setblocking(False)
        print(f"UDP RT link listening on {self.bind_ip}:{self.port}", flush=True)

    def poll_command(self) -> None:
        if self.sock is None:
            return

        while True:
            try:
                data, peer = self.sock.recvfrom(256)
            except BlockingIOError:
                return

            if len(data) < UDP_CMD_STRUCT.size:
                continue

            magic, version, flags, seq, c1, c2, c3, c4 = UDP_CMD_STRUCT.unpack_from(data)
            if magic != UDP_CMD_MAGIC or version != UDP_VERSION:
                continue

            self.peer = peer
            self.last_rx_time = time.monotonic()
            self.cmd_count += 1
            self.current_cmd = (c1, c2, c3, c4)
            self.cmd_enabled = bool(flags & UDP_CMD_ENABLE)

    def read_current_command(self) -> Optional[Tuple[int, int, int, int]]:
        if not self.cmd_enabled:
            return None
        if self.command_timeout > 0 and self.last_rx_time:
            if time.monotonic() - self.last_rx_time > self.command_timeout:
                return None
        return self.current_cmd

    def publish_feedback(self, feedback: Dict[int, MotorFeedback], force: bool = False) -> None:
        if self.sock is None or self.peer is None:
            return

        now = time.monotonic()
        if not force and now < self.next_tx:
            return
        self.next_tx = now + self.tx_period
        self.feedback_seq += 1

        payload = bytearray()
        payload += UDP_FEEDBACK_HEADER_STRUCT.pack(
            UDP_FEEDBACK_MAGIC,
            UDP_VERSION,
            len(MOTOR_IDS),
            self.feedback_seq,
            self.cmd_count,
        )
        for motor_id in MOTOR_IDS:
            item = feedback[motor_id]
            payload += UDP_FEEDBACK_MOTOR_STRUCT.pack(
                item.update_seq,
                item.angle & 0xFFFF,
                item.speed_rpm & 0xFFFF,
                item.current_raw,
                item.temperature & 0xFF,
                0,
                item.count,
            )

        try:
            self.sock.sendto(payload, self.peer)
        except OSError:
            pass

    def status(self, output_allowed: Optional[bool] = None) -> str:
        if self.sock is None:
            return "udp=off"
        if self.peer is None:
            return f"udp=listening:{self.bind_ip}:{self.port}"
        age = time.monotonic() - self.last_rx_time if self.last_rx_time else -1.0
        stale = self.command_timeout > 0 and age > self.command_timeout
        stale_text = " stale" if stale else ""
        rt_text = "en" if self.cmd_enabled else "lock"
        out_text = ""
        if output_allowed is not None:
            out_text = f" out={'en' if output_allowed else 'lock'}"
        req_text = ",".join(str(value) for value in self.current_cmd)
        return (
            f"udp=peer:{self.peer[0]}:{self.peer[1]} age={age:.2f}s "
            f"cmd={self.cmd_count}{stale_text} rt={rt_text}{out_text} req={req_text}"
        )


def wait_for_udp_peer(udp: UdpRtLink, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    next_log = 0.0

    print(f"Waiting for RT UDP peer timeout={timeout:.1f}s", flush=True)
    while True:
        udp.poll_command()
        if udp.peer is not None:
            print(f"RT UDP peer detected: {udp.peer[0]}:{udp.peer[1]}", flush=True)
            return True

        now = time.monotonic()
        if now >= deadline:
            print("ERROR: RT UDP peer not detected before timeout", file=sys.stderr, flush=True)
            return False
        if now >= next_log:
            print(f"{udp.status()} waiting-peer", flush=True)
            next_log = now + 1.0
        time.sleep(0.02)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iface", default="can0")
    parser.add_argument("--bitrate", type=int, default=1000000)
    parser.add_argument("--setup-can", action="store_true")
    parser.add_argument("--cmd-period", type=float, default=0.02)
    parser.add_argument("--log-period", type=float, default=1.0)
    parser.add_argument("--shm-retry-period", type=float, default=2.0)
    parser.add_argument("--send-before-feedback", action="store_true")
    parser.add_argument("--pci-dev", default="0000:ff:05.0")
    parser.add_argument("--uio", default="auto")
    parser.add_argument("--uio-map", type=int, default=1)
    parser.add_argument("--canb-offset", type=lambda value: int(value, 0), default=-1)
    parser.add_argument("--no-shm", action="store_true")
    parser.add_argument("--udp", action="store_true")
    parser.add_argument("--udp-bind", default="0.0.0.0")
    parser.add_argument("--udp-port", type=int, default=15550)
    parser.add_argument("--udp-feedback-period", type=float, default=0.02)
    parser.add_argument("--udp-command-timeout", type=float, default=0.25)
    parser.add_argument("--feedback-json", default="")
    parser.add_argument("--feedback-json-period", type=float, default=0.05)
    parser.add_argument("--require-rt-ping", default="")
    parser.add_argument("--rt-ping-iface", default="enp255s5")
    parser.add_argument("--rt-ping-timeout", type=float, default=60.0)
    parser.add_argument("--rt-ping-interval", type=float, default=1.0)
    parser.add_argument("--require-udp-peer-timeout", type=float, default=0.0)
    parser.add_argument("--allow-nonzero-current", action="store_true")
    parser.add_argument("--i-understand-this-can-move-motors", action="store_true")
    args = parser.parse_args()

    nonzero_allowed = args.allow_nonzero_current and args.i_understand_this_can_move_motors
    if args.allow_nonzero_current and not nonzero_allowed:
        print("Refusing non-zero mode: both safety flags are required.", file=sys.stderr)
        return 2

    if args.require_rt_ping:
        if not wait_for_rt_ping(args.require_rt_ping, args.rt_ping_iface, args.rt_ping_timeout, args.rt_ping_interval):
            return 3

    args.uio = resolve_uio_device(args.uio, args.pci_dev)

    def try_open_shm():
        candidate = CanbSharedMemory(args.uio, args.uio_map, args.canb_offset)
        if candidate.open():
            print(
                f"CANB shared-memory candidate opened: {args.uio} map{args.uio_map} "
                f"size=0x{candidate.size:x} canb_offset=0x{candidate.offset:x}",
                flush=True,
            )
            return candidate
        print("CANB shared-memory candidate not available; running CAN-only safe mode.", flush=True)
        return None

    shm = None if args.no_shm else try_open_shm()
    udp = UdpRtLink(args.udp_bind, args.udp_port, args.udp_feedback_period, args.udp_command_timeout) if args.udp else None
    if udp is not None:
        udp.open()

    if args.require_udp_peer_timeout > 0:
        if udp is None:
            print("ERROR: --require-udp-peer-timeout needs --udp", file=sys.stderr)
            return 4
        if not wait_for_udp_peer(udp, args.require_udp_peer_timeout):
            return 4

    if args.setup_can:
        setup_can_interface(args.iface, args.bitrate)

    sock = open_can_socket(args.iface)
    feedback = {motor_id: MotorFeedback() for motor_id in MOTOR_IDS}
    stop = False
    tx_enobufs = 0
    tx_backoff_until = 0.0
    next_shm_retry = time.monotonic() + args.shm_retry_period
    next_feedback_json = time.monotonic()

    def handle_signal(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"can_gateway_service: iface={args.iface} bitrate={args.bitrate}")
    print("Safety: non-zero current output is disabled." if not nonzero_allowed else "WARNING: non-zero current output is enabled.")

    next_tx = time.monotonic()
    next_log = time.monotonic()
    zero_payload = b"\x00" * 8

    while not stop:
        now = time.monotonic()

        if shm is None and not args.no_shm and now >= next_shm_retry:
            shm = try_open_shm()
            next_shm_retry = now + args.shm_retry_period
        if udp is not None:
            udp.poll_command()

        have_feedback = any(item.count for item in feedback.values())
        should_send = args.send_before_feedback or have_feedback

        if should_send and now >= next_tx and now >= tx_backoff_until:
            currents = (0, 0, 0, 0)
            if nonzero_allowed:
                command = None
                if udp is not None:
                    command = udp.read_current_command()
                if command is None and shm is not None:
                    command = shm.read_current_command()
                if command is not None:
                    currents = command
            payload = pack_current_command(currents) if any(currents) else zero_payload
            try:
                sock.send(pack_can_frame(CMD_ID, payload))
                if shm is not None:
                    shm.tx_count += 1
            except OSError as exc:
                if exc.errno != errno.ENOBUFS:
                    raise
                tx_enobufs += 1
                tx_backoff_until = now + 0.2
                if shm is not None:
                    shm.error_count += 1
            next_tx += args.cmd_period

        got_frame = False
        try:
            frame = sock.recv(16)
            got_frame = True
        except BlockingIOError:
            pass

        if got_frame:
            can_id, dlc, data = unpack_can_frame(frame)
            if can_id & (CAN_EFF_FLAG | CAN_RTR_FLAG | CAN_ERR_FLAG):
                got_frame = False

        if got_frame:
            std_id = can_id & CAN_SFF_MASK
            if std_id in feedback:
                parsed = parse_motor_feedback(data)
                if parsed is not None:
                    item = feedback[std_id]
                    item.angle, item.speed_rpm, item.current_raw, item.temperature = parsed
                    item.count += 1
                    item.update_seq += 1
                    item.last_seen = now
                    if shm is not None:
                        shm.rx_count += 1
                        shm.publish_feedback(feedback)
                    if udp is not None:
                        udp.publish_feedback(feedback)

        if args.feedback_json and now >= next_feedback_json:
            udp_feedback_seq = udp.feedback_seq if udp is not None else 0
            udp_cmd_count = udp.cmd_count if udp is not None else 0
            write_feedback_json(args.feedback_json, feedback, udp_feedback_seq, udp_cmd_count)
            next_feedback_json = now + max(0.01, float(args.feedback_json_period))

        if now >= next_log:
            shm_state = "none"
            if shm is not None:
                shm_state = "rt-ready" if shm.is_rt_ready() else "waiting-rt"
            udp_state = udp.status(nonzero_allowed) if udp is not None else "udp=off"
            print(f"shm={shm_state} {udp_state} tx_enobufs={tx_enobufs} {format_stats(feedback)}", flush=True)
            if udp is not None:
                udp.publish_feedback(feedback, force=True)
            next_log = now + args.log_period

        if not got_frame:
            time.sleep(0.001)

    try:
        sock.send(pack_can_frame(CMD_ID, zero_payload))
    except OSError as exc:
        if exc.errno != errno.ENOBUFS:
            raise
    if shm is not None:
        shm.close()
    print("stopped; final zero-current frame sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
