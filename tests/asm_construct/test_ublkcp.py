import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule
from archutil import adapt_source  # noqa: E402

# ---------------------------------------------------------------------------
# UBLKCP — non-tensor cp.async.bulk (uniform datapath bulk copy).
#
# Semantics verified on sm_120 (RTX 5090, CUDA 13.0 / driver 580.65):
#   UBLKCP.G.S [URb], [URa], URc   shared -> global, bulk_group completion
#                                  (commit via UTMACMDFLUSH, wait DEPBAR.LE)
#   UBLKCP.S.G [URb], [URa], URc   global -> shared, mbarrier tx completion
#
# Empirically: the URc operand is the COPY SIZE in 16-byte (128-bit) units
# (URc=1 -> 16 bytes, URc=2 -> 32 bytes, URc=0x10 -> 256 bytes), NOT the
# mbarrier address as earlier believed.  The mbarrier for the load direction
# is implicit (armed by the preceding SYNCS.ARRIVE.TRANS64 expect_tx).
#
# The load-direction mbarrier completion is verified working on this driver
# (RTX 5090, CUDA 13.0 / driver 580.65) BOTH via `tma_cp_test.cu` (repo root)
# and in hand-built form below.  Three hand-built pitfalls had to be solved
# (see notes/sm90/instr/ublkcp.md):
#   1. ELECT race — `@!P0 BRA` right after `ELECT` reads a stale P0=false on
#      sm_120, skipping the producer.  Insert 8 NOPs after ELECT (or match
#      ptxas's usched: ELECT trans1 / BSSY WAIT12 / BRA trans5).
#   2. Descriptor clobber — do NOT reuse UR4/UR5 (the global memory
#      descriptor) for the mbarrier init computation; the tail STG.E
#      desc[{UR4,UR5}] then faults intermittently (CUDA 719).
#   3. try_wait spin shape — the PHASECHK loop MUST branch back on the
#      PHASECHK's own predicate (`@!P0 BRA poll`).  A timeout counter whose
#      derived predicate drives the loop-back (@P1 BRA poll) prevents the
#      mbarrier phase from EVER completing, even with an arbitrarily large
#      timeout (verified empirically; ptxas uses the same tight loop).
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<46} {got} (exp {want})")

try:
    _ = CudaModule(assemble("#fn k() { EXIT;[7:7:{}:5:0] }"))
    HAVE_GPU = True
except RuntimeError:
    HAVE_GPU = False
    print("--- no CUDA device; GPU semantic checks SKIPPED ---")

if not HAVE_GPU:
    sys.exit(0)

# --- offline: encodings ----------------------------------------------------
lo, hi = assemble_flat("UBLKCP.G.S [UR8], [UR10], UR11;[7:0:{1}:5:1]")[0]
assert lo & 0xFFF == 0x3ba and (hi >> 27) & 1 == 1, hex(lo)
lo, hi = assemble_flat("UBLKCP.S.G [UR10], [UR8], UR15;[7:0:{1}:5:1]")[0]
assert lo & 0xFFF == 0x3ba and (hi >> 27) & 1 == 1, hex(lo)
check("UBLKCP opcode + URB slots encode", 1, 1)

