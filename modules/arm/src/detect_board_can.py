#!/usr/bin/env python3
"""Detect the SocketCAN interface to use for the Piper arm on RK3588 Linux."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


DEFAULT_STATE_PATH = Path(__file__).with_name("piper_can_interface.env")


def run_text(args: list[str]) -> str:
    return subprocess.run(args, check=False, text=True, capture_output=True).stdout


def list_can_interfaces() -> list[str]:
    text = run_text(["ip", "-o", "link", "show", "type", "can"])
    names: list[str] = []
    for line in text.splitlines():
        parts = line.split(":", 2)
        if len(parts) >= 2:
            names.append(parts[1].strip().split("@", 1)[0])
    return names


def choose_can(candidates: list[str], prefer: str | None, allow_can0: bool) -> str:
    if prefer and prefer in candidates:
        return prefer
    if len(candidates) == 1:
        return candidates[0]
    if "can1" in candidates:
        return "can1"
    if allow_can0 and "can0" in candidates:
        return "can0"
    raise SystemExit(
        "Could not choose Piper CAN interface. "
        f"candidates={candidates!r}, prefer={prefer!r}, allow_can0={allow_can0}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect Piper SocketCAN channel.")
    parser.add_argument("--prefer", default="can1")
    parser.add_argument("--allow-can0", action="store_true")
    parser.add_argument("--bitrate", type=int, default=1_000_000)
    parser.add_argument("--env-file", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    candidates = list_can_interfaces()
    channel = choose_can(candidates, args.prefer, args.allow_can0)
    result = {
        "channel": channel,
        "bitrate": int(args.bitrate),
        "candidates": candidates,
        "env_file": args.env_file,
    }

    env_path = Path(args.env_file)
    env_path.write_text(
        f"PIPER_CAN={channel}\nPIPER_CAN_BITRATE={int(args.bitrate)}\n",
        encoding="utf-8",
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(channel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

