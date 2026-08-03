import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler.sass_parser import parse_kernel
from assembler.sass_matcher import create_matcher
from assembler.sass_depcheck import run_depcheck, extract_instr, build_cfg
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
check("S2R w/o req", codes("""#fn k(out<128>) {
S2R R0, SR_TID.X;[0:7:{}:5:1]
IADD3 R1, R0, R0, RZ;[7:7:{}:5:1]
}"""), ["missing_req"])
check("S2R with req", codes("""#fn k(out<128>) {
S2R R0, SR_TID.X;[0:7:{0}:5:1]
IADD3 R1, R0, R0, RZ;[7:7:{0}:5:1]
}"""), [])

# --- 2. LDG descriptor not waited ------------------------------------------
check("LDG w/o desc req", codes("""#fn k(out<128>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{}:8:1]
}"""), ["missing_req"])
check("LDG with desc req", codes("""#fn k(out<128>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{1}:8:1]
}"""), [])

# --- 3. LDG wr=7 consumed -> missing_wr_sb ---------------------------------
check("LDG wr=7 consumed", codes("""#fn k(out<128>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[7:7:{1}:8:1]
IADD3 R2, R8, RZ, RZ;[7:7:{}:5:1]
}"""), ["missing_wr_sb"])

# --- 4. predicated producer still needs req --------------------------------
check("@P1 S2R + no req", codes("""#fn k(out<128>) {
ISETP.GT.AND P1, PT, RZ, RZ, PT;[0:7:{}:5:1]
@P1 S2R R0, SR_TID.X;[0:7:{0}:5:1]
MOV R1, R0;[7:7:{}:5:1]
}"""), ["missing_req"])

# --- 5. shared tally: two LDGs, one consumer req -> clean ------------------
check("shared tally", codes("""#fn k(out<128>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{1}:8:1]
LDG.E R9, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{1}:8:1]
IADD3 R2, R8, RZ, RZ;[7:7:{0}:5:1]
IADD3 R3, R9, RZ, RZ;[7:7:{0}:5:1]
}"""), [])

# --- 6. DEPBAR.LE partial drain grants no coverage -------------------------
check("DEPBAR.LE cnt>0 partial", codes("""#fn k(out<128>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{1}:8:1]
DEPBAR.LE SB0, 0x1;[7:7:{}:5:1]
IADD3 R2, R8, RZ, RZ;[7:7:{}:5:1]
}"""), ["missing_req"])
check("DEPBAR.LE cnt=0 full", codes("""#fn k(out<128>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{1}:8:1]
DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]
IADD3 R2, R8, RZ, RZ;[7:7:{}:5:1]
}"""), [])

# --- 7. DEPBAR.LE with uniform threshold: no crash, no coverage ------------
check("DEPBAR.LE UR threshold", codes("""#fn k(out<128>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
LDG.E R8, desc[{UR4,UR5}][{R0,R1}+0x0];[0:7:{1}:8:1]
DEPBAR.LE SB0, UR3;[7:7:{1}:5:1]
IADD3 R2, R8, RZ, RZ;[7:7:{}:5:1]
}"""), ["missing_req"])

# --- 8. control flow: predicated BRA, taken path missing req ---------------
check("BRA taken path w/o req", codes("""#fn k(out<128>) {
S2R R0, SR_TID.X;[0:7:{}:5:1]
ISETP.GT.AND P0, PT, RZ, 0x3f, PT;[0:7:{}:5:1]
@P0 BRA #label(taken);[7:7:{}:5:1]
IADD3 R1, R0, RZ, RZ;[7:7:{0}:5:1]
#def_label(taken)
MOV R2, R0;[7:7:{}:5:1]
}"""), ["missing_req"])
check("BRA both paths req", codes("""#fn k(out<128>) {
S2R R0, SR_TID.X;[0:7:{}:5:1]
ISETP.GT.AND P0, PT, RZ, 0x3f, PT;[0:7:{}:5:1]
@P0 BRA #label(taken);[7:7:{0}:5:1]
IADD3 R1, R0, RZ, RZ;[7:7:{0}:5:1]
#def_label(taken)
MOV R2, R0;[7:7:{0}:5:1]
}"""), [])

# --- 9. BSSY/BSYNC region: reads without req -------------------------------
check("BSSY/BSYNC region w/o req", codes("""#fn k(out<128>) {
S2R R0, SR_TID.X;[0:7:{}:5:1]
BSSY B0, #label(join);[7:7:{}:5:1]
MOV R1, R0;[7:7:{}:5:1]
BSYNC B0;[7:7:{}:5:1]
#def_label(join)
MOV R2, R0;[7:7:{}:5:1]
}"""), ["missing_req", "missing_req"])

# --- 10. anti-dependency: writer clobbers late-read register ---------------
check("anti_dep STG data", codes("""#fn k(out<128>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
MOV R3, RZ;[7:7:{}:5:1]
STG.E desc[{UR4,UR5}][{R0,R1}+0x0], R3;[0:1:{1}:1:0]
IADD3 R3, RZ, RZ, RZ;[7:7:{}:5:1]
}"""), ["anti_dep"])
check("anti_dep req'd", codes("""#fn k(out<128>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
MOV R3, RZ;[7:7:{}:5:1]
STG.E desc[{UR4,UR5}][{R0,R1}+0x0], R3;[0:1:{1}:1:0]
IADD3 R3, RZ, RZ, RZ;[7:7:{1}:5:1]
}"""), [])

# --- 11. address slots are early reads: rewriting address is fine ----------
check("addr rewrite no anti_dep", codes("""#fn k(out<128>) {
LDCU.64 {UR4,UR5}, #param(out);[1:7:{}:2:0]
MOV R0, RZ;[7:7:{}:5:1]
STG.E desc[{UR4,UR5}][{R0,R1}+0x0], R2;[0:1:{1}:1:0]
MOV R0, RZ;[7:7:{}:5:1]
}"""), [])

# --- 12. divergent retarget: predicated claim outstanding ------------------
check("divergent retarget", codes("""#fn k(out<128>) {
ISETP.GT.AND P1, PT, RZ, RZ, PT;[0:7:{}:5:1]
@P1 S2R R0, SR_TID.X;[0:7:{}:5:1]
MOV32I R3, 0x0;[7:7:{}:5:1]
MUFU.RCP R2, R3;[0:7:{}:8:1]
MOV R1, R3;[7:7:{}:5:1]
}"""), ["divergent_retarget"])

print(f"\n=== depcheck: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
