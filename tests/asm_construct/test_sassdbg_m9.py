"""sassdbg M9 E2E — zero-reservation breakpoints (sassdbg/patch9.py).

  T1  m2_smoke flow: two bps (FFMA, STG), legacy resume() (restore site
      word + bare JMP-site thunk), kernel completes b=2a+1.
  T2  persistent bp in a loop, kernel uses EVERY borrowed register
      (R0/R1 + R2-R7 + formerly-reserved R252/R253 + P1-P3) across 10
      bp hits — fold check proves spill/restore is lossless.
  T3  divergent if/else: two groups park at two sites independently,
      per-lane release via release_group.
  T4  command injection on a parked warp: dump_regs (frame-backed
      R0-R7/PR), set_reg redirecting the kernel's loop sum.

Run:  python3 tests/asm_construct/test_sassdbg_m9.py
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sassdbg.lift import lift, normalize_source
from sassdbg.patch import Debugger

ok = True


def check(name, cond, extra=""):
    global ok
    if not cond:
        ok = False
    print(f"{'ok ' if cond else 'FAIL'} {name:<52} {extra}")


# ---------------------------------------------------------------------------
# T1 — legacy two-breakpoint flow on the nvcc-built m2_smoke kernel
# ---------------------------------------------------------------------------
CUBIN = str(Path(__file__).resolve().parents[1] / "m2_smoke.cubin")
src = normalize_source(lift(CUBIN)["k"])
insts = [ln.strip() for ln in src.splitlines()[1:]
         if ln.strip() and not ln.strip().startswith("#")]
i_ffma = next(i for i, t in enumerate(insts) if t.startswith("FFMA"))
i_stg = next(i for i, t in enumerate(insts) if t.startswith("STG"))

dbg = Debugger(src, max_bps=4)
n = 8
a = dbg.mod.devmem_alloc(n * 4)
b = dbg.mod.devmem_alloc(n * 4)
dbg.mod.device_write(a, struct.pack(f"<{n}f", *range(n)))
dbg.mod.device_write(b, bytes(n * 4))

dbg.launch([a, b, n], block=(n,))
base = dbg.base()
check("T1 target reports code base", base != 0 and base % 16 == 0,
      hex(base))

bp1 = dbg.arm(i_ffma)
bp2 = dbg.arm(i_stg)
dbg.release()

h1 = dbg.wait_hit()
check("T1 first hit is the FFMA bp", h1.id == bp1.id, f"hit id {h1.id}")
got = struct.unpack(f"<{n}f", dbg.mod.device_read(b, n * 4))
check("T1 at bp1 the STG has not run", all(v == 0.0 for v in got))
dbg.resume(h1)

h2 = dbg.wait_hit()
check("T1 second hit is the STG bp", h2.id == bp2.id, f"hit id {h2.id}")
dbg.resume(h2)

dbg.wait_done()
got = struct.unpack(f"<{n}f", dbg.mod.device_read(b, n * 4))
want = tuple(2.0 * i + 1.0 for i in range(n))
check("T1 kernel completes b=2a+1", got == want, str(got))

# ---------------------------------------------------------------------------
# T2 — persistent loop bp; kernel keeps live state in R0/R1, R2-R7,
#      R252/R253 and P1-P3 across 10 hits (fold sum must be exact)
# ---------------------------------------------------------------------------
K2 = """\
#fn k(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R10,R11}, #param(out);[1:7:{}:8:0]
    MOV32I R0, 0xAA;[7:7:{}:5:1]
    MOV32I R1, 0xBB;[7:7:{}:5:1]
    MOV32I R4, 0x100;[7:7:{}:5:1]
    MOV32I R5, 0x200;[7:7:{}:5:1]
    MOV32I R6, 0x300;[7:7:{}:5:1]
    MOV32I R7, 0x400;[7:7:{}:5:1]
    MOV32I R252, 0x777;[7:7:{}:5:1]
    MOV32I R253, 0x888;[7:7:{}:5:1]
    ISETP.EQ.AND P1, PT, R4, 0x100, PT;[7:7:{}:13:1]
    ISETP.NE.AND P2, PT, R4, 0x100, PT;[7:7:{}:13:1]
    ISETP.GT.AND P3, PT, R5, 0x100, PT;[7:7:{}:13:1]
    MOV32I R2, 0x0;[7:7:{}:5:1]
    MOV32I R3, 0x0;[7:7:{}:5:1]
