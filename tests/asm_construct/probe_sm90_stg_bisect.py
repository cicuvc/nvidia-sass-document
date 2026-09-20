#!/usr/bin/env python3
"""Bisect the sm_90 STG fault: stall sweep on (LDC.64, STG).

Each case runs in a subprocess: an illegal-address fault kills the CUDA
context, so cases must not share a process.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def sweep_case(ldc_stall, stg_stall):
    return f"""
#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{{}}:4:0]
    LDC.64 {{R6,R7}}, #param(out);[2:7:{{}}:{ldc_stall}:0]
    MOV32I R10, 0;[7:7:{{1,2}}:8:1]
    MOV32I R10, 0x1234;[7:7:{{}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R10;[0:7:{{}}:{stg_stall}:0]
    EXIT;[7:7:{{0}}:5:0]
}}
"""


def run_one(ls, ss):
    import struct
    sys.path.insert(0, str(REPO))
    from assembler import CudaModule, assemble
    from archutil import adapt_source
    src = sweep_case(ls, ss)
    try:
        mod = CudaModule(assemble(adapt_source(src), check_deps=False))
    except Exception as e:
        return f"ls{ls}_ss{ss}: ASSEMBLE FAIL {str(e)[:100]}"
    out = mod.devmem_alloc(16)
    mod.device_write(out, bytes(16))
    try:
        mod.launch("k", grid=(1,), block=(1,), args=[out])
        mod.synchronize()
        val = struct.unpack("<I", mod.device_read(out, 4))[0]
        return f"ls{ls}_ss{ss}: {'OK' if val == 0x1234 else 'WRONG'} val=0x{val:08x}"
    except Exception as e:
        return f"ls{ls}_ss{ss}: FAULT {str(e)[:60]}"


if __name__ == "__main__":
    if len(sys.argv) == 3:
        print(run_one(int(sys.argv[1]), int(sys.argv[2])), flush=True)
    else:
        for ls in (1, 2, 3, 4):
            for ss in (1, 2, 4):
                r = subprocess.run(
                    [sys.executable, __file__, str(ls), str(ss)],
                    capture_output=True, text=True, timeout=120)
                print(r.stdout.strip() or r.stderr.strip()[:200], flush=True)
