import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# SGXT — sign/zero-extend from a bit position (int_pipe; verified SM120, RTX 5090)
#
# SASS lowering of PTX `szext.mode.type`:
#   szext.clamp.s32 -> SGXT           szext.wrap.s32 -> SGXT.W
#   szext.clamp.u32 -> SGXT.U32       szext.wrap.u32 -> SGXT.W.U32
#   SGXT[.W][.U32] Rd, Ra, Rb|imm|URb
#
# Semantics (silicon-verified): extend the low N bits of Ra to 32 bits,
# N = Rb.  .U32 zero-extends, default .S32 sign-extends; N = 0 -> 0.
#   .C (clamp, default): N >= 32 -> Ra unchanged (N is NOT masked).
#   .W (wrap):           effective N = N mod 32 (N=32 -> 0, N=33 -> 1).
#
# Encodings (0x21a RRR / 0x81a RIR / 0x1c1a RUR): cw -> bit [75],
# fmt (S32=1/U32=0) -> bit [73].  Bit-for-bit ptxas match verified below.
# Scoreboard pattern: SGXT wr=SB{r}, STG req={0,r} (0 = desc/addr from LDCU/LDC).
# Each case uses its OWN result register: reusing one Rd across cases races
# the async STG read against the next SGXT write (depcheck anti_dep).
# ---------------------------------------------------------------------------

# ptxas sm_120 reference (CUDA 12.8, `szext` inline asm, [7:7:{3}:5:1]):
REF = {
    "SGXT":          (0x000000050407781a, 0x008fca0000000200),
    "SGXT.W":        (0x000000050407781a, 0x008fca0000000a00),
    "SGXT.U32":      (0x000000050407781a, 0x008fca0000000000),
    "SGXT.W.U32":    (0x000000050407781a, 0x008fca0000000800),
}
flat = assemble_flat("""SGXT R7, R4, 0x5;[7:7:{3}:5:1]
SGXT.W R7, R4, 0x5;[7:7:{3}:5:1]
SGXT.U32 R7, R4, 0x5;[7:7:{3}:5:1]
SGXT.W.U32 R7, R4, 0x5;[7:7:{3}:5:1]
""")
ok = True
for name, enc in zip(REF, flat):
    good = enc == REF[name]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes {name:10s} lo={enc[0]:016x} hi={enc[1]:016x} (ptxas match)")

# ---------------------------------------------------------------------------
# GPU semantic battery — (inst, expect, ra_preload)
# ---------------------------------------------------------------------------
cases = [
    ("SGXT R2, R0, 0x4",          0xFFFFFFFF, 0x0000000F),  # clamp.s32 N=4
    ("SGXT.U32 R2, R0, 0x4",      0x0000000F, None),        # clamp.u32 N=4
    ("SGXT R2, R0, 0x0",          0x00000000, None),        # N=0
    ("SGXT.W R2, R0, 0x0",        0x00000000, None),        # wrap N=0
    ("SGXT R2, R0, 0x1",          0xFFFFFFFF, None),        # N=1 sign-extend
    ("SGXT.U32 R2, R0, 0x1",      0x00000001, None),        # N=1 zero-extend
    ("SGXT R2, R0, 0x1F",         0x0000000F, None),        # N=31
    ("SGXT R2, R0, 0x20",         0x0000000F, None),        # clamp N=32 -> Ra
    ("SGXT.W R2, R0, 0x20",       0x00000000, None),        # wrap N=32 -> 0
    ("SGXT R2, R0, 0x21",         0x0000000F, None),        # clamp N=33 -> Ra
    ("SGXT.W R2, R0, 0x21",       0xFFFFFFFF, None),        # wrap N=33 -> 1 bit
    ("SGXT R2, R0, 0xFFFFFFFF",   0x0000000F, None),        # clamp huge -> Ra
    ("SGXT.W R2, R0, 0xFFFFFFFF", 0x0000000F, None),        # wrap huge -> 31 bits
    ("SGXT R2, R0, R1",           0x0000000F, 0x0000000F),  # RRR N=5 (R1=5)
    ("SGXT R2, R0, 0x1",          0x00000000, 0x80000000),  # Ra=0x80000000 N=1
    ("SGXT R2, R0, 0x4",          0xFFFFFFF8, 0x00000008),  # Ra=0x8 N=4
]

