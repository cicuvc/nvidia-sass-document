import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat

# ---------------------------------------------------------------------------
# I2I / I2F / F2I / F2F — integer/float conversion families.  Verified SM120.
#
#   I2I.SAT.<U8|S8|U16|S16> Rd, Rb       S32 -> narrow, saturate (int_pipe)
#   I2F.<F32|F64>.<S32|U32|S16|...> Rd,Rb   int -> float (mio_pipe)
#   F2I.<S32|U32>.<F32>.<ROUND|FLOOR|CEIL|TRUNC>[.FTZ] Rd,Rb  float->int
#   F2F.<F16|BF16|F32>.<F32|F16|BF16> Rd,Rb  float format convert (mio_pipe)
#
# I2F/F2I/F2F are mio_pipe DECOUPLED_RD_WR_SCBD (MUFU queue): load input with
# wr=SB1, the conversion req={1} + wr=SB2, consumer STG req={1,2}.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<46} got 0x{got:016x} want 0x{want:016x}")

def fb(v): return struct.unpack("<I", struct.pack("<f", v))[0]
def ffrom(b): return struct.unpack("<f", struct.pack("<I", b & 0xFFFFFFFF))[0]
def db(v): return struct.unpack("<Q", struct.pack("<d", v))[0]
def df(b): return struct.unpack("<d", struct.pack("<Q", b & 0xFFFFFFFFFFFFFFFF))[0]

def f32_to_f16_bits(f):
    b = fb(f)
    e = (b >> 23) & 0xff
    if e == 0: return 0                       # zero/subnormal -> 0
    if e == 0xff: return 0x7C00 | ((b >> 16) & 0x8000) | (0x200 if b & 0x7fffff else 0)
    return (((b >> 16) & 0x8000) | ((e - 112) << 10) | ((b >> 13) & 0x3ff)) & 0xFFFF
def f16_to_f32(v):
    s = (v >> 15) & 1; e = (v >> 10) & 0x1f; m = v & 0x3ff
    if e == 0x1f: return fb(float("inf") * (-1 if s else 1))
    if e == 0: return fb(0.0 * (-1 if s else 1))
    return fb(ffrom(((s << 31) | ((e - 15 + 127) << 23) | (m << 13))))
def f32_to_bf16_bits(f):
    b = fb(f)
    return ((b + 0x8000) >> 16) & 0xFFFF   # round-to-nearest-ish
def bf16_to_f32(v):
    return fb(ffrom(((v & 0xFFFF) << 16)))

def round_f32(f, mode):
    import math
    if mode == "TRUNC":  return math.trunc(f)
    if mode == "FLOOR":  return math.floor(f)
    if mode == "CEIL":   return math.ceil(f)
    if mode == "ROUND":  # nearest even
        lo = math.floor(f); hi = math.ceil(f)
        if f - lo == hi - f:  return hi if lo % 2 else lo
        return round(f)
    return int(f)

