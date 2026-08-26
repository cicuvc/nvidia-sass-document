#!/usr/bin/env python3
"""F2FP on Hopper (sm90) silicon — H20 GPU.

Same harness as test_f2fp.py but arch='sm90', plus Hopper-only questions:

  1. E6M9 destination (dstfmt=2) — the Hopper-only format removed on sm120.
     Hypothesis: sign(1)+exp(6)+mant(9), bias 31, RNE ties-to-even; 16-bit
     per element packed by PACK_AB; overflow -> inf / .SATFINITE -> max.
  2. Arch-diff checks vs the sm120 (RTX 5090) silicon findings: NaN masking,
     fp8 satfinite of inf, TF32 RN, merge semantics, .H1 extract.

Run: python3 tests/asm_construct/test_f2fp_hopper.py        (on an sm90 GPU)
"""
import sys, struct, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

ok = True
def check(name, got, want, probe=False):
    global ok
    if want is None:                       # pure probe row
        print(f"    {name:<44} -> 0x{got:08x}")
        return
    good = got == want
    ok &= good or probe
    if probe and not good:
        print(f"PROBE{name:<38} got 0x{got:08x} want 0x{want:08x}")
    else:
        print(f"{'ok ' if good else 'FAIL'} {name:<46} got 0x{got:08x} want 0x{want:08x}")

def fb(v): return struct.unpack('<I', struct.pack('<f', v))[0]
def fr(b): return struct.unpack('<f', struct.pack('<I', b & 0xffffffff))[0]
def f16_pair(lo_h16, hi_h16): return (hi_h16 << 16) | (lo_h16 & 0xffff)

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

def f32_to_fp8(b, ebits, mant):
    """sm120-verified model: NaN->0x7F; +-inf/overflow -> maxnorm; -0 kept."""
    s = (b >> 31) & 1; e = (b >> 23) & 0xff; m = b & 0x7fffff
    if e == 0xff:
        if m:
            return 0x7F if not (ebits == 5 and mant == 2 and b & 0x7fffff) else 0x7F
        return (s << 7) | (0x7E if ebits == 4 else 0x7B)
    if e == 0:
        return (s << 7)
    E = e - 127
    v = float(fr(b & 0x7fffffff))
    if v >= FP8_MAXV[(ebits, mant)]:
        return (s << 7) | FP8_MAXC[(ebits, mant)]
    if E < -FP8_MIN[(ebits, mant)]:
        u = v / (2.0 ** -FP8_MIN[(ebits, mant)])
        lo = math.floor(u); rem = u - lo
        if rem > 0.5 or (rem == 0.5 and lo % 2 == 1):
            lo += 1
        return (s << 7) | (1 << mant if int(lo) else 0)
    bias = (1 << (ebits - 1)) - 1
    q = _rne((1 << 23) | m, 23 - mant)
    if q == (1 << (mant + 1)):
        q = 1 << mant; E += 1
    emax = (1 << ebits) - 1 if ebits == 4 else (1 << ebits) - 2
    if E + bias > emax:
        return (s << 7) | FP8_MAXC[(ebits, mant)]
    return (s << 7) | (((E + bias) << mant) | (q - (1 << mant)))

def f32_to_e6m9(b, satfinite=False):
    """E6M9 (1+6+9, bias 31) hypothesis: RNE; subnormal-in flush; overflow
    -> inf (or max with satfinite); NaN -> 0x7FFF pattern."""
    s = (b >> 31) & 1; e = (b >> 23) & 0xff; m = b & 0x7fffff
    if e == 0xff:
        if m:
            return (s << 15) | 0x7FFF              # NaN -> all-ones payload (hypothesis)
        return (s << 15) | 0x7E00                 # +-inf (no sat)
    if satfinite and e == 0xff and not m:
        return (s << 15) | 0x7DFF                 # +-inf with .SATFINITE -> max (hypothesis)
    if e == 0:
        return (s << 15)                          # subnormal/zero flush
    E = e - 127
    e9 = E + 31
    frac = (1 << 23) | m
    if satfinite:
        if E > 31:                                # |v| beyond max finite -> max
            return (s << 15) | 0x7DFF
    if e9 >= 63:
        return (s << 15) | 0x7E00                 # overflow -> inf
    if e9 > 0:
        q = _rne(frac, 14)
        if q == (1 << 10):
            q = 1 << 9; e9 += 1
            if e9 >= 63:
                return (s << 15) | 0x7E00
        return (s << 15) | (e9 << 9) | (q & 0x1ff)
    sh = 14 - E
    if sh > 24:
        return (s << 15)
    q, r = divmod(frac, 1 << sh)
    if r * 2 > (1 << sh) or (r * 2 == (1 << sh) and (q & 1)):
        q += 1
    if q >= (1 << 9):
        return (s << 15) | (1 << 9)
    return (s << 15) | q

