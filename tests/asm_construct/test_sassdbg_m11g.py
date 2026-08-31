"""M11g GPU E2E: real cubins default to warp-private heap code."""
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble  # noqa: E402
from sassdbg.cubin import _sections, SHT_SYMTAB, STT_FUNC  # noqa: E402
from sassdbg.private import PrivateKernel  # noqa: E402
from sassdbg.real import CubinDebugger, SharedCubinDebugger  # noqa: E402
from sassdbg.stepper import Stepper  # noqa: E402
from sassdbg.warpcode import CodeImageError  # noqa: E402

CUBIN = str(Path(__file__).resolve().parents[1] / "m2_smoke.cubin")
N = 64
FFMA = 12
FAILS = []


def check(name, got, want):
    ok = got == want
    print(f"{'ok ' if ok else 'FAIL'} {name}" +
          ("" if ok else f": {got!r} want {want!r}"))
    if not ok:
        FAILS.append(name)


try:
    dbg = CubinDebugger(CUBIN, max_warps=2)
except RuntimeError as e:
    if "CUDA_ERROR_NO_DEVICE" in str(e):
        print("SKIP M11g GPU E2E: no CUDA device visible")
        sys.exit(0)
    raise
check("T0 CubinDebugger defaults to PrivateKernel",
      isinstance(dbg, PrivateKernel), True)

a = dbg.mod.devmem_alloc(N * 4)
b = dbg.mod.devmem_alloc(N * 4)
dbg.mod.device_write(a, b"".join(struct.pack("<f", float(i + 1))
                                  for i in range(N)))

# Bare real-cubin launch.
dbg.mod.device_write(b, bytes(N * 4))
dbg.launch([a, b, N], block=(64,))
dbg.wait_ready()
dbg.release()
dbg.wait_done()
out = struct.unpack(f"<{N}f", dbg.mod.device_read(b, N * 4))
check("T0 real cubin output",
      all(abs(out[i] - ((i + 1) * 2.0 + 1.0)) < 1e-6
          for i in range(N)), True)

# Entry word 0 and a body breakpoint live only in each warp's heap copy.
bp0 = dbg.arm(0)
bpf = dbg.arm(FFMA)
dbg.mod.device_write(b, bytes(N * 4))
dbg.launch([a, b, N], block=(N,))
dbg.wait_ready()
dbg.release()
entry = [dbg.wait_hit() for _ in range(2)]
check("T1 real-cubin entry-0 breakpoint hits both private warps",
      {h.warp for h in entry}, {0, 1})
dbg.disarm(bp0)
for h in entry:
    dbg.resume_hit(h)
ffma = [dbg.wait_hit() for _ in range(2)]
check("T1 FFMA breakpoint hits both private warps",
      {h.warp for h in ffma}, {0, 1})
picked = ffma[0]
bits = dbg.dump_regs(picked.warp, ["R2"], lane=5)["R2"]
got = struct.unpack("<f", struct.pack("<I", bits))[0]
check("T1 frame-backed register dump", got,
      float(picked.warp * 32 + 6))
dbg.set_reg(picked.warp, "R2",
            struct.unpack("<I", struct.pack("<f", 100.0))[0], lane=0)
for h in ffma:
    dbg.resume_hit(h)
dbg.wait_done()
out = struct.unpack(f"<{N}f", dbg.mod.device_read(b, N * 4))
check("T1 resumed body reflects selected register write",
      out[picked.warp * 32], 201.0)

# The body breakpoint is persistent across a canonical relaunch.
dbg.mod.device_write(b, bytes(N * 4))
dbg.launch([a, b, N], block=(N,))
dbg.wait_ready()
dbg.release()
again = [dbg.wait_hit() for _ in range(2)]
check("T2 persistent private binding survives relaunch",
      ({h.warp for h in again}, {h.bp.orig_index for h in again}),
      ({0, 1}, {FFMA}))
dbg.disarm(bpf)
for h in again:
    dbg.resume_hit(h)
dbg.wait_done()

# Stepper consumes the lifted CFG while execution stays in private copies.
dbg2 = CubinDebugger(CUBIN, max_warps=1)
a2 = dbg2.mod.devmem_alloc(32 * 4)
b2 = dbg2.mod.devmem_alloc(32 * 4)
dbg2.mod.device_write(a2, b"".join(struct.pack("<f", float(i + 1))
                                    for i in range(32)))
dbg2.mod.device_write(b2, bytes(32 * 4))
st = Stepper(dbg2.source, dbg=dbg2)
st.launch([a2, b2, 32], block=(32,))
bp = st.run_to_entry()
for _ in range(4):
    bp = st.step(bp)
check("T3 private real-cubin stepper lifted path", st.path,
      [0, 1, 2, 3, 4])
bp = st.step(bp)
check("T3 step over terminal exits", bp, None)
dbg2.wait_done()

