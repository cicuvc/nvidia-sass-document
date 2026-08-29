"""sassdbg M5w: multi-warp source-level single-stepping (Stepper over
M3v3 per-warp breakpoints).

Two warps run a warp-uniform divergent if/else.  step_all() advances
every parked warp one instruction at a time; per-warp paths must show
the divergence and the join, and the kernel's per-warp outputs must be
correct after stepping to completion.

Run: python3 tests/asm_construct/test_sassdbg_m5w.py
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sassdbg.stepper import Stepper          # noqa: E402

# inst indices (labels excluded):
#   0 LDCU  1 LDC  2 S2R  3 SHF(warpid)  4 ISETP(P0=warp0)  5 @!P0 BRA w1
#   6 MOV32I 0x10   7 IADD3 +1   8 BRA join          (warp0 path)
#   9 MOV32I 0x20  10 IADD3 +2  11 IADD3 +4          (warp1 path)
#  12 IMAD.WIDE  13 STG.64  14 EXIT                 (join)
SRC = """#fn k(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    S2R R20, SR_TID.X;[5:7:{}:5:1]
    SHF.R.U32.HI R21, RZ, 0x5, R20;[7:7:{5}:5:1]
    ISETP.EQ.AND P0, PT, R21, 0x0, PT;[7:7:{}:13:1]
    @!P0 BRA #label(w1);[7:7:{}:6:0]
    MOV32I R10, 0x10;[7:7:{}:5:1]
    IADD3 R11, R10, 0x1, RZ;[7:7:{}:5:1]
    BRA #label(join);[7:7:{}:6:0]
#def_label(w1)
    MOV32I R10, 0x20;[7:7:{}:5:1]
    IADD3 R11, R10, 0x2, RZ;[7:7:{}:5:1]
    IADD3 R11, R11, 0x4, RZ;[7:7:{}:5:1]
#def_label(join)
    IMAD.WIDE.U32 {R24,R25}, R21, 0x8, {R4,R5};[7:7:{1}:13:1]
    STG.E.64 desc[{UR4,UR5}][{R24,R25}], {R10,R11};[7:7:{0,1}:8:0]
    EXIT;[7:7:{}:4:0]
}
"""

WANT_PATH0 = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14]
WANT_PATH1 = [0, 1, 2, 3, 4, 5, 9, 10, 11, 12, 13, 14]

ok = True


def check(name, cond, extra=""):
    global ok
    if not cond:
        ok = False
    print(f"{'ok ' if cond else 'FAIL'} {name:<52} {extra}")


st = Stepper(SRC, max_warps=2)
out = st.dbg.mod.devmem_alloc(64)
st.dbg.mod.device_write(out, bytes(64))

st.launch([out], block=(64,))
state = st.run_to_entry_all()
check("both warps parked at entry", set(state) == {0, 1}
      and all(bp.orig_index == 0 for bp in state.values()),
      str({w: bp.orig_index for w, bp in state.items()}))

# step in lockstep to the divergent branch, then one step past it
for _ in range(5):
    state = st.step_all(state)
check("lockstep to the branch",
      {w: bp.orig_index for w, bp in state.items()} == {0: 5, 1: 5},
      str({w: bp.orig_index for w, bp in state.items()}))
state = st.step_all(state)
got = {w: bp.orig_index for w, bp in state.items()}
check("warps diverged to their own bodies", got == {0: 6, 1: 9}, str(got))

st.run_all(state)

check("warp0 path", st.paths[0] == WANT_PATH0, str(st.paths[0]))
check("warp1 path", st.paths[1] == WANT_PATH1, str(st.paths[1]))

v = struct.unpack("<8I", st.dbg.mod.device_read(out, 32))
check("warp0 result", v[0:2] == (0x10, 0x11), str(tuple(hex(x) for x in v[:2])))
check("warp1 result", v[2:4] == (0x20, 0x26), str(tuple(hex(x) for x in v[2:4])))

print("\n=== sassdbg M5w multi-warp stepper: ALL PASS ===" if ok
      else "\n=== FAILURES ===")
sys.exit(0 if ok else 1)
