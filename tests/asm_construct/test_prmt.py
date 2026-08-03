import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat

# ---------------------------------------------------------------------------
# PRMT — byte permute (int_pipe).  Verified on SM120.
#
#   PRMT Rd, Ra, Rb, Rc        RRR:  Ra=sourceA, Rb=SELECTOR, Rc=sourceB
#   PRMT[.F4E|.B4E|.RC8|.ECL|.ECR|.RC16] Rd, Ra, Rb, Rc
#   PRMT Rd, Ra, imm, Rc       RIR:  imm=SELECTOR, Rc=sourceB
#   PRMT Rd, Ra, Rb, imm       RRuI: Rb=SELECTOR, imm=sourceB
#
# Semantics (PTX prmt, ISA 9.3 §9.7.9.7):
#   tmp64 = (sourceB << 32) | sourceA   -> byte k of the 8-byte source:
#        byte 0..3 = sourceA.b0..b3, byte 4..7 = sourceB.b0..b3
#   IDX: 4 selectors (c[3:0],c[7:4],c[11:8],c[15:12]) pick, LSB-first:
#        0-7 -> copy source byte n; 8-15 -> sign-extend byte (n-8).
#   specialized modes: all four outputs use the SAME selector = c[1:0],
#        then a fixed 4-row pattern table picks the source bytes.
#
# ptxas maps prmt.b32(.mode) -> PRMT(.MODE) RRR directly.
#
# Gotcha: the SASS operand order is Rd, Ra, Rb=selector, Rc=sourceB — the
# selector is the THIRD operand.  PRMT is int_pipe COUPLED_MATH (no own
# scoreboard); load the inputs with wr=SB1 and let PRMT req={1} wait.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<42} got 0x{got & 0xffffffff:08x} "
          f"want 0x{want & 0xffffffff:08x}")

# source byte numbering for Ra=0x01020304 Rb=0x05060708:
#   byte0=04 byte1=03 byte2=02 byte3=01 byte4=08 byte5=07 byte6=06 byte7=05
BY = [0x04, 0x03, 0x02, 0x01, 0x08, 0x07, 0x06, 0x05]

def idx_expected(ctrl):
    """IDX-mode expected value from a 16-bit selector, LSB-first nibbles.
    nibble 0-7 = copy source byte; 8-15 = sign-extend byte (n-8) into the
    target byte (bit 7 replicated -> 0x00 or 0xFF)."""
    v = 0
    for i in range(4):
        s = (ctrl >> (4 * i)) & 0xF
        b = BY[s & 7]
        if s & 8:
            b = 0xFF if (b & 0x80) else 0x00
        v |= b << (8 * i)
    return v & 0xFFFFFFFF

TABLES = {  # mode -> row[c[1:0]] = [d.b3, d.b2, d.b1, d.b0] source indices
    "F4E":  [[3,2,1,0],[4,3,2,1],[5,4,3,2],[6,5,4,3]],
    "B4E":  [[5,6,7,0],[6,7,0,1],[7,0,1,2],[0,1,2,3]],
    "RC8":  [[0,0,0,0],[1,1,1,1],[2,2,2,2],[3,3,3,3]],
    "ECL":  [[3,2,1,0],[3,2,1,1],[3,2,2,2],[3,3,3,3]],
    "ECR":  [[0,0,0,0],[1,1,1,0],[2,2,1,0],[3,2,1,0]],
    "RC16": [[1,0,1,0],[3,2,3,2],[1,0,1,0],[3,2,3,2]],
}

def mod_expected(mode, c):
    i3, i2, i1, i0 = TABLES[mode][c & 3]
    return (BY[i3] << 24) | (BY[i2] << 16) | (BY[i1] << 8) | BY[i0]

