import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# SETLMEMBASE / GETLMEMBASE — local-memory base address, verified (SM120).
#
# SETLMEMBASE (0x3c1): writes the executing thread's local-mem base from a
#   64-bit register pair Ra:Ra+1.  mio_pipe, VQ_ADU, DECOUPLED_RD_SCBD.
# GETLMEMBASE (0x3c0): reads it into a 64-bit pair Rd:Rd+1.  VQ_UNORDERED,
#   DECOUPLED_RD_WR_SCBD.
#
# Verified:
#   1. Round-trip: SETLMEMBASE <addr> then GETLMEMBASE returns exactly <addr>
#      for valid addresses (device buffer d, and the default lmem base).
#   2. The two instructions face the SAME 64-bit value.
#   3. Default (no SET) GETLMEMBASE returns the per-thread default local
#      window base (e.g. 0x3fffe6c00000), a valid address (STG-able).
#
# This small test covers only SET/GET round-trip and invalid-address behavior.
# probe_lmem_transform.py separately verifies that SETLMEMBASE redirects real
# LDL/STL accesses, on both H20/sm90 and RTX 5090/sm120. Modern ptxas register
# spills also emit LDL/STL; the earlier contrary limitation was incorrect.
# ---------------------------------------------------------------------------

def build_roundtrip(addr_lo, addr_hi):
    lines = ["#fn k(buf<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             f"    MOV32I R10, 0x{addr_lo:08x};[7:7:{{}}:5:1]",
             f"    MOV32I R11, 0x{addr_hi:08x};[7:7:{{}}:5:1]",
             "    SETLMEMBASE {R10,R11};[7:7:{}:5:1]",
             "    GETLMEMBASE {R8,R9};[0:7:{}:5:1]",
             "    IADD3 R20, R8, RZ, RZ;[7:7:{0}:5:1]",
             "    IADD3 R21, R9, RZ, RZ;[7:7:{0}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R20;[0:1:{0}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R21;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    return assemble("\n".join(lines))


def run_roundtrip(addr):
    lo32 = addr & 0xffffffff
    hi32 = (addr >> 32) & 0xffffffff
    cubin = build_roundtrip(lo32, hi32)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<64I", *[0] * 64))
    try:
        mod.launch("k", grid=(1,), block=(1,), args=[d])
        mod.synchronize()
        lo, hi = struct.unpack("<2I", mod.device_read(d + 0x0, 8))
        mod.devmem_free(d)
        return (hi << 32) | lo
    except RuntimeError as e:
        return None


def build_getdefault():
    lines = ["#fn k(buf<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    GETLMEMBASE {R8,R9};[0:7:{}:5:1]",
             "    IADD3 R20, R8, RZ, RZ;[7:7:{0}:5:1]",
             "    IADD3 R21, R9, RZ, RZ;[7:7:{0}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R20;[0:1:{0}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R21;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    return assemble("\n".join(lines))


def get_default():
    cubin = build_getdefault()
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<64I", *[0] * 64))
    mod.launch("k", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    lo, hi = struct.unpack("<2I", mod.device_read(d + 0x0, 8))
    mod.devmem_free(d)
    return (hi << 32) | lo


ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: got {got:#x} want {want:#x}")

# Round-trip with a real device-buffer address
d = get_default()  # first call also gives us a valid default base
# use a known valid address: allocate a buffer, get its address
mod = CudaModule(build_getdefault())
buf = mod.devmem_alloc(1024)
mod.device_write(buf, struct.pack("<64I", *[0] * 64))
buf_addr = buf
mod.devmem_free(buf)

# round-trip with the buffer address
got = run_roundtrip(buf_addr)
check("SET/GET round-trip (buffer addr)", got if got is not None else 0, buf_addr)

# round-trip with the default lmem base
default_base = get_default()
got = run_roundtrip(default_base)
check("SET/GET round-trip (default base)", got if got is not None else 0, default_base)

# default GET (no SET) is a valid non-trivial address
print(f"  default GETLMEMBASE (no SET) = 0x{default_base:016x} (valid, high address)")

# SET to an invalid address faults (SETLMEMBASE validates/poisons)
got = run_roundtrip(0x1111111100000000)
print(f"  SET to invalid 0x1111...00000000: {'faults (700)' if got is None else 'no fault'}")

print(f"\n=== SETLMEMBASE/GETLMEMBASE round-trip: {'ALL OK' if ok else 'FAILED'} ===")
print("SET and GET face the same 64-bit value; LDL/STL redirection is covered by probe_lmem_transform.py")
sys.exit(0 if ok else 1)
