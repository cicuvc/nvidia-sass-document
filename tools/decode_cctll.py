#!/usr/bin/env python3
"""Decoder/verifier for CCTLL (sm_90a) — LOCAL-memory cache control.

Local-memory counterpart of CCTL (notes/cctl.md). Opcodes 0x990 (imm-offset /
whole-cache noSrc), 0x1d90 (uniform-reg offset). mio_pipe, DECOUPLED_RD_SCBD,
VQ_UNORDERED. Simpler than CCTL: no cache selector (D/U/C/I), no .E (local addrs
are 32-bit), COPs limited to PF1/PF2/WB/IV/RS + whole-cache IVALL/WBALL.

Fields:
  op [90:87] cop, Ra [31:24], Ra_offset [63:40] (imm) / Ra_URb [37:32] (UR form)
"""

COP = {0: ".PF1", 1: ".PF2", 2: ".WB", 3: ".IV", 4: ".IVALL", 5: ".RS", 7: ".WBALL"}
NOSRC_COPS = {4, 7}  # IVALL / WBALL

def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)

def reg(n):
    return "RZ" if n == 255 else f"R{n}"

def ureg(n):
    return "URZ" if n == 63 else f"UR{n}"

def pred(p, notbit):
    if p == 7 and not notbit:
        return None
    return ("!" if notbit else "") + ("PT" if p == 7 else f"P{p}")

def decode(lo64, hi64, expect=None):
    v = (hi64 << 64) | lo64
    opcode = (bits(v, 91, 91) << 12) | bits(v, 11, 0)
    assert opcode in (0x990, 0x1d90), f"opcode {opcode:#x}"
    ur_form = (opcode == 0x1d90)
    op = bits(v, 90, 87)
    Ra = bits(v, 31, 24)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)

    mod = COP.get(op, f".op{op}")
    if op in NOSRC_COPS:
        ops = ""
    elif ur_form:
        Ra_URb = bits(v, 37, 32)
        ops = f" [{reg(Ra)}+{ureg(Ra_URb)}]"
    else:
        off = bits(v, 63, 40)
        off = off - (1 << 24) if off >= (1 << 23) else off
        addr = f"[{reg(Ra)}"
        if off:
            addr += f"+{off:#x}"
        addr += "]"
        ops = f" {addr}"
    p = pred(Pg, Pg_not)
    preds = f"@{p} " if p else ""
    asm = f"{preds}CCTLL{mod}{ops} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x0000000000007990, 0x0001e40000000000, "CCTLL.PF1 [R0] ;"),
    (0x0000000000007990, 0x0001e40000800000, "CCTLL.PF2 [R0] ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
