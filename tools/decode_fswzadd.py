#!/usr/bin/env python3
"""Decoder for FSWZADD (FP32 swizzle-add: cross-lane quad partial reduction) on sm_90.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).

NOTE: not emitted by nvcc in the compute paths tried (float warp/quad cg::reduce,
shfl.xor butterflies) nor present in cufft/cublasLt; it is primarily a quad
derivative / partial-reduction primitive. No real captures. Encoding from the CLASS
ENCODING; validation is a round-trip. npCtrl semantics partly inferred.
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OPCODE = 0x822
ROUND = {0: "", 1: ".RM", 2: ".RP", 3: ".RZ"}       # Round1; RN(0) hidden
PAIR  = {0: "PP", 1: "PN", 2: "NP", 3: "ZP"}         # base-4 digit -> quad-lane sign pair

def reg(n): return "RZ" if n == 0xff else f"R{n}"

def np_name(v):                     # 8-char P/N/Z string: 4 base-4 digits (MSB pair first)
    return "".join(PAIR[(v >> (6 - 2*i)) & 3] for i in range(4))

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode == OPCODE, f"bad opcode {opcode:#x}"
    Pg   = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    ftz  = bits(w, 80, 80)          # FTZ
    rnd  = bits(w, 79, 78)          # Round1
    ndv  = bits(w, 77, 77)          # NDV
    Rd   = bits(w, 23, 16); Ra = bits(w, 31, 24); Rc = bits(w, 71, 64)
    npc  = bits(w, 39, 32)
    g = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    mods = ROUND[rnd] + (".FTZ" if ftz else "") + (".NDV" if ndv else "")
    return f"{g}FSWZADD{mods} {reg(Rd)}, {reg(Ra)}, {reg(Rc)}, {np_name(npc)} ;"

def encode(Rd=0, Ra=0, Rc=0, npc=0, ftz=0, rnd=0, ndv=0, Pg=7, Pg_not=0):
    w = (bits(OPCODE,12,12)<<91)|bits(OPCODE,11,0)|((Pg&7)<<12)|((Pg_not&1)<<15)
    w |= (Rd&0xff)<<16 | (Ra&0xff)<<24 | (Rc&0xff)<<64 | (npc&0xff)<<32
    w |= (ndv&1)<<77 | (rnd&3)<<78 | (ftz&1)<<80
    return w & ((1<<64)-1), (w>>64)&((1<<64)-1)

# NP name generation cross-check vs spec enum samples
NP_CHECK = {0:"PPPPPPPP",1:"PPPPPPPN",2:"PPPPPPNP",3:"PPPPPPZP",4:"PPPPPNPP",
            5:"PPPPPNPN",6:"PPPPPNNP",7:"PPPPPNZP",128:"NPPPPPPP",255:"ZPZPZPZP"}

CASES = [
    (encode(Rd=4, Ra=2, Rc=6, npc=0),            "FSWZADD R4, R2, R6, PPPPPPPP ;"),
    (encode(Rd=4, Ra=2, Rc=6, npc=0x99),         f"FSWZADD R4, R2, R6, {np_name(0x99)} ;"),
    (encode(Rd=4, Ra=2, Rc=6, npc=0x99, rnd=3),  f"FSWZADD.RZ R4, R2, R6, {np_name(0x99)} ;"),
    (encode(Rd=4, Ra=2, Rc=6, npc=0, ftz=1),     "FSWZADD.FTZ R4, R2, R6, PPPPPPPP ;"),
    (encode(Rd=4, Ra=2, Rc=6, npc=0, ndv=1),     "FSWZADD.NDV R4, R2, R6, PPPPPPPP ;"),
]

if __name__ == "__main__":
    ok = True
    for v, exp in NP_CHECK.items():
        got = np_name(v); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}NP[{v:>3}] = {got} | exp {exp}")
    for (lo, hi), exp in CASES:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got}")
    print("ROUND-TRIP OK (synthetic)" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
