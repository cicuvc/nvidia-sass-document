import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat
import struct

# SHF — Funnel Shift (integer, int_pipe).
#
# Model under verification on SM120 (RTX 5090):
#   funnel = {Rc[31:0], Ra[31:0]}           64-bit source; Rc = HIGH half,
#                                            Ra = LOW half  (PTX shf operand
#                                            order: SASS Ra == PTX a, SASS
#                                            Rc == PTX b; this is the opposite
#                                            of the prose in
#                                            notes/sm90/instr/shf.md, which has
#                                            the halves swapped — the ptxas
#                                            idioms below prove {Rc,Ra}).
#   .L : result = funnel << n                .R : result = funnel >> n
#   .HI: Rd = result[63:32]                  (plain/.LO: Rd = result[31:0])
#   U32/U64: logical shift                  S32/S64: arithmetic (sign-fill)
#   CWMode C (default) + 64-formats:  n = 6-bit amount, 0..63
#   CWMode C + 32-formats:            n = min(amount, 32)   <-- clamped!
#   CWMode W:                        n = amount & 0x1f   (wrap at 32 — ptxas
#                                            uses .W for rotate idioms with a
#                                            raw amount)
#
# Compiler corroboration (CUDA 12.8, sm_90 & sm_120):
#   unsigned v = (hi<<32)|lo;  v >> k  ->  SHF.R.U64 Rd, lo, k, hi   (lo=Ra, hi=Rc)
#   (int)sa >> 3               ->  SHF.R.S32.HI Rd, RZ, 0x3, sa     (value in Rc)
#   (sa < 0) ? -1 : 0          ->  SHF.R.S32.HI Rd, RZ, 0x1f, sa    (sign mask)
#   rotate(a, n)               ->  SHF.L.W.U32.HI Rd, a, n, a       (.W = wrap)
#
# RESOLVED on SM120 (RTX 5090): U32/S32 vs U64/S64 are NOT aliases. At
# amount >= 32, the 32-formats clamp to 32 while the 64-formats shift the
# full 0..63 (case [41]: SHF.R.U32 k=40 -> shift by 32; SHF.R.U64 k=40 ->
# shift by 40). The battery below probes that boundary and cross-checks the
# register / immediate operand forms against each other.

M64 = (1 << 64) - 1


def shf_model(lo32, hi32, d, fmt, hilo, k, cw):
    """Expected result of SASS SHF (funnel {Rc,Ra}, Rc high / Ra low)."""
    funnel = ((hi32 & 0xFFFFFFFF) << 32) | (lo32 & 0xFFFFFFFF)
    signed = fmt in ("S32", "S64")
    wide = fmt in ("U64", "S64")
    if cw == "W":
        n = k & 0x1F
    else:
        n = k if wide else min(k, 32)   # 32-formats clamp the amount at 32
    if d == "L":
        shifted = (funnel << n) & M64
    else:
        shifted = funnel >> n
        if signed and (funnel >> 63) & 1 and n:
            shifted |= (((1 << n) - 1) << (64 - n)) & M64
    return (shifted >> 32) & 0xFFFFFFFF if hilo else shifted & 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Case table: (label, SASS, lo32=Ra, hi32=Rc, dir, fmt, hilo, k, cw[, exp])
# ---------------------------------------------------------------------------
A, B = 0x89ABCDEF, 0x01234567   # asymmetric pair -> pins funnel orientation
A2, B2 = 0x12345678, 0xFFFFFFFF # negative 64-bit funnel for S tests

cases = []


def add(label, sass, lo, hi, d, fmt, hilo, k, cw="C", exp=None):
    cases.append([label, sass, lo, hi, d, fmt, hilo, k, cw, exp])


# --- funnel orientation + half select (U32, C mode, k=3) --------------------
add("L.LO",  "SHF.L.U32    R4, R0, 0x3, R1", A, B, "L", "U32", 0, 3)
add("L.HI",  "SHF.L.U32.HI R4, R0, 0x3, R1", A, B, "L", "U32", 1, 3)
add("R.LO",  "SHF.R.U32    R4, R0, 0x3, R1", A, B, "R", "U32", 0, 3)
add("R.HI",  "SHF.R.U32.HI R4, R0, 0x3, R1", A, B, "R", "U32", 1, 3)

