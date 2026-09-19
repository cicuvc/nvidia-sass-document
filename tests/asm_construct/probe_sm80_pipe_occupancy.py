#!/usr/bin/env python3
"""GA100 pipe-occupancy scan: inst_executed + cycles_active per scalar op.

Each kernel holds N independent copies of one target operation with all
source slots marked reusable, so the GA100 two-clock backend floor (not RF
collection) is exposed.  A ``poff`` variant guards every target instruction
with an architecturally-false P6 to separate predicate-insensitive admission
pressure from architectural execution, mirroring the GB202 admission probes.

Run under ncu (kernel names encode op and variant, so launch order does not
matter):

    sudo ncu --csv --target-processes all \
      --metrics "$(python3 tests/asm_construct/probe_sm80_pipe_occupancy.py \
          --print-ncu)" \
      python3 tests/asm_construct/probe_sm80_pipe_occupancy.py

Environment: ASSEMBLER_ARCH=sm80, CUDA_VISIBLE_DEVICES=<free A100>.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assembler import CudaModule, assemble  # noqa: E402
from probe_subcore_compute_conflict import OPS  # noqa: E402


# sm_80-encodable scalar subset of the shared OPS table.  Excludes the seven
# mnemonics absent from the sm_80 database (F2IP/I2FP/MOV64IUR/VIMNMX/FHADD/
# FHFMA/VIADD) and the MIO/tensor entries.
CASES = (
    "mov mov32i iadd iadd32i iadd3 lop lop3 lop32i prmt shf shl shr lea "
    "iscadd sel sgxt imnmx iabs bmsk isetp psetp plop3 p2r r2p "
    "fmnmx fsel fset fsetp f2fp i2i i2ip "
    "fadd fmul ffma fswzadd fadd32i fmul32i ffma32i "
    "imad imul imad_hi imad_wide idp2 idp4 imul32i "
    "hadd2 hfma2 hmul2 hmnmx2 hset2 hsetp2 hadd2_32i hfma2_32i hmul2_32i "
    "hadd2_f32 hfma2_mma "
    "dadd dmul dfma dsetp clmad "
    "iadd3_1r "
    "iadd_imad_pair mov_imad_pair ffma_imad_pair "
    "nop"
).split()

# Pair ops are two instructions per unit; only the active variant is useful.
ACTIVE_ONLY = {"iadd_imad_pair", "mov_imad_pair", "ffma_imad_pair"}

METRICS = (
    "smsp__inst_executed.sum,"
    "smsp__inst_executed_pipe_alu.sum,"
    "smsp__inst_executed_pipe_fma.sum,"
    "smsp__inst_executed_pipe_fp16.sum,"
    "smsp__inst_executed_pipe_fp64.sum,"
    "smsp__inst_executed_pipe_xu.sum,"
    "smsp__inst_executed_pipe_uniform.sum,"
    "smsp__pipe_alu_cycles_active.sum,"
    "smsp__pipe_fma_cycles_active.sum,"
    "smsp__pipe_fp64_cycles_active.sum,"
    "smsp__issue_active.sum,"
    "smsp__cycles_active.sum,"
    "smsp__warp_issue_stalled_math_pipe_throttle_per_warp_active.pct"
)


# These have no reusable register-source slots on sm_80; batch_t=7 is an
# illegal encoding for them.
NO_REUSE = {"nop", "mov32i", "psetp", "plop3"}


def source(name: str, count: int, pred_off: bool) -> str:
    op = OPS[name]
    sched = "[7:7:{}:1:0]" if name in NO_REUSE else "[7:7:{}:1:0:7]"
    guard = "@P6 " if pred_off else ""
    if pred_off and f"{name}_rz" in OPS:
        op = OPS[f"{name}_rz"]
    lines = [
        f"#fn occ_{name}{'_poff' if pred_off else ''}() {{",
        "    #pragma MAXREG_COUNT(96)",
        "    MOV R24, 0x3f803c00;[7:7:{}:6:0]",
        "    MOV R25, 0x3f803c00;[7:7:{}:6:0]",
        "    MOV R26, 0x40003c00;[7:7:{}:6:0]",
        "    MOV R27, 0x40003c00;[7:7:{}:6:0]",
        "    MOV R28, 0x3f003c00;[7:7:{}:6:0]",
        "    MOV R29, 0x3f003c00;[7:7:{}:6:0]",
    ]
    for r in range(40, 80):
        lines.append(f"    MOV R{r}, RZ;[7:7:{{}}:6:0]")
    if pred_off:
        # R24 != 0, so P6 is architecturally false for the whole stream.
        lines.append("    ISETP.EQ.AND P6, PT, R24, RZ, PT;[7:7:{}:12:1]")
    for i in range(count):
        lines.append(f"    {guard}{op.instruction(i)};{sched}")
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ops", default=",".join(CASES))
    ap.add_argument("--variants", default="active,poff")
    ap.add_argument("--length", type=int, default=2048)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--grid", type=int, default=108)
    ap.add_argument("--emit-dir", type=Path)
    ap.add_argument("--print-ncu", action="store_true")
    ns = ap.parse_args()
    if ns.print_ncu:
        print(METRICS)
        return 0
    names = [x.strip().lower() for x in ns.ops.split(",") if x.strip()]
    bad = set(names) - set(CASES)
    if bad:
        ap.error(f"unknown cases: {sorted(bad)}")
    variants = [x.strip() for x in ns.variants.split(",") if x.strip()]
    if set(variants) - {"active", "poff"}:
        ap.error("bad variant")
    if ns.emit_dir:
        ns.emit_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        for variant in variants:
            pred_off = variant == "poff"
            if pred_off and name in ACTIVE_ONLY:
                continue
            try:
                cubin = assemble(source(name, ns.length, pred_off),
                                 arch=os.environ.get("PROBE_ARCH", "sm80"), check_deps=False)
            except Exception as exc:
                print(f"{name},{variant},ASSEMBLE_FAIL,{exc}", flush=True)
                continue
            kname = f"occ_{name}{'_poff' if pred_off else ''}"
            if ns.emit_dir:
                (ns.emit_dir / f"{kname}.cubin").write_bytes(cubin)
                print(f"{kname} emitted", flush=True)
                continue
            mod = CudaModule(cubin)
            for rep in range(ns.reps):
                mod.launch(kname, grid=(ns.grid,), block=(32,), args=[])
                mod.synchronize()
                print(f"{kname},{rep}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
