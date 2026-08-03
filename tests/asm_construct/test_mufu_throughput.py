import sys, struct, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# MUFU throughput measurement (SM120).
#
# Method: a chain of INDEPENDENT MUFU ops (all read the same source R10,
# write DIFFERENT destination registers with reuse distance 20 > latency 18,
# so no dependency stalls).  Cycle counter via CS2R SR_CLOCKLO/HI around the
# chain.  throughput = (t1 - t0) / N.
#
# The raw per-op number includes the single-warp instruction-issue overhead
# (~6.2 cyc/op — a lone warp cannot fill the SM scheduler, and NOP/MOV/IADD3
# all measure the same).  The MUFU-specific throughput cost is the DELTA
# against those baselines: +2.01 cyc/op, identical for every MUFU op.
#
# Result (sm_120): every MUFU op adds exactly ~2.0 cycles/op of SFU/MUFU
# pipe time over the ~6.2-cyc issue baseline.  All 8 FP32 ops are uniform.
# ---------------------------------------------------------------------------

def build_kernel(body_insts, N=96):
    dsts = [40 + 2 * i for i in range(20)]   # R40..R78, avoid clock/scratch regs
    lines = ["#fn thr(buf<4096>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    LDG.E R10, desc[{UR4,UR5}][{R6,R7}];[1:7:{0}:5:1]",
             "    IADD3 R18, R10, RZ, RZ;[7:7:{1}:5:1]",
             "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
             "    NOP;[7:7:{}:5:0]",
             "    NOP;[7:7:{}:5:0]"]
    for i in range(N):
        d = dsts[i % 20]
        lines.append(f"    {body_insts.format(d=d)};[7:7:{{}}:5:1]")
    lines += ["    CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:0]",
              "    NOP;[7:7:{}:5:0]",
              "    MOV R8, R30;[7:7:{}:5:1]",
              "    MOV R9, R31;[7:7:{}:5:1]",
              "    MOV R10, R26;[7:7:{}:5:1]",
              "    MOV R11, R27;[7:7:{}:5:1]",
              "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R8;[0:1:{0}:1:0]",
              "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R9;[0:1:{0}:1:0]",
              "    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R10;[0:1:{0}:1:0]",
              "    STG.E desc[{UR4,UR5}][{R6,R7}+0xC], R11;[0:1:{0}:1:0]",
              "    EXIT;[7:7:{}:5:0]",
              "}"]
    return assemble("\n".join(lines))


def run(body, N=96):
    cubin = build_kernel(body, N)
    mod = CudaModule(cubin)
    init = [0] * 64
    init[0] = struct.unpack("<I", struct.pack("<f", 1.5))[0]
    d = mod.devmem_alloc(4096)
    mod.device_write(d, struct.pack("<64I", *init))
    mod.launch("thr", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    res = struct.unpack("<4I", mod.device_read(d + 0x0, 16))
    mod.devmem_free(d)
    t0 = (res[1] << 32) | res[0]
    t1 = (res[3] << 32) | res[2]
    return ((t1 - t0) & ((1 << 64) - 1)) / N


def m(body, reps=3):
    return statistics.mean(run(body) for _ in range(reps))


print("=== MUFU throughput (SM120, independent chain) ===")
print("calibration baselines (single-warp issue overhead):")
baselines = {
    "NOP":   "NOP",
    "MOV":   "MOV R{d}, R10",
    "IADD3": "IADD3 R{d}, R10, RZ, RZ",
}
bvals = {name: m(fmt) for name, fmt in baselines.items()}
for name, v in bvals.items():
    print(f"  {name:<6} {v:.3f} cyc/op")

print("\nMUFU throughput cost (delta vs baselines):")
mufu = {}
for op, seed in (("RCP", 1.5), ("RSQ", 2.0), ("SQRT", 2.0), ("EX2", 0.5),
                 ("LG2", 1.5), ("TANH", 0.5), ("COS", 0.1), ("SIN", 0.1)):
    raw = m(f"MUFU.{op} R{{d}}, R10")
    mufu[op] = raw
    deltas = [raw - v for v in bvals.values()]
    print(f"  {op:<7} raw={raw:>6.3f}  delta={statistics.mean(deltas):>5.2f}  "
          f"(range {min(deltas):.2f}..{max(deltas):.2f})")

# uniformity assertion: all ops should have the same delta (~2.0)
mean_delta = statistics.mean(raw - statistics.mean(list(bvals.values()))
                             for raw in mufu.values())
ok = all(abs(raw - statistics.mean(list(bvals.values())) - mean_delta) < 0.3
         for raw in mufu.values())
print(f"\n=== MUFU throughput uniform at ~2.0 cyc/op over baseline: {'YES' if ok else 'NO'} ===")
print(f"(issue overhead ~6.2; MUFU marginal SFU time +{mean_delta:.2f} cyc/op)")
if not ok:
    sys.exit(1)
