import ctypes, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import _cuda, _check
from tools.tma_helper import cuTensorMapEncodeTiled, cuTensorMapEncodeIm2col

# ---------------------------------------------------------------------------
# CUtensorMap bit-layout regression: forward-constructed descriptors
# (tools/tma_helper.py) must match cuTensorMapEncode* byte-for-byte, and a
# helper-built descriptor must actually drive UTMALDG on the GPU.
# Field table: notes/sm90/arch/cutensormap.md
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {name:<58} {got} (exp {want})")

try:
    _ = CudaModule(assemble("#fn k() { EXIT;[7:7:{}:5:0] }"))
    HAVE_GPU = True
except RuntimeError:
    HAVE_GPU = False
    print("--- no CUDA device; driver-comparison and GPU checks SKIPPED ---")

# --- offline: hardcoded descriptor words (from probe evidence) ------------
buf = ctypes.create_string_buffer(128)
_ = cuTensorMapEncodeTiled(
    buf, 6, 2, 0x0BE00000, [16, 16], [32, 0], [16, 8], [1, 1])
w = struct.unpack("<32I", buf.raw)
check("helper base w2", hex(w[2]), "0x310")
check("helper base w3 (stride/16)", hex(w[3]), "0x2")
check("helper base w8 (dim0-1)", hex(w[8]), "0xf")
check("helper base w13 (box0-1<<24)", hex(w[13]), "0xf000000")
check("helper base w14 (box1-1)", hex(w[14]), "0x7")
check("helper base w16 (tile bytes)", hex(w[16]), "0x100")
check("helper base w18", hex(w[18]), "0x10")
_ = cuTensorMapEncodeTiled(
    buf, 6, 3, 0x0BE00000, [16, 16, 256], [32, 16, 0], [16, 8, 8], [1, 1, 1])
w = struct.unpack("<32I", buf.raw)
check("helper wide bit (tot 65536)", hex(w[2]), "0x200320")

if not HAVE_GPU:
    sys.exit(0 if ok else 1)

# --- driver comparison battery ---------------------------------------------
lib = _cuda()
lib.cuTensorMapEncodeTiled.restype = ctypes.c_int
lib.cuTensorMapEncodeTiled.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
lib.cuTensorMapEncodeIm2col.restype = ctypes.c_int
lib.cuTensorMapEncodeIm2col.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
    ctypes.c_uint, ctypes.c_uint,
    ctypes.POINTER(ctypes.c_uint32),
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]

p = ctypes.c_void_p()
_check(lib.cuMemAlloc(ctypes.byref(p), 1 << 20))
ADDR = p.value or 0

def drv_tiled(dtype, rank, dim, stride, box, elem, il=0, sw=0, promo=0, oob=0):
    d = (ctypes.c_uint64 * rank)(*dim)
    s = (ctypes.c_uint64 * rank)(*stride)
    b = (ctypes.c_uint32 * rank)(*box)
    e = (ctypes.c_uint32 * rank)(*elem)
    t = ctypes.create_string_buffer(128)
    rc = lib.cuTensorMapEncodeTiled(
        ctypes.cast(t, ctypes.c_void_p), dtype, rank, ctypes.c_void_p(ADDR),
        d, s, b, e, il, sw, promo, oob)
    return None if rc else t.raw

def drv_i2c(rank, dim, stride, lo, hi, cpp, ppc, elem, dtype=6):
    d = (ctypes.c_uint64 * rank)(*dim)
    s = (ctypes.c_uint64 * rank)(*stride)
    n = rank - 2
    l = (ctypes.c_int * n)(*lo)
    h = (ctypes.c_int * n)(*hi)
    e = (ctypes.c_uint32 * rank)(*elem)
    t = ctypes.create_string_buffer(128)
    rc = lib.cuTensorMapEncodeIm2col(
        ctypes.cast(t, ctypes.c_void_p), dtype, rank, ctypes.c_void_p(ADDR),
        d, s, l, h, cpp, ppc, e, 0, 0, 0, 0)
    return None if rc else t.raw

