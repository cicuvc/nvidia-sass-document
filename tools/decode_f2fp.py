#!/usr/bin/env python3
"""F2FP full decoder — all 61 variants (9 families), verifying encoding vs disassembly.

F2FP is the int_pipe packed float-to-float converter on Hopper+.  The opcode
(13-bit, [91]||[11:0]) only selects the *operand-position pattern*; the family
is selected by the 3-bit `merge` field ([90:89],[78:78]):

  merge   family                       operand grammar
  -----   ----------------------------  -----------------------------
  0       PACK_AB        base f2fp      Rd, Ra, X
  1       MERGE_C        merge_c        Rd, X, Rc  (F32->F16/BF16/E6M9)
  2       UNPACK_B       8b upconvert   Rd, X       (E5M2/E4M3 src)
  3       PACK_B         tf32           Rd, X
  4       UNPACK_B_MERGE_C  f16->8b     Rd, X, Rc
  5       PACK_AB_MERGE_C   f32->8b     Rd, Ra, X, Rc

X = register / F32Imm / c[bank][off] / c[0x0][UR+off] / UR, per opcode pattern:

  opcode   pat      where X / third operand live
  0x23e    RRR      X=RB1[39:32]  (third=Rc[71:64] for 3-operand families)
  0x43e    RRI      X=Rc[71:64]   (third=imm[63:32])
  0x63e    RRC      X=Rc[71:64]   (third=c[bank][off])
  0x83e    RIR      X=imm[63:32]  (third=Rc[71:64])
  0xa3e    RCR      X=c[bank][off](third=Rc[71:64])
  0x1a3e   RCxR     X=cx[UR][off] (third=Rc[71:64])
  0x1c3e   RUR      X=UR[37:32]   (third=Rc[71:64])
  0x163e   RRCx     X=Rc[71:64]   (third=cx[UR][off])
  0x1e3e   RRU      X=Rc[71:64]   (third=UR[37:32])

Base/tf32/up8 families exist only in the 5 XRR shapes; merge_c/f16->8b/f32->8b
exist in all 9.
"""

import struct
from typing import Optional

# --- field extraction -------------------------------------------------------
def extract(lo64: int, hi64: int, bits: list[int]) -> int:
    val = 0
    for bit in bits:
        bv = ((hi64 >> (bit - 64)) if bit >= 64 else (lo64 >> bit)) & 1
        val = (val << 1) | bv
    return val

def get_opcode(lo64: int, hi64: int) -> int:
    return extract(lo64, hi64, [91, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0])

# opcode (13-bit) -> operand-position pattern
OPS = {
    0x23e:  "RRR",
    0x43e:  "RRI",
    0x63e:  "RRC",
    0x83e:  "RIR",
    0xa3e:  "RCR",
    0x1a3e: "RCxR",
    0x1c3e: "RUR",
    0x163e: "RRCx",
    0x1e3e: "RRU",
}

# merge field [90:89],[78:78] -> family
MERGE_NAMES = {
    0: "PACK_AB",
    1: "MERGE_C",
    2: "UNPACK_B",
    3: "PACK_B",
    4: "UNPACK_B_MERGE_C",
    5: "PACK_AB_MERGE_C",
}

DSTFMT_NAMES = {0: "F16", 1: "BF16", 2: "E6M9", 3: "TF32", 4: "E5M2", 5: "E4M3"}
# srcfmt (space field [74:73]) uses the srcfmt enum's numeric value:
# F32ONLY_f2fp: F32=0 | Float16: F16=1 | SRCFMT_E5M2_E4M3: E5M2=2, E4M3=3
SRCFMT_F32   = {0: "F32"}
SRCFMT_F16   = {1: "F16"}
SRCFMT_8B    = {2: "E5M2", 3: "E4M3"}
RND_NAMES    = {0: "RN", 3: "RZ"}

# ---- operand helpers -------------------------------------------------------
def reg(r: int) -> str:
    return f"R{r}" if r != 0xff else "RZ"

def ur(r: int) -> str:
    return f"UR{r}" if r != 0x3f else "URZ"

def f32imm(lo64: int, hi64: int) -> str:
    v = extract(lo64, hi64, list(range(63, 31, -1)))
    return f"{struct.unpack('>f', struct.pack('>I', v))[0]:g}"

