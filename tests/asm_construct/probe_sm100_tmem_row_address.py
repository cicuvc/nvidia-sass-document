#!/usr/bin/env python3
"""Probe the row field of B200 TMEM addresses used by LDTM/STTM.

Each requested row is run in a fresh subprocess because a deliberately
misaligned TMEM address raises CUDA 716 and poisons that CUDA context.  The
instruction schedule is kept deliberately close to the already validated
TMEM layout-tomography probe.
"""

from __future__ import annotations

import argparse
import os
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble_kernel  # noqa: E402


DEFAULT_ROWS = (0, 1, 15, 16, 17, 31, 32, 33, 47, 48, 49, 63,
                64, 65, 79, 80, 81, 95, 96, 97, 111, 112, 113, 127)
LAYOUTS = {
    # name: (modifier, repeat count, register count, active lane range)
    "32": ("", 2, 2, range(32)),
    "half0": (".16dp32bit_t0_t15", 2, 2, range(16)),
    "half16": (".16dp32bit_t16_t31", 2, 2, range(16, 32)),
    # These layouts have 16 TMEM datapaths, but both halves of the warp carry
    # register payload.  Same-layout STTM/LDTM therefore restores all lanes.
    "64": (".16dp64bit", 2, 2, range(32)),
    "128": (".16dp128bit", 1, 2, range(32)),
    "256": (".16dp256bit", 1, 4, range(32)),
}


def _group(lo: int, count: int) -> str:
    return "{" + ",".join(f"R{i}" for i in range(lo, lo + count)) + "}"