def run_mio(instr, x, xregs=1, dregs=1):
    """mio_pipe conversion: load x into R0 (or R0:R1), run instr (Rd=R8/R8:R9),
    store result.  wr=SB2 on the conversion, STG req={1,2}."""
    lines = ["    LDCU.64 {UR4,UR5}, c[0x0][0x358];[1:7:{}:1:0]",
             "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]",
             "    LDC R0, #param(p0);[1:7:{}:1:0]"]
    if xregs == 2:
        lines.append("    LDC R1, #param(p1);[1:7:{}:1:0]")
    lines.append(f"    {instr}")
    lines.append("    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R8;[0:1:{1,2}:1:0]")
    if dregs == 2:
        lines.append("    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R9;[0:1:{1,2}:1:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    sig = "out<8>, p0<4>" + (", p1<4>" if xregs == 2 else "")
    src = "#fn k(%s) {\n%s\n}" % (sig, "\n".join(lines))
    mod = CudaModule(assemble(src))
    d = mod.devmem_alloc(64)
    try:
        args = [d, x & 0xFFFFFFFF]
        if xregs == 2:
            args.append((x >> 32) & 0xFFFFFFFF)
        mod.launch("k", grid=(1,), block=(1,), args=args)
        mod.synchronize()
        v = struct.unpack("<4I", mod.device_read(d, 16))
        return v[0] | (v[1] << 32)
    finally:
        try: mod.devmem_free(d)
        except: pass

# --- I2I: S32 -> narrow, saturate (int_pipe) -------------------------------
def i2i_sat(dst, x):
    x = x & 0xFFFFFFFF
    if x >> 31: x -= 0x100000000
    lo, hi = {"U8": (0,255), "S8": (-128,127), "U16": (0,65535), "S16": (-32768,32767)}[dst]
    return max(lo, min(hi, x)) & 0xFFFFFFFF

def i2i_run(dst, x):
    src = ("#fn k(out<8>, p0<4>) {\n"
           "    LDCU.64 {UR4,UR5}, c[0x0][0x358];[1:7:{}:1:0]\n"
           "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
           "    LDC R0, #param(p0);[1:7:{}:1:0]\n"
           f"    I2I.SAT.{dst} R8, R0;[7:7:{{1}}:5:1]\n"
           "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R8;[0:1:{1}:1:0]\n"
           "    EXIT;[7:7:{}:5:0]\n}")
    mod = CudaModule(assemble(src))
    d = mod.devmem_alloc(64)
    try:
        mod.launch("k", grid=(1,), block=(1,), args=[d, x]); mod.synchronize()
        return struct.unpack("<4I", mod.device_read(d, 16))[0]
    finally:
        try: mod.devmem_free(d)
        except: pass

for dst, vals in [("U8", [0,1,100,255,256,-1,-200,0x7FFFFFFF,0x80000000]),
                  ("S8", [0,1,127,128,-1,-128,-129,1000,-1000]),
                  ("U16", [0,1,65535,65536,-1,0x7FFFFFFF,0x80000000]),
                  ("S16", [0,1,32767,32768,-1,-32768,-32769,100000])]:
    for x in vals:
        check(f"I2I.SAT.{dst}({x})", i2i_run(dst, x), i2i_sat(dst, x))

# --- I2F: int -> float -----------------------------------------------------
def s32(v): v &= 0xFFFFFFFF; return v - 0x100000000 if v >> 31 else v
def u32(v): return v & 0xFFFFFFFF
def s16(v): v &= 0xFFFF;     return v - 0x10000 if v >> 15 else v

for fmt, x in [("S32", 5), ("S32", -7), ("S32", 0), ("S32", 0x7FFFFFFF),
               ("S32", -0x80000000), ("U32", 0x80000000), ("U32", 0xFFFFFFFF),
               ("S16", 0xFFFF), ("S16", 0x0005), ("U16", 0xFFFF)]:
    r = run_mio(f"I2F.F32.{fmt} R8, R0;[2:7:{{1}}:8:1]", x)
    if fmt == "S32":   want = fb(float(s32(x)))
    elif fmt == "U32": want = fb(float(u32(x)))
    elif fmt == "S16": want = fb(float(s16(x)))
    else:              want = fb(float(u32(x) & 0xFFFF))
    check(f"I2F.F32.{fmt}({x:#x})", r, want)
# F64 dest
for fmt, x in [("S32", -123456), ("U32", 0xFFFFFFFF)]:
    r = run_mio(f"I2F.F64.{fmt} {{R8,R9}}, R0;[2:7:{{1}}:8:1]", x, dregs=2)
    want = db(float(s32(x))) if fmt == "S32" else db(float(u32(x)))
    check(f"I2F.F64.{fmt}({x:#x})", r, want)
for fmt, x in [("S64", 0x123456789)]:
    r = run_mio(f"I2F.F64.{fmt} {{R8,R9}}, {{R0,R1}};[2:7:{{1}}:8:1]", x, xregs=2, dregs=2)
    v = s64 = (x & 0xFFFFFFFFFFFFFFFF)
    want = db(float(v - 0x10000000000000000 if v >> 63 else v))
    check(f"I2F.F64.{fmt}({x:#x})", r, want)

# --- F2I: float -> int (4 rounding modes + U32 + FTZ) ----------------------
F32S = [1.5, 2.5, -1.5, -2.5, 3.7, -3.7, 0.0, 100.0, -100.0, 2147483647.0, -2147483648.0, 0.5, -0.5]
for mode in ["ROUND", "FLOOR", "CEIL", "TRUNC"]:
    for f in F32S:
        r = run_mio(f"F2I.S32.F32.{mode} R8, R0;[2:7:{{1}}:8:1]", fb(f))
        check(f"F2I.S32.F32.{mode}({f})", r, round_f32(f, mode) & 0xFFFFFFFF)
for f in [1.5, 3.7, 4294967295.0, 0.0, 2.9]:
    r = run_mio(f"F2I.U32.F32.TRUNC R8, R0;[2:7:{{1}}:8:1]", fb(f))
    check(f"F2I.U32.F32.TRUNC({f})", r, round_f32(f, "TRUNC") & 0xFFFFFFFF)
# FTZ flushes denormal inputs
r = run_mio("F2I.S32.F32.FTZ.TRUNC R8, R0;[2:7:{1}:8:1]", 0x00000001)  # denormal
check("F2I.S32.F32.FTZ(denorm) -> 0", r, 0)
r = run_mio("F2I.S32.F32.TRUNC R8, R0;[2:7:{1}:8:1]", 0x00000001)
check("F2I.S32.F32 noFTZ(denorm) -> 0 (trunc of tiny)", r, 0)

# --- F2F: float format conversion -------------------------------------------
F16V = [0.0, 1.0, -1.0, 1.5, -2.0, 65504.0, 0.00006103515625]  # exact f16 values
for f in F16V:
    r = run_mio(f"F2F.F16.F32 R8, R0;[2:7:{{1}}:8:1]", fb(f))
    check(f"F2F.F16.F32({f})", r & 0xFFFF, f32_to_f16_bits(f))
for h in [0x3C00, 0xBC00, 0x4200, 0xC400, 0x7BFF]:  # 1.0, -1.0, 32, -128, 65504
    r = run_mio(f"F2F.F32.F16 R8, R0;[2:7:{{1}}:8:1]", h)
    check(f"F2F.F32.F16(0x{h:04x})", r, f16_to_f32(h))
for f in [0.0, 1.0, -1.0, 3.140625, -100.0, 65504.0]:
    r = run_mio(f"F2F.BF16.F32 R8, R0;[2:7:{{1}}:8:1]", fb(f))
    check(f"F2F.BF16.F32({f})", r & 0xFFFF, f32_to_bf16_bits(f))
for h in [0x3F80, 0xBF80, 0x4049, 0x42C8]:  # 1.0, -1.0, ~3.14, ~100
    r = run_mio(f"F2F.F32.BF16 R8, R0;[2:7:{{1}}:8:1]", h)
    check(f"F2F.F32.BF16(0x{h:04x})", r, bf16_to_f32(h))

# --- offline encoding self-check -------------------------------------------
enc = assemble_flat(
    "I2I.SAT.U8 R3, R0;[7:7:{}:5:1]\n"
    "I2I.SAT.S16 R3, R0;[7:7:{}:5:1]\n"
    "I2F.F32.S32 R3, R0;[7:7:{}:5:1]\n"
    "I2F.F32.U32 R3, R0;[7:7:{}:5:1]\n"
    "F2I.S32.F32 R3, R0;[7:7:{}:5:1]\n"
    "F2I.S32.F32.TRUNC R3, R0;[7:7:{}:5:1]\n"
    "F2F.F16.F32 R3, R0;[7:7:{}:5:1]\n"
    "F2F.F32.F16 R3, R0;[7:7:{}:5:1]\n")
ops = [e[0] & 0xFFF for e in enc]
assert ops[:2] == [0x238, 0x238], ops
assert ops[2:4] == [0x306, 0x306], ops
assert ops[4:6] == [0x305, 0x305], ops
assert ops[6:8] == [0x304, 0x304], ops
# F2I dstfmt/srcfmt distinguish
assert (enc[0][1] >> 12) & 3 == 0 and (enc[1][1] >> 12) & 3 == 3, "I2I dstfmt"
print("encoding self-check: opcodes + I2I dstfmt OK")

print(f"\n=== I2I / I2F / F2I / F2F: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
