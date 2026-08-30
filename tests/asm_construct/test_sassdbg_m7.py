"""sassdbg M7 — command injection at a breakpoint (on-demand state access).

While a warp is parked at a breakpoint, the host injects arbitrary
instruction sequences into the warp's per-warp command buffer
(heap-resident — no code patching); the parked handler dispatches them
via CALL.ABS + RET round-trip (hardened IVALL covers the refetch) and
stays parked.  Repeatable until resume.  M9: commands run with
{R0,R1} = the lane's frame pointer and R2-R7/P0-P6 as scratch (no
reserved registers anywhere).

E1  static command round-trip: dump a kernel register (R10 magic)
E2  command REWRITE between dispatches: second command sees fresh
    content (IVALL works) — two different dumps from the same VA
E3  dump preserved state: R246 (never touched by the M9 handler — read
    live) and PR (frame snapshot)
E4  set register: set_reg R10 -> resumed kernel output reflects it;
    set_reg R246 likewise
E5  exec_cmd raw: probe SR_SMID (architecture state probe), and the
    R0/R1 (frame pointer) + control-flow guards fire

Run: python3 tests/asm_construct/test_sassdbg_m7.py
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sassdbg.patch import Debugger  # noqa: E402

B = "[7:7:{}:5:1]"

# idx: 0 LDCU  1 LDC  2 S2R  3 MOV32I R10 magic  4 IADD3 R246 magic
#      5 ISETP P0 (R10 bit0)  6 MOV32I R0 <- BP SITE
#      7 IMAD.WIDE  8 STG R10  9 STG R246  10 STG PR-observation  11 EXIT
SRC = f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    S2R R20, SR_TID.X;[5:7:{{}}:5:1]
    MOV32I R10, 0xC0DE0001;{B}
    MOV32I R246, 0xBEEF246;{B}
    ISETP.EQ.AND P0, PT, R10, 0xC0DE0001, PT;[7:7:{{}}:13:1]
    MOV32I R0, 0x7;{B}
    IMAD.WIDE.U32 {{R24,R25}}, R20, 0x4, {{R4,R5}};[7:7:{{1,5}}:13:1]
    STG.E desc[{{UR4,UR5}}][{{R24,R25}}], R10;[7:7:{{0,1}}:8:0]
    STG.E desc[{{UR4,UR5}}][{{R24,R25}}+0x80], R246;[7:7:{{0,1}}:8:0]
    P2R R1, PR;[7:7:{{}}:4:0]
    STG.E desc[{{UR4,UR5}}][{{R24,R25}}+0x100], R1;[7:7:{{0,1}}:8:0]
    EXIT;{B}
}}
"""
SITE = 6

ok = True


def check(name, cond, extra=""):
    global ok
    if not cond:
        ok = False
    print(f"{'ok ' if cond else 'FAIL'} {name:<52} {extra}")


dbg = Debugger(SRC, max_warps=1)
out = dbg.mod.devmem_alloc(0x200)
dbg.mod.device_write(out, bytes(0x200))
dbg.launch([out], block=(32,))
dbg.wait_base()
bp = dbg.arm(SITE)
dbg.release()
hit = dbg.wait_hit()
check("parked at the site", hit is bp)

# E1: dump a plain register -------------------------------------------------
r = dbg.dump_regs(0, ["R10"])
check("E1 dump R10 magic", r["R10"] == 0xC0DE0001, hex(r["R10"]))

# E2: command rewrite — dump a DIFFERENT register next (same buffer VA) -----
r = dbg.dump_regs(0, ["R20", "R10"])
check("E2 rewritten command: R20=tid", r["R20"] < 32, hex(r["R20"]))
check("E2 rewritten command: R10 still magic", r["R10"] == 0xC0DE0001)

# E3: preserved state — the M9 handler borrows only R2-R7, so R246 is
# read LIVE (still the kernel's value); PR comes from the frame snapshot
r = dbg.dump_regs(0, ["R246", "PR"])
check("E3 dump R246 (live, handler never touched it)",
      r["R246"] == 0xBEEF246, hex(r["R246"]))
check("E3 dump PR via spill slot (P0 set, bit i -> Pi)",
      r["PR"] & 0x1 == 0x1, hex(r["PR"]))

# E5a: exec raw — probe SR_SMID ----------------------------------------------
# results window VA is per-warp; commands address it absolutely (there is
# no reserved blob-base register in M9 — {R2,R3} is a scratch pair here)
res = dbg.arena + dbg.lay.results
dbg.exec_cmd(0, [
    "S2R R4, SR_SMID;[4:7:{}:5:1]",
    f"MOV32I R2, 0x{res & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]",
    f"MOV32I R3, 0x{res >> 32:08x};[7:7:{{}}:5:1]",
    "STG.E.STRONG.GPU [{R2,R3}], R4;[7:7:{4}:8:0]",
])
smid = struct.unpack("<I", dbg.cmd_read(0, 0, 4))[0]
check("E5 exec: SR_SMID probe", 0 <= smid < 4096, hex(smid))

# E5b: guards ----------------------------------------------------------------
try:
    dbg.exec_cmd(0, ["MOV32I R0, 0x0;[7:7:{}:5:1]"])
    check("E5 guard: R0 (frame ptr) write rejected", False)
except ValueError:
    check("E5 guard: R0 (frame ptr) write rejected", True)
try:
    dbg.exec_cmd(0, ["BRA #label(x);[7:7:{}:6:0]"])
    check("E5 guard: control flow rejected", False)
except ValueError:
    check("E5 guard: control flow rejected", True)

# E4: set registers, resume, observe ------------------------------------------
dbg.set_reg(0, "R10", 0xDEAD0000)        # plain register
dbg.set_reg(0, "R246", 0xFEED0246)       # via spill slot
r = dbg.dump_regs(0, ["R10", "R246"])
check("E4 set then dump R10", r["R10"] == 0xDEAD0000, hex(r["R10"]))
check("E4 set then dump R246", r["R246"] == 0xFEED0246, hex(r["R246"]))

dbg.resume(bp)
dbg.wait_done()
v = struct.unpack("<128I", dbg.mod.device_read(out, 0x200))
lane0 = 0
check("E4 resumed kernel stored the SET R10",
      v[lane0] == 0xDEAD0000, hex(v[lane0]))
check("E4 resumed kernel stored the SET R246",
      v[0x80 // 4 + lane0] == 0xFEED0246, hex(v[0x80 // 4 + lane0]))
check("E4 resumed kernel PR observation has P0 (bit i -> Pi)",
      v[0x100 // 4 + lane0] & 0x1 == 0x1, hex(v[0x100 // 4 + lane0]))

print("\n=== sassdbg M7 command injection: ALL PASS ===" if ok
      else "\n=== FAILURES ===")
sys.exit(0 if ok else 1)
