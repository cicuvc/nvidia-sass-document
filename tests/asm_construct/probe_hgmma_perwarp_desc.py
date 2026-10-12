#!/usr/bin/env python3
"""Test whether Hopper HGMMA shared descriptors are consumed per warp.

Two m64n8k16 BF16 cases are tested on one 128-thread warpgroup:

* SR: every warp supplies the same all-one register B fragment, while its
  UR4:UR5 A descriptor selects a different constant shared-memory A tile.
* RS: every warp supplies the same all-one register A fragment, while its
  UR4:UR5 B descriptor selects a different constant shared-memory B tile.

The four shared tiles contain 1, 2, 4, and 8.  Since K=16, every accumulator
word must be 16 times the value selected by that warp's descriptor.  ``shift``
cyclically rotates the four descriptor assignments to distinguish per-warp
selection from a fixed output-row effect.
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


def source(mode: str, pattern: str) -> str:
    if mode not in ("sr", "rs"):
        raise ValueError("mode must be sr or rs")
    if pattern not in ("same", "perwarp"):
        raise ValueError("pattern must be same or perwarp")

    # SR uses the same compact A layout as probe_hgmma_sr_layout.py.  RS uses
    # the compiler-observed B descriptor from tests/ssrs2_test.cu; its wider
    # access pattern gets a separately filled 8-KiB region for every tile.
    desc_fields = 0x80000 if mode == "sr" else 0x400000
    desc_hi = 0x10 if mode == "sr" else 0
    tile_step = 0x800 if mode == "sr" else 0x2000
    tile_bases = tuple(0x400 + tile * tile_step for tile in range(4))
    n = 8 if mode == "sr" else 16
    accregs = n // 2
    # RS retains the fused-gdesc slot convention: printed gdesc[UR8] reads
    # the B half at UR10:UR11, as confirmed by nvcc's UMOV UR10/UR11 setup.
    desc_ur = 4 if mode == "sr" else 10
    lines = [
        f"#fn hgdesc_{mode}_{pattern}(out<8>, shift<4>) {{",
        "    #pragma MAXREG_COUNT(64)",
        "    #pragma SHARED(40960)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC R10, #param(shift);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR.U32 R5, R4, 0x5;[7:7:{2}:5:1]",
        f"    IMAD.WIDE.U32 {{R6,R7}}, R4, 0x{accregs * 4:x}, {{R2,R3}};[7:7:{{0,2}}:5:1]",
        # One thread initializes one 16-byte physical chunk in every tile.
        "    SHF.L.U32 R11, R4, 0x4, RZ;[7:7:{2}:5:1]",
    ]
    tile_bits = (0x3F80, 0x4000, 0x4080, 0x4100)
    for tile, (base, bits) in enumerate(zip(tile_bases, tile_bits)):
        packed = bits | (bits << 16)
        data = 44 + 4 * tile
        lines += [
            f"    MOV32I R{data}, 0x{packed:08x};[7:7:{{}}:5:1]",
            f"    MOV32I R{data + 1}, 0x{packed:08x};[7:7:{{}}:5:1]",
            f"    MOV32I R{data + 2}, 0x{packed:08x};[7:7:{{}}:5:1]",
            f"    MOV32I R{data + 3}, 0x{packed:08x};[7:7:{{}}:5:1]",
        ]
    if mode == "sr":
        # Independent addresses are required here: reusing one address GPR
        # around STS/BAR caused late-address capture and corrupted tiles.
        for tile, base in enumerate(tile_bases):
            lines.append(
                f"    IADD3 R{12 + tile}, R11, 0x{base:x}, RZ;[7:7:{{}}:5:1]")
        for tile in range(4):
            lines.append(
                f"    STS.128 [R{12 + tile}], {reg_group(44 + 4 * tile, 4)};[7:7:{{}}:5:1]")
    else:
        for tile, base in enumerate(tile_bases):
            data = 44 + 4 * tile
            for repeat in range(4):
                off = base + repeat * 0x800
                lines += [
                    f"    IADD3 R12, R11, 0x{off:x}, RZ;[7:7:{{}}:5:1]",
                    f"    STS.128 [R12], {reg_group(data, 4)};[7:7:{{}}:5:1]",
                    # Protect the reused address register and make the shared
                    # initialization fully ordered before the next region.
                    "    BAR.SYNC 0;[7:7:{}:5:1]",
                ]
    lines += [
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        # Descriptor start advances 0x80 for each 0x800-byte shared tile.
        # R2UR gives each warp its own UR4 value.  The same-descriptor control
        # still takes this path, but omits the warp index.
        ("    IADD3 R20, R5, R10, RZ;[7:7:{1}:5:1]" if pattern == "perwarp"
         else "    MOV R20, R10;[7:7:{1}:5:1]"),
        "    LOP3.LUT R20, R20, 0x3, RZ, 0xc0;[7:7:{}:5:1]",
    ]
    lines += [
        f"    IMAD.U32 R20, R20, 0x{tile_step // 16:x}, RZ;[7:7:{{}}:5:1]",
        f"    IADD3 R20, R20, 0x{desc_fields | 0x40:x}, RZ;[7:7:{{}}:5:1]",
        f"    R2UR UR{desc_ur}, R20;[7:7:{{}}:5:1]",
        f"    UMOV UR{desc_ur + 1}, 0x{desc_hi:x};[7:7:{{}}:5:1]",
    ]
    for reg in range(24, 24 + accregs):
        lines.append(f"    MOV32I R{reg}, 0x0;[7:7:{{}}:5:1]")
    for reg in range(40, 44):
        lines.append(f"    MOV32I R{reg}, 0x3f803f80;[7:7:{{}}:5:1]")
    lines += ["    WARPGROUP.ARRIVE;[7:7:{}:4:1]"]
    # Leave a conservative settling gap after both R2UR and the warpgroup
    # fence.  HGMMA has no general scoreboard edge for either dependency.
    lines += ["    NOP;[7:7:{}:5:1]" for _ in range(16)]
    if mode == "sr":
        operands = "gdesc[UR4], {R40,R41}, RZ"
    else:
        operands = "{R40,R41,R42,R43}, gdesc[UR8], RZ"
    hstall = 4 if mode == "sr" else 3
    lines += [
        f"    HGMMA.64x{n}x16.F32.BF16 {reg_group(24, accregs)}, {operands}, !UPT, gsb0;[7:7:{{}}:{hstall}:0]",
        "    WARPGROUP.DEPBAR.LE gsb0, 0x0;[7:7:{}:5:1]",
    ]
    for off in range(0, accregs, 4):
        addr = "[{R6,R7}]" if off == 0 else f"[{{R6,R7}}+0x{off * 4:x}]"
        lines.append(
            f"    STG.E.128.STRONG.GPU {addr}, {reg_group(24 + off, 4)};[7:3:{{}}:8:0]")
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def f32(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def run(mode: str, pattern: str, shifts: tuple[int, ...], verbose: bool,
        controls: dict[int, float] | None = None) -> tuple[bool, dict[int, float]]:
    cubin = assemble(source(mode, pattern), arch="sm90", check_deps=True)
    mod = CudaModule(cubin)
    accregs = 4 if mode == "sr" else 8
    out_size = 128 * accregs * 4
    out = mod.devmem_alloc(out_size)
    all_ok = True
    signatures: dict[int, float] = {}
    try:
        for shift in shifts:
            mod.devmem_set(out, 0, out_size // 4)
            mod.launch(f"hgdesc_{mode}_{pattern}", grid=(1,), block=(128,),
                       args=[out, shift])
            mod.synchronize()
            words = struct.unpack(f"<{128 * accregs}I",
                                  mod.device_read(out, out_size))
            print(f"mode={mode.upper()} pattern={pattern} shift={shift}")
            warp_values: list[list[float]] = []
            for warp in range(4):
                vals = [f32(x) for x in
                        words[warp * 32 * accregs:(warp + 1) * 32 * accregs]]
                unique = sorted(set(vals))
                warp_values.append(unique)
                desc_index = ((warp + shift) if pattern == "perwarp" else shift) & 3
                if controls is None:
                    expected = (16.0 * (1 << desc_index)
                                if mode == "sr" else unique[0])
                else:
                    # If descriptors are warpgroup-wide and selected from
                    # warp 0, every band must match the same-descriptor run
                    # for warp 0's descriptor index, which equals shift.
                    expected = controls[shift]
                ok = unique == [expected]
                print(f"  warp {warp}: desc={desc_index} unique={unique} "
                      f"expected={expected:g} ok={ok}")
                if verbose and not ok:
                    for lane in range(32):
                        row = vals[lane * accregs:(lane + 1) * accregs]
                        print(f"    lane {lane:02d}: {row}")
                all_ok = all_ok and ok
            if controls is None:
                if not (all(x == warp_values[0] for x in warp_values[1:]) and
                        len(warp_values[0]) == 1 and warp_values[0][0] != 0.0):
                    all_ok = False
                else:
                    signatures[shift] = warp_values[0][0]
    finally:
        mod.devmem_free(out)
    return all_ok, signatures


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("sr", "rs", "both"), default="both")
    p.add_argument("--shifts", default="0,1,3",
                   help="comma-separated cyclic descriptor shifts")
    p.add_argument("--verbose", action="store_true")
    ns = p.parse_args()
    shifts = tuple(int(x, 0) & 3 for x in ns.shifts.split(",") if x)
    modes = ("sr", "rs") if ns.mode == "both" else (ns.mode,)
    outcomes = []
    for mode in modes:
        same_ok, controls = run(mode, "same", shifts, ns.verbose)
        perwarp_ok, _ = run(mode, "perwarp", shifts, ns.verbose, controls)
        outcomes += [(mode, "same", same_ok),
                     (mode, "perwarp-selects-warp0", perwarp_ok)]
    print("summary:")
    for mode, pattern, ok in outcomes:
        print(f"  {mode.upper()} {pattern}: expected-values={ok}")
    if not all(ok for _, _, ok in outcomes):
        raise AssertionError("HGMMA per-warp descriptor probe failed")
    print("HGMMA shared descriptors are selected from warp 0: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
