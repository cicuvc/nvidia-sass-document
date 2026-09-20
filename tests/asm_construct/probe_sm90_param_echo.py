#!/usr/bin/env python3
"""Verify the raw c[0x0][0x210] param read + STG path on sm_90 (H100)."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import CudaModule, assemble  # noqa: E402
from archutil import adapt_source  # noqa: E402

CASES = {
    # read param via inline const operand, echo the ADDRESS back through it
    "echo_addr": """
#fn k(out<8>) {
    S2R R0, SR_TID.X;[4:7:{}:6:0]
    MOV R6, 0x10;[7:7:{}:6:0]
    IMAD.WIDE.U32 {R2,R3}, R0, R6, c[0x0][0x210];[7:7:{4}:6:0]
    NOP;[7:7:{}:6:0]
    NOP;[7:7:{}:6:0]
    NOP;[7:7:{}:6:0]
    NOP;[7:7:{}:6:0]
    MOV32I R10, 0xbeef;[7:7:{}:6:0]
    STG.E.64.STRONG.GPU [{R2,R3}], {R2,R3};[0:1:{}:8:0]
    EXIT;[7:7:{0}:5:0]
}
""",
    # same but wait longer before using R2/R3
    "echo_addr_wait": """
#fn k(out<8>) {
    S2R R0, SR_TID.X;[4:7:{}:6:0]
    MOV R6, 0x10;[7:7:{}:6:0]
    IMAD.WIDE.U32 {R2,R3}, R0, R6, c[0x0][0x210];[7:7:{4}:6:0]
    NOP;[7:7:{}:13:1]
    NOP;[7:7:{}:13:1]
    MOV32I R10, 0xbeef;[7:7:{}:6:0]
    STG.E.64.STRONG.GPU [{R2,R3}], {R2,R3};[0:1:{}:8:0]
    EXIT;[7:7:{0}:5:0]
}
""",
}

for name, src in CASES.items():
    mod = CudaModule(assemble(adapt_source(src), check_deps=False))
    out = mod.devmem_alloc(512)
    mod.device_write(out, bytes(512))
    try:
        mod.launch("k", grid=(1,), block=(32,), args=[out])
        mod.synchronize()
        lo, hi = struct.unpack("<QQ", mod.device_read(out, 16))
        ok = (lo & 0xFFFFFFFF) == (out & 0xFFFFFFFF)
        print(f"{name}: OK addr_lo_match={ok} (stored 0x{lo:x})" if ok
              else f"{name}: WRONG stored 0x{lo:x} expected 0x{out:x}",
              flush=True)
    except Exception as e:
        print(f"{name}: FAULT {str(e)[:80]}", flush=True)
    del mod
    from assembler.runner import reset_context
    reset_context()