def run_case(instr, params, count):
    """One kernel per case: LDC a/b/sel into R0/R1/R4 (all wr=SB1), run
    `instr`, store inputs + result.  The 3 input stores before the result
    store give the PRMT writeback time to land (int_pipe COUPLED)."""
    lines = ["    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
             "    LDC R0, #param(a);[1:7:{}:1:0]",
             "    LDC R1, #param(b);[1:7:{}:1:0]",
             "    LDC R4, #param(sel);[1:7:{}:1:0]",
             "    " + instr,
             "    STG.E desc[{UR4,UR5}][{R2,R3}+0x0], R0;[0:1:{}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R2,R3}+0x4], R1;[0:1:{}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R2,R3}+0x8], R4;[0:1:{}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R2,R3}+0xC], R10;[0:1:{}:1:0]"]
    src = ("#fn k(out<8>, a<4>, b<4>, sel<4>) {\n"
           + "\n".join(lines) + "\n    EXIT;[7:7:{}:5:0]\n}")
    mod = CudaModule(assemble(src))
    d = mod.devmem_alloc(16)
    try:
        mod.launch("k", grid=(1,), block=(1,), args=[d] + list(params))
        mod.synchronize()
        return struct.unpack("<4I", mod.device_read(d, 16))[3]
    finally:
        mod.devmem_free(d)

A, B = 0x01020304, 0x05060708

# --- IDX mode RRR ----------------------------------------------------------
for sel, name in [(0x76543210, "identity"),
                  (0x5410, "pack"),
                  (0x7456, "from-sourceB"),
                  (0x00000000, "all byte0"),
                  (0xFFFFFFFF, "all sx byte7"),
                  (0x88888888, "all sx byte0"),
                  (0x08080808, "sx/b0/sx/b0"),
                  (0x1234, "arbitrary 1234")]:
    r = run_case(f"PRMT R10, R0, R4, R1;[7:7:{{1}}:8:1]", [A, B, sel], 1)
    check(f"IDX RRR sel=0x{sel:08x} ({name})", r, idx_expected(sel))

# --- RIR (imm selector) + RRuI (imm sourceB) -------------------------------
r = run_case("PRMT R10, R0, 0x5410, R1;[7:7:{1}:8:1]", [A, B, 0], 1)
check("RIR imm=0x5410 selector", r, idx_expected(0x5410))
r = run_case("PRMT R10, R0, R4, 0x05060708;[7:7:{1}:8:1]", [A, B, 0x5410], 1)
check("RRuI imm=0x05060708 sourceB, sel=R4", r, idx_expected(0x5410))

# --- specialized modes (c[1:0] from R4) ------------------------------------
for mode in TABLES:
    for c in range(4):
        r = run_case(f"PRMT.{mode} R10, R0, R4, R1;[7:7:{{1}}:8:1]",
                     [A, B, c], 1)
        check(f"{mode} c={c}", r, mod_expected(mode, c))

# --- offline encoding self-check -------------------------------------------
enc = assemble_flat(
    "PRMT R3, R0, R1, R2;[7:7:{}:5:1]\n"
    "PRMT.F4E R3, R0, R1, R2;[7:7:{}:5:1]\n"
    "PRMT.RC16 R3, R0, R1, R2;[7:7:{}:5:1]\n"
    "PRMT R3, R0, 0x5410, R2;[7:7:{}:5:1]\n"
    "PRMT R3, R0, R1, 0x5;[7:7:{}:5:1]\n"
    "PRMT R3, R0, UR1, R2;[7:7:{}:5:1]\n")
def op(lo, hi):
    return ((hi >> 27) & 1) << 12 | (lo & 0xFFF), (hi >> 8) & 7
got = [op(*e) for e in enc]
expect = [(0x216, 0), (0x216, 1), (0x216, 6), (0x816, 0), (0x416, 0), (0x1c16, 0)]
assert got == expect, f"{got} != {expect}"
print("encoding self-check: RRR/RIR/RRuI/RUR opcodes + pmode OK")

print(f"\n=== PRMT (byte permute): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
