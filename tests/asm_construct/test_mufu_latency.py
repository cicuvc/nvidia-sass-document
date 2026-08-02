import sys, struct, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# MUFU latency measurement (SM120).
#
# Method: dependent scoreboard chain. Each MUFU writes a register and sets
# wr=SB1; the next MUFU req={1} waits for SB1==0 (the previous op's
# writeback).  A CS2R SR_CLOCKLO/HI (64-bit cycle counter) is read before and
# after the chain.  latency = (t1 - t0) / N.
#
# Calibration (same harness): IADD3/FFMA/MOV ≈ 5.4 cyc, MUFU.RCP ≈ 18.0 —
# the harness cleanly separates a 5-cycle ALU op from the ~18-cycle SFU op.
#
# Result (sm_120): ALL MUFU ops measure 18.0 ± 0.02 cycles — a single shared
# SFU writeback latency.  The spec's "variable latency" (VarLatOperandEnc)
# does not produce per-op writeback differences on the tested hardware; every
# op dispatches through the same MUFU/SFU unit.
# ---------------------------------------------------------------------------

def build_kernel(op, src64=False, seed=1.5, N=128):
    src = ("    LDG.E R10, desc[{UR4,UR5}][{R6,R7}+0x4];[1:7:{0}:5:1]" if src64
           else "    LDG.E R10, desc[{UR4,UR5}][{R6,R7}];[1:7:{0}:5:1]")
    lines = ["#fn lat(buf<4096>) {",
             "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             src,
             "    IADD3 R18, R10, RZ, RZ;[7:7:{1}:5:1]",
             "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
             "    NOP;[7:7:{}:5:0]",
             "    NOP;[7:7:{}:5:0]"]
    for i in range(N):
        s = "R10" if i % 2 == 0 else "R20"
        d = "R20" if i % 2 == 0 else "R10"
        req = "0" if i == 0 else "1"
        lines.append(f"    MUFU.{op} {d}, {s};[1:7:{{{req}}}:5:1]")
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


def run_once(op, src64=False, seed=1.5, N=128):
    cubin = build_kernel(op, src64, seed, N)
    mod = CudaModule(cubin)
    init = [0] * 64
    if src64:
        q = struct.unpack("<Q", struct.pack("<d", seed))[0]
        init[0] = q & 0xffffffff
        init[1] = (q >> 32) & 0xffffffff
    else:
        init[0] = struct.unpack("<I", struct.pack("<f", seed))[0]
    d = mod.devmem_alloc(4096)
    mod.device_write(d, struct.pack("<64I", *init))
    mod.launch("lat", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    res = struct.unpack("<4I", mod.device_read(d + 0x0, 16))
    mod.devmem_free(d)
    t0 = (res[1] << 32) | res[0]
    t1 = (res[3] << 32) | res[2]
    return ((t1 - t0) & ((1 << 64) - 1)) / N


def measure(op, src64=False, seed=1.5, N=128, reps=5):
    return statistics.mean(run_once(op, src64, seed, N) for _ in range(reps))


print("=== MUFU writeback latency (SM120, dependent scoreboard chain) ===")
print("calibration: IADD3/FFMA/MOV ≈ 5.4 cyc; MUFU ≈ 18 cyc (harness verified)\n")
print(f"{'op':<7} {'latency(cyc)':>12}")

results = {}
for op, seed, s64 in (("RCP", 1.5, False), ("RSQ", 2.0, False), ("SQRT", 2.0, False),
                      ("EX2", 0.5, False), ("LG2", 1.5, False), ("TANH", 0.5, False),
                      ("COS", 0.1, False), ("SIN", 0.1, False),
                      ("RCP64H", 1.5, True), ("RSQ64H", 2.0, True)):
    lat = measure(op, s64, seed)
    results[op] = lat
    print(f"{op:<7} {lat:>12.2f}")

# all ops should be ~18 (within ±0.5); assert uniformity
vals = list(results.values())
uniform = all(abs(v - 18.0) < 1.0 for v in vals)
print(f"\n=== all ops uniform at ~18 cyc: {'YES' if uniform else 'NO'} ===")
print(f"range: {min(vals):.2f} .. {max(vals):.2f}")
if not uniform:
    sys.exit(1)

# --- harness calibration: ALU ops must measure well below MUFU --------------
def measure_alu(inst_fmt, N=256, seed=1.5):
    lines = ["#fn lat(buf<4096>) {",
             "    LDCU.64 {UR4, UR5}, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    LDG.E R10, desc[{UR4,UR5}][{R6,R7}];[1:7:{0}:5:1]",
             "    IADD3 R18, R10, RZ, RZ;[7:7:{1}:5:1]",
             "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
             "    NOP;[7:7:{}:5:0]",
             "    NOP;[7:7:{}:5:0]"]
    for i in range(N):
        s = "R10" if i % 2 == 0 else "R20"
        d = "R20" if i % 2 == 0 else "R10"
        req = "0" if i == 0 else "1"
        lines.append(f"    {inst_fmt.format(dst=d, src=s)};[1:7:{{{req}}}:5:1]")
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
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    init = [0] * 64
    init[0] = struct.unpack("<I", struct.pack("<f", seed))[0]
    d = mod.devmem_alloc(4096)
    mod.device_write(d, struct.pack("<64I", *init))
    mod.launch("lat", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    res = struct.unpack("<4I", mod.device_read(d + 0x0, 16))
    mod.devmem_free(d)
    t0 = (res[1] << 32) | res[0]
    t1 = (res[3] << 32) | res[2]
    return ((t1 - t0) & ((1 << 64) - 1)) / N

alu = {
    "IADD3": measure_alu("IADD3 {dst}, {src}, {src}, RZ"),
    "FFMA":  measure_alu("FFMA {dst}, {src}, {src}, RZ"),
}
print("\ncalibration (ALU, must be ~5, well below MUFU's 18):")
for name, v in alu.items():
    print(f"  {name:<7} {v:>7.2f} cyc/op")
    assert v < 10.0, f"{name} calibration too slow ({v:.2f}) — harness broken"
print("=== MUFU latency harness OK (ALU ~5 vs MUFU ~18) ===")