lines = ["#fn k(out<192>) {",
         "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]",
         "    MOV32I R1, 0x00000005;[7:7:{}:5:1]"]
off = 0x40            # main battery AFTER the per-block RUR region (0x00..0x30)
for i, (inst, exp, ra) in enumerate(cases):
    r = (i % 4) + 1
    rd = 12 + i          # unique destination per case
    if ra is not None:
        lines.append(f"    MOV32I R0, 0x{ra:08X};[7:7:{{}}:5:1]")
    lines.append(f"    {inst.replace('R2,', f'R{rd},')};[{r}:7:{{}}:5:1]")
    lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:X}], R{rd};[7:7:{{0,{r}}}:1:0]")
    off += 4

# RUR: N = SR_CTAID.X (0,1,2 per block); Ra=0x0F preloaded
lines += [
    "    S2UR UR0, SR_CTAID.X;[0:7:{}:5:1]",
    "    S2R R8, SR_CTAID.X;[0:7:{}:5:1]",
    "    IMAD.WIDE.U32 {R10,R11}, R8, 0x10, {R6,R7};[5:7:{0}:5:1]",
    "    MOV32I R0, 0x0000000F;[7:7:{}:5:1]",
]
rur = [
    ("SGXT R2, R0, UR0",        0),   # clamp.s32
    ("SGXT.W.U32 R2, R0, UR0",  4),   # wrap.u32
    ("SGXT.U32 R2, R0, UR0",    8),   # clamp.u32
    ("SGXT.W R2, R0, UR0",      12),  # wrap.s32
]
for j, (inst, rel) in enumerate(rur):
    r = ((j + 1) % 4) + 1
    rd = 28 + j          # unique destination per RUR case
    lines.append(f"    {inst.replace('R2,', f'R{rd},')};[{r}:7:{{}}:5:1]")
    lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R10,R11}}+0x{rel:X}], R{rd};[7:7:{{0,5,{r}}}:1:0]")
lines += ["    EXIT;[7:7:{}:5:0]", "}"]

try:
    mod = CudaModule(assemble("\n".join(lines)))
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

d = mod.devmem_alloc(1024)
mod.device_write(d, bytes(1024))
mod.launch("k", grid=(3,), block=(1,), args=[d])
mod.synchronize()
v = struct.unpack("<48I", mod.device_read(d, 48 * 4))
mod.devmem_free(d)

labels = ["clamp.s32 N=4", "clamp.u32 N=4", "clamp.s32 N=0", "wrap.s32 N=0",
          "clamp.s32 N=1", "clamp.u32 N=1", "clamp.s32 N=31", "clamp.s32 N=32",
          "wrap.s32 N=32", "clamp.s32 N=33", "wrap.s32 N=33", "clamp N=huge",
          "wrap N=huge", "RRR N=5", "Ra=80000000 N=1", "Ra=8 N=4"]
for i, (got, want, lab) in enumerate(zip(v[16:32], [c[1] for c in cases], labels)):
    good = got == want
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} [{i:2d}] {lab:18s} = 0x{got:08X} (exp 0x{want:08X})")

# RUR per block (block b stores at out + b*16): N = 0,1,2; Ra=0x0F
for b in range(3):
    n = b
    s32_c, w_u32, u32_c, s32_w = v[4 * b:4 * b + 4]
    lo_mask = (0xF & ((1 << n) - 1)) if n else 0
    exp = [0xFFFFFFFF if n else 0, lo_mask, lo_mask, 0xFFFFFFFF if n else 0]
    good = (s32_c, w_u32, u32_c, s32_w) == tuple(exp)
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} RUR block {b} (N={n}): "
          f"s32={s32_c:#x} w.u32={w_u32:#x} u32={u32_c:#x} w.s32={s32_w:#x}")

print("\n=== SGXT semantic verification: ALL OK ===" if ok else "\n=== SGXT FAILURES ===")
sys.exit(0 if ok else 1)
