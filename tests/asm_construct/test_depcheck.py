import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler.sass_parser import parse_kernel
from assembler.sass_matcher import create_matcher
from assembler.sass_depcheck import run_depcheck, extract_instr, build_cfg, InstrInfo
from assembler.operand import OperandKind

# ---------------------------------------------------------------------------
# Scoreboard dependency checker (assembler/sass_depcheck.py).
#
# Exercises the CFG checker: missing_req / missing_wr_sb / anti_dep /
# divergent_retarget, DEPBAR.LE partial-vs-full drains, predication, and
# control-flow (BRA / BSSY / BSYNC) paths.  Runs against the matcher only
# (no GPU); diagnostics come back from run_depcheck's return value.
# ---------------------------------------------------------------------------

DB = json.load(open(str(Path(__file__).resolve().parents[2] / "sm120.json")))
MATCHER = create_matcher()

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<52} {got}")


def codes(source):
    """Assemble a #fn kernel (resolving labels) and return diagnostic codes."""
    k = parse_kernel(source)
    addrs, labels, results = [], {}, []
    addr = 0
    for inst in k.instructions:
        if inst.mnemonic == "_label_":
            labels.setdefault(inst.label, addr)
        addrs.append(addr)
        if inst.mnemonic != "_label_":
            addr += 16
    for inst, ia in zip(k.instructions, addrs):
        if inst.mnemonic == "_label_":
            results.append(None)
            continue
        for op in inst.operands:
            if op.kind == OperandKind.LABEL:
                op.kind = OperandKind.IMM_S
                op.value = labels[op.value] - (ia + 16)
        results.append(MATCHER.match(inst))
    diags = run_depcheck(DB, k.instructions, results, addrs, kernel_name="k",
                         out=open("/dev/null", "w"))
    return [d.code for d in diags]


# --- 1. S2R without consumer req -------------------------------------------
check("S2R w/o req", codes("""#fn k(out<8>) {
S2R R0, SR_TID.X;[0:7:{}:5:1]
IADD3 R1, R0, R0, RZ;[7:7:{}:5:1]
}"""), ["missing_req"])
check("S2R with req", codes("""#fn k(out<8>) {
S2R R0, SR_TID.X;[0:7:{0}:5:1]
IADD3 R1, R0, R0, RZ;[7:7:{0}:5:1]
}"""), [])

# --- 2. LDG descriptor not waited ------------------------------------------
check("LDG w/o desc req", codes("""#fn k(out<8>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{}:8:1]
}"""), ["missing_req"])
check("LDG with desc req", codes("""#fn k(out<8>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{1}:8:1]
}"""), [])

# --- 3. LDG wr=7 consumed -> missing_wr_sb ---------------------------------
check("LDG wr=7 consumed", codes("""#fn k(out<8>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[7:7:{1}:8:1]
IADD3 R2, R8, RZ, RZ;[7:7:{}:5:1]
}"""), ["missing_wr_sb"])

# --- 4. predicated producer still needs req --------------------------------
check("@P1 S2R + no req", codes("""#fn k(out<8>) {
ISETP.GT.AND P1, PT, RZ, RZ, PT;[0:7:{}:5:1]
@P1 S2R R0, SR_TID.X;[0:7:{0}:5:1]
MOV R1, R0;[7:7:{}:5:1]
}"""), ["missing_req"])

# --- 5. shared tally: two LDGs, one consumer req -> clean ------------------
check("shared tally", codes("""#fn k(out<8>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{1}:8:1]
LDG.E R9, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{1}:8:1]
IADD3 R2, R8, RZ, RZ;[7:7:{0}:5:1]
IADD3 R3, R9, RZ, RZ;[7:7:{0}:5:1]
}"""), [])

