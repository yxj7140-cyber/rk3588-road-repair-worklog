#!/usr/bin/env python3
import argparse
import mmap
import os
import struct
import time


VNET_MAGIC = 0x54454E76
STATE_NAMES = {
    0: "ZERO",
    1: "RESET",
    2: "BCST",
    3: "LINK",
    4: "INIT",
    5: "READY",
    6: "RUN",
}


def map_uio(path, map_index):
    page_size = os.sysconf("SC_PAGE_SIZE")
    uio_name = os.path.basename(path)
    size_path = f"/sys/class/uio/{uio_name}/maps/map{map_index}/size"
    size = int(open(size_path, encoding="ascii").read(), 16)
    fd = os.open(path, os.O_RDWR | os.O_SYNC)
    mm = mmap.mmap(
        fd,
        size,
        mmap.MAP_SHARED,
        mmap.PROT_READ | mmap.PROT_WRITE,
        offset=page_size * map_index,
    )
    return fd, mm, size


def read_regs(path):
    fd, mm, size = map_uio(path, 0)
    try:
        data = mm[: min(64, size)]
        words = struct.unpack("<" + "I" * (len(data) // 4), data)
        print(f"map0_size=0x{size:x}")
        print("regs=" + " ".join(f"{word:08x}" for word in words))
        if len(words) >= 4:
            print(
                "regs_hint intxctrl=0x%08x istat=0x%08x ivpos=%u doorbell=0x%08x"
                % (words[0], words[1], words[2], words[3])
            )
    finally:
        mm.close()
        os.close(fd)


def decode_stub(data):
    magic, ack_ivpos, org_state, pad = struct.unpack("<4I", data)
    ack = ack_ivpos & 0xFFFF
    state = STATE_NAMES.get(org_state, f"UNKNOWN({org_state})")
    magic_text = "vNET" if magic == VNET_MAGIC else f"0x{magic:08x}"
    return magic_text, ack, org_state, state, pad


def read_shm(path, clear_tail=False, samples=1, delay=0.2):
    fd, mm, size = map_uio(path, 1)
    try:
        print(f"map1_size=0x{size:x}")
        if clear_tail:
            print("clearing last two vNET stubs")
            mm[size - 32 : size] = b"\x00" * 32
            mm.flush()

        for sample in range(samples):
            print(f"sample={sample}")
            for index, offset in enumerate((size - 32, size - 16)):
                data = mm[offset : offset + 16]
                magic, ack, org_state, state, pad = decode_stub(data)
                print(
                    "stub%d off=0x%06x raw=%s magic=%s ack=0x%04x state=%u(%s) pad=0x%08x"
                    % (index, offset, data.hex(" "), magic, ack, org_state, state, pad)
                )
            marker_offsets = []
            start = 0
            marker = struct.pack("<I", VNET_MAGIC)
            while True:
                pos = mm.find(marker, start)
                if pos < 0:
                    break
                marker_offsets.append(pos)
                start = pos + 1
            print("vNET_offsets=" + (",".join(hex(x) for x in marker_offsets) if marker_offsets else "not-found"))
            if sample + 1 < samples:
                time.sleep(delay)
    finally:
        mm.close()
        os.close(fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uio", default="/dev/uio0")
    parser.add_argument("--clear-tail", action="store_true")
    parser.add_argument("--samples", type=int, default=1)
    args = parser.parse_args()

    print(f"uio={args.uio}")
    read_regs(args.uio)
    read_shm(args.uio, clear_tail=args.clear_tail, samples=args.samples)


if __name__ == "__main__":
    main()
