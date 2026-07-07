#!/usr/bin/env python3
"""
ULDC decoder — Uniform Load Constant (sm_90)
Decodes 128-bit SASS encodings back to assembly syntax.
"""

import struct

# sz enum
SZ_U8_S8_U16_S16_32_64 = {
    0: ".U8", 1: ".S8", 2: ".U16", 3: ".S16",
    4: "",     5: ".64",
    6: "INVALID6", 7: "INVALID7",
}

# Uniform predicate values
UPG_NAMES = {0: "UP0", 1: "UP1", 2: "UP2", 3: "UP3", 4: "UP4", 5: "UP5", 6: "UP6", 7: "UPT"}
PINZ_NAMES = {0: "UP0", 1: "UP1", 2: "UP2", 3: "UP3", 4: "UP4", 5: "UP5", 6: "UP6", 7: "UPT"}

# Opcodes
OPC_RCR   = 0x0AB9   # uldc_const__RCR:     0b 1 01010111001
OPC_RCxR  = 0x1AB9   # uldc_const__RCxR:    0b 11 01010111001
OPC_IMM   = 0x18B8   # uldc_imm_ / uldc_ur_offs_ / uldc_ur_offs_optional_upx_
OPC_UR_OFFSET = 0x1ABB  # uldc_ur_offset_


def extract(lo64, hi64, msb, lsb):
    """Extract a bitfield from 128-bit instruction: bits [msb:lsb] (inclusive).
    msb and lsb are in 128-bit space [127:0].
    """
    val = 0
    for b in range(lsb, msb + 1):
        if b >= 64:
            bit = (hi64 >> (b - 64)) & 1
        else:
            bit = (lo64 >> b) & 1
        val |= (bit << (b - lsb))
    return val


def decode_uldc(lo64, hi64):
    """Decode one ULDC instruction. Returns (asm_str, variant_name) or (None, reason)."""

    opcode = extract(lo64, hi64, 91, 91) << 12 | extract(lo64, hi64, 11, 0)
    sz = extract(lo64, hi64, 75, 73)
    sz_str = SZ_U8_S8_U16_S16_32_64.get(sz, f".UNKNOWN_SZ{sz}")

    # Predicate
    pg = extract(lo64, hi64, 14, 12)
    pg_not = extract(lo64, hi64, 15, 15)
    pg_name = UPG_NAMES.get(pg, f"UP{pg}")
    pred_str = f"@{'!' if pg_not else ''}{pg_name} " if pg != 7 or pg_not else ""

    # URd
    urd = extract(lo64, hi64, 21, 16)
    urd_str = f"UR{urd}"

    # opex
    opex_hi = extract(lo64, hi64, 124, 122)
    opex_lo = extract(lo64, hi64, 109, 105)
    opex_val = (opex_hi << 5) | opex_lo

    # req
    req = extract(lo64, hi64, 121, 116)

    # pm_pred
    pm_pred = extract(lo64, hi64, 103, 102)

    # Source operand decoding based on variant
    if opcode == OPC_RCR:
        # uldc_const__RCR: ULDC URd, c[bank][offset]
        sb_bank = extract(lo64, hi64, 58, 54)
        ra_offset = extract(lo64, hi64, 53, 38)
        src_str = f"c[0x{sb_bank:x}][0x{ra_offset:x}]"
        variant = "uldc_const__RCR"

    elif opcode == OPC_RCxR:
        # uldc_const__RCxR: ULDC URd, c[URa][offset]
        sa = extract(lo64, hi64, 29, 24)
        ra_offset = extract(lo64, hi64, 53, 38)
        src_str = f"c[UR{sa}][0x{ra_offset:x}]"
        variant = "uldc_const__RCxR"

    elif opcode == OPC_UR_OFFSET:
        # uldc_ur_offset_: ULDC URd, c[bank][URa+offset]
        sb_bank = extract(lo64, hi64, 58, 54)
        ra_offset = extract(lo64, hi64, 53, 38)
        sa = extract(lo64, hi64, 29, 24)
        src_str = f"c[0x{sb_bank:x}][UR{sa}"

        # Decode ConstBankAddress0 offset - this is a signed 17-bit value
        # But in practice it seems to be the offset directly
        ra_offset_17 = extract(lo64, hi64, 53, 38)
        # Sign-extend from 16 bits? or 17? Let me use 16 bits
        if ra_offset_17 & 0x8000:
            ra_offset_17 = ra_offset_17 - 0x10000

        if ra_offset_17 != 0:
            src_str += f"+0x{ra_offset_17 & 0xffff:x}"
        src_str += "]"
        variant = "uldc_ur_offset_"

    elif opcode == OPC_IMM:
        # opcode 0x18b8 is shared by three variants:
        # uldc_imm_:          URd, URZ + imm32 (Sa=URZ forced)
        # uldc_ur_offs_:      URd, NonZeroURa + SIMM32, with UPx predicate
        # uldc_ur_offs_optional_upx_: URd, NonZeroURa + SIMM32, UPx forced to 7/not=1

        sa = extract(lo64, hi64, 29, 24)  # *URa
        sa_offset = extract(lo64, hi64, 69, 38)  # 32-bit

        # Pnz predicate
        pnz = extract(lo64, hi64, 89, 87)
        input_sz_dist = extract(lo64, hi64, 90, 90)

        if sa == 0:  # URZ -> uldc_imm_ variant
            # Immediate load: ULDC URd, imm
            src_str = f"0x{sa_offset:08x}"
            variant = "uldc_imm_"
        else:
            # Register-offset variant
            # Sign-extend 32-bit signed offset
            if sa_offset & 0x80000000:
                imm = sa_offset - 0x100000000
            else:
                imm = sa_offset

            src_str = f"c[0x??][UR{sa}"  # bank is implicit
            if imm != 0:
                if imm < 0:
                    src_str += f"{imm}"
                else:
                    src_str += f"+0x{imm:x}"
            src_str += "]"

            # Check if has UPx predicate
            if pnz != 7:
                pnz_name = PINZ_NAMES.get(pnz, f"UP{pnz}")
                # This is the uldc_ur_offs_ with UPx
                variant = "uldc_ur_offs_"
                asm = f"{pred_str}ULDC{sz_str} {urd_str}, {src_str}, @{'!' if input_sz_dist else ''}{pnz_name}"
                return asm, variant
            else:
                # uldc_ur_offs_optional_upx_ — same but UPx is always PT (7) which is elided
                variant = "uldc_ur_offs_optional_upx_"
                asm = f"{pred_str}ULDC{sz_str} {urd_str}, {src_str}"
                return asm, variant
    else:
        return None, f"unknown opcode 0x{opcode:03x}"

    asm = f"{pred_str}ULDC{sz_str} {urd_str}, {src_str}"
    return asm, variant