# --- 6. DEPBAR.LE partial drain grants no coverage -------------------------
check("DEPBAR.LE cnt>0 partial", codes("""#fn k(out<8>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{1}:8:1]
DEPBAR.LE SB0, 0x1;[7:7:{}:5:1]
IADD3 R2, R8, RZ, RZ;[7:7:{}:5:1]
}"""), ["missing_req"])
check("DEPBAR.LE cnt=0 full", codes("""#fn k(out<8>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{1}:8:1]
DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]
IADD3 R2, R8, RZ, RZ;[7:7:{}:5:1]
}"""), [])

# --- 7. DEPBAR.LE with uniform threshold: no crash, no coverage ------------
check("DEPBAR.LE UR threshold", codes("""#fn k(out<8>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{1}:8:1]
DEPBAR.LE SB0, UR3;[7:7:{1}:5:1]
IADD3 R2, R8, RZ, RZ;[7:7:{}:5:1]
}"""), ["missing_req"])

# --- 8. control flow: predicated BRA, taken path missing req ---------------
check("BRA taken path w/o req", codes("""#fn k(out<8>) {
S2R R0, SR_TID.X;[0:7:{}:5:1]
ISETP.GT.AND P0, PT, RZ, 0x3f, PT;[0:7:{}:5:1]
@P0 BRA #label(taken);[7:7:{}:5:1]
IADD3 R1, R0, RZ, RZ;[7:7:{0}:5:1]
#def_label(taken)
MOV R2, R0;[7:7:{}:5:1]
}"""), ["missing_req"])
check("BRA both paths req", codes("""#fn k(out<8>) {
S2R R0, SR_TID.X;[0:7:{}:5:1]
ISETP.GT.AND P0, PT, RZ, 0x3f, PT;[0:7:{}:5:1]
@P0 BRA #label(taken);[7:7:{0}:5:1]
IADD3 R1, R0, RZ, RZ;[7:7:{0}:5:1]
#def_label(taken)
MOV R2, R0;[7:7:{0}:5:1]
}"""), [])

# --- 9. BSSY/BSYNC region: reads without req -------------------------------
check("BSSY/BSYNC region w/o req", codes("""#fn k(out<8>) {
S2R R0, SR_TID.X;[0:7:{}:5:1]
BSSY B0, #label(join);[7:7:{}:5:1]
MOV R1, R0;[7:7:{}:5:1]
BSYNC B0;[7:7:{}:5:1]
#def_label(join)
MOV R2, R0;[7:7:{}:5:1]
}"""), ["missing_req", "missing_req"])

# --- 10. anti-dependency: writer clobbers late-read register ---------------
check("anti_dep STG data", codes("""#fn k(out<8>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
MOV R3, RZ;[7:7:{}:5:1]
STG.E desc[{UR4,UR5}][{R0,R1}+0x0], R3;[0:1:{1}:1:0]
IADD3 R3, RZ, RZ, RZ;[7:7:{}:5:1]
}"""), ["anti_dep"])
check("anti_dep req'd", codes("""#fn k(out<8>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
MOV R3, RZ;[7:7:{}:5:1]
STG.E desc[{UR4,UR5}][{R0,R1}+0x0], R3;[0:1:{1}:1:0]
IADD3 R3, RZ, RZ, RZ;[7:7:{1}:5:1]
}"""), [])

# --- 11. address slots are early reads: rewriting address is fine ----------
check("addr rewrite no anti_dep", codes("""#fn k(out<8>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
MOV R0, RZ;[7:7:{}:5:1]
STG.E desc[{UR4,UR5}][{R0,R1}+0x0], R2;[0:1:{1}:1:0]
MOV R0, RZ;[7:7:{}:5:1]
}"""), [])

# --- 12. divergent retarget: predicated claim outstanding ------------------
check("divergent retarget", codes("""#fn k(out<8>) {
ISETP.GT.AND P1, PT, RZ, RZ, PT;[0:7:{}:5:1]
@P1 S2R R0, SR_TID.X;[0:7:{}:5:1]
MOV32I R3, 0x0;[7:7:{}:5:1]
MUFU.RCP R2, R3;[0:7:{}:8:1]
MOV R1, R3;[7:7:{}:5:1]
}"""), ["divergent_retarget"])


