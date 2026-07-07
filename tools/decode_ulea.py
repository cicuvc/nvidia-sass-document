#!/usr/bin/env python3
"""
ULEA decoder — Uniform Load Effective Address (sm_90)
Decodes 128-bit SASS encodings back to assembly syntax.
"""

OPC_NOIMM = 0x1291  # ulea_hi_noimm__URURUR_URURUR and variants
OPC_IMM_RRI = 0x1491  # ulea_hi_imm__RRuI_RRI
OPC_IMM_URIUR = 0x1891  # ulea_hi_imm__RuIR_URIR and lo variants, sx32 variants

UPG_NAMES = {0: "UP0", 1: "UP1", 2: "UP2", 3: "UP3", 4: "UP4", 5: "UP5", 6: "UP6", 7: "UPT"}


def extract(lo64, hi64, msb, lsb):
    val = 0
    for b in range(lsb, msb + 1):
        if b >= 64:
            bit = (hi64 >> (b - 64)) & 1
        else:
            bit = (lo64 >> b) & 1
        val |= (bit << (b - lsb))
    return val


def decode_ulea(lo64, hi64):
    opcode = extract(lo64, hi64, 91, 91) << 12 | extract(lo64, hi64, 11, 0)

    pg = extract(lo64, hi64, 14, 12)
    pg_not = extract(lo64, hi64, 15, 15)
    pg_name = UPG_NAMES.get(pg, f"UP{pg}")
    pred_str = f"@{'!' if pg_not else ''}{pg_name} " if pg != 7 or pg_not else ""

    urd = extract(lo64, hi64, 21, 16)
    urd_str = f"UR{urd}"

    pu = extract(lo64, hi64, 83, 81)
    pu_str = f"UPT" if pu == 7 else f"UP{pu}"

    hilo = extract(lo64, hi64, 80, 80)
    sh = extract(lo64, hi64, 74, 74)
    sz = extract(lo64, hi64, 73, 73)

    scale = extract(lo64, hi64, 79, 75)

    ura = extract(lo64, hi64, 29, 24)
    ra_negate = extract(lo64, hi64, 72, 72)
    ura_prefix = "[-]" if ra_negate else ""
    ura_str = f"{ura_prefix}UR{ura}" if ura_prefix else f"UR{ura}"

    # Build modifier string
    modifiers = []
    if opcode in (OPC_IMM_RRI, OPC_IMM_URIUR) and hilo:
        modifiers.append("HI")
    elif opcode == OPC_NOIMM and hilo:
        modifiers.append("HI")  # noimm HI is implicit in cuobjdump but can be explicit
    if sh:
        modifiers.append("X")
    if sz:
        modifiers.append("SX32")
    mod_str = ("." + ".".join(modifiers)) if modifiers else ""

    if opcode == OPC_NOIMM:
        # Noimm URURUR form
        urb = extract(lo64, hi64, 37, 32)
        urc = extract(lo64, hi64, 69, 64)
        urb_inv = extract(lo64, hi64, 63, 63)
        urb_prefix = "[-]" if urb_inv else ""
        urb_str = f"{urb_prefix}UR{urb}" if urb_prefix else f"UR{urb}"

        pnz = extract(lo64, hi64, 89, 87)
        input_sz = extract(lo64, hi64, 90, 90)

        # Build operand list
        operands = [urd_str]
        if pu != 7:
            operands.append(pu_str)
        operands.append(ura_str)
        operands.append(urb_str)
        if urc != 63:  # URc != URZ
            operands.append(f"UR{urc}")
        operands.append(f"0x{scale:x}")

        # .X form adds UPp
        if sh:
            pnz_name = UPG_NAMES.get(pnz, f"UP{pnz}")
            up_str = f"{'!' if input_sz else ''}{pnz_name}"
            operands.append(up_str)

        asm = f"{pred_str}ULEA{mod_str} {', '.join(operands)}"
        return asm, "noimm"

    elif opcode == OPC_IMM_RRI:
        # RRI imm form: URd, UPu, URa, URb, imm, scale
        urb = extract(lo64, hi64, 69, 64)
        imm32 = extract(lo64, hi64, 63, 32)
        urb_str = f"UR{urb}"

        operands = [urd_str]
        if pu != 7:
            operands.append(pu_str)
        operands.append(ura_str)
        operands.append(urb_str)
        operands.append(f"0x{imm32:x}")
        operands.append(f"0x{scale:x}")

        asm = f"{pred_str}ULEA{mod_str} {', '.join(operands)}"
        return asm, "imm_RRI"

    elif opcode == OPC_IMM_URIUR:
        # URIUR imm form: URd, UPu, URa, imm, scale [+ UPp]
        imm32 = extract(lo64, hi64, 63, 32)

        pnz = extract(lo64, hi64, 89, 87)
        input_sz = extract(lo64, hi64, 90, 90)

        operands = [urd_str]
        if pu != 7:
            operands.append(pu_str)
        operands.append(ura_str)
        operands.append(f"0x{imm32:x}")
        operands.append(f"0x{scale:x}")

        if sh:
            pnz_name = UPG_NAMES.get(pnz, f"UP{pnz}")
            up_str = f"{'!' if input_sz else ''}{pnz_name}"
            operands.append(up_str)

        asm = f"{pred_str}ULEA{mod_str} {', '.join(operands)}"
        return asm, "imm_URIUR"

    return None, f"unknown opcode 0x{opcode:03x}"


