#!/usr/bin/env python3
"""Decoder/verifier for UTMACCTL (sm_90a). TMA cache control.

Two distinct opcodes:
  0x19b9 = utmacctl_URa_  : /COP_utmacctl:cop [URa]   (IV / PF, operand = descriptor addr)
  0x9b9  = utmacctl_      : /IVALLONLY:ivall           (IVALL, no operand)
cop field 'fc' at [82]: IV=0, PF=1. ivall 'clear' at [83]: IVALL=1.
"""

COP = {0: "IV", 1: "PF"}

def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)

def ureg(n):
    return "URZ" if n == 63 else f"UR{n}"

def upred(p, notbit):
    if p == 7 and not notbit:
        return None
    return ("!" if notbit else "") + ("UPT" if p == 7 else f"UP{p}")

def decode(lo64, hi64, expect=None):
    v = (hi64 << 64) | lo64
    opcode = (bits(v, 91, 91) << 12) | bits(v, 11, 0)
    assert opcode in (0x19b9, 0x9b9), f"opcode {opcode:#x}"
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)
    pred = upred(Pg, Pg_not)
    preds = f"@{pred} " if pred else ""
    if opcode == 0x19b9:
        cop = bits(v, 82, 82)
        URa = bits(v, 29, 24)
        asm = f"{preds}UTMACCTL.{COP[cop]} [{ureg(URa)}] ;"
    else:  # 0x9b9 IVALL-only
        ivall = bits(v, 83, 83)
        mod = ".IVALL" if ivall else ""
        asm = f"{preds}UTMACCTL{mod} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}   [op={opcode:#x}]")
    if not ok:
        print(f"    expected: {expect}")
    return ok

# Empirically verified (tests/utmacctl_test.cu, sm_90a, CUDA 13.1)
VECTORS = [
    (0x00000000040079b9, 0x0003e20008000000, "UTMACCTL.IV [UR4] ;"),
    (0x00000000040079b9, 0x0001e40008040000, "UTMACCTL.PF [UR4] ;"),
]

# Spec-derived synthetic (0x9b9 IVALL-only form, not observed from stock PTX):
#   opcode 0x9b9, clear[83]=1, Pg=UPT(7)
_iv = (1 << 83) | (7 << 12) | 0x9b9
SYNTH = [((_iv & ((1 << 64) - 1)), (_iv >> 64), "UTMACCTL.IVALL ;")]

if __name__ == "__main__":
    allok = True
    print("# empirical")
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("# spec-derived (0x9b9 IVALL-only)")
    for lo, hi, exp in SYNTH:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