# --- 13. spec-driven block terminators (BB_ENDING_INST / BRANCH_TYPE) ------
# The CFG uses MEM_SCBD_TYPE==BB_ENDING_INST ∪ BRANCH_TYPE∈{BRT_RETURN,
# BRT_BRANCHOUT} instead of a hand-picked mnemonic list, so EXIT/RET/RTT/
# KILL/BPT terminate blocks with no successor, CALL keeps its return point,
# and BREAK jumps to the BSSY target without consuming the stack (BSYNC
# still needs it).
def cfg_succ(source):
    """Return (blocks, succ) from build_cfg for a #fn source."""
    k = parse_kernel(source)
    addrs, labels, results = [], {}, []
    addr = 0
    for inst in k.instructions:
        if inst.mnemonic == "_label_":
            labels.setdefault(inst.label, addr)
        addrs.append(addr)
        if inst.mnemonic != "_label_":
            addr += 16
    insts, infos = [], []
    for inst, ia in zip(k.instructions, addrs):
        insts.append(inst)
        if inst.mnemonic == "_label_":
            infos.append(None)
            continue
        for op in inst.operands:
            if op.kind == OperandKind.LABEL:
                op.kind = OperandKind.IMM_S
                op.value = labels[op.value] - (ia + 16)
        infos.append(extract_instr(inst, MATCHER.match(inst), DB))
    blocks, succ, _ = build_cfg(insts, infos, addrs)
    return blocks, succ


# EXIT terminates: no successor edge (code after EXIT is not reachable)
b, s = cfg_succ("""#fn k() {
EXIT;[7:7:{}:5:0]
MOV R0, R1;[7:7:{}:5:1]
}""")
check("EXIT has no successor", s, [[]])

# RET/RTT terminate (BRANCH_TYPE=BRT_RETURN) — RET's matcher needs a
# const-bank address operand, so exercise build_cfg with a synthetic RTT.
class _FakeInst:
    def __init__(self, mn):
        self.mnemonic = mn
        self.pred = None
        self.operands = []

_fi = [_FakeInst("MOV"), _FakeInst("RTT")]
_f0 = InstrInfo(idx=0, mnemonic="MOV", cls=1)
_f1 = InstrInfo(idx=1, mnemonic="RTT", cls=1)
_f1.branch_type = "BRT_RETURN"
_f1.mem_scbd_type = "BARRIER_INST"     # RTT is BRT_RETURN but not BB_ENDING
_, _s, _ = build_cfg(_fi, [_f0, _f1], [0, 16])
check("BRT_RETURN (RTT) has no successor", _s, [[]])

# BSSY/BREAK/BSYNC: BREAK peeks the BSSY target, BSYNC still resolves it
b, s = cfg_succ("""#fn k() {
BSSY B0, #label(join);[7:7:{}:5:1]
@P0 BREAK B0;[7:7:{}:5:1]
NOP;[7:7:{}:5:1]
BSYNC B0;[7:7:{}:5:1]
#def_label(join)
MOV R0, R1;[7:7:{}:5:1]
}""")
# blocks: [BSSY], [BREAK,NOP,BSYNC], [MOV]; block1's terminal BSYNC -> join block
check("BREAK keeps BSSY target for BSYNC", s, [[1], [2], []])

# CALL keeps its return point as successor
b, s = cfg_succ("""#fn k() {
CALL #label(foo);[7:7:{}:5:1]
MOV R0, R1;[7:7:{}:5:1]
EXIT;[7:7:{}:5:0]
#def_label(foo)
EXIT;[7:7:{}:5:0]
}""")
check("CALL return-point successor", s, [[1], [], []])

print(f"\n=== depcheck: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
