import ctypes, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_kernel, CudaModule
from archutil import adapt_source  # noqa: E402
from assembler.runner import _cuda, _check

# ---------------------------------------------------------------------------
# UTMACCTL — empirical verification of the tensormap descriptor cache
#
# tensormap.replace lowers to a plain STG on the descriptor (no dedicated
# instruction), so the TMA engine can hold a STALE cached descriptor.  The
# documented cure is fence.proxy.tensormap (acquire):
#   sm_90:  DEPBAR {5..0} + UTMACCTL.IV [URa]
#   sm_120: DEPBAR {5..0} + CCTL.E.C.LDCU.IV.DEEP [URa] + UTMACCTL.IV [URa]
# (see notes/sm90/instr/utmacctl.md + notes/sm90/instr/cctl.md)
#
# Test: one kernel, two UTMALDG.2D loads from the SAME descriptor address.
#   phase 1: descriptor points at src A -> tile must be A's data
#   (elected thread rewrites descriptor w0/w1 to src B with a plain STG.64,
#    i.e. exactly what tensormap.replace.global_address emits)
#   phase 2: UTMALDG again — stale cached descriptor loads A; a complete
#            invalidation (CCTL.LDCU.IV.DEEP + UTMACCTL.IV on sm_120) loads B.
#
# Isolation matrix (sm_120): neither CCTL nor UTMACCTL alone refreshes; the
# pair (IV or IVALL) is required.  This test runs the key combinations.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {name:<52} {got} (exp {want})")

try:
    _ = CudaModule(assemble("#fn k() { EXIT;[7:7:{}:5:0] }"))
    HAVE_GPU = True
except RuntimeError:
    HAVE_GPU = False
    print("--- no CUDA device; GPU checks SKIPPED ---")

MB = ("    MEMBAR.ALL.CTA;[7:7:{3}:5:1]\n"
      "    MEMBAR.ALL.GPU;[7:7:{3}:5:1]\n"
      "    ERRBAR;[7:7:{}:5:1]\n"
      "    CGAERRBAR;[7:7:{}:5:1]\n"
      "    DEPBAR.ALL;[7:7:{}:5:1]\n")
CCTL_D = "    CCTL.E.C.LDCU.IV.DEEP [UR16];[7:7:{0}:1:0]\n"
CCTL_S = "    CCTL.E.C.LDCU.IV.SHALLOW [UR16];[7:7:{0}:1:0]\n"
IV     = "    UTMACCTL.IV [UR16];[7:3:{1}:5:1]\n"
IVALL  = "    UTMACCTL.IVALL;[7:7:{3}:5:1]\n"

from archutil import is_sm90  # noqa: E402

if is_sm90():
    # Hopper has no CCTL.LDCU-invalidate suboperation: ptxas(sm_90a) lowers the
    # tensormap.cp_fenceproxy/acquire fence chain to a single UTMACCTL.IV (see
    # notes/sm120/silver-status.md "Blackwell-only").  Skip CCTL combos here.
    print("info CCTL.E.C.LDCU.* variants skipped: Blackwell-only on this ISA")
    CTL_NONE = ""
    CTL_FULL = IV
    CTL_PAIR_NOMBAR = IV
    CTL_CCTL = ""
    CTL_IV   = MB + IV
    CTL_CCTL_IVALL = IVALL
else:
    CTL_NONE = ""
    CTL_FULL = MB + CCTL_D + IV
    CTL_PAIR_NOMBAR = CCTL_D + IV          # membars/DEPBAR not required
    CTL_CCTL = MB + CCTL_D
    CTL_IV   = MB + IV
    CTL_CCTL_IVALL = MB + CCTL_D + IVALL

