import mmap
import os
import struct


MAGIC = b"BNAC"  # 0x43414e42 little endian


def main():
    uio = os.environ.get("UIO", "/dev/uio0")
    map_index = int(os.environ.get("UIO_MAP_INDEX", "1"))
    page_size = os.sysconf("SC_PAGE_SIZE")
    uio_name = os.path.basename(uio)
    size_path = f"/sys/class/uio/{uio_name}/maps/map{map_index}/size"
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
        offset = mm.find(MAGIC)
        print(
            "%s map%d_size=0x%x magic_offset=%s"
            % (uio, map_index, size, "not-found" if offset < 0 else hex(offset))
        )

        for probe in [0, 0x1000, 0x4000, 0x800000, 0x900000]:
            if probe + 64 <= size:
                words = struct.unpack("<16I", mm[probe : probe + 64])
                print(
                    "off=0x%06x magic=0x%08x version=%d size=%d flags=0x%08x rt_hb=%d"
                    % ((probe,) + words[:5])
                )
                print(mm[probe : probe + 32].hex(" "))
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
