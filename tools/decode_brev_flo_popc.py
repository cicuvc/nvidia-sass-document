#!/usr/bin/env python3
"""BREV + POPC + FLO decoders (sm_90).  Validated against ptxas + SM120 probes.

  BREV Rd, Rb / imm / cbank / URb           bit reverse (mio_pipe)
  POPC Rd, [!]Rb / imm / cbank / URb        popcount ([~] = count zeros)
  FLO[.U32][.SH] Rd, [Pu,] [!]Rb            find leading one (PTX bfind)

FLO: fmt/SH at hi[73:74] (0x0=U32.nosh, 0x1=U32.SH, 0x2=S32.nosh, 0x3=S32.SH);
     Pu at hi[83:81] (7=PT, hidden); Sb_invert at lo[63].
"""


def ext(l, h, m, s):
    v = 0
    for b in range(s, m + 1):
        v |= (((h >> (b - 64)) if b >= 64 else (l >> b)) & 1) << (b - s)
    return v


def _src(lo, hi, imm=False):
    invert = ext(lo, hi, 63, 63)
    til = "~" if invert else ""
    return til


def _reg(r):
    return "RZ" if r == 255 else f"R{r}"


def _ur(r):
    return "URZ" if r == 255 else f"UR{r}"


def decode_brev(lo, hi):
    op = ext(lo, hi, 91, 91) << 12 | ext(lo, hi, 11, 0)
    rd = _reg(ext(lo, hi, 23, 16))
    if op == 0x301:
        return f"BREV {rd}, {_reg(ext(lo, hi, 39, 32))}", "RRR"
    if op == 0x901:
        return f"BREV {rd}, 0x{ext(lo, hi, 63, 32):x}", "RIR"
    if op == 0xb01:
        b = ext(lo, hi, 58, 54); o = ext(lo, hi, 53, 40)
        return f"BREV {rd}, c[0x{b:x}][0x{o:x}]", "RCR"
    if op == 0x1b01:
        b = ext(lo, hi, 58, 54); o = ext(lo, hi, 53, 40)
        return f"BREV {rd}, c[{_ur(b)}][0x{o:x}]", "RCxR"
    if op == 0x1d01:
        return f"BREV {rd}, {_ur(ext(lo, hi, 37, 32))}", "RUR"
    return None, f"bad 0x{op:03x}"


def decode_popc(lo, hi):
    op = ext(lo, hi, 91, 91) << 12 | ext(lo, hi, 11, 0)
    rd = _reg(ext(lo, hi, 23, 16))
    til = _src(lo, hi)
    if op == 0x309:
        return f"POPC {rd}, {til}{_reg(ext(lo, hi, 39, 32))}", "RRR"
    if op == 0x909:
        return f"POPC {rd}, 0x{ext(lo, hi, 63, 32):x}", "RIR"
    if op == 0xb09:
        b = ext(lo, hi, 58, 54); o = ext(lo, hi, 53, 40)
        return f"POPC {rd}, {til}c[0x{b:x}][0x{o:x}]", "RCR"
    if op == 0x1b09:
        b = ext(lo, hi, 58, 54); o = ext(lo, hi, 53, 40)
        return f"POPC {rd}, {til}c[{_ur(b)}][0x{o:x}]", "RCxR"
    if op == 0x1d09:
        return f"POPC {rd}, {til}{_ur(ext(lo, hi, 37, 32))}", "RUR"
    return None, f"bad 0x{op:03x}"