def hex_to_u64(hex_str):
    """Parse a hex string to uint64, handling 0x prefix and leading zeros."""
    return int(hex_str, 16)


# Test vectors
TEST_VECTORS = [
    # From libcublas / test kernels
    ("0x00008d00000a7ab9", "0x000fe20000000800", "ULDC UR10, c[0x0][0x234]", "uldc_const__RCR"),
    ("0x0000820000087ab9", "0x000fcc0000000a00", "ULDC.64 UR8, c[0x0][0x208]", "uldc_const__RCR"),
    ("0x0000000000047ab9", "0x000fe20000000800", "ULDC UR4, c[0x0][0x0]", "uldc_const__RCR"),
    ("0x0000880000047ab9", "0x000fc80000000800", "ULDC UR4, c[0x0][0x220]", "uldc_const__RCR"),
    ("0x00008a0000047ab9", "0x000fc60000000a00", "ULDC.64 UR4, c[0x0][0x228]", "uldc_const__RCR"),
    ("0x00008e0000047ab9", "0x000fc60000000a00", "ULDC.64 UR4, c[0x0][0x238]", "uldc_const__RCR"),
    ("0x0000900000047ab9", "0x000fc60000000a00", "ULDC.64 UR4, c[0x0][0x240]", "uldc_const__RCR"),
    ("0x0000860000047ab9", "0x000fe40000000800", "ULDC UR4, c[0x0][0x218]", "uldc_const__RCR"),
    ("0x0000890000067ab9", "0x000fcc0000000800", "ULDC UR6, c[0x0][0x224]", "uldc_const__RCR"),
    ("0x0000840000077ab9", "0x000fe20000000800", "ULDC UR7, c[0x0][0x210]", "uldc_const__RCR"),
    ("0x0000820000047ab9", "0x000fce0000000a00", "ULDC.64 UR4, c[0x0][0x208]", "uldc_const__RCR"),
    ("0x00008a0000067ab9", "0x000fcc0000000a00", "ULDC.64 UR6, c[0x0][0x228]", "uldc_const__RCR"),
    ("0x00008c0000047ab9", "0x000fc60000000a00", "ULDC.64 UR4, c[0x0][0x230]", "uldc_const__RCR"),

    # uldc_ur_offset_ (0x1abb): bank+register-indexed
    ("0x00c0000004047abb", "0x000fe40008000800", "ULDC UR4, c[0x3][UR4]", "uldc_ur_offset_"),

    # Additional from cuobjdump
    ("0x00008f0000077ab9", "0x000fe40000000800", "ULDC UR7, c[0x0][0x23c]", "uldc_const__RCR"),
    ("0x00008e0000077ab9", "0x000fe40000000800", "ULDC UR7, c[0x0][0x238]", "uldc_const__RCR"),
]


def main():
    all_ok = True
    for lo_str, hi_str, expected_asm, expected_variant in TEST_VECTORS:
        lo64 = hex_to_u64(lo_str)
        hi64 = hex_to_u64(hi_str)
        result = decode_uldc(lo64, hi64)
        if result[0] is None:
            print(f"MISMATCH: {lo_str}:{hi_str}")
            print(f"  Error: {result[1]}")
            all_ok = False
        else:
            asm, variant = result
            match_asm = "OK" if asm == expected_asm else "MISMATCH"
            match_var = "OK" if variant == expected_variant else "MISMATCH"
            print(f"{match_asm:>8} | {match_var:>8} | {lo_str}:{hi_str}")
            print(f"         |           | Got:   {asm} [{variant}]")
            if asm != expected_asm:
                print(f"         |           | Want:  {expected_asm} [{expected_variant}]")
                all_ok = False
            if variant != expected_variant:
                all_ok = False

    if all_ok:
        print("\nAll tests passed.")
    else:
        print("\nSome tests FAILED.")


if __name__ == "__main__":
    main()
