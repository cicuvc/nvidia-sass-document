import ctypes, os, struct, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import _cuda, _check, reset_context

# ---------------------------------------------------------------------------
# Cache descriptor (desc[URx] 64-bit) bit-field decode — verified SM120, RTX 5090
#
# Format 1 (createpolicy): UR4 = 0, UR5 = priority byte[31:24] | payload[23:0].
#   fractional: payload = ceil(fraction*16)-1 at [23:20].
#   range:      gsz[23:20]=(UR10-12), agr[18:12]=(addr>>UR10)&0x7f,
#               win[11:5]=primary granule span, UR10=max(ceil(log2(total))-7,12).
# Format 2 (access property / createpolicy.cvt pass-through):
#   UR4 = (base>>12)&0xffffffff; UR5 = hit/miss byte[31:24] | floor(ratio*16)<<20
#         | (num_bytes/128)[19:0].
# See notes/sm90/arch/cache_descriptor.md for the full decode.
# ---------------------------------------------------------------------------

NVCC = "/usr/local/cuda/bin/nvcc"

SRC_CP = r"""
#include <cstdint>
__global__ void fr_last_10(char* ptr, uint64_t* out, uint64_t* pol) {
    unsigned r; uint64_t p;
    asm volatile(".reg .b64 pol2;\n"
                 "createpolicy.fractional.L2::evict_last.b64 pol2, 1.0;\n"
                 "ld.global.L2::cache_hint.u32 %0, [%2], pol2;\n"
                 "mov.u64 %1, pol2;\n"
                 : "=r"(r), "=l"(p) : "l"(ptr));
    *out = r; *pol = p;
}
__global__ void fr_lastfirst_075(char* ptr, uint64_t* out, uint64_t* pol) {
    unsigned r; uint64_t p;
    asm volatile(".reg .b64 pol2;\n"
                 "createpolicy.fractional.L2::evict_last.L2::evict_first.b64 pol2, 0.75;\n"
                 "ld.global.L2::cache_hint.u32 %0, [%2], pol2;\n"
                 "mov.u64 %1, pol2;\n"
                 : "=r"(r), "=l"(p) : "l"(ptr));
    *out = r; *pol = p;
}
__global__ void rg_last_512_2048(char* ptr, uint64_t* out, uint64_t* pol) {
    unsigned r; uint64_t p;
    asm volatile(".reg .b64 pol2;\n"
                 "createpolicy.range.L2::evict_last.b64 pol2, [%2], 512, 2048;\n"
                 "ld.global.L2::cache_hint.u32 %0, [%2], pol2;\n"
                 "mov.u64 %1, pol2;\n"
                 : "=r"(r), "=l"(p) : "l"(ptr));
    *out = r; *pol = p;
}
__global__ void rg_last_1M_2M(char* ptr, uint64_t* out, uint64_t* pol) {
    unsigned r; uint64_t p;
    asm volatile(".reg .b64 pol2;\n"
                 "createpolicy.range.L2::evict_last.b64 pol2, [%2], 1048576, 2097152;\n"
                 "ld.global.L2::cache_hint.u32 %0, [%2], pol2;\n"
                 "mov.u64 %1, pol2;\n"
                 : "=r"(r), "=l"(p) : "l"(ptr));
    *out = r; *pol = p;
}
__global__ void range_split(char* p_a, char* p_ld, uint64_t* out, uint64_t* pol) {
    unsigned r; uint64_t p;
    asm volatile(".reg .b64 pol2;\n"
                 "createpolicy.range.L2::evict_last.b64 pol2, [%2], 512, 2048;\n"
                 "ld.global.L2::cache_hint.u32 %0, [%3], pol2;\n"
                 "mov.u64 %1, pol2;\n"
                 : "=r"(r), "=l"(p) : "l"(p_a), "l"(p_ld));
    *out = r; *pol = p;
}
__global__ void frac_reg(char* ptr, uint64_t* out, uint64_t* pol, float fr) {
    unsigned r; uint64_t p;
    asm volatile(".reg .b64 pol2;\n"
                 ".reg .f32 fr2;\n"
                 "mov.f32 fr2, %3;\n"
                 "createpolicy.fractional.L2::evict_last.b64 pol2, fr2;\n"
                 "ld.global.L2::cache_hint.u32 %0, [%2], pol2;\n"
                 "mov.u64 %1, pol2;\n"
                 : "=r"(r), "=l"(p) : "l"(ptr), "f"(fr));
    *out = r; *pol = p;
}
"""

