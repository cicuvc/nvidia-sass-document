"""M11h release gate: source/CLI private defaults and legacy isolation.

Set SASSDBG_M11H_STRESS=1 for 168 divergent loop iterations (>1000 private
step transitions including WARPSYNC); the ordinary suite uses two iterations.
"""
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sassdbg.patch as patch_mod  # noqa: E402
from sassdbg.patch import Debugger, SharedDebugger  # noqa: E402
from sassdbg.private import PrivateKernel  # noqa: E402
from sassdbg.stepper import Stepper  # noqa: E402
from sassdbg.warpcode import CodeImageError  # noqa: E402

FAILS = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok ' if ok else 'FAIL'} {name}" +
          ("" if ok else f": {got!r} want {want!r}"))
    if not ok:
        FAILS.append(name)


# CPU-only selection gates: the default factory can be audited without a GPU.
orig_private = PrivateKernel.__dict__["from_source"]
orig_shared_init = SharedDebugger.__init__
try:
    seed = object.__new__(PrivateKernel)
    seed.marker = "private"
    PrivateKernel.from_source = classmethod(
        lambda cls, *a, **kw: seed)
    default = Debugger("unused")
    check("T0 Debugger source default selects PrivateKernel",
          (isinstance(default, PrivateKernel), default.marker),
          (True, "private"))

    SharedDebugger.__init__ = lambda self, *a, **kw: setattr(
        self, "marker", "shared")
    fallback = Debugger("unused", backend="shared")
    check("T0 shared engine requires explicit selection",
          (isinstance(fallback, SharedDebugger), fallback.marker),
          (True, "shared"))
finally:
    PrivateKernel.from_source = orig_private
    SharedDebugger.__init__ = orig_shared_init

iters = 168 if os.environ.get("SASSDBG_M11H_STRESS") == "1" else 2
SRC = f"""#fn k(out<8>) {{
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    S2R R2, SR_TID.X;[5:7:{{1}}:5:1]
    LOP3.LUT R2, R2, 0x1F, RZ, 0xC0;[7:7:{{5}}:5:1]
    MOV32I R10, 0x0;[7:7:{{}}:5:1]
#def_label(loop)
    ISETP.LT.AND P0, PT, R2, 0x10, PT;[7:7:{{}}:13:1]
    @P0 BRA #label(lower);[7:7:{{}}:6:0]
    MOV32I R3, 0xA0;[7:7:{{}}:5:1]
    BRA #label(join);[7:7:{{}}:6:0]
#def_label(lower)
    MOV32I R3, 0xB0;[7:7:{{}}:5:1]
#def_label(join)
    WARPSYNC.ALL;[7:7:{{}}:5:1]
    IADD3 R10, R10, 0x1, RZ;[7:7:{{}}:5:1]
    ISETP.LT.AND P1, PT, R10, 0x{iters:x}, PT;[7:7:{{}}:13:1]
    @P1 BRA #label(loop);[7:7:{{}}:6:0]
    IMAD.WIDE.U32 {{R6,R7}}, R2, 0x4, {{R4,R5}};[7:7:{{}}:5:1]
    STG.E.STRONG.GPU [{{R6,R7}}], R10;[7:7:{{}}:8:0]
    EXIT;[7:7:{{}}:5:0]
}}
"""

try:
    st = Stepper(SRC)
except RuntimeError as e:
    if "CUDA_ERROR_NO_DEVICE" in str(e):
        print("SKIP M11h GPU E2E: no CUDA device visible")
        if FAILS:
            sys.exit(1)
        sys.exit(0)
    raise

check("T1 Stepper default owns no legacy Patcher",
      (isinstance(st.dbg, PrivateKernel), hasattr(st.dbg, "patcher")),
      (True, False))
out = st.dbg.mod.devmem_alloc(128)
st.dbg.mod.device_write(out, bytes(128))
st.launch([out])
st.run_to_entry()
groups = st._parked
transitions = 0
while groups:
    groups = st.step_groups(groups)
    transitions += 1
    if transitions > iters * 20 + 32:
        raise RuntimeError("M11h stress step budget exhausted")
st.dbg.wait_done()
vals = struct.unpack("<32I", st.dbg.mod.device_read(out, 128))
check("T1 divergent WARPSYNC loop output",
      vals, (iters,) * 32)
check("T1 transition stress threshold",
      transitions >= (1000 if iters > 2 else 16), True)
print(f"  private step transitions: {transitions}")

# Unsupported source code fails closed; it does not instantiate Patcher or
# silently select the legacy backend.
bad = """#fn bad() {
    LEPC {R2,R3};[7:7:{}:4:0]
    EXIT;[7:7:{}:5:0]
}
"""
old_patcher = patch_mod.Patcher
patch_mod.Patcher = lambda: (_ for _ in ()).throw(
    AssertionError("default path constructed Patcher"))
try:
    try:
        Debugger(bad)
        msg = ""
    except CodeImageError as e:
        msg = str(e)
finally:
    patch_mod.Patcher = old_patcher
check("T2 unsupported source fails closed without shared fallback",
      "PC-sensitive LEPC" in msg, True)

# CLI source and trace modes also default private.  Scoped breakpoints are a
# direct observable: the shared CLI rejects `warp`/`mask` scope.
tmp = Path(tempfile.mkdtemp(prefix="sassdbg_m11h_")) / "loop.sass"
tmp.write_text(SRC)
root = Path(__file__).resolve().parents[2]
cli = subprocess.run(
    [sys.executable, "-m", "sassdbg.cli", "--sass", str(tmp)],
    input="b 9 warp 0 mask 0xffffffff\ninfo b\nr\nc\nq\n",
    capture_output=True, text=True, timeout=90, cwd=root)
if cli.returncode:
    print(cli.stdout); print(cli.stderr)
check("T3 CLI source defaults private",
      (cli.returncode, "w0:0xffffffff" in cli.stdout,
       "hit: warp 0 at inst 9:" in cli.stdout),
      (0, True, True))

trace = subprocess.run(
    [sys.executable, "-m", "sassdbg.cli", "--sass", str(tmp), "--trace"],
    input="b 10 warp 0 mask 0xffffffff\nr\nc\nback 0\nq\n",
    capture_output=True, text=True, timeout=90, cwd=root)
if trace.returncode:
    print(trace.stdout); print(trace.stderr)
check("T3 CLI trace composes with private default",
      (trace.returncode, "hit: warp 0 at inst 10:" in trace.stdout,
       "replay pc" in trace.stdout),
      (0, True, True))

if FAILS:
    print("=== M11h FAILURES:", ", ".join(FAILS), "===")
    sys.exit(1)
print(f"=== sassdbg M11h source default: ALL PASS ({transitions} transitions) ===")
