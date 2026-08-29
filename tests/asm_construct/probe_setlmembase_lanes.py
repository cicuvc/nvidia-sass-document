"""Probe SETLMEMBASE with a different valid 64-bit operand in every lane.

Each lane supplies ``arena + slot(lane) * 1 MiB`` to one converged
SETLMEMBASE.  The kernel records GETLMEMBASE immediately and after a chosen
delay, performs one STL/LDL at SR_LMEMHIOFF, restores the driver base, and the
host scans every candidate arena slot.  This distinguishes a warp-selected
base from genuinely per-lane bases and exposes transient lane-split state.

This is an exploratory probe, not part of tools/run_tests.py.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


WARP = 32
SLOT_STRIDE = 0x100000
ARENA_SIZE = WARP * SLOT_STRIDE
RECORD_SIZE = 0x20
MAGIC = 0xD17E0000


def make_source(delay_nops: int, reverse: bool = False, active_lo: int = 0) -> str:
    delay = "\n".join("    NOP;[7:7:{}:8:0]" for _ in range(delay_nops))
    slot = "IADD3 R8, -R8, 0x1f, RZ;[7:7:{}:5:1]" if reverse else ""
    return f"""#fn set_lanes(out<8>, arena<8>) {{
    #pragma MAXREG_COUNT(64)
    LDC.64 {{R30,R31}}, #param(out);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(arena);[1:7:{{}}:1:0]
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[2:7:{{}}:2:0]
    S2R R8, SR_LANEID;[3:7:{{}}:5:1]
    S2R R14, SR_LMEMHIOFF;[4:7:{{}}:5:1]
    GETLMEMBASE {{R18,R19}};[5:7:{{}}:5:1]

    IMAD.WIDE.U32 {{R28,R29}}, R8, 0x{RECORD_SIZE:x}, {{R30,R31}};[7:7:{{0,3}}:5:1]
    IADD3 R9, R8, RZ, RZ;[7:7:{{}}:5:1]
    {slot}
    IMAD.WIDE.U32 {{R6,R7}}, R8, 0x{SLOT_STRIDE:x}, {{R4,R5}};[7:7:{{1}}:5:1]
    ISETP.GE.U32.AND P0, PT, R9, {active_lo}, PT;[7:7:{{}}:13:1]
    @P0 SETLMEMBASE {{R6,R7}};[7:7:{{}}:5:1]
    GETLMEMBASE {{R20,R21}};[0:7:{{}}:5:1]
{delay}
    GETLMEMBASE {{R22,R23}};[1:7:{{}}:5:1]

    MOV32I R24, 0x{MAGIC:08x};[7:7:{{}}:5:1]
    IADD3 R24, R24, R9, RZ;[7:7:{{}}:5:1]
    STL [R14], R24;[7:7:{{4}}:8:0]
    CCTLL.WB [R14];[7:7:{{}}:5:1]
    MEMBAR.ALL.SYS;[7:7:{{}}:5:1]
    LDL R25, [R14];[3:7:{{}}:8:0]
    IADD3 R26, R25, RZ, RZ;[7:7:{{3}}:5:1]

    SETLMEMBASE {{R18,R19}};[7:7:{{5}}:5:1]
    STG.E.64 desc[{{UR4,UR5}}][{{R28,R29}}+0x00], {{R6,R7}};[7:7:{{2}}:1:0]
    STG.E.64 desc[{{UR4,UR5}}][{{R28,R29}}+0x08], {{R20,R21}};[7:7:{{0}}:1:0]
    STG.E.64 desc[{{UR4,UR5}}][{{R28,R29}}+0x10], {{R22,R23}};[7:7:{{1}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R28,R29}}+0x18], R26;[7:7:{{}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R28,R29}}+0x1c], R24;[7:7:{{}}:1:0]
    EXIT;[7:7:{{0,1,2,3,4,5}}:5:0]
}}
"""


def u64(words, i):
    return words[i] | (words[i + 1] << 32)


def run_once(delay_nops: int, reverse: bool = False, active_lo: int = 0):
    mod = CudaModule(assemble(make_source(delay_nops, reverse, active_lo)))
    out = mod.devmem_alloc(WARP * RECORD_SIZE)
    arena = mod.devmem_alloc(ARENA_SIZE)
    mod.device_write(out, bytes(WARP * RECORD_SIZE))
    mod.device_write(arena, bytes(ARENA_SIZE))
    try:
        mod.launch("set_lanes", grid=(1,), block=(WARP,), args=[out, arena])
        mod.synchronize()
        words = struct.unpack(
            f"<{WARP * RECORD_SIZE // 4}I",
            mod.device_read(out, WARP * RECORD_SIZE),
        )
        records = [
            words[i * RECORD_SIZE // 4:(i + 1) * RECORD_SIZE // 4]
            for i in range(WARP)
        ]
        slots = [
            struct.unpack(f"<{WARP}I", mod.device_read(arena + i * SLOT_STRIDE, WARP * 4))
            for i in range(WARP)
        ]
    finally:
        mod.devmem_free(out)
        mod.devmem_free(arena)
    return arena, records, slots


def summarize(delay_nops: int, reverse: bool, active_lo: int = 0, trials: int = 5):
    tag = "reverse" if reverse else "forward"
    for trial in range(trials):
        arena, records, slots = run_once(delay_nops, reverse, active_lo)
        get0 = [u64(r, 2) for r in records]
        get1 = [u64(r, 4) for r in records]
        intended = [u64(r, 0) for r in records]
        nonzero = {
            slot: [(lane, value) for lane, value in enumerate(values) if value]
            for slot, values in enumerate(slots)
            if any(values)
        }
        get0_slots = [int((v - arena) // SLOT_STRIDE) for v in get0]
        get1_slots = [int((v - arena) // SLOT_STRIDE) for v in get1]
        written_slots = sorted(nonzero)
        print(
            f"delay={delay_nops:2d} {tag:7s} active={active_lo:2d} "
            f"trial={trial}: GET0={sorted(set(get0_slots))} "
            f"GET1={sorted(set(get1_slots))} backing={written_slots} "
            f"LDL={sum(r[6] == r[7] for r in records)}/32"
        )
        if len(set(get0)) != 1 or len(set(get1)) != 1 or len(nonzero) != 1:
            print("  intended slots:", [int((v - arena) // SLOT_STRIDE) for v in intended])
            print("  GET0 slots:    ", get0_slots)
            print("  GET1 slots:    ", get1_slots)
            print("  backing writes:", nonzero)


def main():
    for delay in (0, 1, 4, 16, 64):
        summarize(delay, False, trials=3)
        summarize(delay, True, trials=3)
    for active_lo in (1, 7, 16, 31):
        summarize(0, False, active_lo)
        summarize(0, True, active_lo)


if __name__ == "__main__":
    main()
