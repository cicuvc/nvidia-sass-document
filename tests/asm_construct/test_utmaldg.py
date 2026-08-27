import ctypes, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule
from archutil import adapt_source  # noqa: E402
from assembler.runner import _cuda, _check

# ---------------------------------------------------------------------------
# UTMALDG.2D — hand-built SASS reproduction of the tensor TMA load
# (cp.async.bulk.tensor.2d … mbarrier::complete_tx::bytes).
#
# Descriptor: created host-side with cuTensorMapEncodeTiled (16x16 half
# source, shape {16,16}, stride {32}, box {16,8}), copied into a device
# buffer, and its 64-bit address passed as param 0 (verified working on
# sm_120 — the older "descriptor must be grid_constant" note is stale).
#
# Kernel SASS (ptxas-equivalent, hand-assembled):
#   producer: mbarrier.init (EXCH) -> FENCE/MEMBAR/FENCE -> ARRIVE.TRANS64
#             (A1TR expect_tx=256B) -> UTMALDG.2D [UR8], [UR16]
#   UTMALDG.2D URb block = {UR8=dst smem, UR9=MBARRIER address,
#             UR10=coord[1] (dim1), UR11=coord[0] (dim0)} — the mbarrier is
#             passed INSIDE the coordinate block at URb+1 (leaving UR9=0
#             makes the completion target barrier@0 and the phase never
#             completes).  URa = UR16/UR17 (64-bit global descriptor
#             pointer).  The UTMALDG must be issued with ?WAIT12_END_GROUP
#             usched (?WAIT5 faults 719).  No ELECT/PLOP3 retry handshake is
#             needed (single issue works).
#   consumer: TIGHT try_wait spin (SYNCS.PHASECHK.TRANS64.TRYWAIT P0;
#             @!P0 BRA poll) — the loop-back MUST be the PHASECHK's own
#             predicate (see notes/sm90/instr/ublkcp.md).
#
# Verified on sm_120 (RTX 5090, CUDA 13.0 / driver 580.65): phase completes
# and the 16x8 half tile lands in smem; coordinates {0,0} and {0,8} select
# the correct tensor slice (UR10 = dim1 coord, UR11 = dim0 coord — the
# SASS block order is reversed vs the PTX {c0, c1} operand).
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<52} {got} (exp {want})")

try:
    _ = CudaModule(assemble("#fn k() { EXIT;[7:7:{}:5:0] }"))
    HAVE_GPU = True
except RuntimeError:
    HAVE_GPU = False
    print("--- no CUDA device; GPU semantic checks SKIPPED ---")

# --- offline: encodings ----------------------------------------------------
lo, hi = assemble_flat("UTMALDG.2D [UR8], [UR16];[7:3:{1}:5:1]")[0]
assert lo & 0xFFF == 0x5b4 and (hi >> 27) & 1 == 1, hex(lo)
got_dim = (hi >> 15) & 7                       # rndMode [81:79] = hi bits 17:15
print(f"{'ok ' if got_dim == 1 else 'FAIL'} encode UTMALDG.2D dim field={got_dim} (exp 1)")
ok &= got_dim == 1
got_urb = (lo >> 32) & 0x3f                    # Ra_URb [37:32]
got_ura = (lo >> 24) & 0x3f                    # Sa [29:24]
print(f"{'ok ' if (got_urb, got_ura) == (8, 16) else 'FAIL'} "
      f"encode operands URb={got_urb} URa={got_ura} (exp 8, 16)")
ok &= (got_urb, got_ura) == (8, 16)

if not HAVE_GPU:
    sys.exit(0)

# --- host-side tensor map --------------------------------------------------
lib = _cuda()
lib.cuTensorMapEncodeTiled.restype = ctypes.c_int
lib.cuTensorMapEncodeTiled.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]

# 16x16 half source, values 1..256 (raw bit patterns for easy checking)
src = struct.pack("<256H", *range(1, 257))
mod = CudaModule(assemble("#fn k() { EXIT;[7:7:{}:5:0] }"))
d_src = mod.devmem_alloc(512)
mod.device_write(d_src, src)

shape = (ctypes.c_uint64 * 2)(16, 16)
stride = (ctypes.c_uint64 * 2)(16 * 2, 0)
box = (ctypes.c_uint32 * 2)(16, 8)
elem = (ctypes.c_uint32 * 2)(1, 1)
tmap = ctypes.create_string_buffer(128)
rc = lib.cuTensorMapEncodeTiled(
    ctypes.cast(tmap, ctypes.c_void_p),
    6,                       # CU_TENSOR_MAP_DATA_TYPE_FLOAT16
    2,                       # tensorRank
    ctypes.c_void_p(d_src),
    shape, stride, box, elem,
    0, 0, 0, 0)              # interleave/swizzle/promotion/oob = NONE
_check(rc)
d_tmap = mod.devmem_alloc(128)
mod.device_write(d_tmap, bytes(tmap.raw))