def kernel(ctl):
    body = (
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
        "    LDCU.64 {UR16,UR17}, #param(tmap_ptr);[1:7:{}:1:0]\n"
        "    LDC.64 {R2,R3}, #param(tmap_ptr);[1:7:{}:1:0]\n"
        "    LDC.64 {R4,R5}, #param(new_addr);[1:7:{}:1:0]\n"
        "    UMOV UR6, 0x400;[1:7:{}:1:0]\n"
        "    UMOV UR7, 0x600;[1:7:{}:1:0]\n"
        "    UMOV UR8, 0x500;[1:7:{}:1:0]\n"
        "    UMOV UR9, 0x640;[1:7:{}:1:0]\n"
        "    ELECT P1, URZ, PT;[1:7:{}:1:0]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    @!P1 BRA #label(consumer1);[7:7:{}:5:1]\n"
        "    UMOV UR12, 0x1;[1:7:{}:1:0]\n"
        "    UIADD3 UR12, UPT, UPT, -UR12, 0x100000, URZ;[7:7:{1}:5:1]\n"
        "    USHF.L.U32 UR13, UR12, 0xb, URZ;[7:7:{1}:5:1]\n"
        "    USHF.L.U32 UR12, UR12, 0x1, URZ;[7:7:{1}:5:1]\n"
        "    MOV32I R0, 256;[7:7:{}:5:1]\n"
        "    FENCE.VIEW.ASYNC.S;[1:7:{}:5:1]\n"
        "    SYNCS.EXCH.64 URZ, [UR7], UR12;[3:1:{1}:5:1]\n"
        "    SYNCS.EXCH.64 URZ, [UR9], UR12;[3:1:{1}:5:1]\n"
        "    MEMBAR.ALL.CTA;[7:7:{3}:5:1]\n"
        "    FENCE.VIEW.ASYNC.S;[2:7:{}:5:1]\n"
        "    UMOV UR8, 0x400;[1:7:{}:1:0]\n"
        "    UMOV UR9, 0x600;[1:7:{}:1:0]\n"
        "    UMOV UR10, 0x0;[1:7:{}:1:0]\n"
        "    UMOV UR11, 0x0;[1:7:{}:1:0]\n"
        "    SYNCS.ARRIVE.TRANS64 {RZ,RZ}, [RZ+UR7], R0;[7:1:{}:1:0]\n"
        "    UTMALDG.2D [UR8], [UR16];[7:3:{1}:12:1]\n"
        "    #def_label(consumer1)\n"
        "    #def_label(poll1)\n"
        "    SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR7], RZ;[1:7:{}:2:0]\n"
        "    @!P0 BRA #label(poll1);[7:7:{1}:5:0]\n"
        "    @!P1 BRA #label(consumer2);[7:7:{1}:5:1]\n"
        "    STG.E.64 desc[{UR4,UR5}][{R2,R3}], {R4,R5};[0:1:{1}:1:0]\n"
        + ctl +
        "    UMOV UR8, 0x500;[1:7:{}:1:0]\n"
        "    UMOV UR9, 0x640;[1:7:{}:1:0]\n"
        "    UMOV UR10, 0x0;[1:7:{}:1:0]\n"
        "    UMOV UR11, 0x0;[1:7:{}:1:0]\n"
        "    SYNCS.ARRIVE.TRANS64 {RZ,RZ}, [RZ+UR9], R0;[7:1:{}:1:0]\n"
        "    UTMALDG.2D [UR8], [UR16];[7:3:{1}:12:1]\n"
        "    #def_label(consumer2)\n"
        "    #def_label(poll2)\n"
        "    SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR9], RZ;[1:7:{}:2:0]\n"
        "    @!P0 BRA #label(poll2);[7:7:{1}:5:0]\n"
        "    LDS.64 {R10,R11}, [RZ+0x400];[1:7:{2}:8:1]\n"
        "    LDS.64 {R12,R13}, [RZ+0x408];[1:7:{2}:8:1]\n"
        "    LDS.64 {R14,R15}, [RZ+0x500];[1:7:{2}:8:1]\n"
        "    LDS.64 {R16,R17}, [RZ+0x508];[1:7:{2}:8:1]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R10;[0:1:{1}:1:0]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R11;[0:1:{1}:1:0]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R12;[0:1:{1}:1:0]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0xc], R13;[0:1:{1}:1:0]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R14;[0:1:{1}:1:0]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x14], R15;[0:1:{1}:1:0]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x18], R16;[0:1:{1}:1:0]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x1c], R17;[0:1:{1}:1:0]\n"
        "    EXIT;[7:7:{}:5:0]\n")
    return "#fn k(tmap_ptr<8>, new_addr<8>, out<8>) {\n" \
        "    #pragma NUM_MBARRIERS(2)\n" \
        "    #pragma SHARED(0x4000)\n" + body + "}\n"

# offline: full variant must contain the expected control ops.
# sm_120: CCTL.E.C.LDCU.IV.DEEP (opcode family 0x540/0x1540) + UTMACCTL.IV;
# sm_90 : UTMACCTL.IV only.
enc = assemble_kernel(kernel(CTL_FULL)).encoded
utmas = [e for e in enc
         if (e[0] & 0xFFF) == 0x9b9 and ((e[1] >> 27) & 1) == 1]
