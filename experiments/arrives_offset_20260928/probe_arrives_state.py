#!/usr/bin/env python3
"""Directly observe ARRIVES tx-count and phase for [UR] versus [UR+8]."""
from pathlib import Path
import struct, sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from assembler import assemble, CudaModule

MASK21 = (1 << 21) - 1

def source(mode: str, copies: int) -> str:
    assert mode in ("zero", "offset")
    # UR6 is the operation base; UR7 always holds the physical 0x408 address
    # used for initialization.  Thus both spellings target byte address 0x408.
    if mode == "zero":
        setup = "UMOV UR6, 0x408;[7:7:{}:5:1]"
        addr = "[RZ+UR6]"
    else:
        setup = "UMOV UR6, 0x400;[7:7:{}:5:1]"
        addr = "[RZ+UR6+0x8]"
    ldgsts = []
    for i in range(copies):
        off = i * 0x200
        ldgsts.append(
            f"    LDGSTS.E.BYPASS.128 [R3+0x{off:x}], "
            f"desc[{{UR4,UR5}}][{{R4,R5}}+0x{off:x}];[7:{i & 1}:{{}}:1:0]")
    # Each observation stores lane0's live 64-bit barrier word.
    def obs(off: int) -> str:
        return (
            f"    SYNCS.LD.64 {{R8,R9}}, {addr};[2:7:{{}}:5:1]\n"
            f"    @P0 STG.E.64 desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], "
            "{R8,R9};[0:2:{2}:1:0]\n")
    return f'''#fn probe(inp<8>, out<8>) {{
    #pragma NUM_MBARRIERS(1)
    #pragma SHARED(0x8000)
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(inp);[1:7:{{}}:1:0]
    LDC.64 {{R6,R7}}, #param(out);[1:7:{{}}:1:0]
    S2R R0, SR_TID.X;[3:7:{{}}:5:1]
    ISETP.EQ.U32.AND P0, PT, R0, RZ, PT;[7:7:{{3}}:5:1]
    SHF.L.U32 R1, R0, 4, RZ;[7:7:{{3}}:5:1]
    IADD3 R3, R1, 0x800, RZ;[7:7:{{}}:5:1]
    IADD3 R4, R4, R1, RZ;[7:7:{{1}}:5:1]
    UMOV UR7, 0x408;[7:7:{{}}:5:1]
    UMOV UR8, 0xfffe0;[7:7:{{}}:5:1]
    USHF.L.U32 UR9, UR8, 0xb, URZ;[7:7:{{}}:5:1]
    USHF.L.U32 UR8, UR8, 0x1, URZ;[7:7:{{}}:5:1]
    SYNCS.EXCH.64 URZ, [UR7], UR8;[2:1:{{1}}:5:1]
    BAR.SYNC 0;[7:7:{{2}}:5:1]
    {setup}
{obs(0)}
{chr(10).join(ldgsts)}
{obs(8)}
    SYNCS.ARRIVE.TRANS64.RED.A0T1 {{RZ,RZ}}, {addr}, RZ;[7:7:{{}}:5:1]
{obs(16)}
    ARRIVES.LDGSTSBAR.64.TRANSCNT {addr};[7:7:{{}}:5:1]
{obs(24)}
    SYNCS.ARRIVE.TRANS64.A1T0 {{R10,R11}}, {addr}, RZ;[3:7:{{}}:5:1]
{obs(32)}
    MOV32I R12, 0x0;[7:7:{{}}:5:1]
wait:
    SYNCS.PHASECHK.TRANS64.TRYWAIT P1, {addr}, R12;[4:7:{{}}:2:0]
    @!P1 BRA #label(wait);[7:7:{{4}}:5:0]
{obs(40)}
    LDS.128 {{R12,R13,R14,R15}}, [R3];[5:7:{{}}:8:1]
    @P0 STG.E.128 desc[{{UR4,UR5}}][{{R6,R7}}+0x40], {{R12,R13,R14,R15}};[0:5:{{5}}:1:0]
    EXIT;[7:7:{{0}}:5:0]
}}'''

def run(mode: str, copies: int):
    cubin = assemble(source(mode, copies), check_deps=False, arch="sm120")
    here = Path(__file__).parent
    (here / f"state_{mode}_{copies}.cubin").write_bytes(cubin)
    mod = CudaModule(cubin)
    nbytes = copies * 0x200 + 0x200
    inp = mod.devmem_alloc(nbytes)
    out = mod.devmem_alloc(128)
    pattern = bytes((i * 17 + 3) & 0xff for i in range(nbytes))
    mod.device_write(inp, pattern)
    mod.devmem_set(out, 0xdeadbeef, 32)
    mod.launch("probe", block=(32,), args=[inp, out])
    mod.synchronize()
    data = mod.device_read(out, 128)
    words = struct.unpack_from("<6Q", data)
    payload = bytes(data[0x40:0x50])
    return words, payload, pattern[:16]

if __name__ == "__main__":
    copies = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    results = {}
    for mode in ("zero", "offset"):
        words, payload, want = run(mode, copies)
        results[mode] = words
        print(mode, "payload", payload.hex(), "want", want.hex(), payload == want)
        for name, w in zip(("init", "after_ldgsts", "after_a0t1", "after_arrives", "after_arrive", "final"), words):
            enc = (w >> 21) & MASK21
            logical = (-enc) & MASK21
            print(f"  {name:14s} raw=0x{w:016x} txfield=0x{enc:06x} logical_mod21={logical}")
    print("states_equal", results["zero"] == results["offset"])
