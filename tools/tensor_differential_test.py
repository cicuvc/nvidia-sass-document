#!/usr/bin/env python3
"""Phase 9 tensor differential gate: C++ interpreter == Python reference model.

Drives the semu interpreter (via `semu run` on a hand-assembled cubin) with
random m16n8 fragments and compares the four FP32 accumulator words D0..D3
BIT-FOR-BIT against tools/hmma_model.py.  Coverage:

  * HMMA.16816 (k16) bf16 / f16, HMMA.1688 (k8) bf16 / f16   -- F32 acc
  * QMMA.16832 (k32) in the five spec-legal fp8 formats (e4m3 / e3m4 /
    e2m3 / e5m2 / e3m2) and QMMA.16816 (k16) in the two spec-legal
    formats (e4m3 / e3m4)                                    -- F32 acc
    NOTE: the sm120 spec restricts the qmma_ srcFmt field to values 0..5
    (6/7 are INVALID6/7) and the 16816 shape to values 0..1 ("size 16816
    only allows srcfmt E5M2 or E4M3" in the qmma_ CLASS conditions, where
    the condition names use the sm120 enum values).  With the probed SM120
    format mapping (E4M3=0, E3M4=1, E2M3=2, E5M2=4, E3M2=5, E2M1=6) the
    exercisable set is therefore k32 = E4M3/E3M4/E2M3/E5M2/E3M2 and
    k16 = E4M3/E3M4; E2M1 (field value 6) is INVALID6 and cannot be
    encoded on either shape.
  * OMMA.SF.16864 (k64) e2m1 mxfp4 with varied E8M0 scales    -- F32 acc

For the formats the shipped model hard-codes (bf16/f16/e4m3) the reference is
hmma_model.fda/hmma_frag/qmma_frag directly; the other fp8 formats use a
generic fp8 FDA reference with the same mant/bias/ebits the engine uses
(identical structure, verified e4m3 path).  Non-e4m3 QMMA words are produced
by patching the srcFmtA/B fields of a base e4m3 encoding with the probed SM120
mapping (E4M3=0 E3M4=1 E2M3=2 E5M2=4 E3M2=5 E2M1=6), so the interpreter sees
the same field values the engine's do_tensor decodes.

Usage: tensor_differential_test.py <path-to-semu> [--trials=N]
"""
import argparse
import json
import random
import struct
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
import hmma_model as M
from assembler import assemble, assemble_flat

NOP = ("    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  "
       "NOP;[7:7:{}:5:1]\n")


# ---------------------------------------------------------------------------
# Kernel templates (global layout = the 16-word fragment register image:
#   offset 0x00: a0 a1 a2 a3   offset 0x10: b0 b1
#   offset 0x20: c0 c1 c2 c3   offset 0x30: re rh (OMMA only)
# D written to offset 0x40.)
# ---------------------------------------------------------------------------

