#!/usr/bin/env python3
"""Decoder/verifier for CCTL (sm_90a) — cache control (L1/L2 line ops).

Opcodes: 0x98f (imm-offset / whole-cache noSrc), 0x1d8f (uniform-reg offset).
mio_pipe, INST_TYPE_DECOUPLED_RD_SCBD, VQ_UNORDERED.

Two families:
 - address form: CCTL[.E].<cache>.<cop> [Ra+off]  (cop = PF1/PF2/WB/IV/RS/PML2/DML2/RML2)
 - whole-cache noSrc: CCTL.<cop>  (cop = IVALL/IVALLP/WBALL/WBALLP), Ra pinned RZ

Fields:
  op    [90:87]  cop
  cache [80:78]  Cache (D=0,U=1,C=2,I=3)
  e     [72]     E
  Ra    [31:24], Ra_offset [63:32] (imm form) / Ra_URb [37:32] (UR form)
"""

CACHE = {0: "", 1: ".U", 2: ".C", 3: ".I"}  # D=0 default unprinted
# combined COP space (both address ops and whole-cache ops share the 'op' field)
COP = {0: ".PF1", 1: ".PF2", 2: ".WB", 3: ".IV", 4: ".IVALL", 5: ".RS",
       6: ".IVALLP", 7: ".WBALL", 8: ".WBALLP", 9: ".PML2", 10: ".DML2", 11: ".RML2"}
NOSRC_COPS = {4, 6, 7, 8}  # IVALL/IVALLP/WBALL/WBALLP have no address operand

def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)

def reg(n, wide=False):
    base = "RZ" if n == 255 else f"R{n}"
    return base + (".64" if wide and n != 255 else "")

def ureg(n):
    return "URZ" if n == 63 else f"UR{n}"

def pred(p, notbit):
    if p == 7 and not notbit:
        return None
    return ("!" if notbit else "") + ("PT" if p == 7 else f"P{p}")

def decode(lo64, hi64, expect=None):
    v = (hi64 << 64) | lo64
    opcode = (bits(v, 91, 91) << 12) | bits(v, 11, 0)
    assert opcode in (0x98f, 0x1d8f), f"opcode {opcode:#x}"
    ur_form = (opcode == 0x1d8f)
    op = bits(v, 90, 87)
    cache = bits(v, 80, 78)
    e = bits(v, 72, 72)
    Ra = bits(v, 31, 24)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)

    mods = []
    if e:
        mods.append(".E")
    mods.append(CACHE.get(cache, f".c{cache}"))
    mods.append(COP.get(op, f".op{op}"))
    modstr = "".join(m for m in mods if m)

    if op in NOSRC_COPS:
        ops = ""  # whole-cache, no address
    elif ur_form:
        Ra_URb = bits(v, 37, 32)
        ops = f" [{reg(Ra)}+{ureg(Ra_URb)}]"
    else:
        off = bits(v, 63, 32)
        off = off - (1 << 32) if off >= (1 << 31) else off
        addr = f"[{reg(Ra)}"
        if off:
            addr += f"+{off:#x}"
        addr += "]"
        ops = f" {addr}"
    p = pred(Pg, Pg_not)
    preds = f"@{p} " if p else ""
    asm = f"{preds}CCTL{modstr}{ops} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x000000000200798f, 0x001fe20000000100, "CCTL.E.PF1 [R2] ;"),
    (0x000000000200798f, 0x001fe20000800100, "CCTL.E.PF2 [R2] ;"),
    (0x000000000200798f, 0x001fe20005800100, "CCTL.E.RML2 [R2] ;"),
    (0x000000000200798f, 0x001fe20005000100, "CCTL.E.DML2 [R2] ;"),
    (0x00000000ff00098f, 0x001fe20002000000, "@P0 CCTL.IVALL ;"),  # Pg=P0, Ra pinned RZ, no address
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