# --- hand-built UTMALDG.2D kernel ------------------------------------------
def utmaldg_kernel(c0, c1):
    body = (
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
        "    LDCU.64 {UR16,UR17}, #param(tmap_ptr);[1:7:{}:1:0]\n"
        "    UMOV UR6, 0x400;[1:7:{}:1:0]\n"          # smem dst (all threads)
        "    UMOV UR7, 0x600;[1:7:{}:1:0]\n"          # mbar (all threads)
        "    ELECT P0, URZ, PT;[1:7:{}:1:0]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    @!P0 BRA #label(consumer);[7:7:{}:5:1]\n"
        "    # --- producer (elected thread) ---\n"
        "    UMOV UR12, 0x1;[1:7:{}:1:0]\n"           # mbarrier init count = 1
        "    UIADD3 UR12, UPT, UPT, -UR12, 0x100000, URZ;[7:7:{1}:5:1]\n"
        "    USHF.L.U32 UR13, UR12, 0xb, URZ;[7:7:{1}:5:1]\n"
        "    USHF.L.U32 UR12, UR12, 0x1, URZ;[7:7:{1}:5:1]\n"
        "    MOV32I R0, 256;[7:7:{}:5:1]\n"           # expect_tx = tile bytes
        "    FENCE.VIEW.ASYNC.S;[1:7:{}:5:1]\n"
        "    SYNCS.EXCH.64 URZ, [UR7], UR12;[3:1:{1}:5:1]\n"
        "    MEMBAR.ALL.CTA;[7:7:{3}:5:1]\n"
        "    FENCE.VIEW.ASYNC.S;[2:7:{}:5:1]\n"
        "    UMOV UR8, 0x400;[1:7:{}:1:0]\n"          # tile dst (URb block)
        "    UMOV UR9, 0x600;[1:7:{}:1:0]\n"          # MBARRIER addr (URb+1)
        f"    UMOV UR10, 0x{c1:X};[1:7:{{}}:1:0]\n"   # coord[1] (dim1)
        f"    UMOV UR11, 0x{c0:X};[1:7:{{}}:1:0]\n"   # coord[0] (dim0)
        "    SYNCS.ARRIVE.TRANS64 {RZ,RZ}, [RZ+UR7], R0;[7:1:{}:1:0]\n"
        "    UTMALDG.2D [UR8], [UR16];[7:3:{1}:12:1]\n"  # WAIT12 usched required
        "    #def_label(consumer)\n"
        "    # --- consumer try_wait (tight loop on PHASECHK predicate) ---\n"
        "    #def_label(poll)\n"
        "    SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR7], RZ;[1:7:{}:2:0]\n"
        "    @!P0 BRA #label(poll);[7:7:{1}:5:0]\n"
        "    #def_label(done)\n"
        "    SEL R15, RZ, 0x1, !P0;[1:7:{1}:5:1]\n"   # 1 = phase completed
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R15;[0:1:{1}:1:0]\n"
        "    LDS.64 {R10,R11}, [RZ+0x400];[1:7:{2}:8:1]\n"
        "    LDS.64 {R12,R13}, [RZ+0x408];[1:7:{2}:8:1]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R10;[0:1:{1}:1:0]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0xc], R11;[0:1:{1}:1:0]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R12;[0:1:{1}:1:0]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x14], R13;[0:1:{1}:1:0]\n"
        "    EXIT;[7:7:{}:5:0]\n")
    return "#fn k(tmap_ptr<8>, out<8>) {\n    #pragma NUM_MBARRIERS(1)\n" \
        "    #pragma SHARED(0x4000)\n" + body + "}\n"


def run_tma(c0, c1):
    mod = CudaModule(assemble(adapt_source(utmaldg_kernel(c0, c1))))
    d = mod.devmem_alloc(64)
    mod.device_write(d, bytes(64))
    mod.launch("k", grid=(1,), block=(32,), args=[d_tmap, d],
               shared_mem=0x4000)
    mod.synchronize()
    return struct.unpack("<6I", mod.device_read(d, 24))

# tile at coords {0,0}: rows 0..15, cols 0..7 -> row 0 = source values 1..8
v = run_tma(0, 0)
check("UTMALDG.2D phase completes (coords 0,0)", v[0], 1)
check("UTMALDG.2D tile row 0 = src[0][0..7]", list(v[2:6]),
      [0x00020001, 0x00040003, 0x00060005, 0x00080007])

# tile at coords {0,8}: rows 0..15, cols 8..15 -> row 0 = source values 9..16
v = run_tma(0, 8)
check("UTMALDG.2D phase completes (coords 0,8)", v[0], 1)
check("UTMALDG.2D tile row 0 = src[0][8..15]", list(v[2:6]),
      [0x000a0009, 0x000c000b, 0x000e000d, 0x0010000f])

print(f"\n=== UTMALDG.2D: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
