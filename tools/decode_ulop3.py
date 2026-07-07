#!/usr/bin/env python3
"""
ULOP3 decoder — Uniform Three-Input Logic (sm_90)
Decodes 128-bit SASS encodings back to assembly syntax.
"""

OPC_NOIMM = 0x1292  # LUT & LOP noimm, with optional UPp ALT
OPC_IMM   = 0x1892  # LUT & LOP imm, with optional UPp ALT

UPG_NAMES = {0: "UP0", 1: "UP1", 2: "UP2", 3: "UP3", 4: "UP4", 5: "UP5", 6: "UP6", 7: "UPT"}


def extract(lo64, hi64, msb, lsb):
    val = 0
    for b in range(lsb, msb + 1):
        bit = ((hi64 >> (b - 64)) if b >= 64 else (lo64 >> b)) & 1
        val |= (bit << (b - lsb))
    return val


def ur_str(r):
    """Format uniform register: 63 → URZ."""
    return "URZ" if r == 63 else f"UR{r}"


def decode_ulop3(lo64, hi64):
    opcode = extract(lo64, hi64, 91, 91) << 12 | extract(lo64, hi64, 11, 0)

    urd = extract(lo64, hi64, 21, 16)
    ura = extract(lo64, hi64, 29, 24)
    pu = extract(lo64, hi64, 83, 81)
    imm8 = extract(lo64, hi64, 79, 72)
    pop = extract(lo64, hi64, 80, 80)
    pnz = extract(lo64, hi64, 89, 87)
    input_sz = extract(lo64, hi64, 90, 90)
    pg = extract(lo64, hi64, 14, 12)
    pg_not = extract(lo64, hi64, 15, 15)

    pred_str = f"@{'!' if pg_not else ''}{UPG_NAMES.get(pg, f'UP{pg}')} " if pg != 7 or pg_not else ""
    pu_str = "" if pu == 7 else f"UP{pu}, "
    up_str = f", {'!' if input_sz else ''}{UPG_NAMES.get(pnz, f'UP{pnz}')}"

    if opcode == OPC_NOIMM:
        urb = extract(lo64, hi64, 37, 32)
        urc = extract(lo64, hi64, 69, 64)
        return (f"{pred_str}ULOP3.LUT {pu_str}{ur_str(urd)}, {ur_str(ura)}, {ur_str(urb)}, {ur_str(urc)}, 0x{imm8:02x}{up_str}",
                "noimm_lut")
    elif opcode == OPC_IMM:
        imm32 = extract(lo64, hi64, 63, 32)
        urc = extract(lo64, hi64, 69, 64)
        return (f"{pred_str}ULOP3.LUT {pu_str}{ur_str(urd)}, {ur_str(ura)}, 0x{imm32:x}, {ur_str(urc)}, 0x{imm8:02x}{up_str}",
                "imm_lut")

    return None, f"unknown opcode 0x{opcode:03x}"


def hex_to_u64(s):
    return int(s, 16)


TEST_VECTORS = [
    # Noimm LUT
    ("0x000000053f067292", "0x000fe2000f8e333f",
     "ULOP3.LUT UR6, URZ, UR5, URZ, 0x33, !UPT", "noimm_lut"),

    # Imm LUT (Pu=UPT, no explicit UPu)
    ("0xfffffff004047892", "0x000fe2000f8ec03f",
     "ULOP3.LUT UR4, UR4, 0xfffffff0, URZ, 0xc0, !UPT", "imm_lut"),
    ("0xfffffff004057892", "0x000fe2000f8ec03f",
     "ULOP3.LUT UR5, UR4, 0xfffffff0, URZ, 0xc0, !UPT", "imm_lut"),
    # Imm LUT (Pu=UP0, explicit)
    ("0x0000000709047892", "0x000fe2000f80c03f",
     "ULOP3.LUT UP0, UR4, UR9, 0x7, URZ, 0xc0, !UPT", "imm_lut"),
    ("0x0000001f05057892", "0x000fe2000f80c03f",
     "ULOP3.LUT UP0, UR5, UR5, 0x1f, URZ, 0xc0, !UPT", "imm_lut"),
]


def main():
    all_ok = True
    for lo_str, hi_str, expected_asm, expected_variant in TEST_VECTORS:
        lo64 = hex_to_u64(lo_str)
        hi64 = hex_to_u64(hi_str)
        result = decode_ulop3(lo64, hi64)
        if result[0] is None:
            print(f"MISMATCH: {lo_str}:{hi_str}  Error: {result[1]}")
            all_ok = False
        else:
            asm, variant = result
            ok_asm = "OK" if asm == expected_asm else "MISMATCH"
            ok_var = "OK" if variant == expected_variant else "MISMATCH"
            print(f"{ok_asm:>8} | {ok_var:>8} | {lo_str}:{hi_str}")
            if asm != expected_asm:
                print(f"         |           | Got:   {asm}")
                print(f"         |           | Want:  {expected_asm}")
                all_ok = False
            if variant != expected_variant:
                all_ok = False
    print("\nAll tests passed." if all_ok else "\nSome tests FAILED.")


if __name__ == "__main__":
    main()
