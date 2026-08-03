import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat

# ---------------------------------------------------------------------------
# CLMAD + IDP — GF(2) carryless multiply-add and byte dot-product
# Verified on SM120.
#
#   CLMAD.LO/HI {Rd,Rd+1}, {Ra,Ra+1}, {Rb,Rb+1}, {Rc,Rc+1}   (fma64lite_pipe)
#       lo: Rd = (a otimes b)[63:0] ^ c ;  hi: Rd = (a otimes b)[127:64] ^ c
#       (PTX clmad.lo/hi.u64; carryless / GF(2)[x] polynomial multiply)
#
#   IDP.4A.<U8|S8>.<U8|S8> Rd, Ra, Rb, [-|Rc]                (dp4a)
#       Rd = Rc + sum_i sign/zeroext(a.b[i]) * sign/zeroext(b.b[i])  (i=0..3)
#       SrcAFmt = a bytes, SrcBFmt = b bytes; `-Rc` negates the accumulator.
#
#   IDP.2A.LO/HI.<U16|S16>.<U8|S8> Rd, Ra, Rb, [-|Rc]        (dp2a)
#       a = two 16-bit values; b = four 8-bit values; LO uses b[0:1],
#       HI uses b[2:3].  Rd = Rc + sum_i Va[i] * Vb[LO?i:i+2].
#
# Both are COUPLED_MATH (fixed latency, no own scoreboard) — load inputs with
# wr=SB1, op req={1}; store the result after a small natural gap.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<46} got 0x{got & 0xffffffffffffffff:016x} "
          f"want 0x{want & 0xffffffffffffffff:016x}")

M64 = (1 << 64) - 1

def clmul(a, b):
    """GF(2)[x] carryless product of two 64-bit values -> 128-bit."""
    r = 0
    for i in range(64):
        if (b >> i) & 1:
            r ^= a << i
    return r

def clmad(lo_hi, a, b, c):
    p = clmul(a, b)
    half = (p & M64) if lo_hi == "LO" else (p >> 64)
    return (half ^ c) & M64

def s8(v):  return v - 256 if v & 0x80 else v
def s16(v): return v - 65536 if v & 0x8000 else v

def dp4a(af, bf, a, b, c):
    A = [a & 0xFF, (a >> 8) & 0xFF, (a >> 16) & 0xFF, (a >> 24) & 0xFF]
    B = [b & 0xFF, (b >> 8) & 0xFF, (b >> 16) & 0xFF, (b >> 24) & 0xFF]
    if af == "S8": A = [s8(x) for x in A]
    if bf == "S8": B = [s8(x) for x in B]
    return (c + sum(x * y for x, y in zip(A, B))) & 0xFFFFFFFF

def dp2a(mode, af, bf, a, b, c):
    Va = [a & 0xFFFF, (a >> 16) & 0xFFFF]
    Vb = [b & 0xFF, (b >> 8) & 0xFF, (b >> 16) & 0xFF, (b >> 24) & 0xFF]
    if af == "S16": Va = [s16(x) for x in Va]
    if bf == "S8":  Vb = [s8(x) for x in Vb]
    sel = 0 if mode == "LO" else 2
    return (c + Va[0] * Vb[sel] + Va[1] * Vb[sel + 1]) & 0xFFFFFFFF

def run_clmad(lo_hi, a, b, c):
    lines = ["    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]",
             "    LDC.64 {R0,R1}, #param(a);[1:7:{}:1:0]",
             "    LDC.64 {R2,R3}, #param(b);[1:7:{}:1:0]",
             "    LDC.64 {R4,R5}, #param(c);[1:7:{}:1:0]",
             # CLMAD is COUPLED_EMULATABLE (VQ_REDIRECTABLE, variable latency):
             # write the result scoreboard (wr=2) and let the stores req it.
             f"    CLMAD.{lo_hi} {{R8,R9}}, {{R0,R1}}, {{R2,R3}}, {{R4,R5}};[2:7:{{1}}:8:1]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R0;[0:1:{1}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R2;[0:1:{1}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R4;[0:1:{1}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0xC], R8;[0:1:{1,2}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R9;[0:1:{1,2}:1:0]"]
    src = "#fn k(out<8>, a<8>, b<8>, c<8>) {\n" + "\n".join(lines) + "\n    EXIT;[7:7:{}:5:0]\n}"
    mod = CudaModule(assemble(src))
    d = mod.devmem_alloc(32)
    try:
        mod.launch("k", grid=(1,), block=(1,), args=[d, a, b, c])
        mod.synchronize()
        v = struct.unpack("<8I", mod.device_read(d, 32))
        return v[3] | (v[4] << 32)
    finally:
        mod.devmem_free(d)