check("offline: UTMACCTL.IV present in full variant", len(utmas), 1)
if not is_sm90():
    cctls = [e for e in enc if (e[0] & 0xFFF) == 0x540 and ((e[0] >> 63) & 0xF) == 0]
    check("offline: CCTL.E.C.LDCU.IV.DEEP present in full variant",
          len(cctls), 1)
enc = assemble_kernel(kernel(CTL_NONE)).encoded
cctls = [e for e in enc if (e[0] & 0xFFF) == 0x540]
utmas = [e for e in enc
         if (e[0] & 0xFFF) == 0x9b9 and ((e[1] >> 27) & 1) == 1]
check("offline: no CCTL in no-ctl variant", len(cctls), 0)
check("offline: no UTMACCTL in no-ctl variant", len(utmas), 0)

if not HAVE_GPU:
    sys.exit(0 if ok else 1)

# --- host setup --------------------------------------------------------------
lib = _cuda()
lib.cuTensorMapEncodeTiled.restype = ctypes.c_int
lib.cuTensorMapEncodeTiled.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]

srcA = struct.pack("<256H", *range(1, 257))
srcB = struct.pack("<256H", *range(257, 513))
mod = CudaModule(assemble("#fn k() { EXIT;[7:7:{}:5:0] }"))
dA = mod.devmem_alloc(512); mod.device_write(dA, srcA)
dB = mod.devmem_alloc(512); mod.device_write(dB, srcB)

shape = (ctypes.c_uint64 * 2)(16, 16)
stride = (ctypes.c_uint64 * 2)(16 * 2, 0)
box = (ctypes.c_uint32 * 2)(16, 8)
elem = (ctypes.c_uint32 * 2)(1, 1)
tmap = ctypes.create_string_buffer(128)
_check(lib.cuTensorMapEncodeTiled(
    ctypes.cast(tmap, ctypes.c_void_p), 6, 2, ctypes.c_void_p(dA),
    shape, stride, box, elem, 0, 0, 0, 0))
d_tmap = mod.devmem_alloc(128)
mod.device_write(d_tmap, bytes(tmap.raw))

A_row = [0x00020001, 0x00040003, 0x00060005, 0x00080007]
B_row = [((b << 16) | a) for a, b in
         ((257, 258), (259, 260), (261, 262), (263, 264))]

def run_variant(tag, ctl):
    mod.device_write(d_tmap, bytes(tmap.raw))   # reset descriptor -> src A
    m = CudaModule(assemble(adapt_source(kernel(ctl))))
    d = m.devmem_alloc(64)
    m.device_write(d, bytes(64))
    m.launch("k", grid=(1,), block=(32,), args=[d_tmap, dB, d],
             shared_mem=0x4000)
    m.synchronize()
    return struct.unpack("<8I", m.device_read(d, 32))

def classify(name, v, want_phase2):
    p1 = list(v[0:4])
    p2 = list(v[4:8])
    check(f"{name}: phase1 = A", p1, A_row)
    check(f"{name}: phase2 = {want_phase2}", p2, B_row if want_phase2 == "B"
          else A_row)
    print(f"      {name}: phase1={p1}  phase2={p2} "
          f"({'B (fresh)' if p2 == B_row else 'A (stale cache!)'})")

# sm_90 spec has no CCTL.LDCU; on sm_120 both halves of the invalidate pair are
# required.  If the GPU is Hopper (sm_90), UTMACCTL.IV alone is the expected
# lowering; the full variant still works there.
v = run_variant("no-ctl", CTL_NONE)
classify("no-ctl", v, "A")

v = run_variant("full (CCTL+IV)", CTL_FULL)
classify("full (CCTL+IV)", v, "B")

v = run_variant("CCTL+IV (no membars)", CTL_PAIR_NOMBAR)
classify("CCTL+IV (no membars)", v, "B")

v = run_variant("CCTL only", CTL_CCTL)
classify("CCTL only", v, "A")

v = run_variant("UTMACCTL.IV only", CTL_IV)
classify("UTMACCTL.IV only", v, "A")

v = run_variant("CCTL+IVALL", CTL_CCTL_IVALL)
classify("CCTL+IVALL", v, "B")

print(f"\n=== UTMACCTL: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
