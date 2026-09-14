#!/usr/bin/env python3
"""Probe MIO/LDG-to-RF completion under parity-controlled ALU writes (GB202).

A hot LDG.32 claims SB4.  Before its first req-waiting consumer, an FFMA stream
writes only even or only odd destination registers.  FFMA sources are E/O/E
and every instruction marks all three operands for reuse, minimizing RF reads.

Comparisons:
  load E + writes E  vs load E + writes O
  load O + writes O  vs load O + writes E
and predicated-off FFMA controls with identical encodings/schedules.

If MIO completion and ALU results share a parity-banked 1W commit port, a dense
same-bank active stream can delay the LDG scoreboard release.  Unlike the fixed
pipeline collision probe, this experiment observes actual completion through
the scoreboard and assumes no table latency.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


ARCH = "sm120"


def reg_for(parity: str) -> int:
    return 40 if parity == "E" else 41


def storm_regs(parity: str) -> list[int]:
    p = 0 if parity == "E" else 1
    # Keep the storm disjoint from the widest LDG result, R40..R43.
    regs = [50 + p + 2 * i for i in range(20)]
    assert all((r & 1) == p for r in regs)
    return regs


def source(load_parity: str, write_parity: str, mode: str, n: int,
           width: int = 32) -> str:
    if width == 32:
        ldreg = reg_for(load_parity)
        ld_dst = f"R{ldreg}"
        ld_suffix = ""
    elif width == 64:
        ldreg = 40
        ld_dst = "{R40,R41}"
        ld_suffix = ".64"
    elif width == 128:
        ldreg = 40
        ld_dst = "{R40,R41,R42,R43}"
        ld_suffix = ".128"
    else:
        raise ValueError(f"unsupported LDG width {width}")
    dsts = storm_regs(write_parity)
    lines = [
        "#fn miowb(out<8>, data<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(data);[2:7:{}:1:0]",
        "    S2R R8, SR_TID.X;[3:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R10,R11}, R8, 0x20, {R2,R3};"
        "[7:7:{1,3}:5:1]",
        # E/O/E source distribution; values stay constant across the storm.
        "    MOV32I R24, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R25, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R27, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R28, 0x3f000000;[7:7:{}:5:1]",
    ]
    for r in dsts:
        lines.append(f"    MOV32I R{r}, 0;[7:7:{{}}:5:1]")
    # Warm the exact line and force this first load to complete.
    lines += [
        "    LDG.E R30, desc[{UR4,UR5}][{R6,R7}];[4:7:{0,2}:5:1]",
        "    IADD3 R31, R30, RZ, RZ;[7:7:{4}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        f"    LDG.E{ld_suffix} {ld_dst}, desc[{{UR4,UR5}}][{{R6,R7}}];"
        "[4:7:{}:1:1]",
    ]
    guard = "@P6 " if mode == "pred" else ""
    if mode == "nop":
        lines += ["    NOP;[7:7:{}:1:0]" for _ in range(n)]
    elif mode in ("readE", "readO"):
        # Saturate the selected bank's two GPR read ports without producing a
        # GPR result.  Repeated predicate overwrites have no RAW dependency.
        a, b = ((24, 28) if mode == "readE" else (25, 27))
        lines += [f"    ISETP.EQ P0, R{a}, R{b};[7:7:{{}}:1:1]"
                  for _ in range(n)]
    else:
        for i in range(n):
            # batch/reuse mask 7 caches A/B/C for the next identical-source
            # instruction.  "plain" retains E/O/E reads but no reuse state.
            if mode == "plain":
                mask = 0
            elif mode.startswith("mask"):
                mask = int(mode[4:])
            else:
                mask = 7
            reuse = "" if mask == 0 else f":{mask}"
            lines.append(
                f"    {guard}FFMA R{dsts[i % len(dsts)]}, R24, R27, R28;"
                f"[7:7:{{}}:1:0{reuse}]")
    lines += [
        f"    IADD3 R32, R{ldreg}, RZ, RZ;[7:7:{{4}}:5:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R10,R11}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x8], {R22,R23};[7:1:{}:8:0]",
        "    STG.E.STRONG.GPU [{R10,R11}+0x10], R32;[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run_case(lp: str, wp: str, mode: str, n: int, reps: int,
             width: int = 32) -> list[int]:
    cubin = assemble(source(lp, wp, mode, n, width), arch=ARCH,
                     check_deps=True)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(32 * 32)
    data = mod.devmem_alloc(128)
    mod.device_write(data, struct.pack("<32I", *([0x12345678] * 32)))
    try:
        vals = []
        for rep in range(reps + 1):
            mod.launch("miowb", grid=(1,), block=(32,), args=[out, data])
            mod.synchronize()
            t0, t1, got = struct.unpack("<QQI", mod.device_read(out, 20))
            if got != 0x12345678:
                raise RuntimeError(f"bad LDG result 0x{got:08x}")
            if rep:
                vals.append((t1 - t0) & ((1 << 64) - 1))
        return vals
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)


def main() -> int:
    global ARCH
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arch", choices=("sm90", "sm120"), default="sm120")
    p.add_argument("--counts", default="0,2,4,8,12,16,24,32,48,64")
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("--mask-scan", type=int, metavar="N",
                   help="also sweep FFMA reuse masks 0..7 at count N")
    p.add_argument("--width-scan", type=int, metavar="N",
                   help="compare hot LDG.32/.64/.128 at FFMA count N")
    p.add_argument("--read-scan", type=int, metavar="N",
                   help="compare LDG writes against same-bank 2R ISETP traffic")
    ns = p.parse_args()
    ARCH = ns.arch
    try:
        counts = [int(x) for x in ns.counts.split(",") if x.strip()]
    except ValueError as exc:
        p.error(str(exc))
    if not counts or min(counts) < 0 or ns.reps <= 0:
        p.error("counts must be non-negative and reps positive")

    print("hot LDG scoreboard completion under parity-controlled FFMA writes")
    print("values are best cycles from LDG issue through its req consumer")
    rows = {}
    cases = [
        ("E", "E", "active"), ("E", "O", "active"),
        ("O", "O", "active"), ("O", "E", "active"),
        ("E", "E", "pred"), ("E", "O", "pred"),
        ("E", "E", "plain"), ("E", "O", "plain"),
        ("O", "O", "plain"), ("O", "E", "plain"),
        ("E", "E", "nop"),
    ]
    print("  N   EE-act EO-act dEbest dEmed  OO-act OE-act dObest dOmed  "
          "dEplain dOplain  pred  nop")
    for n in counts:
        for case in cases:
            rows[(n,) + case] = run_case(*case, n, ns.reps)
        ee_s = rows[(n, "E", "E", "active")]
        eo_s = rows[(n, "E", "O", "active")]
        oo_s = rows[(n, "O", "O", "active")]
        oe_s = rows[(n, "O", "E", "active")]
        ee, eo, oo, oe = map(min, (ee_s, eo_s, oo_s, oe_s))
        de_med = statistics.median(ee_s) - statistics.median(eo_s)
        do_med = statistics.median(oo_s) - statistics.median(oe_s)
        ep = min(rows[(n, "E", "E", "pred")])
        op = min(rows[(n, "E", "O", "pred")])
        eep = min(rows[(n, "E", "E", "plain")])
        eop = min(rows[(n, "E", "O", "plain")])
        oop = min(rows[(n, "O", "O", "plain")])
        oep = min(rows[(n, "O", "E", "plain")])
        nop = min(rows[(n, "E", "E", "nop")])
        print(f"{n:3d} {ee:7d} {eo:6d} {ee-eo:+6d} {de_med:+5.1f} "
              f"{oo:7d} {oe:6d} {oo-oe:+6d} {do_med:+5.1f} "
              f"{eep-eop:+8d} {oop-oep:+8d} {ep:5d}/{op:<3d} {nop:4d}")
    if ns.mask_scan is not None:
        if ns.mask_scan < 0:
            p.error("--mask-scan must be non-negative")
        n = ns.mask_scan
        print(f"\nreuse-mask threshold at N={n} (bits A/B/C = 1/2/4)")
        print("mask  same  opposite  delta  same_median opposite_median")
        for mask in range(8):
            mode = f"mask{mask}"
            same = run_case("E", "E", mode, n, ns.reps)
            opposite = run_case("E", "O", mode, n, ns.reps)
            print(f" {mask:>2d}  {min(same):5d} {min(opposite):9d} "
                  f"{min(same)-min(opposite):+6d} "
                  f"{statistics.median(same):11.1f} "
                  f"{statistics.median(opposite):15.1f}")
    if ns.width_scan is not None:
        if ns.width_scan < 0:
            p.error("--width-scan must be non-negative")
        n = ns.width_scan
        print(f"\nLDG width scan at N={n}")
        print("width  E-writes O-writes E-O  E-median O-median  pred-E pred-O nop")
        for width in (32, 64, 128):
            # Wide loads necessarily write both parity banks.  For LDG.32 the
            # destination is R40 (E), retaining the one-bank reference case.
            even = run_case("E", "E", "active", n, ns.reps, width)
            odd = run_case("E", "O", "active", n, ns.reps, width)
            pe = run_case("E", "E", "pred", n, ns.reps, width)
            po = run_case("E", "O", "pred", n, ns.reps, width)
            nop = run_case("E", "E", "nop", n, ns.reps, width)
            print(f"{width:5d} {min(even):9d} {min(odd):8d} "
                  f"{min(even)-min(odd):+3d} "
                  f"{statistics.median(even):8.1f} "
                  f"{statistics.median(odd):8.1f} "
                  f"{min(pe):7d} {min(po):6d} {min(nop):3d}")
    if ns.read_scan is not None:
        if ns.read_scan < 0:
            p.error("--read-scan must be non-negative")
        n = ns.read_scan
        print(f"\n2R-vs-1W independence scan at N={n}")
        print("load  read-E read-O same-opp  nop  readE-med readO-med")
        for lp in ("E", "O"):
            re = run_case(lp, "E", "readE", n, ns.reps)
            ro = run_case(lp, "O", "readO", n, ns.reps)
            nop = run_case(lp, "E", "nop", n, ns.reps)
            same, opp = ((re, ro) if lp == "E" else (ro, re))
            print(f"  {lp}   {min(re):6d} {min(ro):6d} "
                  f"{min(same)-min(opp):+8d} {min(nop):5d} "
                  f"{statistics.median(re):9.1f} "
                  f"{statistics.median(ro):9.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