# --- 1. UBLKCP.G.S store: shared -> global, bulk_group completion ----------
# fill shared[0x800..0x820) with 8 words, bulk-store 32 bytes (URc=2),
# commit_group (UTMACMDFLUSH) + wait_group (DEPBAR.LE), verify global data.
body = (
    "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
    "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
    "    MOV32I R0, 0x11111111;[7:7:{}:5:1]\n"
    "    MOV32I R1, 0x22222222;[7:7:{}:5:1]\n"
    "    STS.64 [RZ+0x800], {R0,R1};[7:7:{}:5:1]\n"
    "    MOV32I R0, 0x33333333;[7:7:{}:5:1]\n"
    "    MOV32I R1, 0x44444444;[7:7:{}:5:1]\n"
    "    STS.64 [RZ+0x808], {R0,R1};[7:7:{}:5:1]\n"
    "    MOV32I R0, 0x55555555;[7:7:{}:5:1]\n"
    "    MOV32I R1, 0x66666666;[7:7:{}:5:1]\n"
    "    STS.64 [RZ+0x810], {R0,R1};[7:7:{}:5:1]\n"
    "    MOV32I R0, 0x77777777;[7:7:{}:5:1]\n"
    "    MOV32I R1, 0x88888888;[7:7:{}:5:1]\n"
    "    STS.64 [RZ+0x818], {R0,R1};[7:7:{}:5:1]\n"
    "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
    "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]\n"
    "    R2UR UR8, R2;[1:7:{1}:5:1]\n"
    "    R2UR UR9, R3;[1:7:{1}:5:1]\n"
    "    UMOV UR10, 0x800;[1:7:{}:1:0]\n"
    "    UMOV UR11, 0x2;[1:7:{}:1:0]\n"
    "    ELECT P1, URZ, PT;[1:7:{}:5:1]\n"
    "    UBLKCP.G.S [UR8], [UR10], UR11;[7:0:{1}:5:1]\n"
    "    UTMACMDFLUSH;[7:0:{1}:5:1]\n"
    "    DEPBAR.LE SB0, 0x0;[7:7:{1}:5:1]\n"
    "    EXIT;[7:7:{}:5:0]\n")
src = "#fn k(out<8>) {\n    #pragma SHARED(0x4000)\n" + body + "}\n"
mod = CudaModule(assemble(adapt_source(src)))
d = mod.devmem_alloc(64)
mod.device_write(d, bytes(64))
mod.launch("k", grid=(1,), block=(1,), args=[d], shared_mem=0x4000)
mod.synchronize()
v = struct.unpack("<8I", mod.device_read(d, 32))
exp = [0x11111111, 0x22222222, 0x33333333, 0x44444444,
       0x55555555, 0x66666666, 0x77777777, 0x88888888]
check("UBLKCP.G.S 32B store (URc=2)", list(v), exp)

# --- 2. store size in 16-byte units: URc=1 -> 16 bytes --------------------
body2 = body.replace("    UMOV UR11, 0x2;[1:7:{}:1:0]", "    UMOV UR11, 0x1;[1:7:{}:1:0]")
src = "#fn k(out<8>) {\n    #pragma SHARED(0x4000)\n" + body2 + "}\n"
mod = CudaModule(assemble(adapt_source(src)))
d = mod.devmem_alloc(64)
mod.device_write(d, bytes(64))
mod.launch("k", grid=(1,), block=(1,), args=[d], shared_mem=0x4000)
mod.synchronize()
v = struct.unpack("<8I", mod.device_read(d, 32))
check("UBLKCP.G.S 16B store (URc=1)", list(v[:4]), exp[:4])
check("UBLKCP.G.S 16B store stops at 16", list(v[4:]), [0, 0, 0, 0])

