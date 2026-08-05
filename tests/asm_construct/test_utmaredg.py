import ctypes, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule
from assembler.runner import _cuda, _check

# ---------------------------------------------------------------------------
# UTMAREDG.2D — hand-built SASS reproduction of the tensor TMA reduction
# store (cp.reduce.async.bulk.tensor.2d.global.shared::cta.<op>.tile.bulk_group).
#
# Identical framing to UTMASTG (shared -> global, bulk_group completion via
# UTMACMDFLUSH + DEPBAR.LE, no mbarrier), plus the RedOp modifier [89:87].
# URb block = {UR8 = shared source, UR9 = coord[1] (dim1),
#              UR10 = coord[0] (dim0)}.  The element type comes from the
# tensor-map descriptor (UINT32 here, so all 8 RedOps are legal).
#
# Verified on sm_120 (RTX 5090, CUDA 13.0 / driver 580.65): dst[i] is reduced
# element-wise with the shared tile, dst[i] = dst[i] <op> src[i].
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

REDOP = {"ADD": 0, "MIN": 1, "MAX": 2, "INC": 3, "DEC": 4,
         "AND": 5, "OR": 6, "XOR": 7}

# --- offline: encodings ----------------------------------------------------
lo, hi = assemble_flat("UTMAREDG.2D.ADD [UR8], [UR16];[7:2:{1}:1:0]")[0]
assert lo & 0xFFF == 0x3b6 and (hi >> 27) & 1 == 1, hex(lo)
got_dim = (hi >> 15) & 7
print(f"{'ok ' if got_dim == 1 else 'FAIL'} encode UTMAREDG.2D dim field={got_dim} (exp 1)")
ok &= got_dim == 1
for op, want in REDOP.items():
    lo, hi = assemble_flat(f"UTMAREDG.2D.{op} [UR8], [UR16];[7:2:{{1}}:1:0]")[0]
    got = (hi >> 23) & 7                       # Pnz [89:87] = hi bits 25:23
    good = got == want
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} encode UTMAREDG.2D.{op:<3} Pnz={got} (exp {want})")

if not HAVE_GPU:
    sys.exit(0)

# --- host-side tensor map (UINT32 over the destination) ---------------------
lib = _cuda()
lib.cuTensorMapEncodeTiled.restype = ctypes.c_int
lib.cuTensorMapEncodeTiled.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]

# shape {8,8} u32, stride {32}, box {4,4} -> 4x4 tile = 64 bytes
def make_tmap(d_dst):
    shape = (ctypes.c_uint64 * 2)(8, 8)
    stride = (ctypes.c_uint64 * 2)(8 * 4, 0)
    box = (ctypes.c_uint32 * 2)(4, 4)
    elem = (ctypes.c_uint32 * 2)(1, 1)
    tmap = ctypes.create_string_buffer(128)
    rc = lib.cuTensorMapEncodeTiled(
        ctypes.cast(tmap, ctypes.c_void_p), 2, 2, ctypes.c_void_p(d_dst),
        shape, stride, box, elem, 0, 0, 0, 0)     # UINT32 = 2
    _check(rc)
    d_tmap = mod.devmem_alloc(128)
    mod.device_write(d_tmap, bytes(tmap.raw))
    return d_tmap

# --- hand-built UTMAREDG.2D kernel ------------------------------------------
def utmaredg_kernel(op, src_vals, dst_init):
    sts = "".join(
        f"    MOV32I R{16 + i}, 0x{v:08X};[7:7:{{}}:5:1]\n"
        f"    STS [RZ+0x{0x400 + 4 * i:X}], R{16 + i};[7:7:{{3}}:5:1]\n"
        for i, v in enumerate(src_vals))
    body = (
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
        "    LDCU.64 {UR16,UR17}, #param(tmap_ptr);[1:7:{}:1:0]\n"
        "    ELECT P0, URZ, PT;[1:7:{}:1:0]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    @!P0 BRA #label(consumer);[7:7:{}:5:1]\n"
        "    # --- producer (elected thread) ---\n"
        + sts +
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    UMOV UR8, 0x400;[1:7:{}:1:0]\n"      # shared source (URb+0)
        "    UMOV UR9, 0x0;[1:7:{}:1:0]\n"        # coord[1] (dim1) = 0
        "    UMOV UR10, 0x0;[1:7:{}:1:0]\n"       # coord[0] (dim0) = 0
        f"    UTMAREDG.2D.{op} [UR8], [UR16];[7:2:{{1}}:1:0]\n"
        "    UTMACMDFLUSH;[7:0:{1}:1:0]\n"
        "    DEPBAR.LE SB0, 0x0;[7:7:{1}:5:1]\n"
        "    #def_label(consumer)\n"
        "    EXIT;[7:7:{}:5:0]\n")
    return "#fn k(tmap_ptr<8>, out<8>) {\n    #pragma SHARED(0x4000)\n" + body + "}\n"

mod = CudaModule(assemble(utmaredg_kernel("ADD", [1, 2, 3, 4], [0] * 4)))


def run_red(op, src_vals, dst_init):
    src = utmaredg_kernel(op, src_vals, dst_init)
    m = CudaModule(assemble(src))
    dd = m.devmem_alloc(8 * 8 * 4)
    m.device_write(dd, struct.pack("<64I", *(dst_init * 16)))
    dt = make_tmap(dd)
    d = m.devmem_alloc(64)
    m.launch("k", grid=(1,), block=(32,), args=[dt, d], shared_mem=0x4000)
    m.synchronize()
    return list(struct.unpack("<8I", m.device_read(dd, 32)))

# --- element-wise reduce into pre-initialized dst ---------------------------
SRC = [0x10, 0x30, 0x50, 0x70]
DST = [0x20, 0x20, 0x20, 0x20]

check("ADD  dst+src", run_red("ADD", SRC, DST)[:4],
      [0x30, 0x50, 0x70, 0x90])
check("MIN  min(dst,src)", run_red("MIN", SRC, DST)[:4],
      [0x10, 0x20, 0x20, 0x20])
check("MAX  max(dst,src)", run_red("MAX", SRC, DST)[:4],
      [0x20, 0x30, 0x50, 0x70])
check("AND  dst&src", run_red("AND", SRC, DST)[:4],
      [0x00, 0x20, 0x00, 0x20])
check("OR   dst|src", run_red("OR", SRC, DST)[:4],
      [0x30, 0x30, 0x70, 0x70])
check("XOR  dst^src", run_red("XOR", SRC, DST)[:4],
      [0x30, 0x10, 0x70, 0x50])

# INC/DEC: source element caps (classic atomic semantics, like UBLKRED)
check("INC  dst<src -> dst+1", run_red("INC", [0x40] * 4, [0x10] * 4)[:4],
      [0x11, 0x11, 0x11, 0x11])
check("INC  dst>=src -> 0", run_red("INC", [0x40] * 4, [0x40] * 4)[:4],
      [0x00, 0x00, 0x00, 0x00])
check("DEC  dst=0 -> src", run_red("DEC", [0x40] * 4, [0x00] * 4)[:4],
      [0x40, 0x40, 0x40, 0x40])
check("DEC  0<dst<=src -> dst-1", run_red("DEC", [0x40] * 4, [0x20] * 4)[:4],
      [0x1f, 0x1f, 0x1f, 0x1f])

print(f"\n=== UTMAREDG.2D: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
