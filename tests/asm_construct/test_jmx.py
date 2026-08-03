import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# JMX / JMXU (absolute indirect) vs BRX / BRXU (relative indirect) — SM120
#
# The indirect-branch family, four forms:
#   BRX  0x949  target = next_pc + Ra + off*4   (RELATIVE; Ra = signed kernel-
#                                                 relative byte offset from next)
#   BRXU 0x1958 target = next_pc + URa + off*4  (RELATIVE, uniform register)
#   JMX  0x94c  target = Ra + off*4             (ABSOLUTE; Ra = 64-bit address)
#   JMXU 0x1959 target = URa + off*4            (ABSOLUTE, uniform register)
#
# The PROPER base for the absolute forms is LEPC (load effective PC) / ULEPC —
# `LEPC Rd` returns the current PC (verified: base 0x07167500 for both the RRR
# and the PC+imm58 forms).  NOT TRAP_RETURN_PC (which is an unreliable
# divergence-side effect).
#
# Verified empirically:
#   JMX  R4, off with R4 = LEPC-PC: off=0x50 -> lands R4+0x50 (skips 2 MOVs),
#                                     off=0x40 -> lands R4+0x40.
#   JMXU UR4, off with UR4 = ULEPC-PC: off=0x40 -> lands +0x40, off=0x30 -> +0x30.
#   BRX  R4, #label(x) with R4=0      -> lands on x (relative).
#   BRXU UR4, #label(x) with UR4=0    -> lands on x (relative).
# Offset operands on scaled fields are BYTES (the encoder divides by SCALE 4).
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}")

def run(kernel_lines, block=32, buf=1024):
    src = "#fn k(buf<1024>) {\n" + "\n".join(kernel_lines) + "\n}"
    cubin = assemble(src)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(buf)
    mod.device_write(d, struct.pack(f"<{buf//4}I", *[0] * (buf // 4)))
    mod.launch("k", grid=(1,), block=(block,), args=[d])
    mod.synchronize()
    v = struct.unpack(f"<{block}I", mod.device_read(d, block * 4))
    mod.devmem_free(d)
    return v[0:block]

# ---- 1. JMX absolute via LEPC ----------------------------------------------
# ULEPC? No — per-thread LEPC R4 at 0x20. JMX R4,0x50 -> R4+0x50 = MOV R22,
# skipping the MOV R21 (0x60).
v = run(["    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(buf);[1:7:{}:1:0]",
         "    MOV32I R20, 0xAAAAAAAA;[7:7:{}:5:1]",
         "    MOV32I R21, 0xBBBBBBBB;[7:7:{}:5:1]",
         "    LEPC {R4,R5};[7:7:{}:5:1]",                    # 0x20
         "    MOV32I R5, 0x0;[7:7:{}:5:1]",             # 0x30
         "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",     # 0x40
         "    JMX {R4,R5}, 0x50;[7:7:{}:5:1]",               # 0x50 -> R4+0x50 = 0x70
         "    MOV32I R21, 0x22222222;[7:7:{}:5:1]",     # 0x60 (skipped)
         "    MOV32I R22, 0x33333333;[7:7:{}:5:1]",     # 0x70 target
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R20;[0:1:{0,1}:1:0]",
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R21;[7:1:{}:1:0]",
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R22;[7:1:{}:1:0]",
         "    EXIT;[7:7:{}:5:0]"])
check("JMX R4(LEPC-PC)+0x50 lands at 0x70 (skips MOV R21)",
      (v[0], v[1], v[2]), (0x11111111, 0xBBBBBBBB, 0x33333333))

# ---- 2. JMXU absolute via ULEPC --------------------------------------------
v = run(["    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(buf);[1:7:{}:1:0]",
         "    MOV32I R20, 0xAAAAAAAA;[7:7:{}:5:1]",
         "    MOV32I R21, 0xBBBBBBBB;[7:7:{}:5:1]",
         "    ULEPC {UR4,UR5};[7:7:{}:5:1]",                  # 0x20
         "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",     # 0x30
         "    JMXU UR4, 0x40;[7:7:{}:5:1]",             # 0x40 -> UR5+0x40 = 0x60
         "    MOV32I R21, 0x22222222;[7:7:{}:5:1]",     # 0x50 (skipped)
         "    MOV32I R22, 0x33333333;[7:7:{}:5:1]",     # 0x60 target
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R20;[0:1:{0,1}:1:0]",
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R21;[7:1:{}:1:0]",
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R22;[7:1:{}:1:0]",
         "    EXIT;[7:7:{}:5:0]"])
check("JMXU UR4(ULEPC-PC)+0x40 lands at 0x60 (skips MOV R21)",
      (v[0], v[1], v[2]), (0x11111111, 0xBBBBBBBB, 0x33333333))

# ---- 3. BRX relative (R4=0 + label) ----------------------------------------
v = run(["    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(buf);[1:7:{}:1:0]",
         "    MOV32I R20, 0xAAAAAAAA;[7:7:{}:5:1]",
         "    MOV32I R21, 0xBBBBBBBB;[7:7:{}:5:1]",
         "    MOV32I R4, 0x0;[7:7:{}:5:1]",
         "    MOV32I R5, 0x0;[7:7:{}:5:1]",
         "    BRX {R4,R5}, #label(x);[7:7:{}:5:1]",
         "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",
         "    MOV32I R21, 0x22222222;[7:7:{}:5:1]",
         "    #def_label(x)",
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R20;[0:1:{0,1}:1:0]",
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R21;[0:1:{0,1}:1:0]",
         "    EXIT;[7:7:{}:5:0]"])
check("BRX R4=0 + label lands on x (relative)",
      (v[0], v[1]), (0xAAAAAAAA, 0xBBBBBBBB))

# ---- 4. BRXU relative (UR=0 + label) ---------------------------------------
v = run(["    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(buf);[1:7:{}:1:0]",
         "    MOV32I R20, 0xAAAAAAAA;[7:7:{}:5:1]",
         "    MOV32I R21, 0xBBBBBBBB;[7:7:{}:5:1]",
         "    BRXU UR4, #label(x);[7:7:{}:5:1]",   # UR5 unset = 0 -> relative
         "    MOV32I R20, 0x11111111;[7:7:{}:5:1]",
         "    MOV32I R21, 0x22222222;[7:7:{}:5:1]",
         "    #def_label(x)",
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R20;[0:1:{0,1}:1:0]",
         "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R21;[0:1:{0,1}:1:0]",
         "    EXIT;[7:7:{}:5:0]"])
check("BRXU UR4=0 + label lands on x (relative)",
      (v[0], v[1]), (0xAAAAAAAA, 0xBBBBBBBB))

print(f"\n=== JMX/JMXU (absolute) vs BRX/BRXU (relative): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
