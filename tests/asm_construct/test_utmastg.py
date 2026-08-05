import ctypes, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule
from assembler.runner import _cuda, _check

# ---------------------------------------------------------------------------
# UTMASTG.2D — hand-built SASS reproduction of the tensor TMA store
# (cp.async.bulk.tensor.2d.global.shared::cta.bulk_group).
#
# Descriptor: created host-side with cuTensorMapEncodeTiled over the
# DESTINATION global buffer (16x16 half, shape {16,16}, stride {32},
# box {16,8}), copied into a device buffer, 64-bit address passed as param 0.
#
# Kernel SASS (ptxas-equivalent, hand-assembled):
#   simple ELECT P0 + 8 NOPs + @!P0 BRA producer guard
#   producer: UTMASTG.2D [UR8], [UR16]  (single issue — no retry handshake)
#             -> UTMACMDFLUSH -> DEPBAR.LE SB0,0   (bulk_group completion,
#             NO mbarrier — stores complete via the bulk-async-group).
#   UTMASTG.2D URb block (3 regs, 96-bit for 2D):
#             {UR8 = shared source, UR9 = coord[1] (dim1),
#              UR10 = coord[0] (dim0)}  — coordinate order reversed vs PTX.
#   URa = UR16/UR17 (64-bit global descriptor pointer).
#
# Verified on sm_120 (RTX 5090, CUDA 13.0 / driver 580.65): the tile lands in
# the global tensor; coords {0,0} and {0,8} shift the stored slice correctly.
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
lo, hi = assemble_flat("UTMASTG.2D [UR8], [UR16];[7:2:{1}:1:0]")[0]
assert lo & 0xFFF == 0x3b5 and (hi >> 27) & 1 == 1, hex(lo)
got_dim = (hi >> 15) & 7                       # rndMode [81:79] = hi bits 17:15
print(f"{'ok ' if got_dim == 1 else 'FAIL'} encode UTMASTG.2D dim field={got_dim} (exp 1)")
ok &= got_dim == 1
got_urb = (lo >> 32) & 0x3f                    # Ra_URb [37:32]
got_ura = (lo >> 24) & 0x3f                    # Sa [29:24]
print(f"{'ok ' if (got_urb, got_ura) == (8, 16) else 'FAIL'} "
      f"encode operands URb={got_urb} URa={got_ura} (exp 8, 16)")
ok &= (got_urb, got_ura) == (8, 16)

if not HAVE_GPU:
    sys.exit(0)

# --- host-side tensor map over the destination -----------------------------
lib = _cuda()
lib.cuTensorMapEncodeTiled.restype = ctypes.c_int
lib.cuTensorMapEncodeTiled.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]

def make_tmap(d_dst):
    shape = (ctypes.c_uint64 * 2)(16, 16)
    stride = (ctypes.c_uint64 * 2)(16 * 2, 0)
    box = (ctypes.c_uint32 * 2)(16, 8)
    elem = (ctypes.c_uint32 * 2)(1, 1)
    tmap = ctypes.create_string_buffer(128)
    rc = lib.cuTensorMapEncodeTiled(
        ctypes.cast(tmap, ctypes.c_void_p), 6, 2, ctypes.c_void_p(d_dst),
        shape, stride, box, elem, 0, 0, 0, 0)
    _check(rc)
    d_tmap = mod.devmem_alloc(128)
    mod.device_write(d_tmap, bytes(tmap.raw))
    return d_tmap

# --- hand-built UTMASTG.2D kernel ------------------------------------------
def utmastg_kernel(c0, c1):
    body = (
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
        "    LDCU.64 {UR16,UR17}, #param(tmap_ptr);[1:7:{}:1:0]\n"
        "    ELECT P0, URZ, PT;[1:7:{}:1:0]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    @!P0 BRA #label(consumer);[7:7:{}:5:1]\n"
        "    # --- producer (elected thread) ---\n"
        "    # fill shared[0x400..0x410) with 8 halfs 1..8 (contiguous)\n"
        "    MOV32I R8, 0x00020001;[7:7:{}:5:1]\n"
        "    MOV32I R9, 0x00040003;[7:7:{}:5:1]\n"
        "    MOV32I R10, 0x00060005;[7:7:{}:5:1]\n"
        "    MOV32I R11, 0x00080007;[7:7:{}:5:1]\n"
        "    STS.128 [RZ+0x400], {R8,R9,R10,R11};[7:7:{3}:5:1]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    UMOV UR8, 0x400;[1:7:{}:1:0]\n"      # shared source (URb+0)
        f"    UMOV UR9, 0x{c1:X};[1:7:{{}}:1:0]\n"  # coord[1] (dim1)
        f"    UMOV UR10, 0x{c0:X};[1:7:{{}}:1:0]\n"  # coord[0] (dim0)
        "    UTMASTG.2D [UR8], [UR16];[7:2:{1}:1:0]\n"
        "    UTMACMDFLUSH;[7:0:{1}:1:0]\n"
        "    DEPBAR.LE SB0, 0x0;[7:7:{1}:5:1]\n"
        "    #def_label(consumer)\n"
        "    EXIT;[7:7:{}:5:0]\n")
    return "#fn k(tmap_ptr<8>, out<8>) {\n    #pragma SHARED(0x4000)\n" + body + "}\n"

mod = CudaModule(assemble(utmastg_kernel(0, 0)))
d_dst = mod.devmem_alloc(16 * 16 * 2)
mod.device_write(d_dst, bytes(16 * 16 * 2))
d_tmap = make_tmap(d_dst)


def run_store(c0, c1):
    src = utmastg_kernel(c0, c1)
    m = CudaModule(assemble(src))
    dd = m.devmem_alloc(16 * 16 * 2)
    m.device_write(dd, bytes(16 * 16 * 2))
    dt = make_tmap(dd)
    d = m.devmem_alloc(64)
    m.launch("k", grid=(1,), block=(32,), args=[dt, d], shared_mem=0x4000)
    m.synchronize()
    return struct.unpack("<32H", m.device_read(dd, 64))

# tile at {0,0}: box {16,8} -> row 0 cols 0..7 = shared halfs 1..8
v = run_store(0, 0)
check("UTMASTG.2D store row0 = shared[0..7] (coords 0,0)",
      list(v[0:8]), [1, 2, 3, 4, 5, 6, 7, 8])

# tile at {0,8}: dim1 offset 8 -> row 0 cols 8..15 = shared halfs 1..8
v = run_store(0, 8)
check("UTMASTG.2D store row0 cols 8..15 (coords 0,8)",
      list(v[8:16]), [1, 2, 3, 4, 5, 6, 7, 8])
check("UTMASTG.2D coords {0,8}: cols 0..7 untouched",
      list(v[0:8]), [0] * 8)

print(f"\n=== UTMASTG.2D: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
