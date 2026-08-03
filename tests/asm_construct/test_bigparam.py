import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# Kernel parameters larger than 8 bytes (e.g. a __grid_constant__ CUtensorMap
# is 128 bytes) must be laid out at their real size in the parameter block and
# passed to cuLaunchKernel with the matching byte width.
#
# The kernel declaration's <size> is the parameter's byte width (pointer = 8,
# tensor map = 128), NOT the size of the buffer a pointer points at.  The
# runner extracts per-parameter sizes from the cubin's EIATTR_KPARAM_INFO
# (size code = (size<<2)|1) and packs int args as 8-byte slots and
# bytes/bytearray args at their full size.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    if isinstance(got, tuple):
        print(f"{'ok ' if good else 'FAIL'} {name:<40} {got} (exp {want})")
    else:
        print(f"{'ok ' if good else 'FAIL'} {name:<40} {got:#x} (exp {want:#x})")

# param layout: out<8> @ 0x380, big<128> @ 0x388.  Read big[4..7] (c[0x0][0x38c]).
KERNEL = """#fn k(out<8>, big<128>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]
    LDC.32 R0, c[0x0][0x38c];[1:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R0;[0:1:{0,1}:1:0]
    EXIT;[7:7:{}:5:0]
}"""

mod = CudaModule(assemble(KERNEL))
d = mod.devmem_alloc(16)

# big = 128 distinct bytes; the word at big[4..7] = 0x07 06 05 04 -> LE 0x07060504
big = bytes(range(128))
mod.launch("k", grid=(1,), block=(1,), args=[d, big])
mod.synchronize()
check("128-byte param (big[4..7])", struct.unpack("<I", mod.device_read(d, 4))[0], 0x07060504)

# param sizes extracted from the cubin
from assembler.runner import _extract_param_sizes
sizes = _extract_param_sizes(assemble(KERNEL))
check("extracted param sizes", tuple(sizes) if sizes else (), (8, 128))

print(f"\n=== big kernel params: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