def cbank(lo64: int, hi64: int) -> str:
    bank = extract(lo64, hi64, [58, 57, 56, 55, 54])
    off  = extract(lo64, hi64, [53, 52, 51, 50, 49, 48, 47, 46,
                                45, 44, 43, 42, 41, 40])
    return f"c[0x{bank:x}][0x{off:x}]"

def cx(lo64: int, hi64: int) -> str:
    u   = extract(lo64, hi64, [37, 36, 35, 34, 33, 32])
    off = extract(lo64, hi64, [53, 52, 51, 50, 49, 48, 47, 46,
                               45, 44, 43, 42, 41, 40]) * 4
    return f"c[0x0][{ur(u)}+0x{off:x}]"

def decode_f2fp(lo64: int, hi64: int) -> Optional[str]:
    opc = get_opcode(lo64, hi64)
    if opc not in OPS:
        return None
    pat = OPS[opc]

    pg     = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])
    rd     = extract(lo64, hi64, [23, 22, 21, 20, 19, 18, 17, 16])
    ra     = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])   # A slot
    rb1    = extract(lo64, hi64, [39, 38, 37, 36, 35, 34, 33, 32])   # B slot (RRR)
    rc     = extract(lo64, hi64, [71, 70, 69, 68, 67, 66, 65, 64])   # C slot
    u      = extract(lo64, hi64, [37, 36, 35, 34, 33, 32])           # 6-bit UR slot

    merge  = extract(lo64, hi64, [90, 89, 78])
    dstfmt = extract(lo64, hi64, [87, 86, 76])
    rnd    = extract(lo64, hi64, [81, 80, 79])   # [81:79] MSB-first
    ntz    = extract(lo64, hi64, [77])
    sz     = extract(lo64, hi64, [75])
    space  = extract(lo64, hi64, [74, 73])
    e72    = extract(lo64, hi64, [72])           # extract (down/merge families)
    e88    = extract(lo64, hi64, [88])           # extract_B (8b upconvert)

    if merge not in MERGE_NAMES or dstfmt not in DSTFMT_NAMES:
        return None
    fam = merge
    ds  = DSTFMT_NAMES[dstfmt]

    # family legality shorthand (full CONDITION text has the srcfmt/dstfmt gates)
    if fam in (0, 1) and dstfmt not in (0, 1, 2):
        return None
    if fam == 3 and dstfmt != 3:
        return None
    if fam == 2 and dstfmt not in (0, 1, 2, 3):
        return None
    if fam in (4, 5) and dstfmt not in (4, 5):
        return None

    sfmt_t = (SRCFMT_8B if fam == 2 else SRCFMT_F16 if fam == 4 else SRCFMT_F32)
    sfmt = sfmt_t.get(space)
    if fam == 4 and dstfmt == 4:  # space is F16(=1) for the f16->8b family
        sfmt = SRCFMT_F16.get(1)
    elif fam == 5:
        sfmt = SRCFMT_F32.get(0)
    if sfmt is None:
        return None

    sat  = ".SATFINITE" if (ntz and fam in (0, 1, 4, 5)) else ""
    relu = ".RELU" if sz else ""
    msuffix = MERGE_NAMES[merge]
    rnd_s = (("." + RND_NAMES[rnd]) if rnd != 0 else "") if fam in (0, 1, 3) else ""
    if (fam == 2 and e88) or (fam in (1, 4, 5) and e72):
        ext = ".H1"
    else:
        ext = ""

    core = f"F2FP{sat}{relu}.{ds}.{sfmt}.{msuffix}"

    rd_s = reg(rd)
    def Rc_s(): return reg(rc)
    def Rb1_s(): return reg(rb1)
    def A_s(): return reg(ra)
    def I_s(): return f32imm(lo64, hi64)
    def CB_s(): return cbank(lo64, hi64)
    def CX_s(): return cx(lo64, hi64)
    def U_s(): return ur(u)
    def Bc_s(): return reg(rc)   # RRx forms: [71:64] holds the B operand

    if fam in (0, 5):                      # real A slot
        a = A_s()
        if fam == 0:
            op2 = {"RRR": Rb1_s, "RIR": I_s, "RCR": CB_s, "RCxR": CX_s, "RUR": U_s}.get(pat)
            if op2 is None:
                return None
            parts = [rd_s, a, op2()]
        else:
            op2, op3 = {
                "RRR":  (Rb1_s, Rc_s),
                "RRI":  (Bc_s, I_s),
                "RRC":  (Bc_s, CB_s),
                "RIR":  (I_s, Rc_s),
                "RCR":  (CB_s, Rc_s),
                "RCxR": (CX_s, Rc_s),
                "RUR":  (U_s, Rc_s),
                "RRCx": (Bc_s, CX_s),
                "RRU":  (Bc_s, U_s),
            }[pat]
            parts = [rd_s, a, op2(), op3()]

    elif fam in (1, 4):                    # merge_c / f16->8b: no A slot
        op2, op3 = {
            "RRR":  (Rb1_s, Rc_s),
            "RRI":  (Bc_s, I_s),
            "RRC":  (Bc_s, CB_s),
            "RIR":  (I_s, Rc_s),
            "RCR":  (CB_s, Rc_s),
            "RCxR": (CX_s, Rc_s),
            "RUR":  (U_s, Rc_s),
            "RRCx": (Bc_s, CX_s),
            "RRU":  (Bc_s, U_s),
        }[pat]
        parts = [rd_s, op2(), op3()]

    else:                                  # up8 / tf32: 2 operands
        op2 = {"RRR": Rb1_s, "RIR": I_s, "RCR": CB_s, "RCxR": CX_s, "RUR": U_s}.get(pat)
        if op2 is None:
            return None
        parts = [rd_s, op2()]

    pre = f"@{'!' if pg_not else ''}P{pg} " if pg != 7 else ""
    return f"({pat}) {pre}{core}{rnd_s}{ext} {', '.join(parts)};"


