import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule
from tools.decode_qspc import decode

# ---------------------------------------------------------------------------
# QSPC — query address-space predicate (SASS lowering of PTX isspacep).
# mio_pipe, VQ_AGU, decoupled RD/WR scoreboard.
#
# Encodings verified:
#   * ptxas (CUDA 12.8, sm_90) emits only the full form with Rd=RZ and .E:
#       QSPC.E.<SP> P0, RZ, [RZ.U32+URb]        (URB base; opcode 0x19aa)
#       QSPC.E.<SP> P0, RZ, [Ra]                (GPR base; opcode 0x3aa)
#   * the noe (32-bit), Ra32/Ra64-URb, PuOnly and RdOnly classes exist in the
#     spec and round-trip through the assembler/decoder.
#
# The GPU section verifies semantics with real window bases read from the
# constant bank (c[0x0][0x18] shared / c[0x0][0x20] local generic bases).
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<52} {got}")

# --- 1. offline: assembler -> decoder round-trip ---------------------------
ROUNDTRIP = [
    # (sass, expected decode of the encoded instruction)
    ("QSPC.E.G P0, RZ, [RZ+UR4];[0:7:{}:1:0]",
     "QSPC.E.G P0, RZ, [RZ.U32+UR4]"),
    ("QSPC.E.L P0, RZ, [RZ+UR4];[0:7:{}:1:0]",
     "QSPC.E.L P0, RZ, [RZ.U32+UR4]"),
    ("QSPC.E.S P1, RZ, [RZ+UR4];[0:7:{}:1:0]",
     "QSPC.E.S P1, RZ, [RZ.U32+UR4]"),
    ("QSPC.E.D P0, RZ, [RZ+UR4];[0:7:{}:1:0]",
     "QSPC.E.D P0, RZ, [RZ.U32+UR4]"),
    ("QSPC.E.G P0, RZ, [UR8];[0:7:{}:1:0]",          # compact [URb] == [RZ+URb]
     "QSPC.E.G P0, RZ, [RZ.U32+UR8]"),
    ("QSPC.G P0, RZ, [RZ+UR4];[0:7:{}:1:0]",         # noe = 32-bit
     "QSPC.G P0, RZ, [RZ.U32+UR4]"),
    ("QSPC.E.G P0, RZ, [R6];[0:7:{}:1:0]",
     "QSPC.E.G P0, RZ, [R6]"),
    ("QSPC.E.G P0, RZ, [R6+0x10];[0:7:{}:1:0]",
     "QSPC.E.G P0, RZ, [R6+0x10]"),
    ("QSPC.G P0, R0, [R2+0x10];[0:7:{}:1:0]",
     "QSPC.G P0, R0, [R2+0x10]"),
    ("QSPC.E.G P0, R0, [R4+UR4+0x8];[0:7:{}:1:0]",
     "QSPC.E.G P0, R0, [R4.U32+UR4+0x8]"),
    ("QSPC.E.G.64 P0, R0, [{R4,R5}+UR4+0x10];[0:7:{}:1:0]",
     "QSPC.E.G P0, R0, [R4.64+UR4+0x10]"),
    ("@!P0 QSPC.E.G PT, R2, [RZ+0x10];[0:7:{}:1:0]",
     "@!P0 QSPC.E.G PT, R2, [RZ+0x10]"),
]
for sass, want in ROUNDTRIP:
    (lo, hi) = assemble_flat(sass)[0]
    got = decode(lo, hi)
    check(f"roundtrip {sass.split(';')[0]}", got, want)

# --- 2. instruction fields must match real ptxas output (sm_90 CUDA 12.8) --
# (scheduling fields [opex/req/sb/pm] are excluded — ptxas picks its own
#  bracket; opcode/operands/modifiers must be bit-identical.)
def instr_fields(lo, hi):
    return (
        lo & 0x000000ffffffffff,          # opcode/ops/URb/offset, incl. Rd/Ra
        hi & ~((0xFF << 38) | (0x3F << 52) | (0x7 << 49) | (0x7 << 46) | (0x3 << 38)),
    )

REAL = [
    ("QSPC.E.G P0, RZ, [RZ+UR4];[0:7:{}:1:0]",
     0x00000004ffff79aa, 0x000e220008000100),
    ("QSPC.E.S P1, RZ, [RZ+UR4];[0:7:{}:1:0]",
     0x00000004ffff79aa, 0x000e220008020500),
    ("QSPC.E.G P0, RZ, [R6];[0:7:{}:1:0]",
     0x0000000006ff73aa, 0x000e640000000100),
]
for sass, want_lo, want_hi in REAL:
    (lo, hi) = assemble_flat(sass)[0]
    got = instr_fields(lo, hi)
    want = instr_fields(want_lo, want_hi)
    check(f"matches ptxas {sass.split(';')[0]}", got, want)

