#!/usr/bin/env python3
"""USEL + UMOV decoders — Uniform Select / Uniform Move (sm_90)"""

UPG = {0: "UP0", 1: "UP1", 2: "UP2", 3: "UP3", 4: "UP4", 5: "UP5", 6: "UP6", 7: "UPT"}

def ext(l, h, m, s):
    v = 0
    for b in range(s, m + 1):
        v |= (((h >> (b - 64)) if b >= 64 else (l >> b)) & 1) << (b - s)
    return v

def ur(r):
    return "URZ" if r == 63 else f"UR{r}"

# ------- USEL -------
def decode_usel(lo, hi):
    op = ext(lo, hi, 91, 91) << 12 | ext(lo, hi, 11, 0)
    urd = ext(lo, hi, 21, 16)
    ura = ext(lo, hi, 29, 24)
    pnz = ext(lo, hi, 89, 87)
    nz = ext(lo, hi, 90, 90)
    up_str = f"{'!' if nz else ''}{UPG.get(pnz, f'UP{pnz}')}"
    pg = ext(lo, hi, 14, 12); pg_n = ext(lo, hi, 15, 15)
    pred = f"@{'!' if pg_n else ''}{UPG.get(pg, f'UP{pg}')} " if pg != 7 or pg_n else ""
    if op == 0x1287:
        urb = ext(lo, hi, 37, 32)
        return f"{pred}USEL {ur(urd)}, {ur(ura)}, {ur(urb)}, {up_str}", "usel_noimm"
    elif op == 0x1887:
        imm = ext(lo, hi, 63, 32)
        return f"{pred}USEL {ur(urd)}, {ur(ura)}, 0x{imm:x}, {up_str}", "usel_imm"
    return None, f"bad opcode 0x{op:03x}"

# ------- UMOV -------
def decode_umov(lo, hi):
    op = ext(lo, hi, 91, 91) << 12 | ext(lo, hi, 11, 0)
    urd = ext(lo, hi, 21, 16)
    pg = ext(lo, hi, 14, 12); pg_n = ext(lo, hi, 15, 15)
    pred = f"@{'!' if pg_n else ''}{UPG.get(pg, f'UP{pg}')} " if pg != 7 or pg_n else ""
    if op == 0x1c82:
        urb = ext(lo, hi, 37, 32)
        return f"{pred}UMOV {ur(urd)}, {ur(urb)}", "umov_UR"
    elif op == 0x882:
        imm = ext(lo, hi, 63, 32)
        return f"{pred}UMOV {ur(urd)}, 0x{imm:x}", "umov_UI"
    return None, f"bad opcode 0x{op:03x}"


h2 = lambda s: int(s, 16)
TESTS = [
    # USEL noimm (0x1287): bit91=1, lo&0xFFF=0x287
    ("USEL", "0x0000000506057287", "0x000fe20008000000", "USEL UR5, UR6, UR5, UP0"),
    # USEL noimm with !UP0: input_reg_sz_32_dist [90]=1
    ("USEL", "0x0000000506057287", "0x000fe2000c000000", "USEL UR5, UR6, UR5, !UP0"),
    # USEL imm (0x1887): bit91=1, lo&0xFFF=0x887
    ("USEL", "0x0000001004047887", "0x000fe20008000000", "USEL UR4, UR4, 0x10, UP0"),
    ("USEL", "0xfffffc000a0a7887", "0x000fe20008000000", "USEL UR10, UR10, 0xfffffc00, UP0"),
    # UMOV UR (0x1c82): bit91=1, lo&0xFFF=0xc82
    ("UMOV", "0x0000003f00067c82", "0x000fe20008000000", "UMOV UR6, URZ"),
    # UMOV UI (0x882): bit91=0, lo&0xFFF=0x882
    ("UMOV", "0x0000000000047882", "0x0000000000000000", "UMOV UR4, 0x0"),
    ("UMOV", "0x0000040000057882", "0x0000000000000000", "UMOV UR5, 0x400"),
]

def main():
    ok = True
    for kind, l, h, want in TESTS:
        lo, hi = h2(l), h2(h)
        r = decode_usel(lo, hi) if kind == "USEL" else decode_umov(lo, hi)
        if r[0] != want:
            print(f"MISMATCH [{kind}]: {l}:{h}  got={r[0]}  want={want}")
        else:
            print(f"OK [{kind}] {want}")
        if r[0] != want: ok = False
    print("\nAll tests passed." if ok else "\nFAILED.")

if __name__ == "__main__":
    main()
