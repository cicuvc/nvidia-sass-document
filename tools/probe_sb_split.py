#!/usr/bin/env python3
"""Probe whether the SM120 scheduler splits a warp at a divergent scoreboard
wait. Builds a ptxas kernel with a predicated-load placeholder (branch),
binary-patches it into a true `@P0 LDG` (half lanes load) vs an all-lanes
LDG, and prints the ncu long-scoreboard stall / duration for both. See
AUTO_DEP_ANALYSIS.md 5b.1. Requires nvcc + ncu (root for counters).
"""
import struct, subprocess, sys, tempfile, os

SRC = r"""
__global__ void k(const float* slow, float* out) {
    int lane = threadIdx.x & 31;
    float v = 0.0f;
    asm volatile("{\n\t.reg .pred p;\n\tsetp.eq.b32 p, %1, 0;\n\t@p ld.global.f32 %0, [%2];\n\t}"
                 : "+f"(v) : "r"(lane & 1), "l"(slow + ((lane*4194304) & 0xFFFFFF)));
    float acc = v;
    #pragma unroll 1
    for (int i = 0; i < 20; i++) acc += 0.001f;
    out[lane] = acc;
}
"""

def build(variant):
    with tempfile.TemporaryDirectory() as td:
        cu = os.path.join(td, "k.cu"); cub = os.path.join(td, "k.cubin")
        open(cu, "w").write(SRC)
        env = dict(os.environ, PATH="/usr/local/cuda/bin:" + os.environ.get("PATH", ""))
        subprocess.run(["nvcc", "-arch=sm_120", "-cubin", "-o", cub, cu], check=True, env=env)
        b = bytearray(open(cub, "rb").read())
        off = b.find(bytes([0x47, 0x09, 0x04, 0, 0, 0, 0, 0]))  # @P0 BRA
        assert off >= 0, "BRA placeholder not found"
        # @P0 LDG (half lanes) or LDG (all lanes); NOP the old load
        lo = 0x0000000402070981 if variant == "pred" else 0x0000000402077981
        hi = 0x000f44000c1e1900
        b[off:off+8] = struct.pack('<Q', lo); b[off+8:off+16] = struct.pack('<Q', hi)
        b[off+16:off+24] = struct.pack('<Q', 0x0000000000007918)
        b[off+24:off+32] = struct.pack('<Q', 0x000fe20000000000)
        p = os.path.join(td, f"{variant}.cubin"); open(p, "wb").write(bytes(b))
        return p

def main():
    M = "gpu__time_duration.sum,smsp__warp_issue_stalled_long_scoreboard_per_warp_active.pct"
    for variant in ("pred", "all"):
        cub = build(variant)
        # driver: load cubin, alloc 256MB cold buffer, launch 32 threads
        drv = os.path.join(os.path.dirname(cub), "drv.py")
        open(drv, "w").write(
            "import sys,struct;sys.path.insert(0,'/home/cicuvc/cs/projects/nvidia-sass-document');"
            "from assembler import CudaModule;"
            f"m=CudaModule(open('{cub}','rb').read());"
            "s=m.devmem_alloc(1<<28);o=m.devmem_alloc(4096);"
            "m.launch('_Z1kPKfPf',grid=(1,),block=(32,),args=[s,o]);m.synchronize();"
            "m.devmem_free(s);m.devmem_free(o)")
        r = subprocess.run(["sudo", "-n", "/usr/local/cuda/bin/ncu", "--metrics", M,
                            "--launch-count", "1", "python3", drv],
                           capture_output=True, text=True)
        print(f"=== {variant} ===")
        for line in r.stdout.splitlines():
            if "duration" in line or "stalled" in line:
                print(line)

if __name__ == "__main__":
    main()
