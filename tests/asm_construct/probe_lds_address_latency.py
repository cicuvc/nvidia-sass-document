#!/usr/bin/env python3
"""Compare scoreboard-visible LDS latency across GPR/UR/immediate addresses."""

from __future__ import annotations

import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


FORMS = {
    "rz": "[RZ]",
    "gpr": "[R26]",
    "ur": "[RZ+UR10]",
    "gpr_ur": "[R26+UR10]",
    "ur_imm": "[RZ+UR10+0x4]",
    "gpr_ur_imm": "[R26+UR10+0x4]",
}


def source(addr: str) -> str:
    return f"""#fn ldsaddrlat(out<8>) {{
    #pragma MAXREG_COUNT(64)
    #pragma SHARED(1024)
    LDC.64 {{R2,R3}}, #param(out);[0:7:{{}}:1:0]
    MOV32I R26, 0x0;[7:7:{{}}:5:1]
    MOV32I R30, 0x12345678;[7:7:{{}}:5:1]
    STS [RZ], R30;[7:7:{{}}:5:1]
    STS [RZ+0x4], R30;[7:7:{{}}:5:1]
    UMOV UR10, URZ;[7:7:{{}}:5:1]
    NOP;[7:7:{{}}:8:1]
    NOP;[7:7:{{}}:8:1]
    CS2R {{R20,R21}}, SR_CLOCKLO;[7:7:{{}}:5:0]
    LDS R40, {addr};[4:7:{{}}:1:1]
    IADD3 R41, R40, RZ, RZ;[7:7:{{4}}:5:1]
    CS2R {{R22,R23}}, SR_CLOCKLO;[7:7:{{}}:5:0]
    NOP;[7:7:{{}}:8:1]
    NOP;[7:7:{{}}:8:1]
    STG.E.64.STRONG.GPU [{{R2,R3}}], {{R20,R21}};[7:0:{{0}}:8:0]
    STG.E.64.STRONG.GPU [{{R2,R3}}+0x8], {{R22,R23}};[7:0:{{}}:8:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def main() -> int:
    for name, addr in FORMS.items():
        mod = CudaModule(assemble(source(addr), check_deps=True))
        out = mod.devmem_alloc(16)
        vals = []
        try:
            for _ in range(21):
                mod.launch("ldsaddrlat", grid=(1,), block=(32,), args=[out])
                mod.synchronize()
                t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                vals.append((t1 - t0) & ((1 << 64) - 1))
        finally:
            mod.devmem_free(out)
        print(f"{name:12s} median={statistics.median(vals):.0f} "
              f"range={min(vals)}..{max(vals)} samples={vals}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
