#!/usr/bin/env python3
"""Print nonzero batch/reuse interpretation for a raw 16-byte SASS stream."""

from __future__ import annotations

import argparse
import pathlib
import re
import struct
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw", type=pathlib.Path)
    parser.add_argument("--arch", default="SM75")
    args = parser.parse_args()

    raw = args.raw.read_bytes()
    text = subprocess.check_output(
        ["nvdisasm", "--binary", args.arch, str(args.raw)],
        text=True,
    )
    lines = [
        line.strip() for line in text.splitlines()
        if re.match(r"\s*/\*[0-9a-f]{4}\*/", line)
    ]
    counts: dict[int, int] = {}
    for index in range(len(raw) // 16):
        _, hi = struct.unpack_from("<QQ", raw, index * 16)
        high3 = (hi >> 58) & 7
        usched = (hi >> 41) & 0x1F
        counts[high3] = counts.get(high3, 0) + 1
        if high3 == 0 and ".reuse" not in lines[index]:
            continue
        kind = "reuse" if ".reuse" in lines[index] else "batch_t"
        print(
            f"{index * 16:04x} {kind:7} value={high3:03b} "
            f"stall={usched & 15} yield={0 if usched >= 16 else 1} "
            f"hi=0x{hi:016x}  {lines[index].split(';')[0]}"
        )
    print("high3 counts:", counts)


if __name__ == "__main__":
    main()
