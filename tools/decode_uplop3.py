#!/usr/bin/env python3
"""
UPLOP3 decoder — Uniform Predicate Three-Input Logic (sm_90)
"""
OPC_0REG = 0x89c  # 0-register, 1out or 2out
UPG_NAMES = {0: "UP0", 1: "UP1", 2: "UP2", 3: "UP3", 4: "UP4", 5: "UP5", 6: "UP6", 7: "UPT"}


def extract(lo64, hi64, msb, lsb):
    val = 0
    for b in range(lsb, msb + 1):
        bit = ((hi64 >> (b - 64)) if b >= 64 else (lo64 >> b)) & 1
        val |= (bit << (b - lsb))
    return val

def pred_str(idx, not_bit):
    name = UPG_NAMES.get(idx, f"UP{idx}")
    return f"!{name}" if not_bit else name

def decode_uplop3(lo64, hi64):
    opcode = extract(lo64, hi64, 91, 91) << 12 | extract(lo64, hi64, 11, 0)

    pu = extract(lo64, hi64, 83, 81)       # UPu
    cop = extract(lo64, hi64, 86, 84)      # UPv (2out) or *7 (1out)
    pnz = extract(lo64, hi64, 89, 87)      # UPp
    pnz_not = extract(lo64, hi64, 90, 90)
    upq = extract(lo64, hi64, 79, 77)      # UPq
    upq_not = extract(lo64, hi64, 80, 80)
    upr = extract(lo64, hi64, 70, 68)      # UPr
    upr_not = extract(lo64, hi64, 71, 71)

    uimm8 = extract(lo64, hi64, 76, 72) << 3 | extract(lo64, hi64, 66, 64)
    vimm8 = extract(lo64, hi64, 23, 16)

    pg = extract(lo64, hi64, 14, 12)
    pg_not = extract(lo64, hi64, 15, 15)
    pred_prefix = f"@{'!' if pg_not else ''}{UPG_NAMES.get(pg, f'UP{pg}')} " if pg != 7 or pg_not else ""

    upu_name = UPG_NAMES.get(pu, f"UP{pu}")
    upv_name = UPG_NAMES.get(cop, f"UP{cop}")

    if opcode == OPC_0REG:
        if cop == 7:  # 1-out (cop=*7=UPT), but observed values show cop=7 for 2-out
            # All observed: cop=7, vimm8=0, so it's 2-out
            return (f"{pred_prefix}UPLOP3.LUT {upu_name}, {upv_name}, "
                    f"{pred_str(pnz, pnz_not)}, {pred_str(upq, upq_not)}, {pred_str(upr, upr_not)}, "
                    f"0x{uimm8:x}, 0x{vimm8:x}"), "2out_0reg"
        else:
            return (f"{pred_prefix}UPLOP3.LUT {upu_name}, "
                    f"{pred_str(pnz, pnz_not)}, {pred_str(upq, upq_not)}, {pred_str(upr, upr_not)}, "
                    f"0x{uimm8:x}"), "1out_0reg"

    return None, f"unknown opcode 0x{opcode:03x}"


def h2i(s): return int(s, 16)

TEST = [
    ("0x000000000000789c", "0x000fe20003f0f070",
     "UPLOP3.LUT UP0, UPT, UPT, UPT, UPT, 0x80, 0x0", "2out_0reg"),
    ("0x000000000000789c", "0x000fd80003f0f070",
     "UPLOP3.LUT UP0, UPT, UPT, UPT, UPT, 0x40, 0x0", "2out_0reg"),
]

def main():
    ok = True
    for l, h, a, v in TEST:
        r = decode_uplop3(h2i(l), h2i(h))
        if r[0] != a or r[1] != v:
            print(f"MISMATCH: {l}:{h}  got={r}  want=({a}, {v})"); ok = False
        else: print(f"OK | {a}")
    print("\nAll tests passed." if ok else "\nFAILED.")

if __name__ == "__main__":
    main()
