"""sassdbg M6 CLI smoke test: drive the REPL via stdin scripts.

  A: pure single-stepping through the sum5 loop (no user breakpoints),
     exact 26-step path
  B: user breakpoints (b 4 / b 8), run/continue hits, kernel completes
  C: --trace reverse: break at the final IADD3, inspect registers at the
     replay point, step backwards twice

Run: python3 tests/asm_construct/test_sassdbg_m6.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ok = True


def check(name, cond, extra=""):
    global ok
    if not cond:
        ok = False
    print(f"{'ok ' if cond else 'FAIL'} {name:<52} {extra}")


SUM5 = """\
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

CALC = """\
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

CLI = [sys.executable, "-m", "sassdbg.cli"]


def run_cli(script: str, *cli_args: str) -> str:
    r = subprocess.run(CLI + list(cli_args), input=script,
                       capture_output=True, text=True, timeout=300,
                       cwd=Path(__file__).resolve().parents[2])
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr[-2000:])
    return r.stdout


tmp = Path(tempfile.mkdtemp(prefix="sassdbg_m6"))
f_sum5 = tmp / "sum5.sass"
f_sum5.write_text(SUM5)
f_calc = tmp / "calc.sass"
f_calc.write_text(CALC)

# --- A: pure stepping -------------------------------------------------------
# 25 steps from inst 0: 0..3 then (4,5,6,7)x5 then 8,9(EXIT) -> exit
out = run_cli("r\n" + "s\n" * 26 + "p\nq\n",
              "--sass", str(f_sum5))
want_path = [0, 1, 2, 3] + [4, 5, 6, 7] * 5 + [8, 9]
check("A: 26-step path via CLI stepping",
      f"warp 0: {want_path}" in out, out[-400:] if ok else "")
check("A: warp exited", "warp 0: exited" in out)
check("A: parked at entry", "hit: warp 0 at inst 0:" in out)

# --- B: user breakpoints ----------------------------------------------------
out = run_cli("b 4\nb 8\nr\nc\nc\nc\nq\n",
              "--sass", str(f_sum5))
check("B: entry hit", "hit: warp 0 at inst 0:" in out)
check("B: bp at loop body hit", "hit: warp 0 at inst 4:" in out)
check("B: bp at STG hit (bp4 consumed after first resume)",
      "hit: warp 0 at inst 8:" in out)
check("B: kernel finished on final continue", "kernel finished" in out)

# --- C: --trace reverse -----------------------------------------------------
# auto-args zero-fill: a[]=0 -> R10=0, R11=1, R12=3, R13=3
out = run_cli("b 9\nr\nc\nregs 0 0 R12\nback\nback\nregs 0 0 R11\nq\n",
              "--sass", str(f_calc), "--trace")
check("C: bp hit at final IADD3", "hit: warp 0 at inst 9:" in out)
check("C: R12 == 3 at bp", "R12 = 0x3" in out)
check("C: first back -> pc 8 (IMAD)", "replay pc = 8" in out)
check("C: second back -> pc 7 (IADD3 R11)", "replay pc = 7" in out)
check("C: R11 == 1 two steps back", "R11 = 0x1" in out)

# --- D: M7 command injection (dump/set/exec on a parked warp) ---------------
out = run_cli("b 4\nr\nc\n"
              "dump 0 R2 R3\n"
              "dump 0 5 R2\n"                     # per-lane (uniform kernel)
              "set 0 R2 0x40\n"
              "dump 0 R2\n"
              "exec 0 IADD3 R2, R2, 0x1, RZ;[7:7:{}:5:1]\n"
              "dump 0 R2\n"
              "exec 0 BRA 0x0\n"                  # must be rejected
              "c\nq\n",
              "--sass", str(f_sum5))
check("D: dump parked regs (R2=0, R3=0 at first loop entry)",
      "w0 lane0 R2 = 0x0" in out and "w0 lane0 R3 = 0x0" in out)
check("D: per-lane dump (lane 5)", "w0 lane5 R2 = 0x0" in out)
check("D: set then dump", "w0 lane0 R2 = 0x40" in out)
check("D: exec IADD3 then dump", "w0 lane0 R2 = 0x41" in out)
check("D: control-flow exec rejected", "rejected:" in out)
check("D: kernel finished after continue", "kernel finished" in out)

print("\n=== sassdbg M6 CLI: ALL PASS ===" if ok else "\n=== FAILURES ===")
sys.exit(0 if ok else 1)