# --- C mode amount sweep, U64, both halves / directions (k 0..63) ----------
for k in (0, 1, 31, 32, 40, 63):
    add(f"L.LO k={k}",  f"SHF.L.U64    R4, R0, 0x{k:X}, R1", A, B, "L", "U64", 0, k)
    add(f"L.HI k={k}",  f"SHF.L.U64.HI R4, R0, 0x{k:X}, R1", A, B, "L", "U64", 1, k)
    add(f"R.LO k={k}",  f"SHF.R.U64    R4, R0, 0x{k:X}, R1", A, B, "R", "U64", 0, k)
    add(f"R.HI k={k}",  f"SHF.R.U64.HI R4, R0, 0x{k:X}, R1", A, B, "R", "U64", 1, k)

# --- W mode wraps the amount at 32 -----------------------------------------
add("W L.HI k=0x20", "SHF.L.W.U32.HI R4, R0, 0x20, R1", A, B, "L", "U32", 1, 0x20, "W")
add("W R.LO k=0x20", "SHF.R.W.U32    R4, R0, 0x20, R1", A, B, "R", "U32", 0, 0x20, "W")
add("W R.HI k=0x23", "SHF.R.W.U32.HI R4, R0, 0x23, R1", A, B, "R", "U32", 1, 0x23, "W")
add("W L.LO k=0x23", "SHF.L.W.U32    R4, R0, 0x23, R1", A, B, "L", "U32", 0, 0x23, "W")

# --- signed arithmetic right shift (negative 64-bit funnel) -----------------
add("R.S64.LO",  "SHF.R.S64    R4, R2, 0x10, R3", A2, B2, "R", "S64", 0, 0x10)
add("R.S64.HI",  "SHF.R.S64.HI R4, R2, 0x10, R3", A2, B2, "R", "S64", 1, 0x10)
add("R.S32.LO",  "SHF.R.S32    R4, R2, 0x10, R3", A2, B2, "R", "S32", 0, 0x10)
add("R.S32.HI",  "SHF.R.S32.HI R4, R2, 0x10, R3", A2, B2, "R", "S32", 1, 0x10)
add("signmask -", "SHF.R.S32.HI R4, RZ, 0x1F, R3", 0, B2, "R", "S32", 1, 0x1F)
add("signmask +", "SHF.R.S32.HI R4, RZ, 0x1F, R1", 0, B,  "R", "S32", 1, 0x1F)
add("L.S64.LO",  "SHF.L.S64    R4, R2, 0x3, R3",  A2, B2, "L", "S64", 0, 3)
add("L.S32.LO",  "SHF.L.S32    R4, R2, 0x3, R3",  A2, B2, "L", "S32", 0, 3)

# --- U32 vs U64 / S32 vs S64 at k >= 32 (identity check) --------------------
add("R.U32.LO 40", "SHF.R.U32 R4, R0, 0x28, R1", A, B, "R", "U32", 0, 0x28)
add("R.U64.LO 40", "SHF.R.U64 R4, R0, 0x28, R1", A, B, "R", "U64", 0, 0x28)
add("L.U32.LO 40", "SHF.L.U32 R4, R0, 0x28, R1", A, B, "L", "U32", 0, 0x28)
add("L.U64.LO 40", "SHF.L.U64 R4, R0, 0x28, R1", A, B, "L", "U64", 0, 0x28)
add("R.S32.LO 40", "SHF.R.S32 R4, R2, 0x28, R3", A2, B2, "R", "S32", 0, 0x28)
add("R.S64.LO 40", "SHF.R.S64 R4, R2, 0x28, R3", A2, B2, "R", "S64", 0, 0x28)

# --- operand forms: register amount (RRR) vs immediate (RuIR), imm Rc (RRuI)
add("RRR k=37",  "SHF.L.U32 R4, R0, R10, R1", A, B, "L", "U32", 0, 0x25)
add("RuIR k=37", "SHF.L.U32 R4, R0, 0x25, R1", A, B, "L", "U32", 0, 0x25)
# RRuI: Rc is the immediate 0 -> funnel {0, A}; amount comes from R10 (=37).
# U32 clamps to 32, so {0,A}<<32 -> LO = 0. (A wrap-at-32 implementation would
# produce A<<5 here, so this also probes the C-mode amount semantics.)
add("RRuI k=37", "SHF.L.U32 R4, R0, R10, 0x0", A, B, "L", "U32", 0, 0x25,
    exp=shf_model(A, 0, "L", "U32", 0, 0x25, "C"))

