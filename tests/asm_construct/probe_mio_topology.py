#!/usr/bin/env python3
"""Cross-subcore MIO/LSU/XU admission and backend topology probe (GB202).

Warp 0 is the timed victim.  Warp 4 (same subcore) or warp 1 (different
subcore) runs a longer contender stream.  Supported streams deliberately
span the proposed boundaries:

  mufu  -> XU backend
  f2f/f2i/i2f -> legacy scalar conversions, VQ_MUFU hypothesis
  shfl  -> warp exchange, placement under test
  lds   -> shared-memory LSU/L1TEX data path (broadcast, no bank conflict)
  ldg   -> unique cache-line global loads, stressing outstanding LSU entries
  ldc   -> ADU constant-load backend, with immediate or GPR index
  brx   -> ADU computed-control-flow backend, with RZ or GPR target
  bar   -> ADU block-barrier support

Results are dead and rotate through 40 registers.  Variable-latency ops use
no write scoreboard because no consumer exists; the measured interval is
queue admission/issue time, not final completion latency.  The script launches
once to warm the module and once per requested repetition, making
``ncu --launch-skip 1 --launch-count 1`` select the first measured launch.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


OPS = (
    "mufu", "mufu_o", "mufu_z",
    "f2f", "f2i", "i2f", "f2f64", "f2i64src", "i2f64src",
    "i2f64dst", "f2fp", "i2fp",
    "shfl", "shfl_o", "shfl_z", "shfl_p", "shfl_rr", "shfl_rr_mix", "shfl_rrr",
    "lds", "lds_e", "lds_o", "lds_u", "lds_eu", "lds_ui", "lds_eui",
    "ldg", "ldc", "ldc_r", "brx_z", "brx_r", "bar",
    "bmov", "bmov_w", "warpsync_a", "warpsync_r",
    "bssy_sync",
)
PLACEMENTS = {
    "solo": (7, 0),
    "same_ab": (4, 1),
    "same_ctrl": (4, 2),
    "diff_ab": (1, 1),
    "diff_ctrl": (1, 2),
}


def body(op: str, n: int, guard: str = "") -> list[str]:
    prefix = f"{guard} " if guard else ""
    lines = []
    for i in range(n):
        rd = 40 + i % 40
        if op == "mufu":
            inst = f"MUFU.RCP R{rd}, R24"
        elif op == "mufu_o":
            inst = f"MUFU.RCP R{rd}, R25"
        elif op == "mufu_z":
            inst = f"MUFU.RCP R{rd}, RZ"
        elif op == "f2f":
            inst = f"F2F.F16.F32 R{rd}, R24"
        elif op == "f2i":
            inst = f"F2I.S32.F32.TRUNC R{rd}, R24"
        elif op == "i2f":
            inst = f"I2F.F32.S32 R{rd}, R24"
        elif op == "f2f64":
            inst = f"F2F.F32.F64 R{rd}, {{R24,R25}}"
        elif op == "f2i64src":
            inst = f"F2I.S32.F64.TRUNC R{rd}, {{R24,R25}}"
        elif op == "i2f64src":
            inst = f"I2F.F32.S64 R{rd}, {{R24,R25}}"
        elif op == "i2f64dst":
            even_rd = 40 + 2 * (i % 20)
            inst = f"I2F.F64.S32 {{R{even_rd},R{even_rd + 1}}}, R24"
        elif op == "f2fp":
            inst = f"F2FP.F16.F32.PACK_AB R{rd}, R24, R25"
        elif op == "i2fp":
            inst = f"I2FP.F32.S32 R{rd}, R24"
        elif op == "shfl":
            inst = f"SHFL.BFLY PT, R{rd}, R24, 0x1, 0x1f"
        elif op == "shfl_o":
            inst = f"SHFL.BFLY PT, R{rd}, R25, 0x1, 0x1f"
        elif op == "shfl_z":
            inst = f"SHFL.BFLY PT, R{rd}, RZ, 0x1, 0x1f"
        elif op == "shfl_p":
            inst = f"SHFL.BFLY P1, R{rd}, R24, 0x1, 0x1f"
        elif op == "shfl_rr":
            inst = f"SHFL.IDX PT, R{rd}, R24, R28, 0x1f"
        elif op == "shfl_rr_mix":
            inst = f"SHFL.IDX PT, R{rd}, R24, R29, 0x1f"
        elif op == "shfl_rrr":
            inst = f"SHFL.IDX PT, R{rd}, R24, R28, R29"
        elif op == "lds":
            inst = f"LDS R{rd}, [RZ]"
        elif op == "lds_e":
            inst = f"LDS R{rd}, [R26]"
        elif op == "lds_o":
            inst = f"LDS R{rd}, [R27]"
        elif op == "lds_u":
            inst = f"LDS R{rd}, [RZ+UR10]"
        elif op == "lds_eu":
            inst = f"LDS R{rd}, [R26+UR10]"
        elif op == "lds_ui":
            inst = f"LDS R{rd}, [RZ+UR10+0x4]"
        elif op == "lds_eui":
            inst = f"LDS R{rd}, [R26+UR10+0x4]"
        elif op == "ldg":
            # One coalesced 128-byte line per warp instruction.  The working
            # set exceeds L1 so profiler replay does not turn it into a tiny
            # permanently hot set.
            inst = (f"LDG.E.STRONG.GPU R{rd}, "
                    f"[{{R18,R19}}+0x{i * 128:x}]")
        elif op == "ldc":
            inst = f"LDC R{rd}, c[0x0][0x0]"
        elif op == "ldc_r":
            inst = f"LDC R{rd}, c[0x0][R26+0x0]"
        elif op == "brx_z":
            inst = f"BRX RZ, #label(brx_{op}_{i})"
        elif op == "brx_r":
            inst = f"BRX {{R26,R27}}, #label(brx_{op}_{i})"
        elif op == "bar":
            inst = "BAR.SYNC 0"
        elif op == "bmov":
            inst = f"BMOV.32 R{rd}, MACTIVE"
        elif op == "bmov_w":
            inst = "BMOV.32 OPT_STACK, R26"
        elif op == "warpsync_a":
            inst = "WARPSYNC.ALL"
        elif op == "warpsync_r":
            inst = "WARPSYNC R32"
        elif op == "bssy_sync":
            lines += [
                f"    {prefix}BSSY B0, #label(cbu_join_{i});"
                "[7:7:{}:5:1]",
                f"    #def_label(cbu_join_{i})",
                f"    {prefix}BSYNC B0;[7:7:{{}}:5:1]",
            ]
            continue
        else:
            raise ValueError(op)
        lines.append(f"    {prefix}{inst};[7:7:{{}}:1:1]")
        if op in ("brx_z", "brx_r"):
            lines.append(f"    #def_label(brx_{op}_{i})")
    return lines


def source(victim: str, contender: str, n: int, factor: int) -> str:
    lines = [
        "#fn miotopo(out<8>, data<8>, contender_warp<4>, kind<4>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    #pragma SHARED(1024)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    LDC.64 {R16,R17}, #param(data);[2:7:{}:1:0]",
        "    LDC R12, #param(contender_warp);[3:7:{}:1:0]",
        "    LDC R13, #param(kind);[4:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[5:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{5}:5:1]",
        "    IMAD.WIDE.U32 {R18,R19}, R4, 0x4, {R16,R17};"
        "[7:7:{2,5}:5:1]",
        "    MOV32I R24, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R25, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R26, 0x0;[7:7:{}:5:1]",
        "    MOV32I R27, 0x0;[7:7:{}:5:1]",
        "    MOV32I R28, 0x1;[7:7:{}:5:1]",
        "    MOV32I R29, 0x1f;[7:7:{}:5:1]",
        "    MOV32I R32, 0xffffffff;[7:7:{}:5:1]",
        "    UMOV UR10, 0x0;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(victim);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, R12, PT;[7:7:{3}:13:1]",
        "    @!P0 BRA #label(done);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R13, 0x1, PT;[7:7:{4}:13:1]",
        "    @P0 BRA #label(active);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R13, 0x2, PT;[7:7:{4}:13:1]",
        "    @P0 BRA #label(control);[7:7:{}:5:1]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(victim)",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += body(victim, n)
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R22,R23};[7:1:{}:8:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(active)",
    ]
    lines += body(contender, n * factor)
    lines += ["    BRA #label(done);[7:7:{}:5:1]", "#def_label(control)"]
    lines += body(contender, n * factor, "@P6")
    lines += ["#def_label(done)", "    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--victim", choices=OPS, default="shfl")
    p.add_argument("--contender", choices=OPS, default="ldg")
    p.add_argument("--placement", choices=PLACEMENTS, default="same_ab")
    p.add_argument("--count", type=int, default=256)
    p.add_argument("--factor", type=int, default=4)
    p.add_argument("--reps", type=int, default=5)
    ns = p.parse_args()
    if min(ns.count, ns.factor, ns.reps) <= 0:
        p.error("count, factor, and reps must be positive")

    mod = CudaModule(assemble(source(ns.victim, ns.contender,
                                     ns.count, ns.factor), check_deps=True))
    out = mod.devmem_alloc(32)
    data_size = ns.count * ns.factor * 128 + 4096
    data = mod.devmem_alloc(data_size)
    mod.devmem_set(data, 0x3f3f3f3f, data_size // 4)
    warp, kind = PLACEMENTS[ns.placement]
    vals = []
    try:
        for rep in range(ns.reps + 1):
            mod.launch("miotopo", grid=(1,), block=(256,),
                       args=[out, data, warp, kind])
            mod.synchronize()
            if rep:
                t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                vals.append((t1 - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)
    print(f"{ns.victim} <- {ns.contender} {ns.placement}: "
          f"cycles={vals} median/op={statistics.median(vals)/ns.count:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
