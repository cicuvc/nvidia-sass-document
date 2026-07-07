#!/usr/bin/env python3
"""Decoder for S2R / S2UR (read Special Register -> GPR / uniform reg) on sm_90.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).
Validated against real cuobjdump captures (sm_90, CUDA 13.1):
  S2R  from tests/s2r_test.cu ; S2UR from libcublasLt.so.
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OP_S2R  = 0x919
OP_S2UR = 0x9c3

# SpecialRegister names (from sm_90_instructions.txt lines 1003-1063)
SR = {
    0:"SR_LANEID",1:"SR_CLOCK",2:"SR_VIRTCFG",3:"SR_VIRTID",
    15:"SR_ORDERING_TICKET",16:"SR_PRIM_TYPE",17:"SR_INVOCATION_ID",
    18:"SR_Y_DIRECTION",19:"SR_THREAD_KILL",20:"SM_SHADER_TYPE",
    21:"SR_DIRECTCBEWRITEADDRESSLOW",22:"SR_DIRECTCBEWRITEADDRESSHIGH",
    23:"SR_DIRECTCBEWRITEENABLED",24:"SR_MACHINE_ID_0",25:"SR_MACHINE_ID_1",
    26:"SR_MACHINE_ID_2",27:"SR_MACHINE_ID_3",28:"SR_AFFINITY",
    29:"SR_INVOCATION_INFO",30:"SR_WSCALEFACTOR_XY",31:"SR_WSCALEFACTOR_Z",
    32:"SR_TID",33:"SR_TID.X",34:"SR_TID.Y",35:"SR_TID.Z",
    37:"SR_CTAID.X",38:"SR_CTAID.Y",39:"SR_CTAID.Z",40:"SR_NTID",
    41:"SR_CirQueueIncrMinusOne",42:"SR_NLATC",44:"SR_SM_SPA_VERSION",
    45:"SR_MULTIPASSSHADERINFO",46:"SR_LWINHI",47:"SR_SWINHI",48:"SR_SWINLO",
    49:"SR_SWINSZ",50:"SR_SMEMSZ",51:"SR_SMEMBANKS",52:"SR_LWINLO",53:"SR_LWINSZ",
    54:"SR_LMEMLOSZ",55:"SR_LMEMHIOFF",56:"SR_EQMASK",57:"SR_LTMASK",58:"SR_LEMASK",
    59:"SR_GTMASK",60:"SR_GEMASK",61:"SR_REGALLOC",62:"SR_BARRIERALLOC",
    64:"SR_GLOBALERRORSTATUS",65:"SR_CGAERRORSTATUS",66:"SR_WARPERRORSTATUS",
    67:"SR_VIRTUALSMID",68:"SR_VIRTUALENGINEID",80:"SR_CLOCKLO",81:"SR_CLOCKHI",
    82:"SR_GLOBALTIMERLO",83:"SR_GLOBALTIMERHI",84:"SR_ESR_PC",85:"SR_ESR_PC_HI",
    96:"SR_HWTASKID",97:"SR_CIRCULARQUEUEENTRYINDEX",
    98:"SR_CIRCULARQUEUEENTRYADDRESSLOW",99:"SR_CIRCULARQUEUEENTRYADDRESSHIGH",
    132:"SR_VARIABLE_RATE",133:"SR_TTU_TICKET_INFO",134:"SR_WARPGROUP_INFO",
    135:"SR_WARPGROUPID",136:"SR_CgaCtaId",137:"SR_GpcLocalCgaId",
    138:"SR_CgaLinearMemorySlot",139:"SR_CTARegPoolSz",255:"SRZ",
}
def sr_name(v): return SR.get(v, f"SR{v}")
def reg(n): return "RZ" if n == 0xff else f"R{n}"
def ureg(n): return "URZ" if n == 0x3f else f"UR{n}"

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    Pg     = bits(w, 14, 12)
    Pg_not = bits(w, 15, 15)
    SRa    = bits(w, 79, 72)
    if opcode == OP_S2R:
        guard = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
        return f"{guard}S2R {reg(bits(w,23,16))}, {sr_name(SRa)} ;"
    if opcode == OP_S2UR:
        guard = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}UP{Pg} "
        return f"{guard}S2UR {ureg(bits(w,21,16))}, {sr_name(SRa)} ;"
    raise AssertionError(f"bad opcode {opcode:#x}")

VEC = [
    # S2R (tests/s2r_test.cu)
    (0x0000000000057919, 0x000e2e0000000000, "S2R R5, SR_LANEID ;"),
    (0x0000000000077919, 0x000e640000000300, "S2R R7, SR_VIRTID ;"),
    (0x0000000000057919, 0x000e2e0000002100, "S2R R5, SR_TID.X ;"),
    (0x0000000000057919, 0x000e2e0000002500, "S2R R5, SR_CTAID.X ;"),
    (0x0000000000057919, 0x000e2e0000003800, "S2R R5, SR_EQMASK ;"),
    (0x0000000000077919, 0x000e620000003900, "S2R R7, SR_LTMASK ;"),
    # S2UR (libcublasLt.so)
    (0x00000000000679c3, 0x000e620000002600, "S2UR UR6, SR_CTAID.Y ;"),
    (0x00000000001079c3, 0x000f220000002500, "S2UR UR16, SR_CTAID.X ;"),
    (0x00000000000579c3, 0x000e220000008800, "S2UR UR5, SR_CgaCtaId ;"),
]

if __name__ == "__main__":
    ok = True
    for lo, hi, exp in VEC:
        got = decode(lo, hi)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:28s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
