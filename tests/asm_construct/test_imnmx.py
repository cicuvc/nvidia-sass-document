import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat
import struct

# ---------------------------------------------------------------------------
# Arch scope: the predicate-result matrix below (Pd/Pv forms) is the sm_120
# extension; the sm_90 spec IMNMX is plain `IMNMX[U32|S32] Rd,Ra,Rb,[!]Pp`
# (S32/U32 only, no 64-bit).  On sm90 we verify that reduced surface here and
# skip the extended matrix.
if __name__ == "__main__":
    try:
        from archutil import same_as_capture, adapt_source, is_sm90  # noqa: E402
    except ImportError:
        same_as_capture = None
    if same_as_capture is not None and not same_as_capture("sm120"):
        ok = True
        _src = """#fn imnmx_test(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]
    MOV32I R0, 0xFFFFFFF9;[7:7:{}:5:1]      // -7 signed / 0xFFFFFFF9 unsigned
    MOV32I R1, 0x00000009;[7:7:{}:5:1]      // +9
    IMNMX.S32 R2, R0, R1, PT;[1:7:{}:3:1]    // min  -> -7 (0xFFFFFFF9); wr=SB1
    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R2;[0:1:{0,1}:3:1]
    IMNMX.U32 R3, R0, R1, PT;[2:7:{}:3:1]    // minu -> +9; wr=SB2
    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R3;[0:1:{0,2}:3:1]
    EXIT;[7:7:{}:5:0]
}"""
        cubin = assemble(adapt_source(_src))
        mod = CudaModule(cubin)
        d = mod.devmem_alloc(16)
        mod.device_write(d, b"\x00" * 16)
        mod.launch("imnmx_test", grid=(1,), block=(1,), args=[d])
        mod.synchronize()
        v = struct.unpack("<2I", mod.device_read(d, 8))
        exp = (0xFFFFFFF9, 9)
        good = v == exp
        ok &= good
        print(f"{'ok ' if good else 'FAIL'} sm90 plain-form min/max: {[hex(x) for x in v]} (exp {[hex(x) for x in exp]})")
        print(f"\n=== IMNMX sm90 reduced surface: {'ALL OK' if ok else 'FAILED'} ===")
        sys.exit(0 if ok else 1)

# IMNMX — Integer Min/Max (int_pipe). Verified on SM120 (RTX 5090).
#
# SM120 syntax (full form, richer than the sm90/sm75 4-operand form):
#   IMNMX[.U32|.U64|.S64] Pu, Pv, Rd, Ra, Rb, [!]Pp, [!]Pq
#   (plain = .S32; 6-operand nopred form omits Pq, encoded PT,!PT)
#
# Semantics found empirically (probe + 100+ case battery, all pass):
#   comp = (Ra <= Rb)                      in the fmt comparison domain
#   comp = comp OR Pq                      Pq=1 forces the compare true
#   min (Pp=PT):  Rd = comp ? Ra : Rb      max (Pp=!PT): Rd = comp ? Rb : Ra
#   Pu = "Ra is the result source"         (min: comp; max: !comp)
#   Pv = (Ra != Rb) OR Pq
#
# Note: ptxas does not emit IMNMX on sm90/sm120 (it prefers VIMNMX); the
# legacy instruction is exercised here directly. IMNMX was extended on
# Blackwell with the Pu/Pv/Pq predicate slots (absent in sm90).


def to_s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v >> 31 else v


def to_s64(v):
    v &= 0xFFFFFFFFFFFFFFFF
    return v - 0x10000000000000000 if v >> 63 else v


def imnmx(a, b, fmt, sense, pq):
    """Expected (Rd, Pu, Pv). a/b are raw bit patterns (32 or 64-bit)."""
    if fmt in ("S32", "S64"):
        sa, sb = (to_s32(a), to_s32(b)) if fmt == "S32" else (to_s64(a), to_s64(b))
        comp = sa <= sb
    else:
        comp = a <= b
    comp = comp or bool(pq)
    if sense == "min":
        rd, pu = (a, 1) if comp else (b, 0)
    else:
        rd, pu = (b, 0) if comp else (a, 1)
    pv = 1 if (a != b) or pq else 0
    return rd, pu, pv


# ---------------------------------------------------------------------------
# Case table: (kind, fmt, a, b, sense, pq_eff, label)
#   kind: "rrr" | "not" (Pq=!P4) | "rir" | "nopred" | "rrr64"
# ---------------------------------------------------------------------------
cases = []


def add(kind, fmt, a, b, sense, pq, label):
    cases.append((kind, fmt, a, b, sense, pq, label))


