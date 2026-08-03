import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# PDL (Programmatic Dependent Launch) via griddepcontrol — ACQBULK + PREEXIT
# (verified SM120, CUDA 12.8 / driver 580.65, RTX 5090)
#
# PTX griddepcontrol maps to two operand-less SASS ops on cbu_pipe:
#   griddepcontrol.wait               -> ACQBULK   (consumer acquire, 0x82e)
#   griddepcontrol.launch_dependents  -> PREEXIT   (producer signal,  0x82d)
#
# Control words emitted by ptxas (sm_120):
#   ACQBULK  [7:7:{}:6:1]  -> ?WAIT6_END_GROUP   opex=6
#   PREEXIT  [7:7:{}:3:0]  -> ?trans3            opex=19 (stall+16)
# (on sm_90 ptxas emits PREEXIT with ?trans8/opex=24 instead — same opcode,
#  different scheduling word; the assembler's bracket reproduces either.)
#
# The assembler reproduces the ptxas encodings bit-for-bit, and the built
# cubins round-trip through cuobjdump as ACQBULK/PREEXIT.  On the GPU,
# launching producer (PREEXIT) then consumer (ACQBULK) on one stream with
# CU_LAUNCH_ATTRIBUTE_PROGRAMMATIC_STREAM_SERIALIZATION makes the consumer
# observe the producer's pre-PREEXIT write (release/acquire pair).
# ---------------------------------------------------------------------------

# Reference encodings captured from `nvcc -arch=sm_120 tests/griddep.cu` +
# `cuobjdump -arch sm_120 -sass` (CUDA 12.8).
REF = {
    "ACQBULK":       (0x000000000000782e, 0x000fcc0000000000),  # ?WAIT6_END_GROUP
    "PREEXIT":       (0x000000000000782d, 0x000fe60000000000),  # ?trans3
    "PREEXIT@P1":    (0x000000000000182d, 0x000fe60000000000),  # @P1 guard
    "ACQBULK@!PT":   (0x000000000000f82e, 0x000fcc0000000000),  # @!PT never-run
}

PROD_SRC = """#fn prod(a<8>, out<8>) {
    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6, R7}, #param(a);[0:7:{}:1:0]
    MOV32I R2, 0x1234;[7:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R2;[0:1:{0}:1:0]
    PREEXIT;[7:7:{}:3:0]
    EXIT;[7:7:{}:5:0]
}"""

CONS_SRC = """#fn cons(a<8>, out<8>) {
    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6, R7}, #param(a);[0:7:{}:1:0]
    LDC.64 {R8, R9}, #param(out);[0:7:{}:1:0]
    ACQBULK;[7:7:{}:6:1]
    LDG.E R20, desc[{UR4,UR5}][{R6,R7}+0x0];[1:7:{0}:5:1]
    IADD3 R22, PT, PT, R20, 0x1, RZ;[7:7:{1}:5:1]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x0], R22;[0:1:{0}:1:0]
    EXIT;[7:7:{}:5:0]
}"""

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}")


# ---- 1) bit-for-bit encoding vs ptxas sm_120 reference (no GPU needed) ----
flat = assemble_flat("""ACQBULK;[7:7:{}:6:1]
PREEXIT;[7:7:{}:3:0]
@P1 PREEXIT;[7:7:{}:3:0]
@!PT ACQBULK;[7:7:{}:6:1]
""")
for name, enc in zip(("ACQBULK", "PREEXIT", "PREEXIT@P1", "ACQBULK@!PT"), flat):
    check(f"bytes {name}", enc, REF[name])
print("reference encodings:")
for name, (lo, hi) in REF.items():
    print(f"  {name:12s} lo={lo:016x} hi={hi:016x}")

# ---- 2) build the PDL kernels with the assembler ----
prod = assemble(PROD_SRC)
cons = assemble(CONS_SRC)

# ---- 3) GPU behavior ----
try:
    mod_prod = CudaModule(prod)
    mod_cons = CudaModule(cons)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print("\nGPU:", mod_prod.device_name)

def launch_once(mod, name, pdl):
    d = mod_prod.devmem_alloc(4096)
    mod_prod.device_write(d, struct.pack("<256I", *([0] * 256)))
    mod.launch_ex(name, grid=(1,), block=(32,), args=[d, d],
                  programmatic_serialization=pdl)
    mod.synchronize()
    v = struct.unpack("<I", mod_prod.device_read(d, 4))[0]
    mod_prod.devmem_free(d)
    return v

# producer alone: PREEXIT signals and continues; a[0] = 0x1234
v = launch_once(mod_prod, "prod", pdl=True)
check("PREEXIT producer alone: a[0]", hex(v), "0x1234")

# consumer alone (a=0): ACQBULK with no prerequisite returns at once; out = 1
v = launch_once(mod_cons, "cons", pdl=True)
check("ACQBULK consumer alone: out[0]", v, 1)

# PDL pair on one stream: prod(PREEXIT) -> cons(ACQBULK); consumer must see
# the write published before PREEXIT (0x1234 + 1 = 0x1235).
d = mod_prod.devmem_alloc(4096)
mod_prod.device_write(d, struct.pack("<256I", *([0] * 256)))
mod_prod.launch_ex("prod", grid=(1,), block=(32,), args=[d, d],
                   programmatic_serialization=True)
mod_cons.launch_ex("cons", grid=(1,), block=(32,), args=[d, d],
                   programmatic_serialization=True)
mod_prod.synchronize()
v = struct.unpack("<I", mod_prod.device_read(d, 4))[0]
mod_prod.devmem_free(d)
check("PDL pair out[0] (release/acquire)", v, 0x1235)

print("\n=== PDL (griddepcontrol -> ACQBULK/PREEXIT) via assembler: ALL OK ===" if ok
      else "\n=== PDL verification FAILED ===")
sys.exit(0 if ok else 1)
