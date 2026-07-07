#!/usr/bin/env python3
"""
UP2UR decoder — Uniform Predicate to Uniform Register (sm_90)
No empirical encodings available; decoder is based on spec only.
"""

OPC_SIMPLE_IMM = 0x1883
OPC_URB = 0x1c83

BSEL_NAMES = {0: "B0", 1: "B1", 2: "B2", 3: "B3"}
UPG_NAMES = {0: "UP0", 1: "UP1", 2: "UP2", 3: "UP3", 4: "UP4", 5: "UP5", 6: "UP6", 7: "UPT"}


def extract(lo64, hi64, msb, lsb):
    val = 0
    for b in range(lsb, msb + 1):
        bit = ((hi64 >> (b - 64)) if b >= 64 else (lo64 >> b)) & 1
        val |= (bit << (b - lsb))
    return val


def decode_up2ur(lo64, hi64):
    opcode = extract(lo64, hi64, 91, 91) << 12 | extract(lo64, hi64, 11, 0)
    bsel = extract(lo64, hi64, 77, 76)
    urd = extract(lo64, hi64, 21, 16)
    sa = extract(lo64, hi64, 29, 24)  # URa, or *63 (URZ) for simple
    pg = extract(lo64, hi64, 14, 12)
    pg_not = extract(lo64, hi64, 15, 15)

    pred_str = f"@{'!' if pg_not else ''}{UPG_NAMES.get(pg, f'UP{pg}')} " if pg != 7 or pg_not else ""
    bsel_str = BSEL_NAMES.get(bsel, f"B{bsel}")

    if opcode == OPC_SIMPLE_IMM:
        ra_offset = extract(lo64, hi64, 63, 32)
        if sa == 63 and ra_offset == 255:
            # Simple form: UP2UR.B0 URd, UPR
            return f"{pred_str}UP2UR.{bsel_str} UR{urd}, UPR", "simple"
        else:
            # Imm form: UP2UR.B0 URd, UPR, URa, imm32
            return f"{pred_str}UP2UR.{bsel_str} UR{urd}, UPR, UR{sa}, 0x{ra_offset:x}", "imm"

    elif opcode == OPC_URB:
        urb = extract(lo64, hi64, 37, 32)
        return f"{pred_str}UP2UR.{bsel_str} UR{urd}, UPR, UR{sa}, UR{urb}", "urb"

    return None, f"unknown opcode 0x{opcode:03x}"


if __name__ == "__main__":
    # No empirical vectors available. Print a plausible decode of a constructed encoding.
    # up2ur_simple_: UP2UR.B0 UR4, UPR
    lo = 0x000000ff3f047883  # URd=4, Sa=63(URZ), Ra_offset=255 (*255)
    hi = 0x00000e0008000000  # bit91=1, insert=0, src_rel_sb=*7, dst_wr_sb=*7
    asm, var = decode_up2ur(lo, hi)
    print(f"[{var}] {asm}")
    print("No empirical test vectors — verification deferred.")
