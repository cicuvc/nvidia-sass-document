"""M5 — single-stepping (Stepper) + reverse-from-breakpoint (wtrace+M3).

Test 1: step a 5-iteration accumulation loop instruction by instruction.
    The expected path (original-source instruction indices) is fully
    static: 0,1,2,3 then (4,5,6,7) x5 then 8,9.  Each step arms the
    parked instruction's static successor set and the hit tells which
    path was taken (the loop-back @P0 BRA is the interesting case).

Test 2: compose wtrace (M4) with the debugger (M3): break in the middle
    of a traced kernel, reconstruct the full architectural state at the
    breakpoint from the trace (forward replay), then step BACKWARDS to
    the state before the previous instruction — reverse execution driven
    by a breakpoint hit.  Resume afterwards and verify the kernel still
    produces the correct result.

Also covers: the wtrace<->debugger register composition (R224-R245 vs
R246-R253 disjoint, UR60/61 shared as the default cdesc — requires
inject_debugger(allow_cdesc_urs=True)).
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule                      # noqa: E402
from sassdbg.stepper import Stepper, Cfg              # noqa: E402
from sassdbg.patch import Debugger                    # noqa: E402
from sassdbg.wtrace import instrument_warp, REGION_BYTES  # noqa: E402
from sassdbg.reverse import WarpReplay                # noqa: E402
from assembler.sass_parser import Lexer, Parser       # noqa: E402

ok = True


def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name}: {got!r}"
          f"{'' if good else f'  (want {want!r})'}")


# ===========================================================================
# 1. single-step a loop
# ===========================================================================
# idx: 0 LDCU / 1 LDC / 2 acc=0 / 3 i=0 / 4 acc+=i / 5 i++ /
#      6 ISETP / 7 @P0 BRA loop / 8 STG / 9 EXIT
LOOP_KERNEL = """\
#fn sum5(out<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    MOV32I R2, 0x0;[7:7:{0,1}:5:1]
    MOV32I R3, 0x0;[7:7:{}:5:1]
    #def_label(loop)
    IADD3 R2, R2, R3, RZ;[7:7:{}:5:1]
    IADD3 R3, R3, 0x1, RZ;[7:7:{}:5:1]
    ISETP.LT.AND P0, PT, R3, 0x5, PT;[7:7:{}:13:1]
    @P0 BRA #label(loop);[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R4,R5}], R2;[0:1:{}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""

# CFG sanity
cfg = Cfg(LOOP_KERNEL)
check("cfg: predicated BRA successors", cfg.next_pcs(7), [8, 4])
check("cfg: plain fall-through", cfg.next_pcs(4), [5])
check("cfg: EXIT terminal", cfg.next_pcs(9), [])

st = Stepper(LOOP_KERNEL)
d = st.dbg.mod.devmem_alloc(64)
st.launch([d], block=(32,))
bp = st.run_to_entry()
while bp is not None:
    bp = st.step(bp)
st.dbg.wait_done()

expected_path = [0, 1, 2, 3] + [4, 5, 6, 7] * 5 + [8, 9]
check("step path through 5-iteration loop", st.path, expected_path)
acc = struct.unpack("<I", st.dbg.mod.device_read(d, 4))[0]
check("loop result (0+1+2+3+4)", acc, 10)
st.dbg.mod.devmem_free(d)

