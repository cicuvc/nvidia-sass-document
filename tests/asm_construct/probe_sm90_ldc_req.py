#!/usr/bin/env python3
"""H100: does req={SB} on an LDC.64 consumer actually cover the load?

Matrix: LDC stall x consumer-req on/off x consumer stall.
Data side is safe: the stored constant is produced long before the STG.
Each case runs in a subprocess (faults poison the CUDA context).
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def case_src(ldc_stall, use_req, cons_stall):
    req = "{2}" if use_req else "{}"
    return f"""
#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{{}}:4:0]
    MOV32I R10, 0x1234;[7:7:{{1}}:8:1]
    LDC.64 {{R6,R7}}, #param(out);[2:7:{{}}:{ldc_stall}:0]
    IADD3 R8, R6, RZ, RZ;[7:7:{req}:{cons_stall}:1]
    IADD3 R9, R7, RZ, RZ;[7:7:{{}}:2:1]
    STG.E desc[{{UR4,UR5}}][{{R8,R9}}+0x0], R10;[0:7:{{}}:4:0]
    EXIT;[7:7:{{0}}:5:0]
}}
"""


def run_one(ls, req, cs):
    import struct
    sys.path.insert(0, str(REPO))
    from assembler import CudaModule, assemble
    from archutil import adapt_source
    try:
        mod = CudaModule(assemble(adapt_source(case_src(ls, req, cs)),
                                  check_deps=False))
    except Exception as e:
        return f"ldcstall={ls} req={int(req)} consstall={cs}: ASSEMBLE FAIL {str(e)[:80]}"
    out = mod.devmem_alloc(16)
    mod.device_write(out, bytes(16))
    try:
        mod.launch("k", grid=(1,), block=(1,), args=[out])
        mod.synchronize()
        val = struct.unpack("<I", mod.device_read(out, 4))[0]
        tag = "OK" if val == 0x1234 else f"WRONG 0x{val:08x}"
    except Exception as e:
        tag = f"FAULT {str(e)[:50]}"
    return f"ldcstall={ls} req={int(req)} consstall={cs}: {tag}"


if __name__ == "__main__":
    if len(sys.argv) == 4:
        print(run_one(*map(int, sys.argv[1:])), flush=True)
    else:
        for ls in (1, 2):
            for req in (0, 1):
                for cs in (1, 5):
                    r = subprocess.run(
                        [sys.executable, __file__, str(ls), str(req), str(cs)],
                        capture_output=True, text=True, timeout=120)
                    print(r.stdout.strip() or r.stderr.strip()[:150], flush=True)
