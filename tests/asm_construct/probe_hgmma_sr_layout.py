#!/usr/bin/env python3
"""Map Hopper's undocumented HGMMA shared-A/register-B fragment.

The kernel uses a no-swizzle K-major shared-memory descriptor for A and lays
out an identity-pattern BF16/F16/TF32 matrix.  One component of
the register B operand is set to 1.0 on each launch.  The nonzero accumulator
coordinate therefore identifies the (k,n) element carried by that
(thread, register, half) component.

Run on Hopper, for example through tools/modal_h100_probe.py.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


def reg_group(first: int, count: int) -> str:
    return "{" + ",".join(f"R{r}" for r in range(first, first + count)) + "}"


def source(n: int, srcfmt: str = "BF16") -> str:
    if n not in (8, 16):
        raise ValueError("the mapping probe currently supports n=8 or n=16")
    bregs = n // 4
    accregs = n // 2
    if srcfmt not in ("BF16", "F16", "TF32"):
        raise ValueError("srcfmt must be BF16, F16, or TF32")
    tf32 = srcfmt == "TF32"
    comps_per_lane = bregs if tf32 else bregs * 2
    one16 = 0x3F80 if srcfmt == "BF16" else 0x3C00
    fmt_suffix = "" if srcfmt == "F16" else f".{srcfmt}"
    kdim = 8 if tf32 else 16

    lines = [
        "#fn hgsrmap(out<8>, selector<4>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    #pragma SHARED(4096)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC R10, #param(selector);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        f"    IMAD.WIDE.U32 {{R6,R7}}, R4, 0x{accregs * 4:x}, {{R2,R3}};[7:7:{{0,2}}:5:1]",
        # Zero the A tile.  Thread t owns one physical 16-byte chunk.
        "    SHF.L.U32 R11, R4, 0x4, RZ;[7:7:{2}:5:1]",
        "    IADD3 R11, R11, 0x400, RZ;[7:7:{}:5:1]",
        "    MOV32I R16, 0x0;[7:7:{}:5:1]",
        "    MOV32I R17, 0x0;[7:7:{}:5:1]",
        "    MOV32I R18, 0x0;[7:7:{}:5:1]",
        "    MOV32I R19, 0x0;[7:7:{}:5:1]",
        "    STS.128 [R11], {R16,R17,R18,R19};[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        # Physical chunk t is (m_group=t>>4, k_group=(t>>3)&1,
        # row=t&7).  Install the identity-pattern nonzero below.
        "    SHR.U32 R12, R4, 0x3;[7:7:{2}:5:1]",
        "    LOP3.LUT R12, R12, 0x1, RZ, 0xc0;[7:7:{}:5:1]",
    ]
    if tf32:
        # A[m,k] = (k == m % 8): k_group=(m%8)>>2 and k_in=m%4.
        lines += [
            "    SHR.U32 R13, R4, 0x2;[7:7:{2}:5:1]",
            "    LOP3.LUT R13, R13, 0x1, RZ, 0xc0;[7:7:{}:5:1]",
            "    ISETP.EQ.U32.AND P0, PT, R12, R13, PT;[7:7:{}:13:1]",
            "    LOP3.LUT R14, R4, 0x3, RZ, 0xc0;[7:7:{2}:5:1]",
            "    IMAD.U32 R14, R14, 0x4, R11;[7:7:{}:5:1]",
            "    MOV32I R15, 0x3f800000;[7:7:{}:5:1]",
            "    @P0 STS [R14], R15;[7:7:{}:5:1]",
        ]
    else:
        # A[m,k] = (k == m % 16): k_group equals the low bit of
        # m_group and k_in equals row.
        lines += [
            "    SHR.U32 R13, R4, 0x4;[7:7:{2}:5:1]",
            "    LOP3.LUT R13, R13, 0x1, RZ, 0xc0;[7:7:{}:5:1]",
            "    ISETP.EQ.U32.AND P0, PT, R12, R13, PT;[7:7:{}:13:1]",
            "    LOP3.LUT R14, R4, 0x7, RZ, 0xc0;[7:7:{2}:5:1]",
            "    IMAD.U32 R14, R14, 0x2, R11;[7:7:{}:5:1]",
            f"    MOV32I R15, 0x{one16:04x};[7:7:{{}}:5:1]",
            "    @P0 STS.U16 [R14], R15;[7:7:{}:5:1]",
        ]
    lines += [
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        # Tight, non-overlapping descriptor for the A tile:
        # start=0x400, LBO=128 B, SBO=256 B, no swizzle.
        "    UMOV UR4, 0x80040;[7:7:{}:5:1]",
        "    UMOV UR5, 0x10;[7:7:{}:5:1]",
    ]

    for r in range(24, 24 + accregs):
        lines.append(f"    MOV32I R{r}, 0x0;[7:7:{{}}:5:1]")
    for r in range(40, 40 + bregs):
        lines.append(f"    MOV32I R{r}, 0x0;[7:7:{{}}:5:1]")

    # selector = global_tid * components_per_lane + component.  Reuse P1
    # while installing the selected element into the B register group.
    shift = comps_per_lane.bit_length() - 1
    lines += [
        f"    SHR.U32 R22, R10, 0x{shift:x};[7:7:{{1}}:5:1]",
        f"    LOP3.LUT R21, R10, 0x{comps_per_lane - 1:x}, RZ, 0xc0;[7:7:{{1}}:5:1]",
        "    ISETP.EQ.U32.AND P0, PT, R4, R22, PT;[7:7:{2}:13:1]",
    ]
    for comp in range(comps_per_lane):
        reg = 40 + (comp if tf32 else comp // 2)
        value = 0x3F800000 if tf32 else (one16 if comp % 2 == 0 else one16 << 16)
        lines += [
            f"    ISETP.EQ.U32.AND P1, PT, R21, 0x{comp:x}, P0;[7:7:{{}}:13:1]",
            f"    @P1 MOV32I R{reg}, 0x{value:08x};[7:7:{{}}:5:1]",
        ]

    lines += [
        "    WARPGROUP.ARRIVE;[7:7:{}:5:1]",
        f"    HGMMA.64x{n}x{kdim}.F32{fmt_suffix} {reg_group(24, accregs)}, "
        f"gdesc[UR4], {reg_group(40, bregs)}, RZ, !UPT, gsb0;[7:7:{{}}:4:0]",
        "    WARPGROUP.DEPBAR.LE gsb0, 0x0;[7:7:{}:5:1]",
    ]
    for off in range(0, accregs, 4):
        count = min(4, accregs - off)
        suffix = "" if count == 1 else f".{count * 32}"
        addr_off = off * 4
        addr = "[{R6,R7}]" if addr_off == 0 else f"[{{R6,R7}}+0x{addr_off:x}]"
        operand = f"R{24 + off}" if count == 1 else reg_group(24 + off, count)
        lines.append(f"    STG.E{suffix}.STRONG.GPU {addr}, {operand};[7:3:{{}}:8:0]")
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def accumulator_coord(tid: int, reg: int) -> tuple[int, int]:
    """PTX-documented m64nN accumulator fragment coordinate."""
    warp = tid >> 5
    lane = tid & 31
    row0 = warp * 16 + lane // 4
    block = reg // 4
    within = reg & 3
    row = row0 + (8 if within >= 2 else 0)
    col = block * 8 + (lane & 3) * 2 + (within & 1)
    return row, col


def run(n: int, srcfmt: str, limit: int | None,
        verbose: bool) -> list[tuple[int, int, int, int, int]]:
    cubin = assemble(source(n, srcfmt), arch="sm90", check_deps=True)
    mod = CudaModule(cubin)
    accregs = n // 2
    comps_per_lane = n // 4 if srcfmt == "TF32" else (n // 4) * 2
    total = 128 * comps_per_lane
    if limit is not None:
        total = min(total, limit)
    out_size = 128 * accregs * 4
    out = mod.devmem_alloc(out_size)
    mappings: list[tuple[int, int, int, int, int]] = []
    try:
        for selector in range(total):
            mod.devmem_set(out, 0, out_size // 4)
            mod.launch("hgsrmap", grid=(1,), block=(128,), args=[out, selector])
            mod.synchronize()
            words = struct.unpack(f"<{128 * accregs}I", mod.device_read(out, out_size))
            nz = []
            for tid in range(128):
                for reg in range(accregs):
                    bits = words[tid * accregs + reg]
                    value = struct.unpack("<f", struct.pack("<I", bits))[0]
                    if value != 0.0:
                        nz.append((tid, reg, bits, value, *accumulator_coord(tid, reg)))
            src_tid, component = divmod(selector, comps_per_lane)
            src_warp, lane = divmod(src_tid, 32)
            if srcfmt == "TF32":
                expected_k = 4 * (component % 2) + lane % 4
                expected_n = 8 * (component // 2) + lane // 4
                expected_coords = {
                    (src_warp * 16 + expected_k, expected_n),
                    (src_warp * 16 + 8 + expected_k, expected_n),
                }
            else:
                j, half = divmod(component, 2)
                expected_k = 8 * (j % 2) + 2 * (lane % 4) + half
                expected_n = 8 * (j // 2) + lane // 4
                expected_coords = {(src_warp * 16 + expected_k, expected_n)}
            got_coords = {(item[-2], item[-1]) for item in nz}
            if (got_coords != expected_coords or
                    any(item[2] != 0x3F800000 for item in nz)):
                raise AssertionError(
                    f"selector={selector} src=T{src_tid}/c{component}: "
                    f"got {nz}, expected 1.0 at {sorted(expected_coords)}")
            mappings.append((src_warp, lane, component, expected_k, expected_n))
            if verbose:
                print(f"T{src_tid:3d} w{src_warp} lane{lane:02d} c{component} -> "
                      f"B[k={expected_k:02d},n={expected_n:02d}] "
                      f"(D {sorted(expected_coords)})")
    finally:
        mod.devmem_free(out)
    return mappings


def summarize(n: int, srcfmt: str,
              mappings: list[tuple[int, int, int, int, int]]) -> None:
    comps_per_lane = n // 4 if srcfmt == "TF32" else (n // 4) * 2
    complete = len(mappings) == 128 * comps_per_lane
    kdim = 8 if srcfmt == "TF32" else 16
    print(f"shape=m64n{n}k{kdim} srcfmt={srcfmt} "
          f"mapped={len(mappings)}/{128 * comps_per_lane}")
    if not complete:
        for item in mappings:
            print(item)
        return

    per_warp = []
    for warp in range(4):
        got = {(k, col) for w, _, _, k, col in mappings if w == warp}
        per_warp.append(got)
        want = {(k, col) for k in range(kdim) for col in range(n)}
        print(f"warp {warp}: {len(got)} unique B coordinates, "
              f"full_tile={got == want}")
    print(f"four warps identical layout={all(x == per_warp[0] for x in per_warp[1:])}")
    print("local mapping (valid independently in every warp):")
    for lane in range(32):
        fields = []
        for component in range(comps_per_lane):
            matches = [(k, col) for w, l, c, k, col in mappings
                       if w == 0 and l == lane and c == component]
            k, col = matches[0]
            fields.append(f"c{component}->({k:02d},{col:02d})")
        print(f"  lane {lane:02d}: " + " ".join(fields))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, choices=(8, 16), default=8)
    p.add_argument("--srcfmt", choices=("BF16", "F16", "TF32"), default="BF16")
    p.add_argument("--limit", type=int, help="run only the first N selectors")
    p.add_argument("--verbose", action="store_true")
    ns = p.parse_args()
    mappings = run(ns.n, ns.srcfmt, ns.limit, ns.verbose)
    summarize(ns.n, ns.srcfmt, mappings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