def run_idp(instr, a, b, c):
    lines = ["    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]",
             "    LDC R0, #param(a);[1:7:{}:1:0]",
             "    LDC R1, #param(b);[1:7:{}:1:0]",
             "    LDC R2, #param(c);[1:7:{}:1:0]",
             "    " + instr,
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R0;[0:1:{}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R1;[0:1:{}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R2;[0:1:{}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0xC], R10;[0:1:{}:1:0]"]
    src = "#fn k(out<8>, a<4>, b<4>, c<4>) {\n" + "\n".join(lines) + "\n    EXIT;[7:7:{}:5:0]\n}"
    mod = CudaModule(assemble(src))
    d = mod.devmem_alloc(16)
    try:
        mod.launch("k", grid=(1,), block=(1,), args=[d, a, b, c])
        mod.synchronize()
        return struct.unpack("<4I", mod.device_read(d, 16))[3]
    finally:
        mod.devmem_free(d)

# --- CLMAD -----------------------------------------------------------------
for lo_hi in ("LO", "HI"):
    cases = [(0x3, 0x3, 0x0),           # carryless 3⊗3=5 (not 9!)
             (0x2, 0x3, 0x1),
             (0x5, 0x3, 0x7),
             (0x1, 0x1, 0xFFFFFFFFFFFFFFFF),
             (0x8000000000000000, 0x8000000000000000, 0x5),
             (0x123456789ABCDEF0, 0xFEDCBA9876543210, 0x0),
             (0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF, 0x0)]
    for a, b, c in cases:
        r = run_clmad(lo_hi, a, b, c)
        check(f"CLMAD.{lo_hi} a=0x{a:016x} b=0x{b:016x} c=0x{c:016x}",
              r, clmad(lo_hi, a, b, c))

# --- IDP.4A (dp4a) ---------------------------------------------------------
A4 = 0x01234567   # bytes 67 45 23 01
B4 = 0x81828384   # bytes 84 83 82 81 (sign bits set on 0x84/0x83/0x82/0x81)
for af, bf in [("U8", "U8"), ("U8", "S8"), ("S8", "U8"), ("S8", "S8")]:
    r = run_idp(f"IDP.4A.{af}.{bf} R10, R0, R1, R2;[7:7:{{1}}:8:1]", A4, B4, 5)
    check(f"IDP.4A.{af}.{bf}", r, dp4a(af, bf, A4, B4, 5))
# negated accumulator
r = run_idp("IDP.4A.U8.U8 R10, R0, R1, -R2;[7:7:{1}:8:1]", A4, B4, 5)
check("IDP.4A.U8.U8 -Rc (negate accumulator)", r, dp4a("U8", "U8", A4, B4, -5))

# --- IDP.2A (dp2a) ---------------------------------------------------------
A2 = 0x00010002   # Va = [0x0002, 0x0001]
B2 = 0x00000102   # Vb = [0x02, 0x01, 0x00, 0x00]
for mode in ("LO", "HI"):
    for af, bf in [("U16", "U8"), ("U16", "S8"), ("S16", "S8")]:
        r = run_idp(f"IDP.2A.{mode}.{af}.{bf} R10, R0, R1, R2;[7:7:{{1}}:8:1]", A2, B2, 1)
        check(f"IDP.2A.{mode}.{af}.{bf}", r, dp2a(mode, af, bf, A2, B2, 1))

# --- offline encoding self-check vs ptxas ----------------------------------
enc = assemble_flat(
    "IDP.4A.U8.U8 R11, R0, R9, R4;[7:7:{}:5:1]\n"
    "IDP.4A.U8.S8 R13, R0, R9, R4;[7:7:{}:5:1]\n"
    "IDP.4A.S8.U8 R15, R0, R9, R4;[7:7:{}:5:1]\n"
    "IDP.4A.S8.S8 R17, R0, R9, R4;[7:7:{}:5:1]\n"
    "IDP.2A.LO.U16.U8 R19, R0, R9, R4;[7:7:{}:5:1]\n"
    "IDP.2A.HI.U16.S8 R21, R0, R9, R4;[7:7:{}:5:1]\n"
    "IDP.2A.LO.S16.S8 R9, R0, R9, R4;[7:7:{}:5:1]\n"
    "CLMAD.LO {R2,R3}, {R4,R5}, {R6,R7}, {R8,R9};[7:7:{}:8:1]\n"
    "CLMAD.HI {R2,R3}, {R4,R5}, {R6,R7}, {R8,R9};[7:7:{}:8:1]\n")
ref_lo = [0x00000009000b7226, 0x00000009000d7226, 0x00000009000f7226,
          0x0000000900117226, 0x0000000900137226, 0x0000000900157226,
          0x0000000900097226]
ref_hi = [0x004fc40000000004, 0x1c0fe40000000404, 0x1c0fe20000000204,
          0x1c0fe40000000604, 0x1c0fe20000001004, 0x1c0fe40000003404,
          0x000fe20000001604]
for i in range(7):
    lo, hi = enc[i]
    assert lo == ref_lo[i], f"IDP lo 0x{lo:x} != 0x{ref_lo[i]:x}"
    assert (hi & 0xFFFF) == (ref_hi[i] & 0xFFFF), f"IDP hi 0x{hi:x}"
assert ((enc[7][1] >> 13) & 1) == 0 and ((enc[8][1] >> 13) & 1) == 1, "CLMAD hilo"
print("encoding self-check: IDP 4A/2A all formats + CLMAD.LO/.HI match ptxas")

print(f"\n=== CLMAD / IDP: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
