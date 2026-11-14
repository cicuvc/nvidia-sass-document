#!/usr/bin/env python3
"""Patch representative TABLES_opex_2 instructions and show nvdisasm's view."""

from __future__ import annotations

import json
import re
import struct
import subprocess
import tempfile
from pathlib import Path


SOURCE = Path(__file__).with_name("probe.cu")
TABLE_DB = Path(__file__).resolve().parents[2] / "sm90.json"


def first_instruction(cubin: Path, mnemonic: str) -> tuple[int, int]:
    text = subprocess.check_output(["cuobjdump", "-sass", str(cubin)], text=True)
    match = re.search(
        rf"\b{mnemonic}\b[\s\S]*?/\*\s*(0x[0-9a-fA-F]+)\s*\*/\s*"
        r"\n\s*/\*\s*(0x[0-9a-fA-F]+)\s*\*/",
        text,
    )
    if not match:
        raise RuntimeError(f"no {mnemonic} found in {cubin}")
    return int(match.group(1), 16), int(match.group(2), 16)


def patch_opex(hi: int, high3: int, usched: int) -> int:
    hi &= ~(((1 << 3) - 1) << 58)
    hi &= ~(((1 << 5) - 1) << 41)
    hi |= (high3 & 0x7) << 58
    hi |= (usched & 0x1F) << 41
    return hi


def load_opex2_table() -> dict[tuple[int, int, int], int]:
    table = json.loads(TABLE_DB.read_text())["tables"]["TABLES_opex_2"]
    rows = {
        tuple(map(int, row["in"])): int(row["out"])
        for row in table["rows"]
    }
    assert len(rows) == 113
    for (batch, usched, reuse), opex in rows.items():
        expected = (usched | 0x20) if reuse else ((batch << 5) | usched)
        assert opex == expected, ((batch, usched, reuse), opex, expected)
    return rows


def main() -> None:
    table = load_opex2_table()
    samples = [
        ("IADD32I", r"IADD3"),
        ("FADD32I", r"FADD"),
        ("LOP32I", r"LOP3\.LUT"),
    ]
    cases = [
        # name, batch_t, usched_info, reuse_src_a
        ("baseline", 0, 10, 0),
        ("batch_start + W1EG", 1, 1, 0),
        ("batch_start_tile + W1EG", 2, 1, 0),
        ("unnamed batch_t=3 + W1EG", 3, 1, 0),
        ("batch_end + W1EG", 4, 1, 0),
        ("barrier_exempt + W11EG", 5, 11, 0),
        ("reuse_src_a + trans1", 0, 17, 1),
        ("reuse_src_a + trans11", 0, 27, 1),
        ("reuse_src_a + W1EG", 0, 1, 1),
        ("batch_start + trans1", 1, 17, 0),
    ]

    with tempfile.TemporaryDirectory(prefix="opex2-sm90-") as td:
        cubin = Path(td) / "probe.cubin"
        subprocess.run(
            ["nvcc", "-arch=sm_90", "-cubin", "-o", str(cubin), str(SOURCE)],
            check=True,
        )
        raw = Path(td) / "one.sm90.bin"
        for sample, mnemonic in samples:
            lo, base_hi = first_instruction(cubin, mnemonic)
            for name, batch, usched, reuse in cases:
                legal = (batch, usched, reuse) in table
                # batch_t[0] and reuse_src_a are physically the same bit, bit 122.
                high3 = batch | reuse
                hi = patch_opex(base_hi, high3, usched)
                raw.write_bytes(struct.pack("<QQ", lo, hi))
                dis = subprocess.check_output(
                    [
                        "nvdisasm",
                        "--binary",
                        "SM90",
                        "--print-instruction-encoding",
                        str(raw),
                    ],
                    text=True,
                )
                instruction = next(
                    line.strip()
                    for line in dis.splitlines()
                    if re.search(rf"\b{mnemonic}\b", line)
                )
                opex = (high3 << 5) | usched
                print(
                    f"{sample:7} {name:28} tuple=({batch},{usched},{reuse}) "
                    f"legal={str(legal):5} opex=0x{opex:02x} "
                    f"hi=0x{hi:016x} | {instruction}"
                )


if __name__ == "__main__":
    main()