# ---- test vectors ----------------------------------------------------------
# (lo64, hi64, expected cuobjdump-style output; .reuse annotations stripped)
# 23 vectors are raw words from real binaries (ptxas sm_120/sm_90 + cublas sm_90),
# 11 are hand-constructed from the spec for variants ptxas doesn't emit.
TESTS = [
    # -- sm_120 ptxas (tests/f2fp_test.cubin) --
    ("0x00000009000b723e", "0x010fc400000010ff",
     "F2FP.BF16.F32.PACK_AB R11, R0, R9;"),
    ("0x000000090011723e", "0x0c0fe400000008ff",
     "F2FP.RELU.F16.F32.PACK_AB R17, R0, R9;"),
    ("0x000000090007723e", "0x0c0fe200000000ff",
     "F2FP.F16.F32.PACK_AB R7, R0, R9;"),
    ("0x000000090004723e", "0x0c0fe200048070ff",
     "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C R4, R0, R9, RZ;"),
    ("0x000000090005723e", "0x0c0fe400048060ff",
     "F2FP.SATFINITE.E5M2.F32.PACK_AB_MERGE_C R5, R0, R9, RZ;"),
    ("0x000000090009723e", "0x000fe200048078ff",
     "F2FP.SATFINITE.RELU.E4M3.F32.PACK_AB_MERGE_C R9, R0, R9, RZ;"),
    ("0x00000004ff09723e", "0x000fc400020006ff",
     "F2FP.F16.E4M3.UNPACK_B R9, R4;"),
    ("0x00000007ff00723e", "0x080fe400048032ff",
     "F2FP.SATFINITE.E4M3.F16.UNPACK_B_MERGE_C R0, R7, RZ;"),
    ("0x00000007ff04723e", "0x000fe200048022ff",
     "F2FP.SATFINITE.E5M2.F16.UNPACK_B_MERGE_C R4, R7, RZ;"),
    ("0x00000005ff05723e", "0x000fe200020004ff",
     "F2FP.F16.E5M2.UNPACK_B R5, R5;"),
    # -- sm_90 ptxas (tests/f2fp_test_sm90.cubin) --
    ("0x000000090007723e", "0x010fc400000000ff",
     "F2FP.F16.F32.PACK_AB R7, R0, R9;"),
    ("0x00000009000b723e", "0x000fca00000010ff",
     "F2FP.BF16.F32.PACK_AB R11, R0, R9;"),
    ("0x000000090011723e", "0x0c0fe200000008ff",
     "F2FP.RELU.F16.F32.PACK_AB R17, R0, R9;"),
    ("0x000000090006723e", "0x0c0fe400048070ff",
     "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C R6, R0, R9, RZ;"),
    ("0x000000090008723e", "0x0c0fe200048078ff",
     "F2FP.SATFINITE.RELU.E4M3.F32.PACK_AB_MERGE_C R8, R0, R9, RZ;"),
    ("0x000000090009723e", "0x000fe400048060ff",
     "F2FP.SATFINITE.E5M2.F32.PACK_AB_MERGE_C R9, R0, R9, RZ;"),
    ("0x00000007ff00723e", "0x002fe200048032ff",
     "F2FP.SATFINITE.E4M3.F16.UNPACK_B_MERGE_C R0, R7, RZ;"),
    ("0x00000006ff05723e", "0x000fc600020006ff",
     "F2FP.F16.E4M3.UNPACK_B R5, R6;"),
    ("0x00000009ff09723e", "0x000fe200020004ff",
     "F2FP.F16.E5M2.UNPACK_B R9, R9;"),
    ("0x00000007ff00723e", "0x000fe200048022ff",
     "F2FP.SATFINITE.E5M2.F16.UNPACK_B_MERGE_C R0, R7, RZ;"),
    # -- cublas sm_90 (F16/BF16 downconvert pattern with Ra=RZ) --
    ("0x00000013ff00723e", "0x000fe200000000ff",
     "F2FP.F16.F32.PACK_AB R0, RZ, R19;"),
    ("0x00000000ff00723e", "0x012fe400000000ff",
     "F2FP.F16.F32.PACK_AB R0, RZ, R0;"),
    ("0x0000000fff00723e", "0x000fe200000000ff",
     "F2FP.F16.F32.PACK_AB R0, RZ, R15;"),
    ("0x00000000ff07723e", "0x000fe200000000ff",
     "F2FP.F16.F32.PACK_AB R7, RZ, R0;"),
    ("0x00000013ff00723e", "0x000fe200000010ff",
     "F2FP.BF16.F32.PACK_AB R0, RZ, R19;"),
    ("0x00000009ff09723e", "0x000fe200000010ff",
     "F2FP.BF16.F32.PACK_AB R9, RZ, R9;"),
    # -- hand-built per spec (variants ptxas does not emit) --
    ("0x404000000205783e", "0x000fe200000000ff",
     "F2FP.F16.F32.PACK_AB R5, R2, 3;"),                    # base RIR imm
    ("0x00c1400902057a3e", "0x000fe200000000ff",
     "F2FP.F16.F32.PACK_AB R5, R2, c[0x3][0x140];"),        # base RCR cbank
    ("0x0000000b02057c3e", "0x000fe200080000ff",
     "F2FP.F16.F32.PACK_AB R5, R2, UR11;"),                 # base RUR
    ("0x00000009ff05723e", "0x000fe20000005006",
     "F2FP.BF16.F32.MERGE_C R5, R9, R6;"),                  # merge_c RRR
    ("0x40c00000ff05783e", "0x080fe40004803206",
     "F2FP.SATFINITE.E4M3.F16.UNPACK_B_MERGE_C R5, 6, R6;"),# f16->8b RIR
    ("0x40400000ff05743e", "0x080fe40004802209",
     "F2FP.SATFINITE.E5M2.F16.UNPACK_B_MERGE_C R5, R9, 3;"),# f16->8b RRI
    ("0x0000000402057e3e", "0x0c0fe2000c807009",
     "F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C R5, R2, R9, UR4;"),  # f32->8b RRU
    ("0x00000009ff05723e", "0x000fe200024050ff",
     "F2FP.TF32.F32.PACK_B R5, R9;"),                       # tf32 RRR
    ("0x40200000ff05783e", "0x000fc400020004ff",
     "F2FP.F16.E5M2.UNPACK_B R5, 2.5;"),                    # up8 RIR
    ("0x00000009ff057c3e", "0x000fc4000a0016ff",
     "F2FP.BF16.E4M3.UNPACK_B R5, UR9;"),                   # up8 RUR
    ("0x00000009ff05a23e", "0x000fe20000000000",
     "@!P2 F2FP.F16.F32.PACK_AB R5, RZ, R9;"),              # predicated
]


def main() -> None:
    print("=" * 76)
    print("F2FP Decoder — verification against cuobjdump disassembly")
    print("=" * 76)

    ok = 0
    for lo_str, hi_str, expected in TESTS:
        lo = int(lo_str, 16)
        hi = int(hi_str, 16)
        result = decode_f2fp(lo, hi)
        if result is None:
            print(f"\nFAIL: UNKNOWN {lo_str}/{hi_str}")
            continue
        match = "match" if expected in result else "MISMATCH"
        if expected in result:
            ok += 1
        print(f"\n  expected: {expected}")
        print(f"  decoded:  {result}  [{match}]")

    print(f"\n{'='*76}")
    print(f"{ok}/{len(TESTS)} matches")


if __name__ == "__main__":
    main()