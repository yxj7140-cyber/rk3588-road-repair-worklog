#!/usr/bin/env python3
"""Read selected files from an ext4 partition without mounting it.

This is a tiny read-only helper for Windows-side TF-card triage. It implements
just enough ext4 parsing for the RK3588 rootfs: superblock, group descriptors,
extent-backed files, and directory entries.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


EXT4_SUPER_MAGIC = 0xEF53
EXT4_EXTENTS_MAGIC = 0xF30A
ROOT_INODE = 2


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


@dataclass(frozen=True)
class Inode:
    ino: int
    mode: int
    size: int
    flags: int
    block: bytes

    @property
    def is_dir(self) -> bool:
        return (self.mode & 0xF000) == 0x4000

    @property
    def is_regular(self) -> bool:
        return (self.mode & 0xF000) == 0x8000

    @property
    def is_symlink(self) -> bool:
        return (self.mode & 0xF000) == 0xA000


class Ext4Reader:
    def __init__(self, image_path: str):
        self.image_path = image_path
        self.fp = open(image_path, "rb")
        self.fp.seek(1024)
        self.sb = self.fp.read(1024)
        if u16(self.sb, 0x38) != EXT4_SUPER_MAGIC:
            raise ValueError(f"not an ext4 filesystem: magic=0x{u16(self.sb, 0x38):04x}")

        self.inodes_count = u32(self.sb, 0x00)
        self.blocks_count = u32(self.sb, 0x04)
        self.first_data_block = u32(self.sb, 0x14)
        self.block_size = 1024 << u32(self.sb, 0x18)
        self.blocks_per_group = u32(self.sb, 0x20)
        self.inodes_per_group = u32(self.sb, 0x28)
        self.inode_size = u16(self.sb, 0x58) or 128
        self.feature_incompat = u32(self.sb, 0x60)
        self.desc_size = u16(self.sb, 0xFE) if (self.feature_incompat & 0x80) else 32
        if self.desc_size < 32:
            self.desc_size = 32
        self.groups_count = (self.blocks_count + self.blocks_per_group - 1) // self.blocks_per_group
        self.gdt_offset = 2 * self.block_size if self.block_size == 1024 else self.block_size

    def close(self) -> None:
        self.fp.close()

    def read_at(self, offset: int, length: int) -> bytes:
        # Windows raw device handles require sector-aligned reads. Align here so
        # callers can still request inode-sized slices safely.
        sector = 512
        aligned_offset = (offset // sector) * sector
        prefix = offset - aligned_offset
        aligned_length = ((prefix + length + sector - 1) // sector) * sector
        self.fp.seek(aligned_offset)
        data = self.fp.read(aligned_length)
        return data[prefix : prefix + length]

    def read_block(self, block_no: int, count: int = 1) -> bytes:
        return self.read_at(block_no * self.block_size, count * self.block_size)

    def group_desc(self, group: int) -> bytes:
        return self.read_at(self.gdt_offset + group * self.desc_size, self.desc_size)

    def inode_table_block(self, group: int) -> int:
        gd = self.group_desc(group)
        lo = u32(gd, 0x08)
        hi = u32(gd, 0x28) if len(gd) >= 0x2C else 0
        return (hi << 32) | lo

    def read_inode(self, ino: int) -> Inode:
        if ino <= 0 or ino > self.inodes_count:
            raise FileNotFoundError(f"invalid inode {ino}")
        group = (ino - 1) // self.inodes_per_group
        index = (ino - 1) % self.inodes_per_group
        table = self.inode_table_block(group)
        raw = self.read_at(table * self.block_size + index * self.inode_size, self.inode_size)
        mode = u16(raw, 0x00)
        size_lo = u32(raw, 0x04)
        size_hi = u32(raw, 0x6C) if len(raw) >= 0x70 else 0
        size = size_lo | (size_hi << 32)
        flags = u32(raw, 0x20)
        return Inode(ino=ino, mode=mode, size=size, flags=flags, block=raw[0x28 : 0x28 + 60])

    def extent_blocks(self, inode: Inode) -> list[tuple[int, int, int]]:
        """Return (logical_block, physical_block, block_count)."""

        def parse_node(block_data: bytes) -> list[tuple[int, int, int]]:
            magic = u16(block_data, 0)
            if magic != EXT4_EXTENTS_MAGIC:
                raise ValueError(f"inode {inode.ino} does not use extents magic=0x{magic:04x}")
            entries = u16(block_data, 2)
            depth = u16(block_data, 6)
            result: list[tuple[int, int, int]] = []
            base = 12
            if depth == 0:
                for i in range(entries):
                    off = base + i * 12
                    logical = u32(block_data, off)
                    length = u16(block_data, off + 4) & 0x7FFF
                    start_hi = u16(block_data, off + 6)
                    start_lo = u32(block_data, off + 8)
                    physical = (start_hi << 32) | start_lo
                    result.append((logical, physical, length))
            else:
                for i in range(entries):
                    off = base + i * 12
                    index_logical = u32(block_data, off)
                    leaf_lo = u32(block_data, off + 4)
                    leaf_hi = u16(block_data, off + 8)
                    leaf = (leaf_hi << 32) | leaf_lo
                    child = self.read_block(leaf)
                    for logical, physical, length in parse_node(child):
                        result.append((logical, physical, length))
            return result

        return sorted(parse_node(inode.block), key=lambda item: item[0])

    def read_file_inode(self, inode: Inode, max_bytes: int | None = None) -> bytes:
        if inode.is_symlink and inode.size <= 60:
            data = inode.block[: inode.size]
            return data[:max_bytes] if max_bytes is not None else data

        wanted = inode.size if max_bytes is None else min(inode.size, max_bytes)
        chunks = bytearray()
        for logical, physical, length in self.extent_blocks(inode):
            if len(chunks) >= wanted:
                break
            # Sparse holes are uncommon in config files, but preserve them if seen.
            expected_len = logical * self.block_size
            if len(chunks) < expected_len:
                chunks.extend(b"\0" * (expected_len - len(chunks)))
            data = self.read_block(physical, length)
            chunks.extend(data)
        return bytes(chunks[:wanted])

    def list_dir_inode(self, inode: Inode) -> list[dict[str, object]]:
        if not inode.is_dir:
            raise NotADirectoryError(f"inode {inode.ino} is not a directory")
        data = self.read_file_inode(inode)
        entries: list[dict[str, object]] = []
        pos = 0
        while pos + 8 <= len(data):
            child_ino = u32(data, pos)
            rec_len = u16(data, pos + 4)
            name_len = data[pos + 6]
            file_type = data[pos + 7]
            if rec_len < 8:
                break
            name = data[pos + 8 : pos + 8 + name_len].decode("utf-8", "replace")
            if child_ino and name not in {".", ".."}:
                entries.append(
                    {
                        "name": name,
                        "inode": child_ino,
                        "file_type": file_type,
                        "rec_len": rec_len,
                    }
                )
            pos += rec_len
        return entries

    def resolve(self, path: str) -> Inode:
        current = self.read_inode(ROOT_INODE)
        clean_parts = [part for part in path.strip("/").split("/") if part]
        if not clean_parts:
            return current
        for part in clean_parts:
            if not current.is_dir:
                raise FileNotFoundError(path)
            entries = self.list_dir_inode(current)
            match = next((entry for entry in entries if entry["name"] == part), None)
            if match is None:
                raise FileNotFoundError(path)
            current = self.read_inode(int(match["inode"]))
        return current

    def read_path(self, path: str, max_bytes: int | None = None) -> bytes:
        inode = self.resolve(path)
        if inode.is_dir:
            listing = self.list_dir_inode(inode)
            return json.dumps(listing, ensure_ascii=False, indent=2).encode("utf-8")
        return self.read_file_inode(inode, max_bytes=max_bytes)

    def info(self) -> dict[str, object]:
        volume = self.sb[0x78:0x88].split(b"\0", 1)[0].decode("utf-8", "replace")
        last_mounted = self.sb[0x88:0xC8].split(b"\0", 1)[0].decode("utf-8", "replace")
        return {
            "image_path": self.image_path,
            "volume": volume,
            "last_mounted": last_mounted,
            "inodes_count": self.inodes_count,
            "blocks_count": self.blocks_count,
            "block_size": self.block_size,
            "blocks_per_group": self.blocks_per_group,
            "inodes_per_group": self.inodes_per_group,
            "inode_size": self.inode_size,
            "desc_size": self.desc_size,
            "groups_count": self.groups_count,
        }


DEFAULT_PATHS = [
    "/etc/os-release",
    "/etc/hostname",
    "/etc/hosts",
    "/etc/fstab",
    "/etc/NetworkManager",
    "/etc/NetworkManager/NetworkManager.conf",
    "/etc/NetworkManager/system-connections",
    "/etc/netplan",
    "/etc/systemd/network",
    "/etc/hostapd",
    "/etc/dnsmasq.conf",
    "/etc/systemd/system",
    "/home/rock",
]


def safe_name(path: str) -> str:
    return path.strip("/").replace("/", "__") or "root"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read selected files from an ext4 rootfs partition.")
    parser.add_argument("--device", default=r"\\.\Harddisk2Partition2")
    parser.add_argument("--out-dir", default=r"E:\BaiduNetdiskDownload\rt\tmp\tf_card_rootfs_dumps")
    parser.add_argument("--path", action="append", dest="paths", help="Path inside rootfs; repeatable.")
    parser.add_argument("--max-bytes", type=int, default=512 * 1024)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reader = Ext4Reader(args.device)
    try:
        info = reader.info()
        print(json.dumps(info, ensure_ascii=False, indent=2))
        (out_dir / "rootfs_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

        paths = args.paths or DEFAULT_PATHS
        summary: list[dict[str, object]] = []
        for path in paths:
            item: dict[str, object] = {"path": path}
            try:
                inode = reader.resolve(path)
                item.update({"inode": inode.ino, "mode": oct(inode.mode), "size": inode.size})
                data = reader.read_path(path, max_bytes=args.max_bytes)
                suffix = ".json" if inode.is_dir else ".txt"
                out_path = out_dir / f"{safe_name(path)}{suffix}"
                if suffix == ".txt":
                    out_path.write_text(data.decode("utf-8", "replace"), encoding="utf-8")
                else:
                    out_path.write_bytes(data)
                item["dump"] = str(out_path)
                print(f"OK {path} -> {out_path}")
            except Exception as exc:  # noqa: BLE001 - diagnostic tool
                item["error"] = f"{type(exc).__name__}: {exc}"
                print(f"MISS {path}: {item['error']}")
            summary.append(item)

        (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        reader.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