# --- 3. GPU semantic verification (skipped when no CUDA device) ------------
try:
    _ = CudaModule(assemble("#fn k() { EXIT;[7:7:{}:5:0] }"))
    HAVE_GPU = True
except RuntimeError:
    HAVE_GPU = False
    print("--- no CUDA device; GPU semantic checks SKIPPED ---")

if HAVE_GPU:
    body = (
        # Window model verified on sm_120 (RTX 5090, CUDA 13.0): the global
        # window covers [0, 0x03f00000) + [0x04000000, ...), the per-thread
        # local window is [0x03f00000, 0x04000000), and shared generic
        # addresses start at 0x100000000.  (ptxas on sm_90 used the
        # c[0x0][0x18]/[0x20] window bases, but on sm_120 those cbank slots
        # read 0 in hand-built cubins — construct the addresses directly.)
        "    LDC.64 {R8,R9}, #param(gptr);[1:7:{}:1:0]\n"
        "    MOV32I R2, 0x400;[7:7:{}:5:1]\n"           # shared lo
        "    MOV32I R3, 0x1;[7:7:{}:5:1]\n"             # shared hi -> 0x100000400
        "    UMOV UR8, 0x400;[7:7:{}:5:1]\n"            # shared lo (URB form)
        "    UMOV UR9, 0x1;[7:7:{}:5:1]\n"              # shared hi
        "    MOV32I R10, 0x3fff000;[7:7:{}:5:1]\n"      # local window
        "    MOV32I R11, 0x0;[7:7:{}:5:1]\n"
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n")
    checks = [
        # (qspc line, address regs, expected, description)
        ("QSPC.E.G P0, RZ, [R8];", 1, "global ptr: isspacep.global"),
        ("QSPC.E.S P0, RZ, [R8];", 0, "global ptr: isspacep.shared"),
        ("QSPC.E.L P0, RZ, [R8];", 0, "global ptr: isspacep.local"),
        ("QSPC.E.D P0, RZ, [R8];", 0, "global ptr: isspacep.cluster"),
        ("QSPC.E.S P0, RZ, [R2];", 1, "shared addr: isspacep.shared"),
        ("QSPC.E.D P0, RZ, [R2];", 1, "shared addr: isspacep.cluster"),
        ("QSPC.E.G P0, RZ, [R2];", 0, "shared addr: isspacep.global"),
        ("QSPC.E.L P0, RZ, [R2];", 0, "shared addr: isspacep.local"),
        ("QSPC.E.S P0, RZ, [RZ+UR8];", 1, "shared addr (URB): isspacep.shared"),
        ("QSPC.E.L P0, RZ, [R10];", 1, "local addr: isspacep.local"),
        ("QSPC.E.G P0, RZ, [R10];", 0, "local addr: isspacep.global"),
        ("QSPC.E.S P0, RZ, [R10];", 0, "local addr: isspacep.shared"),
    ]
    for i, (qspc, exp, name) in enumerate(checks):
        rd = 20 + i
        off = i * 4
        body += (
            # QSPC is decoupled/unordered: its predicate result is written
            # asynchronously and tracked with wr=SB1; the consumer must wait
            # with req={1} (same pattern ptxas emits: QSPC ... &wr=0x1).
            f"    {qspc}[1:7:{{}}:1:0]\n"
            "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
            f"    SEL R{rd}, RZ, 0x1, !P0;[1:7:{{1}}:5:1]\n"
            f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:X}], R{rd};[0:1:{{1}}:1:0]\n"
        )
    body += "    EXIT;[7:7:{}:5:0]\n"
    src = ("#fn k(out<8>, gptr<8>) {\n    #pragma SHARED(0x1000)\n"
           + body + "}\n")
    mod = CudaModule(assemble(src))
    d = mod.devmem_alloc(64)
    g = mod.devmem_alloc(64)
    mod.launch("k", grid=(1,), block=(1,), args=[d, g])
    mod.synchronize()
    v = struct.unpack("<16I", mod.device_read(d, 64))
    for i, (qspc, exp, name) in enumerate(checks):
        check(name, v[i], exp)
    try:
        mod.devmem_free(d); mod.devmem_free(g)
    except Exception:
        pass

print(f"\n=== QSPC: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
