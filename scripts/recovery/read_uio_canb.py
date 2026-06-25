import mmap
import os
import struct
import time

MAGIC = struct.pack("<I", 0x43414E42)


def main():
    path = os.environ.get("UIO", "/dev/uio0")
    map_index = int(os.environ.get("UIO_MAP_INDEX", "1"))
    requested_offset = int(os.environ.get("CANB_OFFSET", "-1"), 0)
    uio_name = os.path.basename(path)
    size_path = f"/sys/class/uio/{uio_name}/maps/map{map_index}/size"
    size = int(open(size_path, encoding="ascii").read(), 16)
    page_size = os.sysconf("SC_PAGE_SIZE")
    fd = os.open(path, os.O_RDWR | os.O_SYNC)

    try:
        mm = mmap.mmap(
            fd,
            size,
            mmap.MAP_SHARED,
            mmap.PROT_READ | mmap.PROT_WRITE,
            offset=page_size * map_index,
        )

        offset = requested_offset
        if offset < 0:
            offset = mm.find(MAGIC)
        print("canb_offset=%s" % ("not-found" if offset < 0 else hex(offset)))
        if offset < 0:
            return

        for index in range(8):
            data = mm[offset : offset + 128]
            words = struct.unpack("<32I", data)
            print(
                "iter=%d magic=0x%08x version=%d size=%d flags=0x%08x "
                "rt_hb=%d linux_hb=%d rt_cmd_seq=%d linux_fb_seq=%d"
                % ((index,) + words[:8])
            )
            print(data[:64].hex(" "))
            time.sleep(0.2)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
