#!/usr/bin/env python3
"""Decoder for BMOV (convergence-Barrier / CBU-state MOVe) on sm_90.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).

NOTE: BMOV is not emitted by nvcc (0 occurrences in cublas per notes/cbu_state.md);
it appears only in trap / at-exit / barrier-spill code. No real captures. Field
layout is from the CLASS ENCODING; validation is a round-trip (encode -> decode).
See notes/cbu_state.md for the CBU_STATE selector meaning.
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

# CBU_STATE selector (Sa[29:24]); see notes/cbu_state.md
CBU = {**{i: f"B{i}" for i in range(16)},
       16:"THREAD_STATE_ENUM.0",17:"THREAD_STATE_ENUM.1",18:"THREAD_STATE_ENUM.2",
       19:"THREAD_STATE_ENUM.3",20:"THREAD_STATE_ENUM.4",21:"TRAP_RETURN_PC.LO",
       22:"TRAP_RETURN_PC.HI",23:"TRAP_RETURN_MASK",24:"MEXITED",25:"MKILL",
       26:"MACTIVE",27:"MATEXIT",28:"OPT_STACK",29:"API_CALL_DEPTH",
       30:"ATEXIT_PC.LO",31:"ATEXIT_PC.HI",32:"MCOLLECTIVE"}
def cbu(v): return CBU.get(v, f"CBU{v}")
def reg(n): return "RZ" if n == 0xff else f"R{n}"

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    Pg   = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    ORb  = bits(w, 84, 84)               # clear (read) / pquad (write)
    Sa   = bits(w, 29, 24)               # cbu_state / Ba
    g = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    if opcode == 0x355:                                    # read state -> GPR
        suf = ".CLEAR" if ORb else ""
        return f"{g}BMOV{suf} {reg(bits(w,23,16))}, {cbu(Sa)} ;"
    if opcode == 0x356:                                    # write state <- reg
        suf = ".PQUAD" if ORb else ""
        return f"{g}BMOV{suf} {cbu(Sa)}, {reg(bits(w,39,32))} ;"
    if opcode == 0x956:                                    # write state <- imm32
        suf = ".PQUAD" if ORb else ""
        return f"{g}BMOV{suf} {cbu(Sa)}, {bits(w,63,32):#x} ;"
    if opcode == 0x357:                                    # 64-bit atexit PC <- reg
        return f"{g}BMOV.64 ATEXIT_PC, {reg(bits(w,39,32))} ;"
    if opcode == 0xf56:                                    # write state <- barrier reg
        suf = ".PQUAD" if ORb else ""
        return f"{g}BMOV{suf} {cbu(Sa)}, B{bits(w,19,16)} ;"
    if opcode == 0xf55:                                    # barrier-reg dest
        if ORb:                                            # clear_barrier: Bd <- Ba (+clear)
            return f"{g}BMOV.CLEAR B{bits(w,19,16)}, B{Sa} ;"
        return f"{g}BMOV B{bits(w,19,16)}, {cbu(Sa)} ;"    # clear_bd: Bd <- cbu_state_nonbar
    raise AssertionError(f"bad opcode {opcode:#x}")

def enc(op, Sa=0, Rd=0, Rb=0, imm=0, barReg=0, ORb=0, Pg=7):
    w = (bits(op,12,12)<<91)|bits(op,11,0)|((Pg&7)<<12)
    w |= (ORb&1)<<84 | (Sa&0x3f)<<24 | (barReg&0xf)<<16
    if op == 0x355: w |= (Rd&0xff)<<16
    if op in (0x356,0x357): w |= (Rb&0xff)<<32
    if op == 0x956: w |= (imm & 0xffffffff)<<32
    return w & ((1<<64)-1), (w>>64)&((1<<64)-1)

CASES = [
    (enc(0x355, Sa=0, Rd=4),            "BMOV R4, B0 ;"),
    (enc(0x355, Sa=0, Rd=4, ORb=1),     "BMOV.CLEAR R4, B0 ;"),
    (enc(0x356, Sa=26, Rb=6, ORb=1),    "BMOV.PQUAD MACTIVE, R6 ;"),
    (enc(0x356, Sa=24, Rb=6),           "BMOV MEXITED, R6 ;"),
    (enc(0x956, Sa=30, imm=0x1234),     "BMOV ATEXIT_PC.LO, 0x1234 ;"),
    (enc(0x357, Rb=8),                  "BMOV.64 ATEXIT_PC, R8 ;"),
    (enc(0xf56, Sa=26, barReg=3, ORb=1),"BMOV.PQUAD MACTIVE, B3 ;"),
    (enc(0xf55, Sa=20, barReg=5),       "BMOV B5, THREAD_STATE_ENUM.4 ;"),
    (enc(0xf55, Sa=2, barReg=5, ORb=1), "BMOV.CLEAR B5, B2 ;"),
]

if __name__ == "__main__":
    ok = True
    for (lo, hi), exp in CASES:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:34s} | exp {exp}")
    print("ROUND-TRIP OK (synthetic)" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