# fp8_to_f16 helper (sm120-verified)
def fp8_to_f16(b, ebits, mant):
    s = (b >> (ebits + mant)) & 1
    e = (b >> mant) & ((1 << ebits) - 1)
    m = b & ((1 << mant) - 1)
    if ebits == 5 and mant == 2:
        if e == 0x1F and m == 0:
            return 0x7C00 | (s << 15)
        if e == 0x1F:
            return 0x7FFF
    if ebits == 4 and (b & 0xFF) == 0x7F:
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
def add(name, instr, want, pre, probe=False):
    cases.append((name, instr, want, pre, probe))

def fp8pair(hi, lo): return ((hi & 0xff) << 8) | (lo & 0xff)

# --- Hopper-only: E6M9 ------------------------------------------------------
add("E6M9 1.0|2.0 orient",
    "F2FP.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(fb(1.0)) << 16) | f32_to_e6m9(fb(2.0)), {0: fb(1.0), 1: fb(2.0)})
add("E6M9 0.5|-1.5",
    "F2FP.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(fb(0.5)) << 16) | f32_to_e6m9(fb(-1.5)), {0: fb(0.5), 1: fb(-1.5)})
add("E6M9 rne tie-even",
    "F2FP.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(0x3F802000) << 16) | f32_to_e6m9(fb(1.0)), {0: 0x3F802000, 1: fb(1.0)})
add("E6M9 rne up",
    "F2FP.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(0x3F803000) << 16) | f32_to_e6m9(fb(1.0)), {0: 0x3F803000, 1: fb(1.0)})
add("E6M9 65504",
    "F2FP.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(fb(65504.0)) << 16) | 0, {0: fb(65504.0), 1: fb(0.0)})
add("E6M9 2^31",
    "F2FP.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(fb(2.0**31)) << 16) | 0, {0: fb(2.0**31), 1: fb(0.0)})
add("E6M9 overflow->inf",
    "F2FP.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(fb(2.0**32)) << 16) | 0, {0: fb(2.0**32), 1: fb(0.0)})
add("E6M9 +inf",
    "F2FP.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(fb(float('inf'))) << 16) | 0, {0: 0x7F800000, 1: fb(0.0)})
add("E6M9 -inf",
    "F2FP.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(fb(float('-inf'))) << 16) | 0, {0: 0xFF800000, 1: fb(0.0)})
add("E6M9 nan",
    "F2FP.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(0x7FC00000) << 16) | 0, {0: 0x7FC00000, 1: fb(0.0)})
add("E6M9 -0",
    "F2FP.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(0x80000000) << 16) | 0, {0: 0x80000000, 1: fb(0.0)})
add("E6M9 subnorm flush",
    "F2FP.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(0x00000001) << 16) | 0, {0: 0x00000001, 1: fb(0.0)})
add("E6M9 sat 1e10",
    "F2FP.SATFINITE.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(fb(1e10), satfinite=True) << 16) | 0, {0: fb(1e10), 1: fb(0.0)})
add("E6M9 sat -1e10",
    "F2FP.SATFINITE.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(fb(-1e10), satfinite=True) << 16) | 0, {0: fb(-1e10), 1: fb(0.0)})
add("E6M9 relu neg->0",
    "F2FP.RELU.E6M9.F32.PACK_AB {rd}, R0, R1",
    (0 << 16) | f32_to_e6m9(fb(2.0)), {0: fb(-1.0), 1: fb(2.0)})
add("E6M9 2^-25 subnorm result",
    "F2FP.E6M9.F32.PACK_AB {rd}, R0, R1",
    (f32_to_e6m9(fb(2.0 ** -25)) << 16) | 0, {0: fb(2.0 ** -25), 1: fb(0.0)})
# --- arch-diff vs sm120 -----------------------------------------------------
add("f16 nan->?",       "F2FP.F16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(0x0000, 0x7FFF), {0: 0x7FC00000, 1: fb(0.0)})
add("f16 overflow->inf","F2FP.F16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(0x0000, 0x7C00), {0: fb(65520.0), 1: fb(0.0)})
add("bf16 rne tie",     "F2FP.BF16.F32.PACK_AB {rd}, R0, R1",
    f16_pair(f32_to_bf16_rne(fb(1.0)), f32_to_bf16_rne(0x3F808000)), {0: 0x3F808000, 1: fb(1.0)})
add("e4m3 1.0|2.0",     "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(fb(1.0), 4, 3), f32_to_fp8(fb(2.0), 4, 3)), {0: fb(1.0), 1: fb(2.0)})
add("e4m3 nan->?",       "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(0x7FC00000, 4, 3), 0x00), {0: 0x7FC00000, 1: fb(0.0)})
add("e4m3 +inf->max",   "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(0x7F800000, 4, 3), f32_to_fp8(0xFF800000, 4, 3)), {0: 0x7F800000, 1: 0xFF800000})
add("e4m3 relu neg->0", "F2FP.SATFINITE.RELU.E4M3.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(0x00, f32_to_fp8(fb(2.0), 4, 3)), {0: fb(-1.0), 1: fb(2.0)})
add("e5m2 +inf->?",      "F2FP.SATFINITE.E5M2.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(0x7F800000, 5, 2), 0x00), {0: 0x7F800000, 1: fb(0.0)})
add("e5m2 nan->?",       "F2FP.SATFINITE.E5M2.F32.PACK_AB_MERGE_C {rd}, R0, R1, RZ",
    fp8pair(f32_to_fp8(0x7FC00000, 5, 2), 0x00), {0: 0x7FC00000, 1: fb(0.0)})
add("f16->e4m3 pair",   "F2FP.SATFINITE.E4M3.F16.UNPACK_B_MERGE_C {rd}, R0, RZ",
    fp8pair(f32_to_fp8(fb(2.0), 4, 3), f32_to_fp8(fb(1.0), 4, 3)), {0: f16_pair(0x3C00, 0x4000)})
add("up e4m3->f16",     "F2FP.F16.E4M3.UNPACK_B {rd}, R0",
    f16_pair(fp8_to_f16(0x38, 4, 3), fp8_to_f16(0x40, 4, 3)), {0: 0x00004038})
add("up e4m3 nan 0x7F", "F2FP.F16.E4M3.UNPACK_B {rd}, R0",
    f16_pair(0x0000, 0x7FFF), {0: 0x00007F00})
add("tf32 rne",         "F2FP.TF32.F32.PACK_B {rd}, R0",
    0x3F804000, {0: 0x3F803000})
# --- merge semantics (Hopper) ----------------------------------------------
add("merge H0 lo",      "F2FP.F16.F32.MERGE_C {rd}, R0, R1",
    0x0000 | f32_to_f16_rne(fb(1.0)), {0: fb(1.0), 1: 0xCAFE0000})
add("merge H1 hi",      "F2FP.F16.F32.MERGE_C.H1 {rd}, R0, R1",
    f32_to_f16_rne(fb(1.0)) | 0xCAFE0000, {0: fb(1.0), 1: 0xCAFE0000})
add("e4m3f16 merge C",  "F2FP.SATFINITE.E4M3.F16.UNPACK_B_MERGE_C {rd}, R0, R1",
    0x00004038, {0: f16_pair(0x3C00, 0x4000), 1: 0xDEAD0000})
add("e4m3f16 merge H1", "F2FP.SATFINITE.E4M3.F16.UNPACK_B_MERGE_C.H1 {rd}, R0, R1",
    0xDEAD4038, {0: f16_pair(0x3C00, 0x4000), 1: 0xDEAD0000})
add("e4m3f32 merge C",  "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C {rd}, R0, R1, R2",
    0x00003840, {0: fb(1.0), 1: fb(2.0), 2: 0xCAFE0000})

# ---------------------------------------------------------------------------
lines = ["#fn k(out<8>) {",
         "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]"]
off = 0x100
for i, (name, instr, want, pre, probe) in enumerate(cases):
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
    mod = CudaModule(assemble(src, arch="sm90"))
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

d = mod.devmem_alloc(off)
mod.device_write(d, bytes(off))
mod.launch("k", grid=(1,), block=(1,), args=[d])
mod.synchronize()
vec = struct.unpack(f"<{off//4}I", mod.device_read(d, off))
mod.devmem_free(d)

print(f"hopper F2FP battery ({len(cases)} cases):")
for i, (name, instr, want, pre, probe) in enumerate(cases):
    got = vec[(0x100 // 4) + i]
    check(f"[{i:2d}] {name}", got, want, probe)

print(f"\n=== F2FP Hopper: {'ALL PASS' if ok else 'FAILURES — see rows'} ===")
sys.exit(0 if ok else 1)