# ===========================================================================
# 2. reverse from a breakpoint hit (wtrace + debugger composition)
# ===========================================================================
# R13 = (a[tid]+1)*3 + a[tid];  bp sits on the final IADD3
CALC_KERNEL = """\
#fn calc(a<8>, b<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(a);[1:7:{}:8:0]
    LDC.64 {R6,R7}, #param(b);[2:7:{}:1:0]
    S2R R2, SR_TID.X;[0:7:{}:5:1]
    IMAD.WIDE.U32 {R8,R9}, R2, 0x4, {R4,R5};[7:7:{0,1}:5:1]
    IMAD.WIDE.U32 {R14,R15}, R2, 0x4, {R6,R7};[7:7:{0,2}:5:1]
    LDG.E R10, desc[{UR4,UR5}][{R8,R9}];[3:7:{}:1:0]
    IADD3 R11, R10, 0x1, RZ;[7:7:{3}:5:1]
    IMAD R12, R11, 0x3, RZ;[7:7:{}:5:1]
    IADD3 R13, R12, R10, RZ;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R14,R15}], R13;[0:1:{}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""
A2 = [0x100 + 3 * t for t in range(32)]


def want2(t):
    return ((A2[t] + 1) * 3 + A2[t]) & 0xFFFFFFFF


ik = instrument_warp(CALC_KERNEL)
dbg = Debugger(ik.source, max_bps=8, allow_cdesc_urs=True)

# locate the final IADD3 (bp target) in the WTRACE-source numbering
decl = Parser(Lexer(ik.source).tokenize()).parse_kernel()
bp_idx = None
widx = 0
for inst in decl.instructions:
    if inst.mnemonic == "_label_":
        continue
    if inst.mnemonic == "IADD3" and any(
            op.kind.name == "REG" and op.value == 13
            for op in inst.operands[:1]):
        bp_idx = widx
    widx += 1
assert bp_idx is not None
# the original-kernel step index of that instruction (for replay checks)
orig_step = next(s.idx for s in ik.steps if "IADD3 R13" in s.text)

a_dev = dbg.mod.devmem_alloc(256)
b_dev = dbg.mod.devmem_alloc(256)
trace = dbg.mod.devmem_alloc(REGION_BYTES)
dbg.mod.device_write(a_dev, struct.pack("<32I", *A2))
dbg.mod.device_write(trace, bytes(REGION_BYTES))

dbg.launch([a_dev, b_dev, trace], block=(32,))
dbg.wait_base()
bp = dbg.arm(bp_idx)
dbg.release()
hit = dbg.wait_hit()
check("breakpoint hit at final IADD3", hit.orig_index, bp_idx)

rp = WarpReplay(ik.sidecar(), bytes(dbg.mod.device_read(trace,
                                                       REGION_BYTES)))
st2 = rp.replay()
# state at the breakpoint = BEFORE the bp instruction executed
check("replay pc == bp step", st2.pc, orig_step)
check("R12 at bp == (a+1)*3", tuple(st2.reg(t, 12) for t in range(32)),
      tuple(((A2[t] + 1) * 3) & 0xFFFFFFFF for t in range(32)))
check("R13 not yet written at bp",
      all(13 not in st2.regs[t] for t in range(32)), True)
check("no b stores in trace at bp", len(st2.mem), 0)

# reverse: one step back -> pc moves to the IMAD step, whose effects are
# still applied (pc=N semantics: frames 0..N applied, matching M4);
# the bp instruction's own (never-executed) write is what disappeared
rp.step_back(st2)
check("step_back pc == IMAD step", st2.pc, orig_step - 1)
check("R12 still applied at IMAD step",
      tuple(st2.reg(t, 12) for t in range(32)),
      tuple(((A2[t] + 1) * 3) & 0xFFFFFFFF for t in range(32)))
check("R13 (bp instruction) absent",
      all(13 not in st2.regs[t] for t in range(32)), True)
# second step back -> IMAD's write pops off too
rp.step_back(st2)
check("2nd step_back pc == IADD3-R11 step", st2.pc, orig_step - 2)
check("R11 applied", tuple(st2.reg(t, 11) for t in range(32)),
      tuple(A2[t] + 1 for t in range(32)))
check("R12 gone after undoing the IMAD",
      all(12 not in st2.regs[t] for t in range(32)), True)
# third -> before the first IADD3: R10 = raw a[tid], R11 gone
rp.step_back(st2)
check("R10 three steps back == a[tid]",
      tuple(st2.reg(t, 10) for t in range(32)), tuple(A2))
check("R11 gone three steps back",
      all(11 not in st2.regs[t] for t in range(32)), True)

# resume: kernel completes with correct results
dbg.resume(hit)
dbg.wait_done()
bvals = struct.unpack("<32I", dbg.mod.device_read(b_dev, 128))
check("kernel result after resume", bvals,
      tuple(want2(t) for t in range(32)))

dbg.mod.devmem_free(a_dev)
dbg.mod.devmem_free(b_dev)
dbg.mod.devmem_free(trace)

print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