# --- 3. UBLKCP.S.G load: global -> shared copies (mbarrier path) -----------
# The copy itself works; the mbarrier tx-completion does not fire on this
# driver (see header).  Verify the data lands in shared.
body3 = (
    "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
    "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
    "    LDC.64 {R2,R3}, #param(gsrc);[1:7:{}:1:0]\n"
    "    R2UR UR8, R2;[1:7:{1}:5:1]\n"
    "    R2UR UR9, R3;[1:7:{1}:5:1]\n"
    "    UMOV UR10, 0x800;[1:7:{}:1:0]\n"
    "    UMOV UR6, 0x400;[1:7:{}:1:0]\n"
    "    UMOV UR12, 0x1;[1:7:{}:1:0]\n"
    "    UIADD3 UR12, UPT, UPT, -UR12, 0x100000, URZ;[7:7:{1}:5:1]\n"
    "    USHF.L.U32 UR13, UR12, 0xb, URZ;[7:7:{1}:5:1]\n"
    "    USHF.L.U32 UR12, UR12, 0x1, URZ;[7:7:{1}:5:1]\n"
    "    SYNCS.EXCH.64 URZ, [UR6], UR12;[2:1:{1}:5:1]\n"
    "    MOV32I R0, 16;[7:7:{}:5:1]\n"
    "    SYNCS.ARRIVE.TRANS64 {RZ,RZ}, [RZ+UR6], R0;[1:7:{2}:5:1]\n"
    "    MOV32I R2, 0x1;[7:7:{}:5:1]\n"
    "    R2UR UR15, R2;[1:7:{}:5:1]\n"
    "    ELECT P1, URZ, PT;[1:7:{}:5:1]\n"
    "    UBLKCP.S.G [UR10], [UR8], UR15;[0:7:{2}:5:1]\n"
    # spin until the copied word lands (async bulk load; the mbarrier
    # completion in hand-built form is an open item — poll the data itself)
    "    MOV32I R14, 0x20000;[7:7:{}:5:1]\n"
    "    #def_label(spin)\n"
    "    LDS R10, [RZ+UR10];[1:7:{2}:8:1]\n"
    "    ISETP.EQ.U32.AND P0, PT, R10, 0x1, PT;[7:7:{2}:5:1]\n"
    "    @P0 BRA #label(datadone);[7:7:{}:5:1]\n"
    "    IADD3 R14, R14, -1, RZ;[7:7:{2}:5:1]\n"
    "    ISETP.GT.U32.AND P1, PT, R14, RZ, PT;[7:7:{2}:5:1]\n"
    "    @P1 BRA #label(spin);[7:7:{}:5:1]\n"
    "    #def_label(datadone)\n"
    "    LDS.64 {R10,R11}, [RZ+UR10];[1:7:{2}:5:1]\n"
    "    LDS.64 {R12,R13}, [RZ+UR10+0x8];[1:7:{2}:5:1]\n"
    "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
    "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R10;[0:1:{1}:1:0]\n"
    "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R11;[0:1:{1}:1:0]\n"
    "    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R12;[0:1:{1}:1:0]\n"
    "    STG.E desc[{UR4,UR5}][{R6,R7}+0xc], R13;[0:1:{1}:1:0]\n"
    "    EXIT;[7:7:{}:5:0]\n")
src = "#fn k(out<8>, gsrc<8>) {\n    #pragma NUM_MBARRIERS(1)\n    #pragma SHARED(0x4000)\n" + body3 + "}\n"
mod = CudaModule(assemble(adapt_source(src)))
d = mod.devmem_alloc(64)
g = mod.devmem_alloc(0x200)
pat = struct.pack("<16I", *range(1, 17))
mod.device_write(g, pat)
mod.launch("k", grid=(1,), block=(1,), args=[d, g], shared_mem=0x4000)
mod.synchronize()
v = struct.unpack("<4I", mod.device_read(d, 16))
check("UBLKCP.S.G 16B load (URc=1) data", list(v), [1, 2, 3, 4])

