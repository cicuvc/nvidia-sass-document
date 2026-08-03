import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# R2UR — register to uniform register (udp_pipe; verified SM120, RTX 5090)
#
#   R2UR [Pu,] URd, Ra | R2UR.OR Pu, URd, Ra | R2UR.FILL/BROADCAST ... (0x2ca)
#
# Verified semantics on silicon:
#   * URd = the value of Ra in the FIRST ACTIVE lane (lowest active laneid
#     under the guard predicate).  Full warp  -> lane 0's value; @P0 with
#     lanes 8..31 active -> lane 8's value; @!P0 (lanes 0..7) -> lane 0's.
#   * The .OR variant does NOT perform a cross-lane OR-reduce (REDUX.OR is
#     the real reduction: OR(1..32) == 0x3F verified).  .FILL/.BROADCAST
#     (Blackwell nonconformity encodings) behave identically to the plain
#     form in every configuration probed.
#   * Pu (destination predicate) read back 0 via P2R in all probed cases
#     (uniform/divergent source, full/partial mask) — role unresolved.
#   * 64-bit register->uniform moves are two R2URs (low then high word).
# ---------------------------------------------------------------------------

# Reference encodings (schedule [2:7:{}:5:1] = wr_sb 2, WAIT5_END_GROUP).
# Note: the noOR nonconformity variants show Pu when it is explicit; the
# hidden-PT default encodes 0b111 at [83:81] (hi bits 0xe0000).
REF = [
    (0x00000000021072ca, 0x000fca00000e0000, "R2UR UR16, R2"),
    (0x00000000021072ca, 0x000fca0000100000, "R2UR.OR P0, UR16, R2"),
    (0x00000000021072ca, 0x000fca0000400000, "R2UR.FILL P0, UR16, R2"),
    (0x00000000021072ca, 0x000fca0000800000, "R2UR.BROADCAST P0, UR16, R2"),
    (0x00000000021072ca, 0x000fca00004e0000, "R2UR.FILL UR16, R2 (Pu=PT default)"),
    (0x00000000021072ca, 0x000fca00008e0000, "R2UR.BROADCAST UR16, R2 (Pu=PT default)"),
]
flat = assemble_flat("""R2UR UR16, R2;[2:7:{}:5:1]
R2UR.OR P0, UR16, R2;[2:7:{}:5:1]
R2UR.FILL P0, UR16, R2;[2:7:{}:5:1]
R2UR.BROADCAST P0, UR16, R2;[2:7:{}:5:1]
R2UR.FILL UR16, R2;[2:7:{}:5:1]
R2UR.BROADCAST UR16, R2;[2:7:{}:5:1]
""")
ok = True
for i, (lo, hi, name) in enumerate(REF):
    good = flat[i] == (lo, hi)
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes {name:24s} lo={flat[i][0]:016x} hi={flat[i][1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def settle_store(ur, rd, off):
    """Settle a udp-written URx then store it via IADD3 RUR to out+off."""
    return f"""    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR9, {ur};[7:7:{{}}:5:1]
    UMOV UR14, {ur};[7:7:{{2}}:5:1]
    IADD3 {rd}, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], {rd};[7:7:{{0,1}}:1:0]
"""


def kernel(body):
    return f"""#fn t(out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
{body}    EXIT;[7:7:{{}}:5:0]
}}"""


def run(body, block=32):
    reset_context()
    mod = build(kernel(body))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(block,), args=[d])
    mod.synchronize()
    data = mod.device_read(d, 0x40)
    mod.devmem_free(d)
    return struct.unpack("<16I", data)


try:
    build(kernel(""))
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

UNI = "    MOV32I R2, 0x12345678;[2:7:{}:5:1]\n"
DIV = """    S2R R2, SR_LANEID;[0:7:{}:5:1]
    IADD3 R2, R2, 1, RZ;[7:7:{0}:5:1]
"""
MASK = """    S2R R8, SR_LANEID;[0:7:{}:5:1]
    IADD3 R8, R8, 1, RZ;[7:7:{0}:5:1]
    ISETP.GE.AND P0, PT, R8, 0x9, PT;[7:7:{}:13:1]
"""

# uniform source -> exact value through every encoding variant
for label, inst in [("noOR", "R2UR UR16, R2"),
                    ("OR", "R2UR.OR P0, UR16, R2"),
                    ("FILL", "R2UR.FILL UR16, R2"),
                    ("BROADCAST", "R2UR.BROADCAST UR16, R2")]:
    v = run(UNI + f"    {inst};[2:7:{{}}:5:1]\n" + settle_store("UR16", "R20", 0x0))[0]
    good = v == 0x12345678
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} uniform {label:10s} -> 0x{v:08x} (exp 0x12345678)")