# --- main battery: RRR, S32/U32, a<b / a>b / a==b, min/max, Pq=0/1 ----------
for a, b in [(5, 7), (7, 5), (5, 5), (-3, 5), (-5, -3),
             (0x7FFFFFFF, 0x80000000), (-1, 1), (0, 0)]:
    for sense in ("min", "max"):
        for pq in (0, 1):
            add("rrr", "S32", a & 0xFFFFFFFF, b & 0xFFFFFFFF, sense, pq,
                f"S32 {a:08x},{b:08x} {sense} Pq={pq}")
for a, b in [(0xFFFFFFF0, 7), (7, 0xFFFFFFF0), (0xFFFFFFFF, 0xFFFFFFFF)]:
    for sense in ("min", "max"):
        for pq in (0, 1):
            add("rrr", "U32", a, b, sense, pq,
                f"U32 {a:08x},{b:08x} {sense} Pq={pq}")

# --- Pq negated: Pq=!P4 (P4=0 -> effective 1) -> select mode ---------------
add("not", "S32", 5, 7, "min", 1, "S32 5,7 min Pq=!P4(1)")
add("not", "S32", 7, 5, "min", 1, "S32 7,5 min Pq=!P4(1)")

# --- RIR: immediate Rb -------------------------------------------------------
add("rir", "U32", 5, 7, "min", 0, "RIR U32 min(5,0x7)")
add("rir", "U32", 5, 7, "max", 0, "RIR U32 max(5,0x7)")

# --- nopred form (no Pq operand; encoded PT,!PT = effective false) ----------
add("nopred", "S32", 7, 5, "min", 0, "nopred S32 min(7,5)")
add("nopred", "S32", 7, 5, "max", 0, "nopred S32 max(7,5)")

# --- 64-bit register pairs (Pq=0) -------------------------------------------
M64 = (1 << 64) - 1
for a, b in [(0xFFFFFFFF, 0x100000000),
             (0x100000000, 0xFFFFFFFF),
             ((-1) & M64, 1),
             (0x1234567812345678, 0x1234567812345678)]:
    for fmt in ("U64", "S64"):
        for sense in ("min", "max"):
            add("rrr64", fmt, a & M64, b & M64, sense, 0,
                f"{fmt} {a & M64:016x},{b & M64:016x} {sense}")

# ---------------------------------------------------------------------------
# Build the kernel
# ---------------------------------------------------------------------------
lines = ["#fn imnmx_test(out<8>) {",
         "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
         "    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]",
         "    ISETP.T P5, RZ, RZ;[7:7:{}:5:1]   // P5 = 1",
         "    ISETP.F P4, RZ, RZ;[7:7:{}:5:1]"]  # P4 = 0

store_off = []  # per-case list of (offset, width) stores
case_stores = []  # per-case tuple of store offsets


def stg(off, reg):
    lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:X}], {reg};[0:1:{{0}}:1:0]")


off = 0
cur = []
for kind, fmt, a, b, sense, pq, label in cases:
    suf = "" if fmt == "S32" else "." + fmt
    s = "PT" if sense == "min" else "!PT"
    if kind in ("rrr", "not"):
        lines.append(f"    MOV32I R0, 0x{a:08X};[7:7:{{}}:5:1]")
        lines.append(f"    MOV32I R1, 0x{b:08X};[7:7:{{}}:5:1]")
        pqop = "!P4" if kind == "not" else ("P4" if pq == 0 else "P5")
        lines.append(f"    IMNMX{suf} P2, P3, R2, R0, R1, {s}, {pqop};[7:7:{{}}:8:1]")
        stg(off, "R2"); store_off.append((off, 4)); off += 4
        cur = [off - 4]
    elif kind == "rir":
        lines.append(f"    MOV32I R0, 0x{a:08X};[7:7:{{}}:5:1]")
        lines.append(f"    IMNMX{suf} P2, P3, R2, R0, 0x{b:X}, {s}, P4;[7:7:{{}}:8:1]")
        stg(off, "R2"); store_off.append((off, 4)); off += 4
        cur = [off - 4]
    elif kind == "nopred":
        lines.append(f"    MOV32I R0, 0x{a:08X};[7:7:{{}}:5:1]")
        lines.append(f"    MOV32I R1, 0x{b:08X};[7:7:{{}}:5:1]")
        lines.append(f"    IMNMX{suf} P2, P3, R2, R0, R1, {s};[7:7:{{}}:8:1]")
        stg(off, "R2"); store_off.append((off, 4)); off += 4
        cur = [off - 4]
    elif kind == "rrr64":
        lo_a, hi_a = a & 0xFFFFFFFF, (a >> 32) & 0xFFFFFFFF
        lo_b, hi_b = b & 0xFFFFFFFF, (b >> 32) & 0xFFFFFFFF
        # a = R10/R11, b = R12/R13 (NOT R6/R7 — those hold the out-buffer addr)
        lines.append(f"    MOV32I R10, 0x{lo_a:08X};[7:7:{{}}:5:1]")
        lines.append(f"    MOV32I R11, 0x{hi_a:08X};[7:7:{{}}:5:1]")
        lines.append(f"    MOV32I R12, 0x{lo_b:08X};[7:7:{{}}:5:1]")
        lines.append(f"    MOV32I R13, 0x{hi_b:08X};[7:7:{{}}:5:1]")
        lines.append(f"    IMNMX{suf} P2, P3, {{R2,R3}}, {{R10,R11}}, {{R12,R13}}, {s}, P4;[7:7:{{}}:8:1]")
        stg(off, "R2"); store_off.append((off, 4)); off += 4
        stg(off, "R3"); store_off.append((off, 4)); off += 4
        cur = [off - 8, off - 4]
    # predicate snapshot (bit 2 = Pu = P2, bit 3 = Pv = P3)
    lines.append("    P2R R8, PR, RZ, 0x7f;[7:7:{1}:8:0]")
    stg(off, "R8"); store_off.append((off, 4)); off += 4
    cur.append(off - 4)
    case_stores.append(tuple(cur))