# Assembler kernel that dumps the driver-placed policy word at c[0x0][0x358].
FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"
SRC_358 = f"""#fn rd358(out<8>) {{
    LDCU.64 {{UR4, UR5}}, c[0x0][0x358];[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    UMOV UR9, UR4;[7:7:{{}}:5:1]
    UMOV UR9, UR5;[7:7:{{}}:5:1]
    UMOV UR9, UR4;[7:7:{{}}:5:1]
    UMOV UR9, UR5;[7:7:{{}}:5:1]
    UMOV UR14, UR4;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
    UMOV UR15, UR5;[7:7:{{}}:5:1]
    IADD3 R3, PT, PT, RZ, UR15, RZ;[7:7:{{}}:8:1]
{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x4], R3;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""

class CUaccessPolicyWindow(ctypes.Structure):
    _fields_ = [("base_ptr", ctypes.c_void_p), ("num_bytes", ctypes.c_size_t),
                ("hitRatio", ctypes.c_float), ("hitProp", ctypes.c_int),
                ("missProp", ctypes.c_int)]
class CUstreamAttrValue(ctypes.Union):
    _fields_ = [("accessPolicyWindow", CUaccessPolicyWindow),
                ("pad", ctypes.c_ubyte * 64)]

ok = True

def check(name, got, exp):
    global ok
    good = got == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {name}: got 0x{got:016x} exp 0x{exp:016x}")

try:
    reset_context()
    mod = CudaModule(assemble(SRC_358, check_deps=False))
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

lib = _cuda()

# ---- createpolicy via ptxas (compile once, run each variant) -------------
tmp = Path(tempfile.mkdtemp(prefix="cd_"))
cu = tmp / "cp.cu"
cu.write_text(SRC_CP)
cubin = tmp / "cp.cubin"
have_ptxas = False
if os.path.exists(NVCC):
    r = subprocess.run([NVCC, "-arch=sm_120", "-O3", "-cubin",
                        "-o", str(cubin), str(cu)],
                       capture_output=True, text=True)
    have_ptxas = r.returncode == 0

if have_ptxas:
    cpmod = CudaModule(cubin.read_bytes())
    src = cpmod.devmem_alloc(1 << 20)
    out = cpmod.devmem_alloc(16); pol = cpmod.devmem_alloc(16)
    cpmod.device_write(src, bytes(1 << 20))
    srcaddr = src

    def run_cp(fname):
        mang = (f"_Z{len(fname)}{fname}PcPmS0_f" if fname == "frac_reg"
                else f"_Z{len(fname)}{fname}PcPmS0_" if fname == "two_loads"
                else f"_Z{len(fname)}{fname}PcS_PmS0_" if fname == "range_split"
                else f"_Z{len(fname)}{fname}PcPmS0_")
        cpmod.device_write(pol, bytes(16))
        cpmod.launch(mang, grid=(1,), block=(1,), args=[src, out, pol])
        cpmod.synchronize()
        return struct.unpack("<Q", cpmod.device_read(pol, 8))[0]

    def run_cp_args(mang, args):
        cpmod.device_write(pol, bytes(16))
        cpmod.launch(mang, grid=(1,), block=(1,), args=args)
        cpmod.synchronize()
        return struct.unpack("<Q", cpmod.device_read(pol, 8))[0]

    print("\n-- createpolicy descriptors --")
    check("fractional evict_last 1.0", run_cp("fr_last_10"),
          0x14f0000000000000)
    check("fractional last.first 0.75", run_cp("fr_lastfirst_075"),
          0x15b0000000000000)

    v = run_cp("rg_last_512_2048")
    ur10 = 12
    agr = (srcaddr >> ur10) & 0x7f
    exp = (0x1c << 56) | (agr << 44) | (1 << 37)          # 0x1c | agr<<12 | win<<5 in UR5
    check(f"range last 512/2048 (base 0x{srcaddr:x})", v, exp)

    v = run_cp("rg_last_1M_2M")
    ur10 = 14
    agr = (srcaddr >> ur10) & 0x7f
    win = min(((srcaddr + (1 << ur10) + 1048576 - 1) >> ur10) -
              (srcaddr >> ur10), 0x7f)
    exp = (0x1c << 56) | (2 << 52) | (agr << 44) | (win << 37)
    check(f"range last 1M/2M (win={win}, agr=0x{agr:x})", v, exp)

    # desc depends on the policy address [a], NOT the load address
    v_same_ld = run_cp_args("_Z11range_splitPcS_PmS0_", [src, src + 0x80, out, pol])
    v_pa = run_cp_args("_Z11range_splitPcS_PmS0_", [src + 0x1000, src + 0x80, out, pol])
    check("range: load-addr change keeps desc (0x%016x)" % v_same_ld,
          v_same_ld, 0x1c00002000000000)
    check("range: policy-addr [a]+0x1000 -> agr field +1",
          v_pa, 0x1c00102000000000)

    def f32b(fr):
        return struct.unpack("<Q", struct.pack("<f", fr) + b"\x00\x00\x00\x00")[0]

    v = run_cp_args("_Z8frac_regPcPmS0_f", [src, out, pol, f32b(0.75)])
    check("fractional register fraction 0.75 (dynamic desc)", v, 0x14b0000000000000)
    v = run_cp_args("_Z8frac_regPcPmS0_f", [src, out, pol, f32b(0.0625)])
    check("fractional register fraction 1/16 -> nibble 0", v, 0x1400000000000000)
    cpmod.devmem_free(src); cpmod.devmem_free(out); cpmod.devmem_free(pol)
else:
    print("skip createpolicy checks (nvcc unavailable)")

# ---- access property (stream policy window) ------------------------------
print("\n-- access-property descriptor (c[0x0][0x358]) --")
stream = ctypes.c_void_p()
_check(lib.cuStreamCreate(ctypes.byref(stream), 0))
winbuf = mod.devmem_alloc(1 << 16)

def read358(base, nbytes, ratio, hit, miss, warmup=10):
    w = CUaccessPolicyWindow(ctypes.c_void_p(base), nbytes,
                             ctypes.c_float(ratio), hit, miss)
    v = CUstreamAttrValue(); v.accessPolicyWindow = w
    if lib.cuStreamSetAttribute(stream, 1, ctypes.byref(v)) != 0:
        return None
    d = mod.devmem_alloc(16); mod.device_write(d, bytes(16))
    for _ in range(warmup):
        mod.launch("rd358", grid=(1,), block=(1,), args=[d], stream=stream.value)
        mod.synchronize()
    mod.launch("rd358", grid=(1,), block=(1,), args=[d], stream=stream.value)
    mod.synchronize()
    data = struct.unpack("<Q", mod.device_read(d, 8))[0]
    mod.devmem_free(d)
    return data

v = read358(winbuf, 4096, 1.0, 2, 1)          # persisting/streaming
exp = ((winbuf >> 12) & 0xffffffff) | (0x05f00020 << 32)
check(f"stream persisting/streaming ratio=1.0 num=4096 (base 0x{winbuf:x})", v, exp)

v = read358(winbuf, 4096, 0.5, 2, 1)
exp = ((winbuf >> 12) & 0xffffffff) | (0x05800020 << 32)
check("ratio=0.5 -> nibble 8", v, exp)

v = read358(winbuf, 8192, 1.0, 1, 0)          # streaming/normal, num 8192
exp = ((winbuf >> 12) & 0xffffffff) | (0x02f00040 << 32)
check("streaming/normal ratio=1.0 num=8192 (byte 0x02)", v, exp)

# num field rounding: ceil(num/4096)*32, min 32
v = read358(winbuf, 10000, 1.0, 2, 1)
exp = ((winbuf >> 12) & 0xffffffff) | (0x05f00060 << 32)
check("num=10000 -> ceil/4096=3 -> nf=0x60", v, exp)

v = read358(winbuf, 0, 1.0, 2, 1)
exp = 0
check("num=0 -> no window (desc=0)", v, exp)

v = read358(winbuf, 134217728, 1.0, 2, 1)     # 128 MB: 0x100000 overflows -> 0
exp = ((winbuf >> 12) & 0xffffffff) | (0x05f00000 << 32)
check("num=128MB -> 20-bit overflow encodes nf=0", v, exp)

# ratio nibble: floor(ratio*16); out-of-range ratio rejected by driver
v = read358(winbuf, 4096, 0.0625, 2, 1)
exp = ((winbuf >> 12) & 0xffffffff) | (0x05100020 << 32)
check("ratio=1/16 -> nibble 1", v, exp)

if read358(winbuf, 4096, 1.5, 2, 1) is None:
    print("ok  ratio=1.5 rejected by driver (INVALID_VALUE)")
else:
    ok = False
    print("FAIL ratio=1.5 accepted")

# base rounds down to 4 KB: +0xFFF unchanged, +0x1000 -> +1
v0 = read358(winbuf, 4096, 1.0, 2, 1)
v1 = read358(winbuf + 0xfff, 4096, 1.0, 2, 1)
v2 = read358(winbuf + 0x1000, 4096, 1.0, 2, 1)
good = v0 == v1 and v2 == v0 + 1
ok &= good
print(f"{'ok ' if good else 'FAIL'} base rounding: +0xFFF same, +0x1000 -> UR4+1 (base>>12)")

mod.devmem_free(winbuf)
_check(lib.cuStreamDestroy(stream))

print("\n=== cache descriptor decode: ALL OK ===" if ok else "\n=== CACHE DESC FAILURES ===")
sys.exit(0 if ok else 1)
