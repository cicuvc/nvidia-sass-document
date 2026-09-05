"""Observe the physical sm_120 mbarrier v0 word after barrier-cache eviction.

SYNCS updates an SM-local mbarrier cache.  A plain LDS may therefore see stale
shared memory.  Every observation below first executes SYNCS.CCTL.IV for the
barrier address, waits for it, and only then loads the 64-bit shared backing.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from archutil import adapt_source  # noqa: E402


MASK20 = (1 << 20) - 1
MASK21 = (1 << 21) - 1


def physical_word(expected, pending, tx=0, phase=0):
    """sm_90/sm_120 layout::v0 word; counters use two's-complement fields."""
    return (((-expected) & MASK20) << 1
            | ((-tx) & MASK21) << 21
            | ((-pending) & MASK20) << 43
            | (phase & 1) << 63)


HEAD = (
    "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
    "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
    "    UMOV UR6, 0x400;[1:7:{}:1:0]\n"
)


def init(count):
    # This is ptxas's mbarrier.init lowering.  UR8/UR9 form a 64-bit pair.
    return (
        f"    UMOV UR8, 0x{count:x};[1:7:{{}}:1:0]\n"
        "    UIADD3 UR8, UPT, UPT, -UR8, 0x100000, URZ;[7:7:{1}:5:1]\n"
        "    USHF.L.U32 UR9, UR8, 0xb, URZ;[7:7:{1}:5:1]\n"
        "    USHF.L.U32 UR8, UR8, 0x1, URZ;[7:7:{1}:5:1]\n"
        "    SYNCS.EXCH.64 URZ, [UR6], UR8;[2:1:{1}:5:1]\n"
    )


def arrive(count=1, drop=False, no_complete=False):
    if count == 1 and not no_complete:
        mod = ".OPTOUT" if drop else ""
        return f"    SYNCS.ARRIVE.TRANS64{mod}.A1T0 {{R0,R1}}, [RZ+UR6], RZ;[2:7:{{2}}:5:1]\n"
    mods = (".TMASK" if no_complete else "") + (".OPTOUT" if drop else "")
    return (
        f"    MOV32I R2, 0x{count:x};[7:7:{{}}:5:1]\n"
        f"    SYNCS.ARRIVE.TRANS64{mods}.ART0 {{R0,R1}}, [RZ+UR6], R2;[2:7:{{2}}:5:1]\n"
    )


def tx(count, complete=False):
    mode = "A0TX" if complete else "A0TR"
    return (
        f"    MOV32I R2, 0x{count:x};[7:7:{{}}:5:1]\n"
        f"    SYNCS.ARRIVE.TRANS64.RED.{mode} {{RZ,RZ}}, [RZ+UR6], R2;[2:7:{{2}}:5:1]\n"
    )


OBSERVE = (
    "    SYNCS.CCTL.IV [RZ+UR6];[1:7:{2}:5:1]\n"
    "    LDS.64 {R8,R9}, [RZ+UR6];[2:7:{1}:8:1]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R8,R9};[0:2:{1,2}:1:0]\n"
    "    EXIT;[7:7:{0}:5:0]\n"
)


def read_word(count, ops=""):
    src = ("#fn k(out<8>) {\n"
           "    #pragma NUM_MBARRIERS(1)\n"
           "    #pragma SHARED(0x4000)\n"
           + HEAD + init(count) + ops + OBSERVE + "}\n")
    mod = CudaModule(assemble(adapt_source(src)))
    out = mod.devmem_alloc(8)
    mod.launch("k", grid=(1,), block=(1,), args=[out], shared_mem=0x4000)
    mod.synchronize()
    return struct.unpack("<Q", mod.device_read(out, 8))[0]


try:
    CudaModule(assemble(adapt_source("#fn k() { EXIT;[7:7:{}:5:0] }")))
except RuntimeError:
    print("--- no CUDA device; mbarrier backing-word checks SKIPPED ---")
    sys.exit(0)


cases = [
    ("init(1)", 1, "", physical_word(1, 1)),
    ("init(3)", 3, "", physical_word(3, 3)),
    ("init(0x123)", 0x123, "", physical_word(0x123, 0x123)),
    ("arrive 1/3", 3, arrive(), physical_word(3, 2)),
    ("arrive count=2/3", 3, arrive(2), physical_word(3, 1)),
    ("arrive_drop 1/3", 3, arrive(drop=True), physical_word(2, 2)),
    ("expect_tx(1)", 3, tx(1), physical_word(3, 3, 1)),
    ("expect_tx(0x12345)", 3, tx(0x12345), physical_word(3, 3, 0x12345)),
    ("tx128 complete64", 3, tx(128) + tx(64, True), physical_word(3, 3, 64)),
    ("phase completion", 2, arrive() + arrive(), physical_word(2, 2, 0, 1)),
]

ok = True
for name, count, ops, want in cases:
    got = read_word(count, ops)
    passed = got == want
    ok &= passed
    print(f"{'ok ' if passed else 'FAIL'} {name:<24} 0x{got:016x} (exp 0x{want:016x})")

print(f"\n=== MBARRIER physical layout: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
