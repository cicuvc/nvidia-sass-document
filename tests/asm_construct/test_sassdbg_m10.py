"""sassdbg M10 — attach the debugger to a REAL nvcc cubin (no source).

The cubin image is patched in memory before cuModuleLoadData: the
kernel entry's first two instructions become LEPC+JMP into a
heap-resident prologue (arena VA baked into its immediates — no dbgctrl
param on a real kernel), which reports the base, parks at the gate,
replays the two displaced instructions verbatim, and RETs back to
entry+0x20.  Orig inst 0/1 live at the heap replay slots (bps work
there too); everything else is the stock M9 engine.

T0  trampoline/prologue alone: no bps, kernel computes correctly
T1  bp at orig 0 (heap replay slot) AND orig 12 (FFMA, 2 warps):
    dump R2 (frame view of the LDG result a[i]), set_reg lane 0,
    resumed output reflects the set
T2  persistence across relaunch: the still-armed bp fires again

Run: python3 tests/asm_construct/test_sassdbg_m10.py
"""
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sassdbg.real import CubinDebugger  # noqa: E402
from assembler import assemble  # noqa: E402

CUBIN = str(Path(__file__).resolve().parents[1] / "m2_smoke.cubin")
N = 64                                    # 2 warps
FFMA = 12                                 # orig index of the FFMA

ok = True


def check(name, cond, extra=""):
    global ok
    if not cond:
        ok = False
    print(f"{'ok ' if cond else 'FAIL'} {name:<52} {extra}")


dbg = CubinDebugger(CUBIN, max_warps=2)
a = dbg.mod.devmem_alloc(N * 4)
b = dbg.mod.devmem_alloc(N * 4)
dbg.mod.device_write(a, b"".join(struct.pack("<f", float(i + 1))
                                 for i in range(N)))

# --- T0: bare trampoline run -------------------------------------------------
dbg.mod.device_write(b, bytes(N * 4))
dbg.launch([a, b, N], block=(N,))
base = dbg.base()
check("T0 base reported (16-aligned code VA)",
      base and base % 16 == 0, hex(base))
dbg.release()
dbg.wait_done()
out = struct.unpack(f"<{N}f", dbg.mod.device_read(b, N * 4))
check("T0 trampoline+replay: b[i] = a[i]*2+1",
      all(abs(out[i] - ((i + 1) * 2.0 + 1.0)) < 1e-6 for i in range(N)))

# --- T1: bps at orig 0 (heap replay) and orig 12 (FFMA) ----------------------
bp0 = dbg.arm(0)
bpf = dbg.arm(FFMA)
dbg.launch([a, b, N], block=(N,))
dbg.base()
dbg.mod.device_write(b, bytes(N * 4))
dbg.release()
hits = [dbg.wait_hit().id for _ in range(2)]      # both warps at inst 0
check("T1 bp at orig 0 (heap replay slot) hit by both warps",
      hits == [bp0.id, bp0.id])
dbg.resume(bp0)                                   # restores replay slot
h1 = dbg.wait_hit()
w1 = h1.warp                                      # NB: wait_hit returns the
h2 = dbg.wait_hit()                               # SAME bp object per site —
w2 = h2.warp                                      # read .warp immediately
check("T1 FFMA bp hit by both warps", {w1, w2} == {0, 1})
r = dbg.dump_regs(w1, ["R2"], lane=5)
got = struct.unpack("<f", struct.pack("<I", r["R2"]))[0]
want = float(w1 * 32 + 5 + 1)                     # i = tid = warp*32+lane
check("T1 dump R2 lane5 = a[tid] (frame view of the LDG result)",
      abs(got - want) < 1e-6, f"a[{w1 * 32 + 5}]={got}")
dbg.set_reg(w1, "R2", struct.unpack("<I", struct.pack("<f", 100.0))[0],
            lane=0)
dbg.resume(bpf)
dbg.wait_done()
out = struct.unpack(f"<{N}f", dbg.mod.device_read(b, N * 4))
check("T1 resumed kernel: lane0 of the set warp stored 100*2+1",
      abs(out[w1 * 32] - 201.0) < 1e-6, f"b[{w1 * 32}]={out[w1 * 32]}")
check("T1 all other lanes correct",
      all(abs(out[i] - ((i + 1) * 2.0 + 1.0)) < 1e-6
          for i in range(N) if i != w1 * 32))

