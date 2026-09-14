#!/usr/bin/env python3
"""Test whether a younger hot LDG can complete ahead of an older cold LDG."""

from __future__ import annotations

import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


SOURCE = r"""#fn mioorder(out<8>, cold<8>, hot<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]
    LDC.64 {R6,R7}, #param(cold);[2:7:{}:1:0]
    LDC.64 {R8,R9}, #param(hot);[3:7:{}:1:0]
    LDG.E R30, desc[{UR4,UR5}][{R8,R9}];[4:7:{0,3}:1:1]
    IADD3 R31, R30, RZ, RZ;[7:7:{4}:5:1]
    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]
    LDG.E R40, desc[{UR4,UR5}][{R6,R7}];[4:7:{2}:1:1]
    LDG.E R41, desc[{UR4,UR5}][{R8,R9}];[5:7:{}:1:1]
    IADD3 R42, R41, RZ, RZ;[7:7:{5}:5:1]
    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]
    IADD3 R43, R40, RZ, RZ;[7:7:{4}:5:1]
    CS2R {R24,R25}, SR_CLOCKLO;[7:7:{}:5:0]
    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:0:{1}:8:0]
    STG.E.64.STRONG.GPU [{R2,R3}+8], {R22,R23};[7:0:{}:8:0]
    STG.E.64.STRONG.GPU [{R2,R3}+0x10], {R24,R25};[7:0:{}:8:0]
    STG.E.STRONG.GPU [{R2,R3}+0x18], R42;[7:0:{}:8:0]
    STG.E.STRONG.GPU [{R2,R3}+0x1c], R43;[7:0:{}:8:0]
    EXIT;[7:7:{}:5:0]
}"""


def main() -> int:
    mod = CudaModule(assemble(SOURCE, check_deps=True))
    out = mod.devmem_alloc(32)
    cold = mod.devmem_alloc(4 << 20)
    hot = mod.devmem_alloc(128)
    mod.devmem_set(cold, 0x11223344, (4 << 20) // 4)
    mod.devmem_set(hot, 0x55667788, 128 // 4)
    hot_wait, old_wait = [], []
    try:
        # Each launch uses a new 64-KiB-spaced cold line.  The hot line is
        # explicitly warmed inside that same launch before timing begins.
        for rep in range(32):
            cp = cold + rep * 0x10000
            mod.launch("mioorder", grid=(1,), block=(32,), args=[out, cp, hot])
            mod.synchronize()
            t0, th, tc, vh, vc = struct.unpack(
                "<QQQII", mod.device_read(out, 32))
            if (vh, vc) != (0x55667788, 0x11223344):
                raise RuntimeError(f"bad data hot={vh:#x} cold={vc:#x}")
            if rep:
                hot_wait.append((th - t0) & ((1 << 64) - 1))
                old_wait.append((tc - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(hot)
        mod.devmem_free(cold)
        mod.devmem_free(out)
    print(f"younger-hot wait: {hot_wait}")
    print(f"older-cold wait:  {old_wait}")
    print(f"median hot={statistics.median(hot_wait):.1f} "
          f"cold={statistics.median(old_wait):.1f} cycles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