def hex_to_u64(s):
    return int(s, 16)


TEST_VECTORS = [
    # Noimm basic (opcode 0x1291) — scale=0x18, URc=URZ(63), UPu=UPT(7)
    # ULEA UR6, UR7, UR6, 0x18
    ("0x0000000607067291", "0x001fe2000f8ec03f", "ULEA UR6, UR7, UR6, 0x18", "noimm"),

    # Noimm — scale=0x7, URc=URZ(63), UPu=UP0(0)
    # ULEA UR8, UP0, UR4, UR5, 0x7
    ("0x0000000504087291", "0x001fc8000f80383f", "ULEA UR8, UP0, UR4, UR5, 0x7", "noimm"),
    # ULEA UR6, UP0, UR6, UR4, 0x7
    ("0x0000000406067291", "0x001fc8000f80383f", "ULEA UR6, UP0, UR6, UR4, 0x7", "noimm"),

    # Imm URIUR (opcode 0x1891) — default (no HI/X/SX32), UPu=UPT
    # ULEA UR6, UR6, 0x400, 0x18
    ("0x0000040006067891", "0x002fe2000f8ec03f", "ULEA UR6, UR6, 0x400, 0x18", "imm_URIUR"),
    # ULEA UR13, UR13, 0x400, 0x18
    ("0x000004000d0d7891", "0x002fe2000f8ec03f", "ULEA UR13, UR13, 0x400, 0x18", "imm_URIUR"),

    # Imm URIUR (opcode 0x1891) — HI.X.SX32
    ("0xffffffff07077891", "0x000fe200080f0e3f", "ULEA.HI.X.SX32 UR7, UR7, 0xffffffff, 0x1, UP0", "imm_URIUR"),
    ("0xffffffff06067891", "0x000fe200080f0e3f", "ULEA.HI.X.SX32 UR6, UR6, 0xffffffff, 0x1, UP0", "imm_URIUR"),
    ("0xffffffff08087891", "0x000fe200080f0e3f", "ULEA.HI.X.SX32 UR8, UR8, 0xffffffff, 0x1, UP0", "imm_URIUR"),
]


def main():
    all_ok = True
    for lo_str, hi_str, expected_asm, expected_variant in TEST_VECTORS:
        lo64 = hex_to_u64(lo_str)
        hi64 = hex_to_u64(hi_str)
        result = decode_ulea(lo64, hi64)
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