# --- T2: bp persistence across relaunch --------------------------------------
bpf2 = dbg.arm(FFMA)                 # re-arm (T1's resume consumed it)
dbg.mod.device_write(b, bytes(N * 4))
dbg.launch([a, b, N], block=(N,))
dbg.base()
dbg.release()
hits = [dbg.wait_hit().id for _ in range(2)]
check("T2 re-armed FFMA bp fires on relaunch", hits == [bpf2.id] * 2)
dbg.resume(bpf2)
dbg.wait_done()
out = struct.unpack(f"<{N}f", dbg.mod.device_read(b, N * 4))
check("T2 relaunched kernel output correct",
      all(abs(out[i] - ((i + 1) * 2.0 + 1.0)) < 1e-6 for i in range(N)))

# --- T3: stepper on the lifted source (single warp) --------------------------
from sassdbg.stepper import Stepper  # noqa: E402

dbg2 = CubinDebugger(CUBIN, max_warps=1)
a2 = dbg2.mod.devmem_alloc(32 * 4)
b2 = dbg2.mod.devmem_alloc(32 * 4)
dbg2.mod.device_write(a2, b"".join(struct.pack("<f", float(i + 1))
                                   for i in range(32)))
dbg2.mod.device_write(b2, bytes(32 * 4))
st = Stepper(dbg2.source, dbg=dbg2)
st.launch([a2, b2, 32], block=(32,))
bp = st.run_to_entry()
for _ in range(4):                    # 0(LDC) 1(S2R) 2(LDCU) 3(ISETP) 4(@P0 EXIT)
    bp = st.step(bp)
check("T3 stepped path = [0,1,2,3,4] through the predicated EXIT",
      st.path == [0, 1, 2, 3, 4], str(st.path))
bp = st.step(bp)                      # inst 4 is terminal -> run free
check("T3 step over terminal returns None (kernel ran to completion)",
      bp is None)
st.dbg.wait_done()
out = struct.unpack("<32f", dbg2.mod.device_read(b2, 32 * 4))
check("T3 stepped kernel output correct",
      all(abs(out[i] - ((i + 1) * 2.0 + 1.0)) < 1e-6 for i in range(32)))

# --- T4: displaced-instruction outputs survive the return path ---------------
# The old prologue reloaded its return target through R4/R5/R8/R9 *after*
# replay, silently destroying an entry instruction that defined those regs.
K_ENTRY_OUTPUTS = """\
#fn k(out<8>) {
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
    f.write(assemble(K_ENTRY_OUTPUTS))
    f.flush()
    dbg3 = CubinDebugger(f.name)
    out3 = dbg3.mod.devmem_alloc(8)
    dbg3.mod.device_write(out3, bytes(8))
    dbg3.launch([out3], block=(1,))
    dbg3.base()
    dbg3.release()
    dbg3.wait_done()
    got = struct.unpack("<II", dbg3.mod.device_read(out3, 8))
check("T4 replay preserves R4/R5 outputs into original inst 2",
      got == (0x12345678, 0x23456789), str(tuple(map(hex, got))))

# --- T5: ELF symbol with a nonzero entry offset ------------------------------
# Exercise the section slice independently of the GPU.  Some cubins place
# several functions in one text section; end = entry + size, not just size.
from sassdbg.cubin import (_sections, load_kernel, SHT_SYMTAB,  # noqa: E402
                           STT_FUNC)

raw = bytearray(assemble(K_ENTRY_OUTPUTS))
secs = _sections(raw)
symtab = next(s for s in secs if s.typ == SHT_SYMTAB)
strtab = secs[symtab.link]
for j in range(symtab.size // symtab.entsize):
    pos = symtab.off + j * symtab.entsize
    st_name, st_info, _other, st_shndx, st_value, st_size = \
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
    f.write(raw)
    f.flush()
    kt = load_kernel(f.name, "k")
check("T5 nonzero ELF entry slices exactly symbol.size bytes",
      kt.n_insts == 6 and kt.word(0) != (0, 0), str(kt.n_insts))

print("\n=== sassdbg M10 real-cubin attach: ALL PASS ===" if ok
      else "\n=== FAILURES ===")
sys.exit(0 if ok else 1)
