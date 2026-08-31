"""M11f GPU E2E: masked commands on divergent private execution groups."""
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sassdbg.private import PrivateKernel, ScopeError  # noqa: E402


SRC = """#fn k(out<8>) {
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    S2R R2, SR_TID.X;[5:7:{1}:5:1]
    LOP3.LUT R3, R2, 0x1F, RZ, 0xC0;[7:7:{5}:5:1]
    ISETP.LT.AND P0, PT, R3, 0x10, PT;[7:7:{}:13:1]
    @P0 BRA #label(lower);[7:7:{}:6:0]
    MOV32I R10, 0xA0;[7:7:{}:5:1]
    NOP;[7:7:{}:8:0]
    BRA #label(join);[7:7:{}:6:0]
#def_label(lower)
    MOV32I R10, 0xB0;[7:7:{}:5:1]
    NOP;[7:7:{}:8:0]
#def_label(join)
    IMAD.WIDE.U32 {R6,R7}, R2, 0x4, {R4,R5};[7:7:{}:5:1]
    STG.E.STRONG.GPU [{R6,R7}], R10;[7:7:{}:8:0]
    EXIT;[7:7:{}:5:0]
}
"""

FAILS = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok ' if ok else 'FAIL'} {name}" +
          ("" if ok else f": {got!r} want {want!r}"))
    if not ok:
        FAILS.append(name)


try:
    k = PrivateKernel.from_source(SRC, max_warps=2, max_bps=8)
except RuntimeError as e:
    if "CUDA_ERROR_NO_DEVICE" in str(e):
        print("SKIP M11f GPU E2E: no CUDA device visible")
        sys.exit(0)
    raise

out = k.mod.devmem_alloc(256)
k.mod.device_write(out, bytes(256))
upper = k.arm(6)
lower = k.arm(9)
k.launch([out], block=(64,))
k.wait_ready()
k.release()

# Collect both divergent groups of both warps.  The first report is tight;
# cooperative mode is explicit and lets its sibling publish another slot.
hits = {0: [], 1: []}
while sum(map(len, hits.values())) < 4:
    h = k.wait_hit()
    hits[h.warp].append(h)
    if len(hits[h.warp]) == 1:
        k.cooperate(h.warp)
for w in (0, 1):
    k.freeze(w)
check("T0 two divergent groups per warp",
      [{h.bp.orig_index for h in hits[w]} for w in (0, 1)],
      [{6, 9}, {6, 9}])

check("T1 dump lower and upper live registers",
      (k.dump_regs(0, ["R10"], lane=5)["R10"],
       k.dump_regs(0, ["R10"], lane=20)["R10"]),
      (0xB0, 0xA0))

# Three rewritten command images and disjoint masks.  Per-lane generations
# ensure lane 5 cannot replay lane 20's later command.
k.set_reg(0, "R10", 0xDEAD0000, lane=5)
k.exec_cmd(0, ["IADD3 R10, R10, 0x1, RZ;[7:7:{}:5:1]"],
           lane_mask=1 << 5)
k.set_reg(0, "R10", 0xFEED0000, lane=20)
check("T2 masked rewrite has no stale cross-lane replay",
      (k.dump_regs(0, ["R10"], lane=5)["R10"],
       k.dump_regs(0, ["R10"], lane=20)["R10"]),
      (0xDEAD0001, 0xFEED0000))

# Frame-backed low registers and command validation remain available.
r = k.dump_regs(0, ["R0", "R2", "PR"], lane=5)
check("T3 frame-backed dump returns architectural values",
      (r["R2"], bool(r["PR"] & 1)), (5, True))
try:
    k.exec_cmd(0, ["MOV32I R0, 0;[7:7:{}:5:1]"])
    check("T3 R0 frame-pointer guard", False, True)
except ValueError:
    check("T3 R0 frame-pointer guard", True, True)
try:
    k.exec_cmd(0, ["BRA 0x0;[7:7:{}:6:0]"])
    check("T3 control-flow guard", False, True)
except ValueError:
    check("T3 control-flow guard", True, True)
try:
    k.exec_cmd(0, ["NOP;[7:7:{}:8:0]"], lane_mask=0)
    check("T3 nonparked command mask rejected", False, True)
except ScopeError:
    check("T3 nonparked command mask rejected", True, True)

k.disarm(upper)
k.disarm(lower)
for w in (0, 1):
    k.resume_hit(hits[w][0])
k.wait_done()
vals = struct.unpack("<64I", k.mod.device_read(out, 256))
want = [0xB0 if lane < 16 else 0xA0 for lane in range(32)] * 2
want[5] = 0xDEAD0001
want[20] = 0xFEED0000
check("T4 resumed output reflects only selected warp/lane writes",
      list(vals), want)

# CLI exposes private breakpoint scope and routes live inspection through the
# per-lane command generations rather than the legacy shared handler.
tmp = Path(tempfile.mkdtemp(prefix="sassdbg_m11f_")) / "groups.sass"
tmp.write_text(SRC)
proc = subprocess.run(
    [sys.executable, "-m", "sassdbg.cli", "--sass", str(tmp),
     "--backend", "warp_private", "--block", "64", "--max-warps", "2"],
    input=("b 6 warp 0 mask 0xffff0000\ninfo b\nr\nc\n"
           "dump 0 20 R10\nset 0 20 R10 0xcafe\ndump 0 20 R10\nq\n"),
    capture_output=True, text=True, timeout=60,
    cwd=Path(__file__).resolve().parents[2])
if proc.returncode:
    print(proc.stdout)
    print(proc.stderr)
check("T5 CLI private scope and per-lane dump/set",
      (proc.returncode, "w0:0xffff0000" in proc.stdout,
       "hit: warp 0 at inst 6:" in proc.stdout,
       "w0 lane20 R10 = 0xa0" in proc.stdout,
       "w0 lane20 R10 = 0xcafe" in proc.stdout),
      (0, True, True, True, True))

if FAILS:
    print("=== M11f FAILURES:", ", ".join(FAILS), "===")
    sys.exit(1)
print("=== sassdbg M11f masked command injection: ALL PASS ===")
