"""RF bank-structure probe (H800/sm_90): 2 parity banks x 2R1W, .reuse bypass.

Hand-written SASS FFMA storms with fully controlled register-number parity
and .reuse flags (sched bracket 6th field: bit0=srcA, bit1=srcB, bit2=srcC).
One warp, 16 independent accumulator chains, stall=1 (~2.1-2.4 cyc/op floor).

Results (H800, 1 warp, cyc/op):
    nop 2.44 | eee/ooo 3.11 (conflict +1) | eeo/eoe/oee 2.11 (clean)
    eee+reuseA 2.11 | eee+reuseB 2.11 | eee+reuseAB(C) 2.43 (=baseline)
=> bank = register-number LSB parity; 2 reads/bank/instr free, 3rd = +1 cyc;
   .reuse operands are served from the reuse cache, not the RF ports.

Run: assemble locally, scp rf_*.cubin to the GPU host, then execute each
with CudaModule(block=(32,)) and read (t1-t0)/512 from the first 8 bytes.
"""
import sys
sys.path.insert(0, "/home/cicuvc/cs/projects/nvidia-sass-document")
from assembler import assemble

N = 512
DSTS = [40 + 2 * i for i in range(16)]

KERNELS = {
    "nop":     (None, None, None, "[7:7:{}:1:0]"),
    "eee":     ("R4", "R10", "R8", "[7:7:{}:1:0]"),
    "ooo":     ("R5", "R11", "R9", "[7:7:{}:1:0]"),
    "eeo":     ("R4", "R10", "R9", "[7:7:{}:1:0]"),
    "eoe":     ("R4", "R9", "R10", "[7:7:{}:1:0]"),
    "oee":     ("R9", "R4", "R10", "[7:7:{}:1:0]"),
    "eee_rA":  ("R4", "R10", "R8", "[7:7:{}:1:0:1]"),
    "eee_rB":  ("R4", "R10", "R8", "[7:7:{}:1:0:2]"),
    "eee_rAB": ("R4", "R10", "R8", "[7:7:{}:1:0:3]"),
    "eee_rABC": ("R4", "R10", "R8", "[7:7:{}:1:0:7]"),
}

PROLOGUE = """#fn thr(buf<8>) {
    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]
    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:1]
    S2R R0, SR_TID.X;[7:7:{}:6:0]
    SHF.R.U32.HI R1, RZ, 0x5, R0;[7:7:{}:6:0]
    IMAD R1, R1, 0x10, RZ;[7:7:{}:6:0]
    IADD3 R2, P0, R6, R1, RZ;[7:7:{0}:6:0]
    PLOP3.LUT P1, PT, PT, PT, PT, 0x0;[7:7:{}:6:0]"""

EPILOGUE = """    IADD3.X R3, P1, R7, RZ, RZ, P0, P1;[7:7:{}:6:0]
    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:6:0]
    STG.E desc[{UR4,UR5}][{R2,R3}+0x0], R30;[0:1:{0}:6:0]
    STG.E desc[{UR4,UR5}][{R2,R3}+0x4], R32;[0:1:{0}:6:0]
    STG.E desc[{UR4,UR5}][{R2,R3}+0x8], R40;[0:1:{0}:6:0]
    EXIT;[7:7:{}:5:0]
}"""


def build(sa, sb, sc, sched):
    lines = [PROLOGUE]
    for r in [4, 5, 8, 9, 10, 11]:
        lines.append(f"    MOV R{r}, 0x3f800000;[7:7:{{}}:6:0]")
    for d in DSTS:
        lines.append(f"    MOV R{d}, 0x0;[7:7:{{}}:6:0]")
    lines += ["    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:6:0]",
              "    NOP;[7:7:{}:0:1]"]
    for i in range(N):
        d = DSTS[i % 16]
        if sa is None:
            lines.append(f"    NOP;{sched}")
        else:
            lines.append(f"    FFMA R{d}, {sa}, {sb}, {sc};{sched}")
    lines.append(EPILOGUE)
    return assemble("\n".join(lines), check_deps=False, arch="sm90")


if __name__ == "__main__":
    for name, (sa, sb, sc, sched) in KERNELS.items():
        open(f"rf_{name}.cubin", "wb").write(build(sa, sb, sc, sched))
    print("built", len(KERNELS), "cubins")
