#!/usr/bin/env python3
"""Decoder for QSPC (query address-space predicate = PTX isspacep) on sm_90.

128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).
Two opcode families:
  0x3aa  (bit[91]=0) — GPR base:      QSPC[.E].<SP> Pu, Rd, [Ra+off]
  0x19aa (bit[91]=1) — URB base:      QSPC[.E].<SP> Pu, Rd, [Ra.U32|.64+URb+off]

ptxas emits only the full form (Pu + Rd=RZ) with .E; the noe/32-bit, PuOnly,
RdOnly and Ra32/Ra64 URB forms exist in the spec and are decoded here too.
Validated against real cuobjdump captures (sm_90, CUDA 12.8) and against
nvdisasm output for assembler-produced sm_120 cubins.
"""
import sys


def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)


SPACE = {0: "G", 1: "L", 2: "S", 3: "D"}


def reg(n):
    return "RZ" if n == 0xff else f"R{n}"


def ureg(n):
    return "URZ" if n == 0x3f else f"UR{n}"


def pred(n):
    return "PT" if n == 7 else f"P{n}"


def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    if opcode == 0x3aa:
        urb = False
    elif opcode == 0x19aa:
        urb = True
    else:
        raise ValueError(f"not QSPC: opcode {opcode:#x}")

    Pg     = bits(w, 14, 12)
    Pg_not = bits(w, 15, 15)
    Rd     = bits(w, 23, 16)
    Ra     = bits(w, 31, 24)
    off    = bits(w, 63, 40)
    e      = bits(w, 72, 72)
    space  = bits(w, 74, 73)
    Pu     = bits(w, 83, 81)

    guard = ""
    if Pg != 7 or Pg_not:
        guard = f"@{'!' if Pg_not else ''}P{Pg} "

    s = f"{guard}QSPC{'.E' if e else ''}.{SPACE[space]} {pred(Pu)}, {reg(Rd)}, "

    if not urb:
        addr = f"[{reg(Ra)}"
    else:
        URb = bits(w, 39, 32)
        if bits(w, 90, 90):
            tag = "64"          # Ra64: GPR pair + UR pair
        else:
            tag = "U32"         # Ra32 / RaRZ: 32-bit GPR part
        addr = f"[{reg(Ra)}.{tag}+{ureg(URb)}"
    if off:
        addr += f"+0x{off:X}"
    addr += "]"
    return s + addr


# (lo64, hi64, expected cuobjdump-style disassembly)
VEC = [
    # --- real ptxas output, sm_90 CUDA 12.8 (tests/qspc_test.cu) ---
    (0x00000004ffff79aa, 0x000e220008000100, "QSPC.E.G P0, RZ, [RZ.U32+UR4]"),
    (0x00000004ffff79aa, 0x000e220008020500, "QSPC.E.S P1, RZ, [RZ.U32+UR4]"),
    (0x00000004ffff79aa, 0x000e620008000300, "QSPC.E.L P0, RZ, [RZ.U32+UR4]"),
    (0x00000004ffff79aa, 0x000e620008000500, "QSPC.E.S P0, RZ, [RZ.U32+UR4]"),
    (0x00000004ffff79aa, 0x000e620008000700, "QSPC.E.D P0, RZ, [RZ.U32+UR4]"),
    (0x00000008ffff79aa, 0x000e680008000100, "QSPC.E.G P0, RZ, [RZ.U32+UR8]"),
    (0x0000000006ff73aa, 0x000e640000000100, "QSPC.E.G P0, RZ, [R6]"),
    (0x0000000006ff73aa, 0x000e640000000500, "QSPC.E.S P0, RZ, [R6]"),
    # --- assembler round-trips, verified via nvdisasm (sm_120 cubin) ---
    (0x00000004040079aa, 0x000e220008000100, "QSPC.E.G P0, R0, [R4.U32+UR4]"),
    (0x00000804040079aa, 0x000e220008000100, "QSPC.E.G P0, R0, [R4.U32+UR4+0x8]"),
    (0x00000004040079aa, 0x000e22000c000100, "QSPC.E.G P0, R0, [R4.64+UR4]"),
    (0x00001004040079aa, 0x000e22000c000100, "QSPC.E.G P0, R0, [R4.64+UR4+0x10]"),
    (0x00001000020073aa, 0x000e220000000000, "QSPC.G P0, R0, [R2+0x10]"),
    (0x00000004ffff79aa, 0x000e220008000000, "QSPC.G P0, RZ, [RZ.U32+UR4]"),
    # RdOnly / guard-predicate forms (constructed, spec-valid)
    (0x0000000404ff79aa, 0x00000008020100, "QSPC.E.G P1, RZ, [R4.U32+UR4]"),
    (0x00001000ff0283aa, 0x00000000000e0100, "@!P0 QSPC.E.G PT, R2, [RZ+0x10]"),
]


if __name__ == "__main__":
    ok = True
    for lo, hi, exp in VEC:
        try:
            got = decode(lo, hi)
        except ValueError as ex:
            got = str(ex)
        m = "OK " if got == exp else "XX "
        if got != exp:
            ok = False
        print(f"{m}{got:42s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
