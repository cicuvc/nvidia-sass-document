#!/usr/bin/env python3
"""Decoder/verifier for STAS (sm_90a). Store-async to distributed shared memory.

STAS = PTX st.async.shared::cluster (store to a remote CTA's shared memory +
signal an mbarrier tx-count). Single opcode 0x1dbd, three CLASS variants that
differ only in the address-register form (64-bit pair / RZ / 32-bit):
  bit[90] input_reg_sz : 1 = Ra is a 64-bit register pair ([Ra.64])
Fields:
  sz   [75:73]  SZ_32_64_128 (32=4 default, 64=5, 128=6)
  mem  [80:77]  sem/sco/private via TABLES_mem_4 (WEAK/nosco/noprivate -> 0)
  Ra_URc [69:64], Ra_offset [63:40], Rb [39:32], Ra [31:24]
"""

SZ = {4: "32", 5: "64", 6: "128"}

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
    assert opcode == 0x1dbd, f"opcode {opcode:#x}"
    sz = bits(v, 75, 73)
    mem = bits(v, 80, 77)
    a64 = bits(v, 90, 90)
    Ra = bits(v, 31, 24)
    Rb = bits(v, 39, 32)
    Ra_URc = bits(v, 69, 64)
    Ra_off = bits(v, 63, 40)
    Pg = bits(v, 14, 12)
    Pg_not = bits(v, 15, 15)
    src_rel_sb = bits(v, 115, 113)

    mods = []
    if SZ[sz] != "32":
        mods.append("." + SZ[sz])
    # address operand
    addr = f"[{reg(Ra, wide=bool(a64))}"
    if Ra_URc != 63:
        addr += f"+{ureg(Ra_URc)}"
    if Ra_off:
        addr += f"+{Ra_off:#x}"
    addr += "]"
    p = pred(Pg, Pg_not)
    preds = f"@{p} " if p else ""
    asm = f"{preds}STAS{''.join(mods)} {addr}, {reg(Rb)} ;"
    ok = (expect is None) or (asm.split(';')[0].split() == expect.split(';')[0].split())
    print(f"{'OK ' if ok else 'BAD'} {asm}   [mem={mem} rd_sb={src_rel_sb}]")
    if not ok:
        print(f"    expected: {expect}")
    return ok

VECTORS = [
    (0x0000000002007dbd, 0x001fe2000c00083f, "STAS [R2.64], R0 ;"),
    (0x0000000204007dbd, 0x001fe2000c000a3f, "STAS.64 [R4.64], R2 ;"),
    (0x0000000402007dbd, 0x001fe2000c000c3f, "STAS.128 [R2.64], R4 ;"),
    (0x0000000402007dbd, 0x001fe2000c000a3f, "STAS.64 [R2.64], R4 ;"),
    (0x0000000002007dbd, 0x001fe2000c00083f, "STAS [R2.64], R0 ;"),
]

if __name__ == "__main__":
    allok = True
    for lo, hi, exp in VECTORS:
        allok &= decode(lo, hi, exp)
    print("\nALL PASS" if allok else "\nFAILURES")