# Outputs defined by the first two original instructions survive because the
# private copy executes them in place; no M10 replay-return scratch exists.
entry_src = """#fn k(out<8>) {
    MOV32I R4, 0x12345678;[7:7:{}:5:1]
    MOV32I R5, 0x23456789;[7:7:{}:5:1]
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R10,R11}, #param(out);[1:7:{}:8:0]
    STG.E desc[{UR4,UR5}][{R10,R11}], R4;[7:7:{0,1}:8:0]
    STG.E desc[{UR4,UR5}][{R10,R11}+0x4], R5;[7:7:{}:8:0]
    EXIT;[7:7:{}:5:0]
}
"""
with tempfile.NamedTemporaryFile(suffix=".cubin") as f:
    f.write(assemble(entry_src)); f.flush()
    d3 = CubinDebugger(f.name)
    out3 = d3.mod.devmem_alloc(8)
    d3.mod.device_write(out3, bytes(8))
    d3.launch([out3], block=(1,))
    d3.wait_ready(); d3.release(); d3.wait_done()
    got3 = struct.unpack("<II", d3.mod.device_read(out3, 8))
check("T4 entry outputs survive private dispatch",
      got3, (0x12345678, 0x23456789))

# ELF symbols may begin inside a shared text section.  The private template,
# lifted CFG, and trampoline patch must all use entry+size rather than treating
# symbol.size as a section-relative end offset.
raw = bytearray(assemble(entry_src))
secs = _sections(raw)
symtab = next(s for s in secs if s.typ == SHT_SYMTAB)
strtab = secs[symtab.link]
for j in range(symtab.size // symtab.entsize):
    pos = symtab.off + j * symtab.entsize
    st_name, st_info, _other, _shndx, st_value, st_size = \
        struct.unpack_from("<IBBHQQ", raw, pos)
    end = raw.index(0, strtab.off + st_name)
    name = raw[strtab.off + st_name:end].decode()
    if name in ("k", "_Z1k") and (st_info & 0xF) == STT_FUNC:
        struct.pack_into("<Q", raw, pos + 8, st_value + 16)
        struct.pack_into("<Q", raw, pos + 16, st_size - 16)
        break
else:
    raise AssertionError("test fixture has no FUNC k")
with tempfile.NamedTemporaryFile(suffix=".cubin") as f:
    f.write(raw); f.flush()
    dn = CubinDebugger(f.name, "k")
check("T4 nonzero symbol entry builds exact private template",
      (dn._kt.entry_off != 0, dn.template.n_insts,
       len(dn.template.replay_plans)), (True, 6, 6))

cta_src = """#fn cta(out<8>) {
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    S2R R2, SR_TID.X;[5:7:{1}:5:1]
    S2R R3, SR_CTAID.X;[4:7:{}:5:1]
    IMAD R2, R3, 0x20, R2;[7:7:{4,5}:5:1]
    IMAD.WIDE.U32 {R6,R7}, R2, 0x4, {R4,R5};[7:7:{}:5:1]
    STG.E.STRONG.GPU [{R6,R7}], R2;[7:1:{}:8:0]
    EXIT;[7:7:{1}:5:0]
}
"""
with tempfile.NamedTemporaryFile(suffix=".cubin") as f:
    f.write(assemble(cta_src)); f.flush()
    dc = CubinDebugger(f.name, max_warps=2)
    oc = dc.mod.devmem_alloc(N * 4)
    dc.mod.device_write(oc, bytes(N * 4))
    dc.launch([oc], grid=(2,), block=(32,))
    dc.wait_ready(); dc.release(); dc.wait_done()
    gotc = struct.unpack(f"<{N}I", dc.mod.device_read(oc, N * 4))
check("T4 multi-CTA real cubin uses distinct private copies",
      gotc, tuple(range(N)))

# Unsupported private code fails closed and names the explicit compatibility
# fallback.  Selecting shared is a user decision, never an automatic retry.
bad_src = """#fn bad() {
    LEPC {R2,R3};[7:7:{}:4:0]
    EXIT;[7:7:{}:5:0]
}
"""
with tempfile.NamedTemporaryFile(suffix=".cubin") as f:
    f.write(assemble(bad_src)); f.flush()
    try:
        CubinDebugger(f.name)
        msg = ""
    except CodeImageError as e:
        msg = str(e)
    check("T5 PC-sensitive rejection is actionable",
          ("PC-sensitive LEPC" in msg, "backend='shared'" in msg),
          (True, True))
fallback = CubinDebugger(CUBIN, backend="shared")
check("T5 shared backend remains explicit fallback",
      isinstance(fallback, SharedCubinDebugger), True)

cli = subprocess.run(
    [sys.executable, "-m", "sassdbg.cli", "--cubin", CUBIN,
     "--block", "32"],
    input=("b 3 warp 0 mask 0xffffffff\ninfo b\nr\nc\n"
           "dump 0 5 R7\nq\n"),
    capture_output=True, text=True, timeout=60,
    cwd=Path(__file__).resolve().parents[2])
if cli.returncode:
    print(cli.stdout); print(cli.stderr)
check("T6 CLI real-cubin path defaults private",
      (cli.returncode, "w0:0xffffffff" in cli.stdout,
       "hit: warp 0 at inst 3:" in cli.stdout,
       "w0 lane5 R7 = 0x5" in cli.stdout),
      (0, True, True, True))

if FAILS:
    print("=== M11g FAILURES:", ", ".join(FAILS), "===")
    sys.exit(1)
print("=== sassdbg M11g real-cubin private default: ALL PASS ===")
