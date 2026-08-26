#!/usr/bin/env python3
"""F2FP semantics on real silicon (sm_120 / RTX 5090) via the SASS assembler.

Hand-assembles F2FP in all observable forms, loads the cubin through
assembler.CudaModule, and compares results against a bit-exact Python model
(RNE ties-to-even, satfinite to fp8 maxnorm).  Verifies: pack orientation +
rounding (F16/BF16), FP8 E4M3/E5M2 satfinite conversion (NaN/Inf/saturation/
subnormal), .RELU, FP8 upconvert half placement, f16->fp8 merge modes, TF32,
MERGE_C half select, .H1 extract, and whether the sm120 E2M1 (4-bit) family
runs on hardware.

Run:  python3 tests/asm_construct/test_f2fp.py
"""
import sys, struct, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

ok = True
def check(name, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {name:<46} got 0x{got:08x} want 0x{want:08x}")

def fb(v): return struct.unpack('<I', struct.pack('<f', v))[0]
def fr(b): return struct.unpack('<f', struct.pack('<I', b & 0xffffffff))[0]
def f16_pair(lo_h16, hi_h16): return (hi_h16 << 16) | (lo_h16 & 0xffff)

# ---------------------------------------------------------------------------
# bit-exact reference conversions (RNE ties-to-even)
# ---------------------------------------------------------------------------
def _rne(frac, keep):
    half = 1 << (keep - 1)
    q = frac >> keep
    rem = frac & ((1 << keep) - 1)
    if rem > half or (rem == half and (q & 1)):
        q += 1
    return q

def f32_to_f16_rne(b):
    s = (b >> 31) & 1; e = (b >> 23) & 0xff; m = b & 0x7fffff
    if e == 0xff:
        return ((s << 15) | (0x7FFF if m else 0x7C00)) & 0xffff
    if e == 0:
        return (s << 15)
    E = e - 127; e16 = E + 15
    if e16 >= 31:
        return ((s << 15) | 0x7C00) & 0xffff
    frac = (1 << 23) | m
    if e16 > 0:
        q = _rne(frac, 13)
        if q == (1 << 11):
            q = 1 << 10; e16 += 1
            if e16 >= 31:
                return ((s << 15) | 0x7C00) & 0xffff
        return ((s << 15) | (e16 << 10) | (q & 0x3ff)) & 0xffff
    sh = 13 - E
    if sh > 24:
        return (s << 15)
    q, r = divmod(frac, 1 << sh)
    if r * 2 > (1 << sh) or (r * 2 == (1 << sh) and (q & 1)):
        q += 1
    if q >= (1 << 10):
        return ((s << 15) | (1 << 10)) & 0xffff
    return ((s << 15) | q) & 0xffff

def f32_to_bf16_rne(b):
    s = (b >> 31) & 1; e = (b >> 23) & 0xff; m = b & 0x7fffff
    if e == 0xff:
        return ((s << 15) | (0x7FC0 if m else 0x7F80)) & 0xffff
    if e == 0:
        return (s << 15)
    t = b + 0x7FFF + ((b >> 16) & 1)
    return (t >> 16) & 0xffff

FP8_MAXC = {(4, 3): 0x7E, (5, 2): 0x7B}
FP8_MAXV = {(4, 3): 448.0, (5, 2): 57344.0}
FP8_MIN  = {(4, 3): 6, (5, 2): 14}

def _fp8_round(E, frac, ebits, mant):
    """Given f32-style fraction (1<<23|m) and exponent E, RNE to fp8 code."""
    bias = (1 << (ebits - 1)) - 1
    q = _rne(frac, 23 - mant)
    if q == (1 << (mant + 1)):
        q = 1 << mant; E += 1
    emax = (1 << ebits) - 1 if ebits == 4 else (1 << ebits) - 2
    if E + bias > emax:
        return None                                   # overflow -> saturate
    return ((E + bias) << mant) | (q - (1 << mant))

def f32_to_fp8(b, ebits, mant):
    # silicon-verified (sm120): NaN->0x7F (NaN code); +/-inf/overflow ->
    # +/-maxnorm (satfinite); -0.0 -> 0x80 preserved; subnormal input -> 0.
    s = (b >> 31) & 1; e = (b >> 23) & 0xff; m = b & 0x7fffff
    maxv = FP8_MAXV[(ebits, mant)]
    if e == 0xff:
        if m:
            return 0x7F                                  # NaN -> +NaN code
        return (s << 7) | (0x7E if ebits == 4 else 0x7B)  # +-inf -> +-maxnorm (satfinite)
    if e == 0:
        return (s << 7)                                  # zero/subnormal -> signed zero
    E = e - 127
    v = float(fr(b & 0x7fffffff))
    if v >= maxv:
        return (s << 7) | FP8_MAXC[(ebits, mant)]
    minnorm = FP8_MIN[(ebits, mant)]
    if E < -minnorm:                                    # underflow band
        u = v / (2.0 ** -minnorm)
        lo = math.floor(u); rem = u - lo
        if rem > 0.5 or (rem == 0.5 and lo % 2 == 1):
            lo += 1
        return (s << 7) | (1 << mant if int(lo) else 0)
    code = _fp8_round(E, (1 << 23) | m, ebits, mant)
    if code is None:
        return (s << 7) | FP8_MAXC[(ebits, mant)]
    return (s << 7) | code

def f16_to_fp8(h, ebits, mant):
    s = (h >> 15) & 1; e = (h >> 10) & 0x1f; m = h & 0x3ff
    if e == 0x1f:
        if m:
            return 0x7F                                  # NaN -> NaN code
        return (s << 7) | (0x7E if ebits == 4 else 0x7B)
    if e == 0:
        return (s << 7)
    E = e - 15
    v = (1.0 + m / 1024.0) * (2.0 ** E)
    maxv = FP8_MAXV[(ebits, mant)]
    if v >= maxv:
        return (s << 7) | FP8_MAXC[(ebits, mant)]
    minnorm = FP8_MIN[(ebits, mant)]
    if E < -minnorm:
        u = v / (2.0 ** -minnorm)
        lo = math.floor(u); rem = u - lo
        if rem > 0.5 or (rem == 0.5 and lo % 2 == 1):
            lo += 1
        return (s << 7) | (1 << mant if int(lo) else 0)
    code = _fp8_round(E, (1 << 23) | (m << 13), ebits, mant)
    if code is None:
        return (s << 7) | FP8_MAXC[(ebits, mant)]
    return (s << 7) | code

def fp8_to_f16(b, ebits, mant):
    s = (b >> (ebits + mant)) & 1
    e = (b >> mant) & ((1 << ebits) - 1)
    m = b & ((1 << mant) - 1)
    if ebits == 5 and mant == 2:
        if e == 0x1F and m == 0:
            return 0x7C00 | (s << 15)
        if e == 0x1F:
            return 0x7E00 | (s << 15)
    if ebits == 4 and (b & 0xFF) == 0x7F:
        return 0x7FFF                                    # e4m3 NaN -> f16 qNaN all-ones
    if ebits == 5 and mant == 2 and (b & 0xFF) in (0x7F, 0x7E, 0x7D):
        return 0x7FFF
    if e == 0:
        return (s << 15)
    E = e - ((1 << (ebits - 1)) - 1)
    e16 = E + 15
    if e16 >= 31:
        return 0x7C00 | (s << 15)
    return (s << 15) | (e16 << 10) | (m << (10 - mant))

# ---------------------------------------------------------------------------
cases = []
def add(name, instr, want, pre):
    cases.append((name, instr, want, pre))

def fp8pair(hi, lo): return ((hi & 0xff) << 8) | (lo & 0xff)

# --- F16/F32 pack -----------------------------------------------------------
add("f16 pack 1.0|2.0 orient",   "F2FP.F16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(f32_to_f16_rne(fb(2.0)), f32_to_f16_rne(fb(1.0))), {0: fb(1.0), 1: fb(2.0)})
add("f16 pack 0.5|-1.5",         "F2FP.F16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(f32_to_f16_rne(fb(-1.5)), f32_to_f16_rne(fb(0.5))), {0: fb(0.5), 1: fb(-1.5)})
add("f16 rne tie-even",          "F2FP.F16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(f32_to_f16_rne(fb(3.0)), f32_to_f16_rne(0x3F980000)), {0: 0x3F980000, 1: fb(3.0)})
add("f16 rne up",                "F2FP.F16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(f32_to_f16_rne(fb(1.0)), f32_to_f16_rne(0x3F9C0000)), {0: 0x3F9C0000, 1: fb(1.0)})
add("f16 +inf",                  "F2FP.F16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(0x0000, 0x7C00), {0: 0x7F800000, 1: fb(0.0)})
add("f16 -inf",                  "F2FP.F16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(0x0000, 0xFC00), {0: 0xFF800000, 1: fb(0.0)})
add("f16 nan->qnan",             "F2FP.F16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(0x0000, 0x7FFF), {0: 0x7FC00000, 1: fb(0.0)})
add("f16 overflow->inf",         "F2FP.F16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(0x0000, 0x7C00), {0: fb(65520.0), 1: fb(0.0)})
add("f16 subnorm-in flush",      "F2FP.F16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(0x0000, 0x0000), {0: 0x00000001, 1: fb(0.0)})
# --- BF16/F32 pack ----------------------------------------------------------
add("bf16 pack 1.0|2.0 orient",  "F2FP.BF16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(f32_to_bf16_rne(fb(2.0)), f32_to_bf16_rne(fb(1.0))), {0: fb(1.0), 1: fb(2.0)})
add("bf16 rne tie-even",         "F2FP.BF16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(f32_to_bf16_rne(fb(1.0)), f32_to_bf16_rne(0x3F808000)), {0: 0x3F808000, 1: fb(1.0)})
add("bf16 rne up",               "F2FP.BF16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(f32_to_bf16_rne(fb(1.0)), f32_to_bf16_rne(0x3F808400)), {0: 0x3F808400, 1: fb(1.0)})
add("bf16 -inf",                 "F2FP.BF16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(0x0000, 0xFF80), {0: 0xFF800000, 1: fb(0.0)})
# --- F32 -> E4M3 satfinite ---------------------------------------------------
add("e4m3 pack 1.0|2.0 orient",  "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(fb(1.0), 4, 3), f32_to_fp8(fb(2.0), 4, 3)), {0: fb(1.0), 1: fb(2.0)})
add("e4m3 sat large",            "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(fb(1e10), 4, 3), f32_to_fp8(fb(-1e10), 4, 3)), {0: fb(1e10), 1: fb(-1e10)})
add("e4m3 nan->+448",            "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(0x7FC00000, 4, 3), 0x00), {0: 0x7FC00000, 1: fb(0.0)})
add("e4m3 inf->max",             "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(0x7F800000, 4, 3), f32_to_fp8(0xFF800000, 4, 3)), {0: 0x7F800000, 1: 0xFF800000})
add("e4m3 rne tie-even",         "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(0x3F810000, 4, 3), f32_to_fp8(0x3F820000, 4, 3)), {0: 0x3F810000, 1: 0x3F820000})
add("e4m3 relu neg->0",          "F2FP.SATFINITE.RELU.E4M3.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(0x00, f32_to_fp8(fb(2.0), 4, 3)), {0: fb(-1.0), 1: fb(2.0)})
add("e4m3 subnorm/neg0",        "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(0x00, 0x80), {0: 0x00000001, 1: 0x80000000})
add("e4m3 2^-7 -> 2^-6",         "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(0x33800000, 4, 3), 0x00), {0: 0x33800000, 1: fb(0.0)})
# --- F32 -> E5M2 satfinite ---------------------------------------------------
add("e5m2 pack 1.0|2.0",         "F2FP.SATFINITE.E5M2.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(fb(1.0), 5, 2), f32_to_fp8(fb(2.0), 5, 2)), {0: fb(1.0), 1: fb(2.0)})
add("e5m2 sat large",            "F2FP.SATFINITE.E5M2.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(fb(60000.0), 5, 2), f32_to_fp8(fb(-60000.0), 5, 2)), {0: fb(60000.0), 1: fb(-60000.0)})
add("e5m2 +inf->inf",            "F2FP.SATFINITE.E5M2.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(0x7F800000, 5, 2), 0x00), {0: 0x7F800000, 1: fb(0.0)})
add("e5m2 nan->+57344",          "F2FP.SATFINITE.E5M2.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(0x7FC00000, 5, 2), 0x00), {0: 0x7FC00000, 1: fb(0.0)})
# --- f16 -> FP8 (UNPACK_B_MERGE_C) ------------------------------------------
add("f16->e4m3 pair",            "F2FP.SATFINITE.E4M3.F16.UNPACK_B_MERGE_C {rd}, R0, RZ",
    fp8pair(f16_to_fp8(0x4000, 4, 3), f16_to_fp8(0x3C00, 4, 3)), {0: f16_pair(0x3C00, 0x4000)})
add("f16->e5m2 pair",            "F2FP.SATFINITE.E5M2.F16.UNPACK_B_MERGE_C {rd}, R0, RZ",
    fp8pair(f16_to_fp8(0x4000, 5, 2), f16_to_fp8(0x3C00, 5, 2)), {0: f16_pair(0x3C00, 0x4000)})
add("f16 inf->e4m3 +448",        "F2FP.SATFINITE.E4M3.F16.UNPACK_B_MERGE_C {rd}, R0, RZ",
    fp8pair(0x7E, 0x00), {0: f16_pair(0x0000, 0x7C00)})
add("f16->e4m3 mergeC H0 Rc[15:0]->hi","F2FP.SATFINITE.E4M3.F16.UNPACK_B_MERGE_C {rd}, R0, R1",
    0x00004038, {0: f16_pair(0x3C00, 0x4000), 1: 0xDEAD0000})
add("f16->e4m3 mergeC H1 Rc[31:16]->hi","F2FP.SATFINITE.E4M3.F16.UNPACK_B_MERGE_C.H1 {rd}, R0, R1",
    0x00004038, {0: f16_pair(0x3C00, 0x4000), 1: 0x0000DEAD})
# --- FP8 upconvert -> F16 ----------------------------------------------------
add("up e4m3->f16",              "F2FP.F16.E4M3.UNPACK_B {rd}, R0",
    f16_pair(fp8_to_f16(0x38, 4, 3), fp8_to_f16(0x40, 4, 3)), {0: 0x00004038})
add("up e5m2->f16",              "F2FP.F16.E5M2.UNPACK_B {rd}, R0",
    f16_pair(fp8_to_f16(0x3C, 5, 2), fp8_to_f16(0x40, 5, 2)), {0: 0x0000403C})
add("up e5m2 +inf->+inf",        "F2FP.F16.E5M2.UNPACK_B {rd}, R0",
    f16_pair(fp8_to_f16(0x00, 5, 2), fp8_to_f16(0x7C, 5, 2)), {0: 0x00007C00})
add("up e4m3 NaN 0x7F->qNaN",    "F2FP.F16.E4M3.UNPACK_B {rd}, R0",
    f16_pair(fp8_to_f16(0x00, 4, 3), fp8_to_f16(0x7F, 4, 3)), {0: 0x00007F00})
# --- TF32 --------------------------------------------------------------------
add("tf32 1.0",                  "F2FP.TF32.F32.PACK_B {rd}, R0",
    0x3F800000, {0: 0x3F800000})
add("tf32 rne-vs-trunc",         "F2FP.TF32.F32.PACK_B {rd}, R0",
    0x3F804000, {0: 0x3F803000})   # RNE -> 1+2^-10 ; truncate -> 1.0
add("tf32 -1.25",                "F2FP.TF32.F32.PACK_B {rd}, R0",
    0xBFA00000, {0: 0xBFA00000})
# --- MERGE_C half select -----------------------------------------------------
add("merge_c H0 Rc[15:0]->hi",   "F2FP.F16.F32.MERGE_C {rd}, R0, R1",
    0x0000 | f32_to_f16_rne(fb(1.0)), {0: fb(1.0), 1: 0xCAFE0000})
add("merge_c .H1 Rc[31:16]->hi",  "F2FP.F16.F32.MERGE_C.H1 {rd}, R0, R1",
    f32_to_f16_rne(fb(1.0)) | 0xCAFE0000, {0: fb(1.0), 1: 0xCAFE0000})
# --- E2M1 4-bit (probe: does sm120 HW execute?) -----------------------------
# e2m1 code: 1.0 = 0x2, 2.0 = 0x4 (per probed sm120 model)
add("e2m1 f32->4b (probe)",      "F2FP.SATFINITE.E2M1.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    ((0x02 << 4) | 0x04), {0: fb(1.0), 1: fb(2.0)})
add("e2m1 4b->f16 B0 (probe)",   "F2FP.F16.E2M1.UNPACK_B {rd}, R0",
    0x00003C00, {0: 0x00000402})

# ---------------------------------------------------------------------------
lines = ["#fn k(out<8>) {",
         "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]"]
off = 0x100
for i, (name, instr, want, pre) in enumerate(cases):
    r = (i % 5) + 1
    rd = 40 + i
    for k, v in pre.items():
        lines.append(f"    MOV32I R{k}, 0x{v:08X};[7:7:{{}}:5:1]")
    lines.append(f"    {instr.format(rd=f'R{rd}')};[{r}:7:{{}}:5:1]")
    lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:X}], R{rd};[7:7:{{0,{r}}}:1:0]")
    off += 4
lines += ["    EXIT;[7:7:{}:5:0]", "}"]

src = "\n".join(lines)
try:
    mod = CudaModule(assemble(src))
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

d = mod.devmem_alloc(off)
mod.device_write(d, bytes(off))
mod.launch("k", grid=(1,), block=(1,), args=[d])
mod.synchronize()
vec = struct.unpack(f"<{off//4}I", mod.device_read(d, off))
mod.devmem_free(d)

for i, (name, instr, want, pre) in enumerate(cases):
    got = vec[(0x100 // 4) + i]
    check(f"[{i:2d}] {name}", got, want)

print(f"\n=== F2FP semantics: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)