def isolation_source(layout: str, second_row: int) -> str:
    """Store distinct tags at two adjacent legal row bands, then reload both."""
    modifier, repeat, nregs, _ = LAYOUTS[layout]
    if second_row == 0:
        second_row = 32 if layout == "32" else 16
    suffix = "" if repeat == 1 else f".x{repeat}"
    name = f"tmemrow_{layout}_{second_row}"
    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(80)",
        "    #pragma SHARED(0x800)",
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:2:0]",
        "    SHL R12, R4, 0x10;[7:7:{1}:5:1]",
        "    S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]",
        "    UMOV UR4, 0x400;[7:7:{}:1:0]",
        "    ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]",
        "    #!tmem_alloc_1cta(UR5, 32)",
        "    LDS R10, [UR5];[0:7:{}:1:0]",
        "    R2UR UR10, R10;[7:7:{0}:13:1]",
        f"    IADD3 R11, R10, {second_row << 16:#x}, RZ;"
        "[7:7:{0}:5:1]",
        "    R2UR UR11, R11;[7:7:{}:13:1]",
    ]
    for bank, ur in ((0x81000000, 10), (0x82000000, 11)):
        for reg in range(nregs):
            lines += [
                f"    IADD3 R{20 + reg}, R12, {bank | reg:#x}, RZ;"
                "[7:7:{}:5:1]"
            ]
        lines += [
            "    NOP;[7:7:{}:8:1]",
            f"    STTM{modifier}{suffix} tmem[UR{ur}], "
            f"{_group(20, nregs)};[7:7:{{}}:1:0]",
            "    FENCE.VIEW.ASYNC.T;[0:7:{}:2:0]",
            "    NOP;[7:7:{0}:1:0]",
        ]
    for reg in range(2 * nregs):
        lines += [f"    MOV32I R{40 + reg}, 0xfeed0000;[7:7:{{}}:5:1]"]
    lines += [
        f"    LDTM{modifier}{suffix} {_group(40, nregs)}, tmem[UR10];"
        "[1:7:{}:1:0]",
        f"    LDTM{modifier}{suffix} {_group(40 + nregs, nregs)}, "
        "tmem[UR11];[2:7:{}:1:0]",
        "    NOP;[7:7:{1,2}:1:0]",
        f"    IMAD.WIDE.U32 {{R8,R9}}, R4, {2 * nregs * 4:#x}, "
        "{R2,R3};[7:7:{0}:5:1]",
    ]
    for i in range(0, 2 * nregs, 2):
        lines += [
            f"    STG.E.64.STRONG.GPU [{{R8,R9}}+{i * 4:#x}], "
            f"{{R{40 + i},R{41 + i}}};[7:0:{{}}:1:0]"
        ]
    lines += [
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    #!tmem_dealloc_1cta(UR5, 32)",
        "    #!tmem_relinquish_alloc_permit_1cta()",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def source(row: int, layout: str, operation: str = "roundtrip") -> str:
    if operation == "isolation":
        return isolation_source(layout, row)
    modifier, repeat, nregs, _ = LAYOUTS[layout]
    addr = (row & 0x7f) << 16
    name = f"tmemrow_{layout}_{row}"
    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(80)",
        "    #pragma SHARED(0x800)",
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:2:0]",
        "    SHL R12, R4, 0x10;[7:7:{1}:5:1]",
        "    S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]",
        "    UMOV UR4, 0x400;[7:7:{}:1:0]",
        "    ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]",
        "    #!tmem_alloc_1cta(UR5, 32)",
        "    LDS R10, [UR5];[0:7:{}:1:0]",
    ]
    if addr:
        lines += [
            f"    IADD3 R10, R10, {addr:#x}, RZ;[7:7:{{0}}:5:1]",
            "    R2UR UR10, R10;[7:7:{}:13:1]",
        ]
    else:
        lines += ["    R2UR UR10, R10;[7:7:{0}:13:1]"]

    # Many independent writes intentionally provide the same source-settling
    # interval as probe_sm100_tmem_layout_tomography.py.
    for i in range(16):
        tag = 0x80000000 | ((row & 0x7f) << 8) | i
        lines += [
            f"    IADD3 R{20 + i}, R12, {tag:#x}, RZ;[7:7:{{}}:5:1]"
        ]
    for i in range(16):
        lines += [f"    MOV32I R{40 + i}, 0xfeed0000;[7:7:{{}}:5:1]"]

    suffix = "" if repeat == 1 else f".x{repeat}"
    if operation in ("roundtrip", "store"):
        lines += [
            f"    STTM{modifier}{suffix} tmem[UR10], {_group(20, nregs)};"
            "[7:7:{}:1:0]",
            "    FENCE.VIEW.ASYNC.T;[0:7:{}:2:0]",
            "    NOP;[7:7:{0}:1:0]",
        ]
    if operation in ("roundtrip", "load"):
        lines += [
            f"    LDTM{modifier}{suffix} {_group(40, nregs)}, tmem[UR10];"
            "[1:7:{}:1:0]",
            "    NOP;[7:7:{1}:1:0]",
        ]
    if operation == "roundtrip":
        lines += [
            f"    IMAD.WIDE.U32 {{R8,R9}}, R4, {nregs * 4:#x}, "
            "{R2,R3};[7:7:{0}:5:1]",
        ]
        for i in range(0, nregs, 2):
            lines += [
                f"    STG.E.64.STRONG.GPU [{{R8,R9}}+{i * 4:#x}], "
                f"{{R{40 + i},R{41 + i}}};[7:{i // 2}:{{1}}:1:0]"
            ]
        lines += [f"    NOP;[7:7:{{{(nregs // 2) - 1}}}:1:0]"]
    lines += [
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    #!tmem_dealloc_1cta(UR5, 32)",
        "    #!tmem_relinquish_alloc_permit_1cta()",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def expected(row: int, layout: str, lane: int, reg: int) -> int:
    if lane not in LAYOUTS[layout][3]:
        return 0xFEED0000
    return 0x80000000 | (lane << 16) | ((row & 0x7f) << 8) | reg


def worker(row: int, layout: str, operation: str) -> int:
    name = f"tmemrow_{layout}_{row}"
    result = assemble_kernel(source(row, layout, operation), arch="sm100a",
                             check_deps=False)
    mod = CudaModule(result.code)
    nregs = LAYOUTS[layout][2]
    size = 32 * nregs * (2 if operation == "isolation" else 1) * 4
    out = mod.devmem_alloc(size)
    try:
        mod.launch(name, grid=(1,), block=(32,), args=[out])
        mod.synchronize()
        nwords = size // 4
        words = (struct.unpack(f"<{nwords}I", mod.device_read(out, size))
                 if operation in ("roundtrip", "isolation") else ())
    finally:
        mod.devmem_free(out)
    if operation not in ("roundtrip", "isolation"):
        print(f"row={row:3d} PASS_{operation.upper()}")
        return 0
    bad = []
    copies = 2 if operation == "isolation" else 1
    for lane in range(32):
        for reg in range(nregs * copies):
            got = words[nregs * copies * lane + reg]
            if operation == "isolation":
                copy, src_reg = divmod(reg, nregs)
                want = (0xFEED0000 if lane not in LAYOUTS[layout][3] else
                        (0x81000000 + copy * 0x01000000) |
                        (lane << 16) | src_reg)
            else:
                want = expected(row, layout, lane, reg)
            if got != want:
                bad.append((lane, reg, got, want))
    sample = ",".join(f"{value:08x}" for value in words[:8])
    if bad:
        if operation == "isolation":
            alias = True
            for lane in range(32):
                for copy in range(2):
                    for src_reg in range(nregs):
                        got = words[2 * nregs * lane + copy * nregs + src_reg]
                        want = (0xFEED0000
                                if lane not in LAYOUTS[layout][3] else
                                0x82000000 | (lane << 16) | src_reg)
                        alias &= got == want
            if alias:
                print(f"row={row:3d} ALIAS_ROW0 sample={sample}")
                return 0
        detail = " ".join(
            f"l{lane}r{reg}:{got:08x}!={want:08x}"
            for lane, reg, got, want in bad[:6])
        print(f"row={row:3d} DATA_FAIL nbad={len(bad)} sample={sample} {detail}")
        return 2
    print(f"row={row:3d} PASS sample={sample}")
    return 0


def orchestrate(rows: tuple[int, ...], layout: str, operation: str) -> int:
    path = Path(__file__).resolve()
    print(f"layout={layout} operation={operation} "
          f"rows={','.join(map(str, rows))}")
    for row in rows:
        proc = subprocess.run(
            [sys.executable, str(path), "--worker-row", str(row),
             "--layout", layout, "--operation", operation],
            text=True, capture_output=True,
            env=os.environ)
        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode == 0:
            print(output)
        elif "716" in output or "MISALIGNED" in output.upper():
            print(f"row={row:3d} FAULT_MISALIGNED")
        else:
            tail = output.replace("\n", " | ")[-500:]
            print(f"row={row:3d} ERROR rc={proc.returncode} {tail}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", choices=tuple(LAYOUTS), default="half0")
    parser.add_argument("--operation",
                        choices=("roundtrip", "store", "load", "isolation"),
                        default="roundtrip")
    parser.add_argument("--rows", default=",".join(map(str, DEFAULT_ROWS)))
    parser.add_argument("--worker-row", type=int)
    ns = parser.parse_args()
    rows = tuple(int(value, 0) for value in ns.rows.split(","))
    if any(row < 0 or row > 127 for row in rows):
        parser.error("rows must be in 0..127")
    if ns.worker_row is not None:
        return worker(ns.worker_row, ns.layout, ns.operation)
    return orchestrate(rows, ns.layout, ns.operation)


if __name__ == "__main__":
    raise SystemExit(main())
