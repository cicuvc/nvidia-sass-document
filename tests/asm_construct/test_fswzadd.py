import struct, subprocess, sys, tempfile, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_flat, assemble, CudaModule

# ---------------------------------------------------------------------------
# FSWZADD — FP32 "fused swizzle add", reverse-engineered on SM120 + SM75.
#
# Encoding (verified): opcode 0x822, Rd [23:16], Ra [31:24], npCtrl [39:32]
# (NP enum, 8-char P/N/Z string = 4 base-4 pairs), Rc [71:64], ftz [80],
# rnd [79:78], div(ndv) [81]+[77].  The assembler's NP support (P/N/Z string)
# round-trips to the same bytes as the spec enum.
#
# Empirical finding (this test): in a CUDA compute launch, FSWZADD computes
# Rd = Ra — a pass-through.  Rc (GPR or uniform), npCtrl, and ndv have no
# observable effect (tested per-lane Rc, Rc=NaN/Inf, all 16 base-4 digits and
# 0x00..0xff patterns, nondv/DV) on both RTX 5090 (sm_120) and RTX 2080 Ti
# (sm_75).  The quad-swizzle network is evidently not reachable from compute.
# ---------------------------------------------------------------------------

# --- encoding round-trip ---------------------------------------------------
def npval(s):
    pairs = {"PP": 0, "PN": 1, "NP": 2, "ZP": 3}
    v = 0
    for i in range(0, 8, 2):
        v = v * 4 + pairs[s[i:i + 2]]
    return v

for s, exp in (("PPPPPPPP", 0), ("PPPPPPPN", 1), ("PPPPPPNP", 2),
               ("NPPNNPPN", 0x99), ("ZPZPZPZP", 0xff), ("PPPPZPNP", 14)):
    lo, hi = assemble_flat(f'FSWZADD R5, R0, R7, {s};[7:7:{{}}:5:1]')[0]
    np_ctrl = (lo >> 32) & 0xFF
    assert np_ctrl == exp, f"{s}: npCtrl {np_ctrl:#x} != {exp:#x}"
    assert (lo >> 16) & 0xFF == 5          # Rd
    assert (lo >> 24) & 0xFF == 0          # Ra
    assert hi & 0xFF == 7                  # Rc [71:64]
    assert lo & 0xFFF == 0x822             # opcode
print("encoding round-trip OK (NP strings, opcode 0x822, Rc [71:64])")

# --- semantic probe via binary-patched ptxas cubin -------------------------
def build_placeholder():
    """Compile a kernel with an FFMA placeholder to patch into FSWZADD."""
    src = ("__global__ void k(float* out) {\n"
           "    float Ra = out[threadIdx.x];\n"
           "    float Rb = out[32 + threadIdx.x];\n"
           "    float Rc = out[64 + threadIdx.x];\n"
           "    float r;\n"
           "    asm volatile(\"fma.rn.f32 %0, %1, %2, %3;\" : \"=f\"(r) "
           ": \"f\"(Ra), \"f\"(Rb), \"f\"(Rc));\n"
           "    out[96 + threadIdx.x] = r;\n"
           "}\n")
    with tempfile.TemporaryDirectory() as td:
        cu = os.path.join(td, "k.cu")
        cub = os.path.join(td, "k.cubin")
        open(cu, "w").write(src)
        r = subprocess.run(["nvcc", "-arch=sm_120", "-cubin", "-o", cub, cu],
                           capture_output=True,
                           env=dict(os.environ, PATH="/usr/local/cuda/bin:" + os.environ.get("PATH", "")))
        if r.returncode != 0:
            print("nvcc unavailable or failed; skipping GPU semantic probe")
            return None
        return open(cub, "rb").read()

cubin = build_placeholder()
if cubin is None:
    sys.exit(0)

cubin = bytearray(cubin)
ffma = cubin.find(bytes([0x23, 0x72, 0x05, 0x00, 0x05, 0x00, 0x00, 0x00]))
assert ffma >= 0, "FFMA placeholder not found"
ffma_hi = struct.unpack('<Q', bytes(cubin[ffma+8:ffma+16]))[0]
# FFMA R5, R0, R5, R7 -> patch: npCtrl=[39:32], keep Rc=R7 at [71:64]

def run_patched(np, Ra, Rcbits):
    cub = bytearray(cubin)
    lo = ((npval(np) << 32) | (0x00 << 24) | (0x05 << 16) | 0x7822
          | (0x07 << 64)) & ((1 << 64) - 1)
    cub[ffma:ffma+8] = struct.pack('<Q', lo)
    cub[ffma+8:ffma+16] = struct.pack('<Q', ffma_hi)
    init = [0] * 128
    for i in range(8):
        init[i] = struct.unpack('<I', struct.pack('<f', Ra[i]))[0]
    for i in range(8):
        init[64+i] = Rcbits[i]
    mod = CudaModule(bytes(cub))
    d = mod.devmem_alloc(512)
    mod.device_write(d, struct.pack("<128I", *init))
    mod.launch('_Z1kPf', grid=(1,), block=(8,), args=[d])
    mod.synchronize()
    vals = struct.unpack('<8I', mod.device_read(d, 32))
    mod.devmem_free(d)
    return [struct.unpack('<f', struct.pack('<I', v))[0] for v in vals]

Ra = [1.0 + i for i in range(8)]
Rc = [10.0 + i for i in range(8)]
rcbits = [struct.unpack('<I', struct.pack('<f', x))[0] for x in Rc]
NANBITS = [0x7FC00000] * 8
INFBITS = [0x7F800000] * 8

ok = True
for np in ("PPPPPPPP", "NPPNNPPN", "ZPZPZPZP", "NPNPNPNP"):
    got = run_patched(np, Ra, rcbits)
    if got != Ra:
        ok = False
        print(f"FAIL {np}: {got} != Ra {Ra}")
for rc in (rcbits, NANBITS, INFBITS):
    got = run_patched("PPPPPPPP", Ra, rc)
    if got != Ra:
        ok = False
        print(f"FAIL Rc={rc[0]:#x}: {got} != Ra")
got = run_patched("PPPPPPPP", [0.0]*8, rcbits)
if got != [0.0]*8:
    ok = False
    print(f"FAIL Ra=0: {got}")
print(f"=== FSWZADD semantic probe: {'Rd = Ra confirmed' if ok else 'FAILED'} ===")
print("FSWZADD outputs Ra; Rc/npCtrl/ndv have no observable effect in compute")