# --- 4. UBLKCP.S.G load: mbarrier phase completes (hand-built) ------------
# Full ptxas-equivalent flow, hand-assembled:
#   elect + 8 NOPs + @!P0 BRA  (producer guard; the NOPs fix the ELECT
#                               stale-P0 race observed on sm_120)
#   producer (elected): mbarrier init via SYNCS.EXCH.64, FENCE/EXCH/MEMBAR/
#                       FENCE chain, UBLKCP.S.G 512B, ARRIVE.TRANS64 (A1TR,
#                       expect_tx = byte count 512 in R0)
#   consumer (all threads): TIGHT try_wait spin
#                       SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR7], RZ
#                       @!P0 BRA poll
#   -> the phase completes (P0 true) and the copied words read back.
# NOTE: the loop-back MUST be predicated on the PHASECHK result itself.
# A timeout counter branching on its own predicate (@P1 BRA poll) makes the
# phase never complete (see notes/sm90/instr/ublkcp.md).
body4 = (
    "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
    "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
    "    UMOV UR6, 0x400;[1:7:{}:1:0]\n"          # smem dst (all threads)
    "    UMOV UR7, 0x600;[1:7:{}:1:0]\n"          # mbar (all threads)
    "    ELECT P0, URZ, PT;[1:7:{}:1:0]\n"
    "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
    "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
    "    @!P0 BRA #label(consumer);[7:7:{}:5:1]\n"
    "    # --- producer (elected thread) ---\n"
    "    UMOV UR12, 0x1;[1:7:{}:1:0]\n"
    "    UIADD3 UR12, UPT, UPT, -UR12, 0x100000, URZ;[7:7:{1}:5:1]\n"
    "    USHF.L.U32 UR13, UR12, 0xb, URZ;[7:7:{1}:5:1]\n"
    "    USHF.L.U32 UR12, UR12, 0x1, URZ;[7:7:{1}:5:1]\n"
    "    LDCU.64 {UR10,UR11}, #param(gsrc);[2:7:{1}:5:1]\n"
    "    MOV32I R0, 512;[7:7:{}:5:1]\n"           # expect_tx byte count
    "    FENCE.VIEW.ASYNC.S;[1:7:{}:5:1]\n"
    "    SYNCS.EXCH.64 URZ, [UR7], UR12;[3:1:{1}:5:1]\n"
    "    MEMBAR.ALL.CTA;[7:7:{3}:5:1]\n"
    "    FENCE.VIEW.ASYNC.S;[2:7:{}:5:1]\n"
    "    UMOV UR8, 0x20;[1:7:{}:1:0]\n"           # 512 bytes (16B units)
    "    UBLKCP.S.G [UR6], [UR10], UR8;[7:1:{2}:5:1]\n"
    "    SYNCS.ARRIVE.TRANS64 {RZ,RZ}, [RZ+UR7], R0;[7:1:{}:1:0]\n"
    "    #def_label(consumer)\n"
    "    # --- consumer try_wait (tight loop on PHASECHK predicate) ---\n"
    "    #def_label(poll)\n"
    "    SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR7], RZ;[1:7:{}:2:0]\n"
    "    @!P0 BRA #label(poll);[7:7:{1}:5:0]\n"
    "    #def_label(done)\n"
    "    SEL R15, RZ, 0x1, !P0;[1:7:{1}:5:1]\n"   # 1 = phase completed
    "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R15;[0:1:{1}:1:0]\n"
    "    LDS.64 {R10,R11}, [RZ+UR6];[1:7:{2}:8:1]\n"
    "    LDS.64 {R12,R13}, [RZ+UR6+0x8];[1:7:{2}:8:1]\n"
    "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
    "    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R10;[0:1:{1}:1:0]\n"
    "    STG.E desc[{UR4,UR5}][{R6,R7}+0xc], R11;[0:1:{1}:1:0]\n"
    "    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R12;[0:1:{1}:1:0]\n"
    "    STG.E desc[{UR4,UR5}][{R6,R7}+0x14], R13;[0:1:{1}:1:0]\n"
    "    EXIT;[7:7:{}:5:0]\n")
src = "#fn k(out<8>, gsrc<8>) {\n    #pragma NUM_MBARRIERS(1)\n    #pragma SHARED(0x4000)\n" + body4 + "}\n"
mod = CudaModule(assemble(adapt_source(src)))
d = mod.devmem_alloc(64)
g = mod.devmem_alloc(0x200)
pat = struct.pack("<16I", *range(1, 17))
mod.device_write(g, pat)
mod.launch("k", grid=(1,), block=(32,), args=[d, g], shared_mem=0x4000)
mod.synchronize()
v = struct.unpack("<6I", mod.device_read(d, 24))
check("UBLKCP.S.G mbarrier phase completes (block=32)", v[0], 1)
check("UBLKCP.S.G 512B load data", list(v[2:6]), [1, 2, 3, 4])

print(f"\n=== UBLKCP: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
