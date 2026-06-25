import mmap
import os
import struct
import time


MARKERS = {
    b"BNAC": "CANB",
    b"vNET": "vNET",
}


def hexdump(data):
    return " ".join(f"{byte:02x}" for byte in data)


def read_words(mm, offset, count=16):
    data = mm[offset : offset + count * 4]
    if len(data) < count * 4:
        return []
    return struct.unpack("<" + "I" * count, data)


def main():
    uio = os.environ.get("UIO", "/dev/uio0")
    map_index = int(os.environ.get("UIO_MAP_INDEX", "1"))
    page_size = os.sysconf("SC_PAGE_SIZE")
    size_path = f"/sys/class/uio/{os.path.basename(uio)}/maps/map{map_index}/size"
    size = int(open(size_path, encoding="ascii").read(), 16)
    fd = os.open(uio, os.O_RDWR | os.O_SYNC)

    try:
        mm = mmap.mmap(
            fd,
            size,
            mmap.MAP_SHARED,
            mmap.PROT_READ | mmap.PROT_WRITE,
            offset=page_size * map_index,
        )

        print(f"uio={uio} map{map_index}_size=0x{size:x}")
        for marker, name in MARKERS.items():
            start = 0
            found = []
            while True:
                pos = mm.find(marker, start)
                if pos < 0:
                    break
                found.append(pos)
                start = pos + 1
            print(f"{name}_offsets=" + (",".join(hex(x) for x in found) if found else "not-found"))

        probes = [
            0,
            0x20,
            0x100,
            0x1000,
            0x200000,
            0x400000,
            0x600000,
            0x7FF000,
            0x800000,
            0x9F0000,
            0x9FFFC0,
            0x9FFFE0,
        ]
        for offset in probes:
            if offset + 64 > size:
                continue
            words = read_words(mm, offset)
            print(
                "off=0x%06x words=%s"
                % (offset, " ".join(f"{word:08x}" for word in words[:8]))
            )
            print(hexdump(mm[offset : offset + 64]))

        print("heartbeat samples at offset 0:")
        for index in range(5):
            words = read_words(mm, 0, 8)
            print(
                "iter=%d magic=0x%08x version=%d size=%d flags=0x%08x "
                "rt_hb=%d linux_hb=%d"
                % ((index,) + words[:6])
            )
            time.sleep(0.2)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