expected = []
for _, _, lo, hi, d, fmt, hilo, k, cw, exp in cases:
    expected.append(exp if exp is not None
                    else shf_model(lo, hi, d, fmt, hilo, k, cw))

# ---------------------------------------------------------------------------
# Build the kernel: same case list drives the SASS text and the expectations.
# ---------------------------------------------------------------------------
lines = ["#fn shf_test(out<256>) {",
         "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]",
         "    MOV32I R0, 0x89ABCDEF;[7:7:{}:5:1]   // Ra: low half",
         "    MOV32I R1, 0x01234567;[7:7:{}:5:1]   // Rc: high half",
         "    MOV32I R2, 0x12345678;[7:7:{}:5:1]   // low half (signed tests)",
         "    MOV32I R3, 0xFFFFFFFF;[7:7:{}:5:1]   // high half, negative funnel",
         "    MOV32I R10, 0x00000025;[7:7:{}:5:1]  // shift amount 37 (RRR/RRuI)"]
for i, c in enumerate(cases):
    lines.append(f"    {c[1]};[7:7:{{}}:8:1]")
    lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{i*4:X}], R4;[0:1:{{0}}:1:0]")
lines += ["    EXIT;[7:7:{}:5:0]",
          "}"]

cubin = assemble("\n".join(lines))
Path("x.cubin").write_bytes(cubin)

# --- offline encoding self-check: 13-bit opcode of each form ----------------
FORM_OPCODE = {
    "RRR": 0x219, "RuIR": 0x819, "RRuI": 0x419,
    "RUR": 0x1c19, "RRU": 0x1e19,
}
enc = assemble_flat(
    "SHF.L.U32 R3, R0, R8, R7;[7:7:{}:5:1]\n"
    "SHF.L.U32 R3, R0, 0x5, R7;[7:7:{}:5:1]\n"
    "SHF.L.U32 R3, R0, R8, 0x5;[7:7:{}:5:1]\n"
    "SHF.L.U32 R3, R0, UR4, R7;[7:7:{}:5:1]\n"
    "SHF.L.U32 R3, R0, R8, UR5;[7:7:{}:5:1]\n")
for (name, exp_op), (lo, hi) in zip(FORM_OPCODE.items(), enc):
    op = ((hi >> 27) & 1) << 12 | (lo & 0xFFF)
    assert op == exp_op, f"{name}: opcode 0x{op:x} != 0x{exp_op:x}"
print("encoding self-check: RRR/RuIR/RRuI/RUR/RRU opcodes OK")

# ---------------------------------------------------------------------------
# Run on GPU and compare
# ---------------------------------------------------------------------------
try:
    mod = CudaModule(cubin)
except RuntimeError as e:
    print(f"GPU unavailable: {e}")
    print("Encoding self-check passed; the semantic run needs a CUDA device")
    print("(SM120). Re-run on the GPU box (same pattern as the other")
    print("asm_construct tests).")
    sys.exit(2)
d = mod.devmem_alloc(4 * len(cases))
mod.launch("shf_test", grid=1, block=1, args=[d])
mod.synchronize()
vals = struct.unpack(f"<{len(cases)}I", mod.device_read(d, 4 * len(cases)))

print("=== SHF Semantic Verification (SM120) ===")
print()
ok = True
for i, (label, sass, *_rest) in enumerate(cases):
    got, exp = vals[i], expected[i]
    status = "OK" if got == exp else "FAIL"
    ok &= got == exp
    print(f"[{i+1:3d}] {label:<13} {sass:<34} got 0x{got:08x} "
          f"expected 0x{exp:08x}  {status}")

print()
print(f"=== {'ALL OK' if ok else 'SOME FAILED'} ===")
print("Key findings:")
print("  funnel = {Rc, Ra} (Rc high / Ra low); .HI selects result[63:32]")
print("  U64/S64 use the full 0..63 amount; U32/S32 clamp the amount at 32")
print("  W mode wraps at 32 (amount & 31); C mode is 0..63 / clamped")
print("  S32/S64 right shifts are arithmetic; U32/U64 are logical")

mod.devmem_free(d)