def kernel_body(mma_line, extra_ldg=""):
    return f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6,R7}}, #param(out);[1:7:{{}}:1:0]
    LDG.E.128 {{R16,R17,R18,R19}}, desc[{{UR4,UR5}}][{{R6,R7}}+0x0];[5:7:{{0,1}}:8:1]
    LDG.E.64 {{R20,R21}}, desc[{{UR4,UR5}}][{{R6,R7}}+0x10];[5:7:{{0,1}}:8:1]
    LDG.E.128 {{R24,R25,R26,R27}}, desc[{{UR4,UR5}}][{{R6,R7}}+0x20];[5:7:{{0,1}}:8:1]
{extra_ldg}""" + NOP + NOP + f"""    {mma_line}
""" + NOP + NOP + """    IADD3 R8, R6, 0x40, RZ;[7:7:{1}:5:1]
    IADD3 R9, R7, RZ, RZ;[7:7:{1}:5:1]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x0], R28;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x4], R29;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0x8], R30;[0:1:{0,1}:1:0]
    STG.E desc[{UR4,UR5}][{R8,R9}+0xC], R31;[0:1:{0,1}:1:0]
    EXIT;[7:7:{}:5:0]
}"""

K_HMMA_K16 = kernel_body(
    "HMMA.16816.F32.{SRC} {R28,R29,R30,R31}, {R16,R17,R18,R19}, "
    "{R20,R21}, {R24,R25,R26,R27};[7:7:{5}:1:0]")
K_HMMA_K8 = kernel_body(
    "HMMA.1688.F32.{SRC} {R28,R29,R30,R31}, {R16,R17}, R20, "
    "{R24,R25,R26,R27};[7:7:{5}:1:0]")
K_QMMA_K32 = kernel_body(
    "QMMA.16832.F32.E4M3.E4M3 {R28,R29,R30,R31}, {R16,R17,R18,R19}, "
    "{R20,R21}, {R24,R25,R26,R27};[7:7:{5}:1:0]")
K_QMMA_K16 = kernel_body(
    "QMMA.16816.F32.E4M3.E4M3 {R28,R29,R30,R31}, {R16,R17}, R20, "
    "{R24,R25,R26,R27};[7:7:{5}:1:0]")

# Exact QMMA SASS lines (used to locate/patch the srcFmt fields).
MMA_QMMA_K32 = (
    "QMMA.16832.F32.E4M3.E4M3 {R28,R29,R30,R31}, {R16,R17,R18,R19}, "
    "{R20,R21}, {R24,R25,R26,R27};[7:7:{5}:1:0]")
MMA_QMMA_K16 = (
    "QMMA.16816.F32.E4M3.E4M3 {R28,R29,R30,R31}, {R16,R17}, R20, "
    "{R24,R25,R26,R27};[7:7:{5}:1:0]")

K_OMMA = kernel_body(
    "OMMA.SF.16864.F32.E2M1.E2M1.E8 {R28,R29,R30,R31}, {R16,R17,R18,R19}, "
    "{R20,R21}, {R24,R25,R26,R27}, R22, R23, URZ;[7:7:{5}:1:0]",
    extra_ldg="    LDG.E.64 {R22,R23}, desc[{UR4,UR5}][{R6,R7}+0x30];[5:7:{0,1}:8:1]\n")


# ---------------------------------------------------------------------------
# Generic fp8 FDA reference (identical structure to the engine; e4m3 == model)
# ---------------------------------------------------------------------------

def fda_generic(fmt, c, a_vals, b_vals):
    """One fp8 output element for any of the six fp8 formats.

    Matches the engine's params (mant/bias/ebits) and the verified e4m3 path
    for e4m3 (checked against hmma_model.fda on random inputs).
    """
    if fmt == "e4m3":
        return M.fda(c, a_vals, b_vals, "e4m3")
    if fmt == "e5m2": mant, bias, ebits = 2, 15, 5
    elif fmt == "e3m4": mant, bias, ebits = 4, 3, 3
    elif fmt == "e2m3": mant, bias, ebits = 3, 1, 2
    elif fmt == "e3m2": mant, bias, ebits = 2, 3, 3
    elif fmt == "e2m1": mant, bias, ebits = 1, 1, 2
    else: raise ValueError(fmt)

    if M._special(c, 23) == "nan":
        return M.NAN_OUT
    for a, b in zip(a_vals, b_vals):
        if a in (0x7F, 0xFF) or b in (0x7F, 0xFF):
            return M.NAN_OUT
    c_sp = M._special(c, 23)
    if c_sp in ("+inf", "-inf"):
        return 0x7F800000 if c_sp == "+inf" else 0xFF800000

    def _sm(v):
        sign = -1 if (v >> (mant + ebits)) else 1
        e = (v >> mant) & ((1 << ebits) - 1)
        m = v & ((1 << mant) - 1)
        if e == 0:
            return sign, m, mant, 1 - bias
        return sign, (1 << mant) + m, mant, e - bias

    c_sign, c_num, c_den, c_e = M._fp32_sm(c)
    have_c = c_num != 0
    e_max = c_e if have_c else None
    prods = []
    for a, b in zip(a_vals, b_vals):
        sa, anum, aden, ae = _sm(a)
        sb, bnum, bden, be = _sm(b)
        p = (sa * sb, anum * bnum, aden + bden, ae + be)
        prods.append(p)
        if e_max is None or p[3] > e_max:
            e_max = p[3]
    if e_max is None:
        e_max = 0
    total = 0
    if have_c:
        total += M._to_fixed(c_sign * c_num, c_den, c_e - e_max + M.F)
    for sign, num, den_log2, e in prods:
        total += M._to_fixed(sign * num, den_log2, e - e_max + M.F)
    return M._normalize_fp32(total, e_max - M.F)


def ref_qmma(frag16, fmt):
    """m16n8k32 fp8 fragment reference for any fp8 format."""
    a = [frag16[i] for i in range(4)]
    b = [frag16[4], frag16[5]]
    ai = [[(a[i] >> (8 * j)) & 0xFF for j in range(4)] for i in range(4)]
    bi = [[(b[i] >> (8 * j)) & 0xFF for j in range(4)] for i in range(2)]
    P, Q = [], []
    for j in range(4):
        P += [ai[0][j], bi[0][j]] * 4 + [ai[2][j], bi[1][j]] * 4
        Q += [ai[1][j], bi[0][j]] * 4 + [ai[3][j], bi[1][j]] * 4
    A, B = P[0::2], P[1::2]
    A2, B2 = Q[0::2], Q[1::2]
    return [fda_generic(fmt, frag16[8], A, B),
            fda_generic(fmt, frag16[9], A, B),
            fda_generic(fmt, frag16[10], A2, B2),
            fda_generic(fmt, frag16[11], A2, B2)]


def ref_qmma_k16(frag16, fmt):
    """m16n8k16 fp8 fragment reference (a0/a1, b0; a2/a3/b1 unused)."""
    a0, a1, b0 = frag16[0], frag16[1], frag16[4]
    c = frag16[8:12]
    P, Q = [], []
    for j in range(4):
        a0j = (a0 >> (8 * j)) & 0xFF
        a1j = (a1 >> (8 * j)) & 0xFF
        b0j = (b0 >> (8 * j)) & 0xFF
        P += [a0j, b0j] * 4
        Q += [a1j, b0j] * 4
    A, B = P[0::2], P[1::2]
    A2, B2 = Q[0::2], Q[1::2]
    return [fda_generic(fmt, c[0], A, B), fda_generic(fmt, c[1], A, B),
            fda_generic(fmt, c[2], A2, B2), fda_generic(fmt, c[3], A2, B2)]


def ref_hmma_k8(frag16, fmt):
    """m16n8k8 bf16/f16 fragment reference (a0/a1, b0; 2 distinct pairs x4)."""
    a0, a1, b0 = frag16[0], frag16[1], frag16[4]
    c = frag16[8:12]
    al0, ah0 = a0 & 0xFFFF, a0 >> 16
    al1, ah1 = a1 & 0xFFFF, a1 >> 16
    b0l, b0h = b0 & 0xFFFF, b0 >> 16
    P = [al0, b0l] * 4 + [ah0, b0h] * 4
    Q = [al1, b0l] * 4 + [ah1, b0h] * 4
    A, B = P[0::2], P[1::2]
    A2, B2 = Q[0::2], Q[1::2]
    return [M.fda(c[0], A, B, fmt), M.fda(c[1], A, B, fmt),
            M.fda(c[2], A2, B2, fmt), M.fda(c[3], A2, B2, fmt)]


def ref_omma(frag16):
    return M.omma_frag(frag16)


# ---------------------------------------------------------------------------
# Fragment generators
# ---------------------------------------------------------------------------

def rnd8():
    if random.random() < 0.15:
        return random.choice([0x7F, 0xFF, 0x7C, 0xFC, 0x00, 0x80])
    return random.randint(0, 255)


def rnd_fp8_word():
    return rnd8() | (rnd8() << 8) | (rnd8() << 16) | (rnd8() << 24)


def rnd_half():
    return random.choice([0x3F80, 0xC000, 0x4000, 0x7F80, 0xFF80, 0x7FC0,
                          0x0001, 0x0000, 0x8000, 0x3C00]) | random.randint(0, 1)


def rnd_half_word():
    return rnd_half() | (rnd_half() << 16)


def rnd_c():
    r = random.random()
    if r < 0.8:
        return struct.unpack("<I", struct.pack("<f", random.uniform(-1e4, 1e4)))[0]
    if r < 0.9:
        return struct.unpack("<I", struct.pack("<f", random.uniform(-1e35, 1e35)))[0]
    if r < 0.95:
        return random.choice([0, 0x80000000, 0x7F800000, 0xFF800000])
    return random.choice([0x7FC00000, 0x7F800001, 0xFFC00000])


def rnd_e2m1_nibble():
    return random.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0xA, 0xB, 0xC, 0xD, 0xE, 0xF])


def rnd_e2m1_word():
    return sum(rnd_e2m1_nibble() << (4 * n) for n in range(8))


def rnd_scale_word():
    return random.choice([0x7F7F7F7F, 0x80808080, 0x00000000, 0x01010101,
                          0x7E7E7E7E, 0x7F3F7F3F, 0xFE7F7FFE]) if random.random() < 0.5 \
        else random.getrandbits(32)


# ---------------------------------------------------------------------------
# QMMA srcFmt patching (probed SM120 mapping) + cubin text patch
# ---------------------------------------------------------------------------

QMMA_FMT_FIELD = {"e4m3": 0, "e3m4": 1, "e2m3": 2, "e5m2": 4, "e3m2": 5,
                  "e2m1": 6}


def patch_qmma_srcfmt(cubin, qmma_line, fmtA, fmtB):
    """Patch srcFmtA/srcFmtB in the QMMA instruction word inside the cubin.

    The qmma_ ENCODING places srcFmtA at bits [83:82] (high two bits) then
    [78] (low bit) — i.e. the 3-bit field value is 4*b83 + 2*b82 + b78 — so
    to write the semantic value `fa` the low bit goes to b78 and the high two
    bits to 82..83.  The same layout applies to srcFmtB (bits [85:84]/[79]).
    Returns the patched cubin.  The (lo,hi) word (assembled from the kernel's
    own QMMA line, so registers match) appears exactly once.
    """
    fa, fb = QMMA_FMT_FIELD[fmtA], QMMA_FMT_FIELD[fmtB]
    lo, hi = assemble_flat(qmma_line)[0]
    w = lo | (hi << 64)
    w &= ~((1 << 78))  # clear b78 (srcFmtA low bit)
    w &= ~((0b11 << 82))  # clear [83:82] (srcFmtA high bits)
    w &= ~((1 << 79))  # clear b79 (srcFmtB low bit)
    w &= ~((0b11 << 84))  # clear [85:84] (srcFmtB high bits)
    w |= (fa & 1) << 78
    w |= ((fa >> 1) & 0b11) << 82
    w |= (fb & 1) << 79
    w |= ((fb >> 1) & 0b11) << 84
    plo, phi = w & 0xFFFFFFFFFFFFFFFF, (w >> 64) & 0xFFFFFFFFFFFFFFFF
    pat = struct.pack("<QQ", lo, hi)
    new = struct.pack("<QQ", plo, phi)
    idx = cubin.find(pat)
    if idx < 0:
        raise RuntimeError("QMMA word not found in cubin")
    return cubin[:idx] + new + cubin[idx + 16:]


def fiv(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


# ---------------------------------------------------------------------------
# Per-family case runner
# ---------------------------------------------------------------------------

class Case:
    def __init__(self, name, kernel, frag, frag_fmt, patch=None, frag16=None,
                 mma_line=None):
        self.name = name
        self.kernel = kernel        # template (with {SRC} for HMMA)
        self.frag = frag            # fragment register image (words)
        self.frag_fmt = frag_fmt    # python format tag ('bf16','f16','e4m3',...)
        self.patch = patch          # (fmtA, fmtB) for QMMA srcFmt patch
        self.frag16 = frag16        # 16-word python-model fragment (optional)
        self.mma_line = mma_line    # exact QMMA SASS line (for srcFmt patch)


def mangle(name):
    return f"_Z{len(name)}{name}"


def build_and_run(semu, case, global_words):
    """Assemble the kernel, patch as needed, run semu, return D words."""
    src = case.kernel.replace("{SRC}", case.frag_fmt)
    cubin = assemble(src)
    if case.patch:
        # Patch the srcFmt fields of the kernel's actual QMMA line.
        cubin = patch_qmma_srcfmt(cubin, case.mma_line, *case.patch)

    buf = [0] * 256
    buf[:len(global_words)] = global_words
    ghex = struct.pack("<%dI" % len(buf), *buf).hex()

    with open("/tmp/semu_tensor_diff.cubin", "wb") as f:
        f.write(cubin)
    # The assembler emits the mangled symbol (_Z1k) as the ELF kernel name;
    # semu's find_kernel does an exact match on that mangled name.  Options
    # must precede the positional args (semu's option parser stops at the
    # first positional).
    r = subprocess.run([str(semu), "run", "--global=" + ghex,
                        "/tmp/semu_tensor_diff.cubin", mangle("k"),
                        "1", "32"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None, (f"semu run failed rc={r.returncode}: "
                      f"stderr={r.stderr[-400:]} stdout={r.stdout[-200:]}")
    out = json.loads(r.stdout)
    global_hex = out.get("global", "")
    gb = bytes.fromhex(global_hex)
    if len(gb) < 0x50:
        return None, "global output too short"
    return list(struct.unpack("<4I", gb[0x40:0x50])), None


def run_case(semu, case, expected_fn):
    # Build the 16-word model fragment (the frag register image with pads).
    f = [0] * 16
    f[:len(case.frag)] = case.frag
    f16 = case.frag16 if case.frag16 is not None else f
    want = expected_fn(f16)
    d, err = build_and_run(semu, case, case.frag)
    if err:
        return False, f"{case.name}: {err}"
    if d != want:
        return False, (f"{case.name}: C++ {[hex(x) for x in d]} != "
                       f"python {[hex(x) for x in want]}")
    return True, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("semu", help="path to the semu CLI binary")
    ap.add_argument("--trials", type=int, default=6)
    args = ap.parse_args()
    semu = Path(args.semu).resolve()
    if not semu.exists():
        print(f"FAIL: semu binary not found: {semu}", file=sys.stderr)
        return 2

    random.seed(0x7E57C0DE)
    total = 0
    fails = 0
    checked = 0  # never auto-pass

    def run(case, expected_fn):
        nonlocal total, fails, checked
        total += 1
        ok, msg = run_case(semu, case, expected_fn)
        checked += 1
        if not ok:
            fails += 1
            print(f"FAIL {msg}")

    for t in range(args.trials):
        # HMMA k16 bf16 / f16
        frag = [rnd_half_word() for _ in range(6)] + [rnd_c() for _ in range(4)]
        run(Case(f"hmma_k16_bf16_t{t}",
                 K_HMMA_K16, frag, "bf16"),
            lambda f16: M.hmma_frag(f16, "bf16"))
        run(Case(f"hmma_k16_f16_t{t}",
                 K_HMMA_K16, frag, "f16"),
            lambda f16: M.hmma_frag(f16, "f16"))
        # HMMA k8 bf16 / f16 (a0/a1, b0, c)
        frag8 = [rnd_half_word() for _ in range(2)] + [rnd_half_word()] + \
                [rnd_c() for _ in range(4)]
        frag8img = [frag8[0], frag8[1], 0, 0, frag8[2], 0, 0, 0] + frag8[3:]
        run(Case(f"hmma_k8_bf16_t{t}",
                 K_HMMA_K8, frag8img, "bf16", frag16=frag8img),
            lambda f16: ref_hmma_k8(f16, "bf16"))
        run(Case(f"hmma_k8_f16_t{t}",
                 K_HMMA_K8, frag8img, "f16", frag16=frag8img),
            lambda f16: ref_hmma_k8(f16, "f16"))
        # QMMA k32 — the spec-legal srcFmt values under the probed mapping
        # are 0..5 (INVALID6/7 rejected by the qmma_ CLASS conditions), i.e.
        # E4M3/E3M4/E2M3/E5M2/E3M2.
        qfrag = [rnd_fp8_word() for _ in range(6)] + [rnd_c() for _ in range(4)]
        for fmt in ["e4m3", "e3m4", "e2m3", "e5m2", "e3m2"]:
            run(Case(f"qmma_k32_{fmt}_t{t}",
                     K_QMMA_K32, qfrag, fmt, patch=(fmt, fmt),
                     mma_line=MMA_QMMA_K32),
                lambda f16, fmt=fmt: ref_qmma(f16, fmt))
        # QMMA k16 — the sm120 spec restricts the 16816 shape to srcFmt
        # field values 0..1 ("size 16816 only allows srcfmt E5M2 or E4M3" in
        # the qmma_ CLASS condition, named per the sm120 enum); under the
        # probed mapping those are E4M3 (0) and E3M4 (1), so only those two
        # formats are exercised (patching any other value decodes illegal).
        q16 = [rnd_fp8_word() for _ in range(2)] + [rnd_fp8_word()] + \
              [rnd_c() for _ in range(4)]
        q16img = [q16[0], q16[1], 0, 0, q16[2], 0, 0, 0] + q16[3:]
        for fmt in ["e4m3", "e3m4"]:
            run(Case(f"qmma_k16_{fmt}_t{t}",
                     K_QMMA_K16, q16img, fmt, patch=(fmt, fmt), frag16=q16img,
                     mma_line=MMA_QMMA_K16),
                lambda f16, fmt=fmt: ref_qmma_k16(f16, fmt))
        # OMMA k64 e2m1 with random scales.  The kernel's LDG layout places
        # A at words 0-3, B at 4-5, C at 8-11, Re/Rh at 12-13 (words 6-7
        # unused); the model fragment (frag16) instead is [A,B,Re,Rh,C].
        ofrag = [rnd_e2m1_word() for _ in range(6)] + [rnd_c() for _ in range(4)] \
                + [rnd_scale_word(), rnd_scale_word()]
        og_glob = [ofrag[0], ofrag[1], ofrag[2], ofrag[3],  # A
                   ofrag[4], ofrag[5],                      # B
                   0, 0,                                    # unused
                   ofrag[6], ofrag[7], ofrag[8], ofrag[9],  # C at 8-11
                   ofrag[10], ofrag[11]]                    # Re,Rh at 12-13
        om16 = [ofrag[0], ofrag[1], ofrag[2], ofrag[3],
                ofrag[4], ofrag[5], ofrag[10], ofrag[11]] + ofrag[6:10]
        run(Case(f"omma_k64_t{t}",
                 K_OMMA, og_glob, "e2m1", frag16=om16),
            lambda f16: M.omma_frag(f16))

    if checked == 0:
        print("FAIL: no cases ran", file=sys.stderr)
        return 1
    print(f"tensor differential: {checked} cases, {fails} failures, "
          f"0 skipped")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