cases = []
for dt, kw in [
    (0, dict(dim=[16,16], stride=[16,0], box=[16,8], elem=[1,1])),
    (1, dict(dim=[16,16], stride=[32,0], box=[16,8], elem=[1,1])),
    (2, dict(dim=[16,16], stride=[64,0], box=[16,8], elem=[1,1])),
    (6, dict(dim=[16,16], stride=[32,0], box=[16,8], elem=[1,1])),
    (8, dict(dim=[16,16], stride=[128,0], box=[16,8], elem=[1,1])),
    (9, dict(dim=[16,16], stride=[32,0], box=[16,8], elem=[1,1])),
    (11, dict(dim=[16,16], stride=[64,0], box=[16,8], elem=[1,1])),
    (13, dict(dim=[256,16], stride=[128,0], box=[128,8], elem=[1,1])),
    (14, dict(dim=[256,16], stride=[256,0], box=[128,8], elem=[1,1])),
    (15, dict(dim=[256,16], stride=[256,0], box=[128,8], elem=[1,1])),
]:
    cases.append(("tiled dtype%d" % dt, drv_tiled(dt, 2, **kw),
                  lambda buf, dt=dt, kw=kw: cuTensorMapEncodeTiled(
                      buf, dt, 2, ADDR, kw["dim"], kw["stride"],
                      kw["box"], kw["elem"])))
cases.append(("tiled r1", drv_tiled(6, 1, [16], [0], [16], [1]),
              lambda buf: cuTensorMapEncodeTiled(
                  buf, 6, 1, ADDR, [16], [0], [16], [1])))
cases.append(("tiled r3", drv_tiled(6, 3, [16,16,8], [32,16,0], [16,8,8],
                                    [1,1,1]),
              lambda buf: cuTensorMapEncodeTiled(
                  buf, 6, 3, ADDR, [16,16,8], [32,16,0], [16,8,8], [1,1,1])))
cases.append(("tiled r5", drv_tiled(6, 5, [16,16,8,8,8],
                                    [32,512,4096,32768,0],
                                    [8,8,8,8,8], [1]*5),
              lambda buf: cuTensorMapEncodeTiled(
                  buf, 6, 5, ADDR, [16,16,8,8,8], [32,512,4096,32768,0],
                  [8,8,8,8,8], [1]*5)))
for sw in [1, 2, 3, 4, 5, 6]:
    cases.append((f"tiled sw{sw}",
                  drv_tiled(6, 2, [16,16], [32,0], [16,8], [1,1], sw=sw),
                  lambda buf, sw=sw: cuTensorMapEncodeTiled(
                      buf, 6, 2, ADDR, [16,16], [32,0], [16,8], [1,1],
                      swizzle=sw)))
cases.append(("tiled elem[2,3,4]", drv_tiled(6, 3, [16,16,8], [32,16,0],
                                             [16,8,8], [2,3,4]),
              lambda buf: cuTensorMapEncodeTiled(
                  buf, 6, 3, ADDR, [16,16,8], [32,16,0], [16,8,8], [2,3,4])))
cases.append(("tiled wide dim", drv_tiled(6, 2, [70000,16], [32,0], [16,8],
                                          [1,1]),
              lambda buf: cuTensorMapEncodeTiled(
                  buf, 6, 2, ADDR, [70000,16], [32,0], [16,8], [1,1])))
cases.append(("tiled il2 sw4", drv_tiled(6, 3, [16,16,16], [512,32,0],
                                         [16,8,16], [1,1,1], il=2, sw=4),
              lambda buf: cuTensorMapEncodeTiled(
                  buf, 6, 3, ADDR, [16,16,16], [512,32,0], [16,8,16],
                  [1,1,1], interleave=2, swizzle=4)))
cases.append(("i2c r3 corners", drv_i2c(3, [16,16,16], [256,32,0],
                                        [-100], [1000], 16, 64, [2,1,1]),
              lambda buf: cuTensorMapEncodeIm2col(
                  buf, 6, 3, ADDR, [16,16,16], [256,32,0], [-100], [1000],
                  16, 64, [2,1,1])))
cases.append(("i2c r4", drv_i2c(4, [16,16,16,16], [512,32,256,0],
                                [-2, 3], [8, 16], 8, 8, [1,1,1,1]),
              lambda buf: cuTensorMapEncodeIm2col(
                  buf, 6, 4, ADDR, [16,16,16,16], [512,32,256,0],
                  [-2, 3], [8, 16], 8, 8, [1,1,1,1])))
cases.append(("i2c r5 neg", drv_i2c(5, [16,16,16,16,16], [512,32,256,2048,0],
                                    [-16,-16,-16], [15,15,15], 8, 8, [1]*5),
              lambda buf: cuTensorMapEncodeIm2col(
                  buf, 6, 5, ADDR, [16,16,16,16,16], [512,32,256,2048,0],
                  [-16,-16,-16], [15,15,15], 8, 8, [1]*5)))

