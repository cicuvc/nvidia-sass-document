#!/usr/bin/env python3
"""Decoder for SGXT (sign/zero-extend from a bit position) on sm_90 — int_pipe.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).

Verified against real cuobjdump captures (sm_90, CUDA 13.1) via PTX `szext.{clamp,
wrap}.{s32,u32}` inline asm. (ptxas won't emit SGXT from plain shift/bitfield C code —
it prefers the SHF idiom — but the PTX `szext` instruction lowers straight to SGXT.)
Twin of the uniform USGXT (see notes/usgxt.md).

  SGXT[.W][.U32] Rd, Ra, Rb : extend Ra from the bit position in Rb;
    fmt S32 (default) = sign-extend, U32 = zero-extend; cw C (default) = clamp position, W = wrap.
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

FORM = {0x21a: "R", 0x81a: "I", 0xa1a: "C", 0x1a1a: "Cx", 0x1c1a: "U"}

def reg(n): return "RZ" if n == 0xff else f"R{n}"

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode in FORM, f"bad opcode {opcode:#x}"
    Pg = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    cw  = bits(w, 75, 75)      # CWMode: C=0 (default), W=1
    fmt = bits(w, 73, 73)      # REDUX_SZ: U32=0, S32=1 (default)
    Rd = bits(w, 23, 16); Ra = bits(w, 31, 24)
    g = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    mods = (".W" if cw else "") + ("" if fmt else ".U32")
    f = FORM[opcode]
    if f == "R":  src = reg(bits(w, 39, 32))
    elif f == "U": src = f"UR{bits(w,37,32)}"
    elif f == "I": src = f"{bits(w,63,32):#x}"
    else:
        bank = bits(w, 58, 54); off = bits(w, 53, 40) << 2
        src = f"c[{bank:#x}][{off:#x}]"
    return f"{g}SGXT{mods} {reg(Rd)}, {reg(Ra)}, {src} ;"

def enc(op, Rd=0, Ra=0, Rb=0, URb=0, imm=0, cw=0, fmt=1, Pg=7):
    w = (bits(op,12,12)<<91)|bits(op,11,0)|((Pg&7)<<12)
    w |= (Rd&0xff)<<16 | (Ra&0xff)<<24 | (cw&1)<<75 | (fmt&1)<<73
    if op == 0x21a: w |= (Rb&0xff)<<32
    if op == 0x1c1a: w |= (URb&0x3f)<<32
    if op == 0x81a: w |= (imm & 0xffffffff)<<32
    return w & ((1<<64)-1), (w>>64)&((1<<64)-1)

# real captures (lo64, hi64, expected) — via szext inline asm
REAL = [
    (0x0000000d0207781a, 0x004fca0000000200, "SGXT R7, R2, 0xd ;"),        # szext.clamp.s32 imm
    (0x000000050209721a, 0x008fca0000000200, "SGXT R9, R2, R5 ;"),         # clamp.s32
    (0x000000050209721a, 0x008fca0000000a00, "SGXT.W R9, R2, R5 ;"),       # wrap.s32
    (0x000000050209721a, 0x008fca0000000000, "SGXT.U32 R9, R2, R5 ;"),     # clamp.u32
    (0x000000050209721a, 0x008fca0000000800, "SGXT.W.U32 R9, R2, R5 ;"),   # wrap.u32
]
SYNTH = [
    (enc(0x1c1a, Rd=4, Ra=2, URb=3), "SGXT R4, R2, UR3 ;"),                # uniform src (round-trip)
]

if __name__ == "__main__":
    ok = True
    print("-- real captures --")
    for lo, hi, exp in REAL:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:24s} | exp {exp}")
    print("-- synthetic round-trip --")
    for (lo, hi), exp in SYNTH:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:20s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