#def_label(loop)
    IADD3 R2, R2, 0x7, RZ;[7:7:{}:5:1]
    IADD3 R3, R3, 0x1, RZ;[7:7:{}:5:1]
    ISETP.LT.AND P0, PT, R3, 0xA, PT;[7:7:{}:13:1]
    @P0 BRA #label(loop);[7:7:{}:5:1]
    MOV32I R8, 0x0;[7:7:{}:5:1]
    @P1 IADD3 R8, R8, R4, RZ;[7:7:{}:5:1]
    @P2 IADD3 R8, R8, 0xFFFF, RZ;[7:7:{}:5:1]
    @P3 IADD3 R8, R8, R5, RZ;[7:7:{}:5:1]
    IADD3 R8, R8, R6, RZ;[7:7:{}:5:1]
    IADD3 R8, R8, R7, RZ;[7:7:{}:5:1]
    IADD3 R8, R8, R0, RZ;[7:7:{}:5:1]
    IADD3 R8, R8, R1, RZ;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R10,R11}], R2;[7:7:{}:8:0]
    STG.E desc[{UR4,UR5}][{R10,R11}+0x4], R8;[7:7:{}:8:0]
    STG.E desc[{UR4,UR5}][{R10,R11}+0x8], R252;[7:7:{}:8:0]
    STG.E desc[{UR4,UR5}][{R10,R11}+0xC], R253;[0:1:{}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""
insts2 = [ln.strip() for ln in K2.splitlines()
          if ln.strip() and not ln.strip().startswith("#")
          and ln.strip() != "}"]
i_loop = insts2.index("IADD3 R2, R2, 0x7, RZ;[7:7:{}:5:1]")
orig_loop = "IADD3 R2, R2, 0x7, RZ;[7:7:{}:5:1]"

dbg2 = Debugger(K2, max_bps=4)
out = dbg2.mod.devmem_alloc(0x200)
dbg2.mod.device_write(out, bytes(0x200))
dbg2.launch([out], block=(32,))
dbg2.base()
bp = dbg2.arm(i_loop)
dbg2.release()
for i in range(10):
    h = dbg2.wait_hit()
    assert h.id == bp.id
    dbg2.resume_thunk(bp, [orig_loop])
dbg2.wait_done()
r2, fold, r252, r253 = struct.unpack("<4I", dbg2.mod.device_read(out, 16))
check("T2 loop sum after 10 persistent hits", r2 == 70, hex(r2))
check("T2 R0/R1+R4-R7+P1-P3 fold exact",
      fold == 0x100 + 0x200 + 0x300 + 0x400 + 0xAA + 0xBB, hex(fold))
check("T2 formerly-reserved R252/R253 survive",
      (r252, r253) == (0x777, 0x888), f"{hex(r252)},{hex(r253)}")

# ---------------------------------------------------------------------------
# T3 — divergent if/else: independent groups, per-group release
# ---------------------------------------------------------------------------
K3 = """\
#fn k(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    S2R R2, SR_TID.X;[5:7:{0,1}:5:1]
    LOP3.LUT R3, R2, 0x10, RZ, 0xC0;[7:7:{5}:5:1]
    ISETP.EQ.AND P0, PT, R3, RZ, PT;[7:7:{}:13:1]
    @P0 BRA #label(hi);[7:7:{}:6:0]
    MOV32I R6, 0x111;[7:7:{}:5:1]
    BRA #label(join);[7:7:{}:6:0]
#def_label(hi)
    MOV32I R6, 0x222;[7:7:{}:5:1]
#def_label(join)
    IMAD R8, R2, 0x4, R4;[7:7:{}:5:1]
    MOV R9, R5;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R8,R9}], R6;[0:1:{}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""
lines3 = [ln.strip() for ln in K3.splitlines()
          if ln.strip() and not ln.strip().startswith("#")]
i_lo = lines3.index("MOV32I R6, 0x111;[7:7:{}:5:1]")
i_hi = lines3.index("MOV32I R6, 0x222;[7:7:{}:5:1]")

dbg3 = Debugger(K3, max_bps=4)
out3 = dbg3.mod.devmem_alloc(0x100)
dbg3.mod.device_write(out3, bytes(0x100))
dbg3.launch([out3], block=(32,))
dbg3.base()
bp_lo = dbg3.arm(i_lo)
bp_hi = dbg3.arm(i_hi)
dbg3.release()

hits = {}
for _ in range(2):
    w, g = dbg3.wait_group_hit()
    hits[g.bp.id] = (w, g.mask)
    dbg3.release_group(w, g, [
        f"MOV32I R6, 0x{'111' if g.bp is bp_lo else '222'};[7:7:{{}}:5:1]"])
dbg3.wait_done()
check("T3 both branch groups parked independently",
      hits.get(bp_lo.id, (0, 0))[1] == 0xFFFF0000 and
      hits.get(bp_hi.id, (0, 0))[1] == 0x0000FFFF,
      str({k: hex(v[1]) for k, v in hits.items()}))
got3 = struct.unpack("<32I", dbg3.mod.device_read(out3, 32 * 4))
check("T3 divergent results correct",
      got3[:16] == (0x222,) * 16 and got3[16:] == (0x111,) * 16,
      f"{hex(got3[0])}..{hex(got3[31])}")

# ---------------------------------------------------------------------------
# T4 — command injection: dump_regs / set_reg on a parked warp
# ---------------------------------------------------------------------------
dbg4 = Debugger(K2, max_bps=4)
out4 = dbg4.mod.devmem_alloc(0x200)
dbg4.mod.device_write(out4, bytes(0x200))
dbg4.launch([out4], block=(32,))
dbg4.base()
bp4 = dbg4.arm(i_loop)
dbg4.release()
dbg4.wait_hit()                     # parked BEFORE the first += 7

regs = dbg4.dump_regs(0, ["R2", "R3", "R4", "R252", "PR"], lane=0)
# PR = 0xB: the gate ISETP leaves P0=1 at kernel entry (documented M5
# behavior) on top of the kernel's P1/P3
check("T4 dump_regs reads kernel state from the frame",
      regs["R2"] == 0 and regs["R3"] == 0 and regs["R4"] == 0x100
      and regs["R252"] == 0x777 and regs["PR"] == 0xB,
      str(regs))

# set ALL lanes: the kernel's final STG is a uniform-address store won
# by the highest lane, so a lane-0-only set would be invisible in out[0]
for lane in range(32):
    dbg4.set_reg(0, "R2", 0x100, lane=lane)
check("T4 set_reg wrote the frame slot",
      dbg4.dump_regs(0, ["R2"], lane=0)["R2"] == 0x100)

dbg4.resume_thunk(bp4, [orig_loop])
for _ in range(9):                  # remaining 9 persistent hits
    dbg4.wait_hit()
    dbg4.resume_thunk(bp4, [orig_loop])
dbg4.wait_done()
r2b, foldb = struct.unpack("<2I", dbg4.mod.device_read(out4, 8))
check("T4 set_reg steered the loop sum",
      r2b == 0x100 + 70 and foldb == 0x100 + 0x200 + 0x300 + 0x400
      + 0xAA + 0xBB, f"{hex(r2b)},{hex(foldb)}")

print("\n=== sassdbg M9:", "ALL PASS ===" if ok else "FAILURES ===")
sys.exit(0 if ok else 1)