def decode_flo(lo, hi):
    op = ext(lo, hi, 91, 91) << 12 | ext(lo, hi, 11, 0)
    rd = _reg(ext(lo, hi, 23, 16))
    sh = ext(lo, hi, 74, 74)
    sz = ext(lo, hi, 73, 73)          # 0=U32, 1=S32
    pu = ext(lo, hi, 83, 81)
    til = _src(lo, hi)
    mod = (".U32" if sz == 0 else "") + (".SH" if sh else "")
    pu_s = "" if pu == 7 else f", P{pu}"
    src = {"RRR": _reg(ext(lo, hi, 39, 32)),
           "imm": f"0x{ext(lo, hi, 63, 32):x}"}.get(
               "RRR" if op in (0x300, 0x1d00) else "imm", "")
    if op == 0x300:
        return f"FLO{mod} {rd}{pu_s}, {til}{_reg(ext(lo, hi, 39, 32))}", "RRR"
    if op == 0x900:
        return f"FLO{mod} {rd}{pu_s}, 0x{ext(lo, hi, 63, 32):x}", "RIR"
    if op == 0xb00:
        b = ext(lo, hi, 58, 54); o = ext(lo, hi, 53, 40)
        return f"FLO{mod} {rd}{pu_s}, {til}c[0x{b:x}][0x{o:x}]", "RCR"
    if op == 0x1b00:
        b = ext(lo, hi, 58, 54); o = ext(lo, hi, 53, 40)
        return f"FLO{mod} {rd}{pu_s}, {til}c[{_ur(b)}][0x{o:x}]", "RCxR"
    if op == 0x1d00:
        return f"FLO{mod} {rd}{pu_s}, {til}{_ur(ext(lo, hi, 37, 32))}", "RUR"
    return None, f"bad 0x{op:03x}"


DECODERS = {"BREV": decode_brev, "POPC": decode_popc, "FLO": decode_flo}

# --- validation vectors (ptxas sm_90 + SM120 probes + assembler) ------------
VECTORS = [
    ("BREV", 0x0000000200097301, 0x008e300000000000, "BREV R9, R2"),          # ptxas
    ("BREV", 0x0000000500037901, 0x000e4a0000000000, "BREV R3, 0x5"),          # RIR
    ("BREV", 0x0000000500037d01, 0x000e4a0008000000, "BREV R3, UR5"),          # RUR
    ("POPC", 0x0000001400197309, 0x000e620000000000, "POPC R25, R20"),         # ptxas
    ("POPC", 0x8000000000037309, 0x000e4a0000000000, "POPC R3, ~R0"),          # [~]
    ("POPC", 0x0000000500037909, 0x000e4a0000000000, "POPC R3, 0x5"),          # RIR
    ("POPC", 0x0000000500037d09, 0x000e4a0008000000, "POPC R3, UR5"),          # RUR
    ("FLO",  0x0000000200007300, 0x000e6200000e0000, "FLO.U32 R0, R2"),        # ptxas
    ("FLO",  0x0000000900087300, 0x000e2200000e0400, "FLO.U32.SH R8, R9"),     # ptxas
    ("FLO",  0x0000000200117300, 0x000e2200000e0600, "FLO.SH R17, R2"),        # ptxas
    ("FLO",  0x00000004000d7300, 0x004e2200000e0000, "FLO.U32 R13, R4"),       # ptxas
    ("FLO",  0x00000004000f7300, 0x000e6200000e0400, "FLO.U32.SH R15, R4"),    # ptxas
    ("FLO",  0x0000000000037300, 0x000e4a0000080000, "FLO.U32 R3, P4, R0"),    # Pu=P4
    ("FLO",  0x0000000500037900, 0x000e4a00000e0200, "FLO R3, 0x5"),           # S32 RIR
    ("FLO",  0x0000000500037d00, 0x000e4a00080e0600, "FLO.SH R3, UR5"),        # RUR
    ("FLO",  0x8000000000037300, 0x000e4a00000e0000, "FLO.U32 R3, ~R0"),       # [~]
]


def main() -> int:
    bad = 0
    for mnem, lo, hi, want in VECTORS:
        got, form = DECODERS[mnem](lo, hi)
        ok = got == want
        if not ok:
            bad += 1
        print(f"{'ok ' if ok else 'FAIL'} {lo:016x} {hi:016x} -> {got:28s} "
              f"(want {want!r})")
    print(f"\n=== decode_brev_flo_popc: {'ALL PASS' if bad == 0 else str(bad) + ' FAIL'} ===")
    return bad


if __name__ == "__main__":
    raise SystemExit(main())