# divergent source: full warp elects lane 0 (value 1)
v = run(DIV + "    R2UR UR16, R2;[2:7:{}:5:1]\n" + settle_store("UR16", "R20", 0x0))[0]
good = v == 1
ok &= good
print(f"{'ok ' if good else 'FAIL'} divergent full-warp noOR -> {v} (exp 1 = lane0's lane+1)")

# .OR is NOT a cross-lane OR-reduce (REDUX.OR control = 0x3f)
v = run(DIV + "    R2UR.OR P0, UR16, R2;[2:7:{}:5:1]\n" + settle_store("UR16", "R20", 0x0))[0]
good = v == 1
ok &= good
print(f"{'ok ' if good else 'FAIL'} divergent .OR -> {v} (exp 1; NOT 0x3f — REDUX.OR is the real reduce)")

v = run(DIV + "    REDUX.OR UR16, R2;[2:7:{}:5:1]\n" + settle_store("UR16", "R20", 0x0))[0]
good = v == 0x3F
ok &= good
print(f"{'ok ' if good else 'FAIL'} REDUX.OR control -> 0x{v:02x} (exp 0x3f = OR of 1..32)")

# partial active mask: first active lane is lane 8 -> its value is 9
for label, inst in [("noOR", "R2UR UR16, R2"),
                    ("OR", "R2UR.OR P1, UR16, R2"),
                    ("FILL", "R2UR.FILL UR16, R2"),
                    ("BROADCAST", "R2UR.BROADCAST UR16, R2")]:
    v = run(DIV + MASK + f"    @P0 {inst};[2:7:{{}}:5:1]\n" + settle_store("UR16", "R20", 0x0))[0]
    good = v == 9
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} partial-mask @P0 {label:10s} -> {v} (exp 9 = first active lane 8)")

# negated guard: active lanes 0..7, first active lane 0 -> 1
v = run(DIV + MASK + "    @!P0 R2UR UR16, R2;[2:7:{}:5:1]\n" + settle_store("UR16", "R20", 0x0))[0]
good = v == 1
ok &= good
print(f"{'ok ' if good else 'FAIL'} partial-mask @!P0 noOR -> {v} (exp 1 = first active lane 0)")

# 64-bit register pair -> two R2URs (low then high word)
vals = run("""    MOV32I R2, 0xDEADBEEF;[2:7:{}:5:1]
    MOV32I R3, 0x12345678;[3:7:{}:5:1]
    R2UR UR16, R2;[4:7:{}:5:1]
    R2UR UR17, R3;[5:7:{}:5:1]
""" + settle_store("UR16", "R20", 0x0) + settle_store("UR17", "R21", 0x4))
good = vals[0] == 0xDEADBEEF and vals[1] == 0x12345678
ok &= good
print(f"{'ok ' if good else 'FAIL'} 64-bit pair -> lo=0x{vals[0]:08x} hi=0x{vals[1]:08x} (exp DEADBEEF/12345678)")

print("\n=== R2UR semantic verification: ALL OK ===" if ok else "\n=== R2UR FAILURES ===")
sys.exit(0 if ok else 1)
