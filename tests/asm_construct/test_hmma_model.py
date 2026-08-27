import sys, struct, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from assembler import assemble, CudaModule
from archutil import adapt_source  # noqa: E402
import hmma_model as M

# ---------------------------------------------------------------------------
# Bit-accurate tensor-core fp16/bf16 model (FDA, F=25, RZ) vs SM120 hardware.
#
# hmma_model.fda() implements the Fused-Dot-Add algorithm of arXiv:2511.10909
# (Hopper HMMA.16816.F32/.BF16: F=25 align bits, exact fixed-point sum,
# round-to-zero at the FP32 23rd bit, canonical NaN 0x7FFFFFFF, full subnormal
# support).  hmma_model.hmma_frag() maps a 16-word m16n8k16 fragment
# (a0..a3, b0..b1, c0..c3) to D0..D3 via the probed slot layout.
#
# The random fragment tests here re-launch the hand-assembled HMMA on the
# simulator with the exact same fragment words and compare all four D outputs
# bit-for-bit against the model.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = list(got) == list(want)
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<44} {got}")

NOP = "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
KERNEL = """#fn k(out<8>, gsrc<8>) {
    ULDC.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[7:7:{}:2:0]
    LDC.64 {R6,R7}, #param(gsrc);[1:7:{}:1:0]
    LDC.64 {R2,R3}, #param(out);[2:7:{}:1:0]
    LDG.E.128 {R16,R17,R18,R19}, desc[{UR4,UR5}][{R6,R7}+0x0];[5:7:{1}:8:1]
    LDG.E.64 {R20,R21}, desc[{UR4,UR5}][{R6,R7}+0x10];[5:7:{1}:8:1]
    LDG.E.128 {R24,R25,R26,R27}, desc[{UR4,UR5}][{R6,R7}+0x20];[5:7:{1}:8:1]
""" + NOP + NOP + """    HMMA.16816.F32.{SRCFMT} {R28,R29,R30,R31}, {R16,R17,R18,R19}, {R20,R21}, {R24,R25,R26,R27};[7:7:{5}:1:0]
""" + NOP + NOP + """    IADD3 R8, R2, 0x40, RZ;[7:7:{1}:5:1]
    IADD3 R9, R3, RZ, RZ;[7:7:{1}:5:1]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x0], R28;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x4], R29;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x8], R30;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0xC], R31;[0:1:{0,1}:1:0]
    EXIT;[7:7:{}:5:0]
}"""


def run_hw(srcfmt, frag16):
    mod = CudaModule(assemble(adapt_source(KERNEL.replace("{SRCFMT}", srcfmt))))
    d = mod.devmem_alloc(2048 * 4)
    buf = [0] * 2048
    buf[:16] = frag16
    mod.device_write(d, struct.pack("<%dI" % 2048, *buf))
    mod.launch("k", grid=(1,), block=(32,), args=[d, d])
    mod.synchronize()
    out = struct.unpack("<4I", mod.device_read(d + 0x40, 16))
    try:
        mod.devmem_free(d)
    except Exception:
        pass
    return out


def rand_half(fmt):
    """Layered random bf16/f16: normal, extreme exponents, subnormal/zero,
    and NaN/inf (so the FDA special-value paths are exercised)."""
    mant = 7 if fmt == "bf16" else 10
    ebits = 8 if fmt == "bf16" else 5
    r = random.random()
    if r < 0.5:
        e = random.randint(1, (1 << ebits) - 2)
        m = random.randint(0, (1 << mant) - 1)
    elif r < 0.7:
        c = random.random()
        if c < 0.3:
            e, m = 1, 0                       # min normal
        elif c < 0.6:
            e, m = (1 << ebits) - 2, (1 << mant) - 1   # max normal
        elif c < 0.85:
            e, m = 0, random.randint(1, (1 << mant) - 1)  # subnormal
        else:
            e, m = 0, 0                       # zero
    else:
        if random.random() < 0.5:
            e, m = (1 << ebits) - 1, 0        # inf
        else:
            e, m = (1 << ebits) - 1, random.randint(1, (1 << mant) - 1)  # NaN
    v = (e << mant) | m
    if random.random() < 0.5:
        v |= 1 << (mant + ebits)
    return v


def rand_f32():
    r = random.random()
    if r < 0.75:
        return struct.unpack("<I", struct.pack("<f", random.uniform(-1e4, 1e4)))[0]
    if r < 0.85:
        return struct.unpack("<I", struct.pack("<f", random.uniform(-1e35, 1e35)))[0]
    if r < 0.93:
        return random.choice([0, 0x80000000])
    if r < 0.97:
        return random.choice([0x7F800000, 0xFF800000])
    return random.choice([0x7FC00000, 0x7F800001, 0xFFC00000])


# --- FDA model self-test (already-verified bit vectors) ---------------------
selftest_ok = M.selftest()
check("model self-test", [selftest_ok], [True])

# --- random fragments vs hardware, bit-exact ---------------------------------
random.seed(0xC0FFEE)
for fmt, sf in [("bf16", "BF16"), ("f16", "F16")]:
    for trial in range(16):
        frag = [rand_half(fmt) | (rand_half(fmt) << 16) if i < 6 else rand_f32()
                for i in range(16)]
        hw = run_hw(sf, frag)
        md = M.hmma_frag(frag, fmt)
        check(f"{fmt} random frag {trial}", hw, md)

print(f"\n=== HMMA bit-accurate model (FDA): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