n = 0
for tag, drv, fn in cases:
    buf = ctypes.create_string_buffer(128)
    rc = fn(buf)
    n += 1
    name = f"helper==driver {tag}"
    if rc != 0 or drv is None:
        check(name, "encode failed", "both ok")
        continue
    check(name, buf.raw.hex(), drv.hex())

# --- UTMALDG on GPU with a helper-built descriptor --------------------------
src = struct.pack("<256H", *range(1, 257))
mod = CudaModule(assemble("#fn k() { EXIT;[7:7:{}:5:0] }"))
d_src = mod.devmem_alloc(512)
mod.device_write(d_src, src)
buf = ctypes.create_string_buffer(128)
_check(cuTensorMapEncodeTiled(
    buf, 6, 2, d_src, [16, 16], [32, 0], [16, 8], [1, 1]))
d_tmap = mod.devmem_alloc(128)
mod.device_write(d_tmap, buf.raw)

def utmaldg_kernel(c0, c1):
    body = (
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
        "    LDCU.64 {UR16,UR17}, #param(tmap_ptr);[1:7:{}:1:0]\n"
        "    UMOV UR6, 0x400;[1:7:{}:1:0]\n"
        "    UMOV UR7, 0x600;[1:7:{}:1:0]\n"
        "    ELECT P0, URZ, PT;[1:7:{}:1:0]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    @!P0 BRA #label(consumer);[7:7:{}:5:1]\n"
        "    UMOV UR12, 0x1;[1:7:{}:1:0]\n"
        "    UIADD3 UR12, UPT, UPT, -UR12, 0x100000, URZ;[7:7:{1}:5:1]\n"
        "    USHF.L.U32 UR13, UR12, 0xb, URZ;[7:7:{1}:5:1]\n"
        "    USHF.L.U32 UR12, UR12, 0x1, URZ;[7:7:{1}:5:1]\n"
        "    MOV32I R0, 256;[7:7:{}:5:1]\n"
        "    FENCE.VIEW.ASYNC.S;[1:7:{}:5:1]\n"
        "    SYNCS.EXCH.64 {URZ,URZ}, [UR7], UR12;[3:1:{1}:5:1]\n"
        "    MEMBAR.ALL.CTA;[7:7:{3}:5:1]\n"
        "    FENCE.VIEW.ASYNC.S;[2:7:{}:5:1]\n"
        "    UMOV UR8, 0x400;[1:7:{}:1:0]\n"
        "    UMOV UR9, 0x600;[1:7:{}:1:0]\n"
        f"    UMOV UR10, 0x{c1:X};[1:7:{{}}:1:0]\n"
        f"    UMOV UR11, 0x{c0:X};[1:7:{{}}:1:0]\n"
        "    SYNCS.ARRIVE.TRANS64 {RZ,RZ}, [RZ+UR7], R0;[7:1:{}:1:0]\n"
        "    UTMALDG.2D [UR8], [UR16];[7:3:{1}:12:1]\n"
        "    #def_label(consumer)\n"
        "    #def_label(poll)\n"
        "    SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR7], RZ;[1:7:{}:2:0]\n"
        "    @!P0 BRA #label(poll);[7:7:{1}:5:0]\n"
        "    #def_label(done)\n"
        "    SEL R15, RZ, 0x1, !P0;[1:7:{1}:5:1]\n"
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
    m = CudaModule(assemble(utmaldg_kernel(c0, c1)))
    d = m.devmem_alloc(64)
    m.device_write(d, bytes(64))
    m.launch("k", grid=(1,), block=(32,), args=[d_tmap, d], shared_mem=0x4000)
    m.synchronize()
    return struct.unpack("<6I", m.device_read(d, 24))

v = run_tma(0, 0)
check("helper-desc UTMALDG phase completes", v[0], 1)
check("helper-desc UTMALDG row0", list(v[2:6]),
      [0x00020001, 0x00040003, 0x00060005, 0x00080007])
v = run_tma(0, 8)
check("helper-desc UTMALDG row0 @col8", list(v[2:6]),
      [0x000a0009, 0x000c000b, 0x000e000d, 0x0010000f])

print(f"\n=== tmap_helper: {'ALL PASS' if ok else 'FAILURES'} ({n} driver cases) ===")
sys.exit(0 if ok else 1)