lines += ["    EXIT;[7:7:{}:5:0]", "}"]
src = "\n".join(lines)
assert off <= 768, f"need {off} bytes"
cubin = assemble(src)
Path("x.cubin").write_bytes(cubin)

# --- offline encoding self-check -------------------------------------------
enc = assemble_flat(
    "IMNMX.S32 P0, P1, R2, R0, R1, PT, P4;[7:7:{}:8:1]\n"
    "IMNMX.U32 P0, P1, R2, R0, 0x7, PT, P4;[7:7:{}:8:1]\n"
    "IMNMX.S32 P0, P1, R2, R0, UR5, PT, P4;[7:7:{}:8:1]\n"
    "IMNMX.U64 P0, P1, {R2,R3}, {R4,R5}, {R6,R7}, PT, P4;[7:7:{}:8:1]\n")
for (name, exp_op), (lo, hi) in zip(
        (("RRR", 0x217), ("RIR", 0x817), ("RUR", 0x1c17), ("RRR64", 0x217)), enc):
    op = ((hi >> 27) & 1) << 12 | (lo & 0xFFF)
    assert op == exp_op, f"{name}: opcode 0x{op:x} != 0x{exp_op:x}"
print("encoding self-check: RRR/RIR/RUR/64 opcodes OK")

# --- run on GPU -------------------------------------------------------------
mod = CudaModule(cubin)
d = mod.devmem_alloc(off)
mod.launch("imnmx_test", grid=(1,), block=(1,), args=[d])
mod.synchronize()
vals = struct.unpack(f"<{off // 4}I", mod.device_read(d, off))

print("=== IMNMX Semantic Verification (SM120) ===")
print()
ok = True
for i, ((kind, fmt, a, b, sense, pq, label), offs) in enumerate(
        zip(cases, case_stores)):
    exp_rd, exp_pu, exp_pv = imnmx(a, b, fmt, sense, pq)
    if kind == "rrr64":
        o1, o2, o3 = offs
        got_rd = vals[o1 // 4] | (vals[o2 // 4] << 32)
        pr = vals[o3 // 4]
    else:
        o1, o2 = offs
        got_rd = vals[o1 // 4]
        pr = vals[o2 // 4]
    got_pu, got_pv = (pr >> 2) & 1, (pr >> 3) & 1
    width = 16 if kind == "rrr64" else 8
    status = "OK" if (got_rd, got_pu, got_pv) == (exp_rd, exp_pu, exp_pv) else "FAIL"
    ok &= status == "OK"
    print(f"[{i+1:3d}] {label:<34} Rd=0x{got_rd:0{width}x} "
          f"Pu={got_pu} Pv={got_pv}  expected Rd=0x{exp_rd:0{width}x} "
          f"Pu={exp_pu} Pv={exp_pv}  {status}")

print()
print(f"=== {'ALL OK' if ok else 'SOME FAILED'} ===")
print("Key findings (SM120):")
print("  comp = (Ra <= Rb) in fmt domain; min -> Ra, max -> Rb on comp")
print("  Pq=1 forces comp true (select mode); Pq effective value = Pq xor @not")
print("  Pu = 'Ra is result'; Pv = (Ra != Rb) OR Pq")
print("  U64/S64 compare 64-bit register pairs; U32/S32 are 32-bit")

mod.devmem_free(d)
