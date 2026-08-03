import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# BMSK — bitmask from position + width (int_pipe; verified SM120, RTX 5090)
#
#   BMSK[.C|.W] Rd, Ra, Rb|imm|URb
#   Rd = ((1 << width) - 1) << pos, truncated to 32 bits.
#   Ra = POSITION, Rb = WIDTH  (silicon-confirmed: pos=4,w=3 -> 0x70).
#
#   .C (clamp, default): operands used as-is; the "clamp" is just the natural
#      32-bit truncation of the shifted mask (pos=2,w=32 -> 0xFFFFFFFC, NOT a
#      width-clamped 0x3FFFFFFC).  pos>=32 -> 0; width>=32 -> all bits below
#      the position (e.g. pos=0,w=32 -> 0xFFFFFFFF).
#   .W (wrap): pos & 31 and width & 31 before the same formula
#      (pos=33 -> pos 1; width=33 -> width 1; width=32 -> 0).
#
# Encodings (0x21b RRR / 0x81b RIR / 0x1c1b RUR): cw -> bit [75].
# ptxas does not emit BMSK from plain C on sm_120 ((1u<<n)-1 lowers to
# SHF.L + LOP3), so this is exercised directly via the assembler.
# Scoreboard pattern: BMSK wr=SB{r}, STG req={0,r}.
# Each case uses its OWN result register: reusing one Rd across cases races
# the async STG read against the next BMSK write (depcheck anti_dep).
# ---------------------------------------------------------------------------

flat = assemble_flat("""BMSK R6, R13, R6;[7:7:{}:5:1]
BMSK.W R6, R13, R6;[7:7:{}:5:1]
BMSK R6, R13, 0x1f;[7:7:{}:5:1]
BMSK.W R6, R13, 0x21;[7:7:{}:5:1]
""")
REF = [
    (0x000000060d06721b, 0x000fca0000000000),  # BMSK (C, default)
    (0x000000060d06721b, 0x000fca0000000800),  # BMSK.W (cw bit75)
    (0x0000001f0d06781b, 0x000fca0000000000),  # BMSK RIR
    (0x000000210d06781b, 0x000fca0000000800),  # BMSK.W RIR w=33
]
ok = True
for i, enc in enumerate(flat):
    good = enc == REF[i]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")

# ---------------------------------------------------------------------------
# GPU semantic battery — (inst, expect, [ra,rb preloads])
# ---------------------------------------------------------------------------
cases = [
    ("BMSK.C R2, R0, R1",          0x00000070, (0x00000004, 0x00000003)),  # pos=4 w=3
    ("BMSK.C R2, R0, R1",          0x00000078, (0x00000003, 0x00000004)),  # pos=3 w=4
    ("BMSK.C R2, R0, R1",          0xC0000000, (0x0000001E, 0x00000004)),  # pos=30 w=4 C trunc
    ("BMSK.W R2, R0, R1",          0xC0000000, None),                      # W same
    ("BMSK.W R2, R0, R1",          0x80000000, (0x0000001F, 0x00000002)),  # pos=31 w=2
    ("BMSK.C R2, R0, 0x20",        0xFFFFFFFC, (0x00000002, None)),        # pos=2 w=32 C trunc
    ("BMSK.W R2, RZ, 0x20",        0x00000000, (0x00000000, None)),        # w=32 W -> width&31=0
    ("BMSK.W R2, RZ, 0x21",        0x00000001, None),                      # w=33 W -> 1 bit
    ("BMSK.C R2, RZ, 0x21",        0xFFFFFFFF, None),                      # w=33 C -> all-ones
    ("BMSK.W R2, R0, R1",          0x00000002, (0x00000021, 0x00000001)),  # pos=33 w=1 W -> pos&31=1
    ("BMSK.C R2, R0, R1",          0x00000000, None),                      # pos=33 w=1 C -> 0
    ("BMSK.C R2, RZ, R1",          0x00000000, (0x00000000, 0x00000000)),  # w=0
    ("BMSK.C R2, R0, 0x18",        0xFFFFFF00, (0x00000008, None)),        # pos=8 w=24
    ("BMSK.C R2, RZ, 0x1F",        0x7FFFFFFF, (0x00000000, None)),        # pos=0 w=31
]

lines = ["#fn k(out<128>) {",
         "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]"]
off = 0x40            # main battery AFTER the per-block RUR region (0x00..0x20)
for i, (inst, exp, pre) in enumerate(cases):
    r = (i % 4) + 1
    rd = 12 + i          # unique destination per case
    if pre is not None:
        ra, rb = pre
        if ra is not None:
            lines.append(f"    MOV32I R0, 0x{ra:08X};[7:7:{{}}:5:1]")
        if rb is not None:
            lines.append(f"    MOV32I R1, 0x{rb:08X};[7:7:{{}}:5:1]")
    lines.append(f"    {inst.replace('R2,', f'R{rd},')};[{r}:7:{{}}:5:1]")
    lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:X}], R{rd};[7:7:{{0,{r}}}:1:0]")
    off += 4

# RUR: pos=0 (RZ), width = SR_CTAID.X (0,1,2 per block)
lines += [
    "    S2UR UR0, SR_CTAID.X;[0:7:{}:5:1]",
    "    S2R R8, SR_CTAID.X;[0:7:{}:5:1]",
    "    IMAD.WIDE.U32 {R10,R11}, R8, 0x10, {R6,R7};[5:7:{0}:5:1]",
]
rur = [
    ("BMSK.C R2, RZ, UR0",   0),
    ("BMSK.W R2, RZ, UR0",   4),
    ("BMSK.C R2, RZ, 0x0",   8),
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

labels = ["pos=4 w=3", "pos=3 w=4", "pos=30 w=4 C", "pos=30 w=4 W",
          "pos=31 w=2 W", "pos=2 w=32 C", "w=32 W", "w=33 W", "w=33 C",
          "pos=33 w=1 W", "pos=33 w=1 C", "w=0", "pos=8 w=24", "w=31"]
for i, (got, want, lab) in enumerate(zip(v[16:30], [c[1] for c in cases], labels)):
    good = got == want
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} [{i:2d}] {lab:14s} = 0x{got:08X} (exp 0x{want:08X})")

# RUR per block (block b stores at out + b*16): width = 0,1,2 at pos=0
for b in range(3):
    w = b
    c_val, w_val, zero = v[4 * b:4 * b + 3]
    exp_c = (1 << w) - 1 if w else 0
    exp_w = (1 << (w & 31)) - 1 if w else 0
    good = (c_val == exp_c and w_val == exp_w and zero == 0)
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} RUR block {b} (w={w}): C={c_val:#x} W={w_val:#x} zero={zero:#x}")

print("\n=== BMSK semantic verification: ALL OK ===" if ok else "\n=== BMSK FAILURES ===")
sys.exit(0 if ok else 1)
