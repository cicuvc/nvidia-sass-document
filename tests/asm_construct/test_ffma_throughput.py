import sys, struct, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# FFMA throughput measurement (SM120), same independent-chain method as
# test_mufu_throughput.py.
#
# Chain of INDEPENDENT FFMA ops: all read the same sources (R10, R10), write
# DIFFERENT destination registers (R40..R78, reuse distance 20), so no
# dependency stalls.  CS2R SR_CLOCKLO/HI around the chain.
#
# Result: FFMA (and FMUL/FADD/neg/imm variants) measure the SAME as the
# NOP/MOV/IADD3 baseline (~6.18 cyc/op) — ZERO marginal cost.  Unlike MUFU
# (+2.01 cyc/op), a single-warp stream of independent FMAs runs at the pure
# instruction-issue floor; the FMA pipe is not the bottleneck (it accepts
# well more than 1/cycle, so single-warp issue saturates it).  In other
# words: FFMA has no throughput penalty over NOP — it fully rides the issue
# rate, consistent with fmalighter_pipe being a dual-issue/high-throughput
# unit (MUFU's mio/SFU pipe is the one that adds +2 cyc/op).
# ---------------------------------------------------------------------------

def build_kernel(body_insts, N=96):
    dsts = [40 + 2 * i for i in range(20)]
    lines = ["#fn thr(buf<8>) {",
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


def m(body, reps=4):
    return statistics.mean(run(body) for _ in range(reps))


print("=== FFMA throughput (SM120, independent chain) ===")
ONE = struct.unpack("<I", struct.pack("<f", 1.0))[0]

nop = m("NOP")
print(f"  NOP baseline    {nop:.3f} cyc/op")

tests = (
    ("FFMA",     "FFMA R{d}, R10, R10, RZ"),
    ("FFMA.neg", "FFMA R{d}, -R10, R10, R10"),
    ("FFMA.imm", f"FFMA R{{d}}, R10, R10, 0f{ONE:08x}"),
    ("FMUL",     "FMUL R{d}, R10, R10"),
    ("FADD",     "FADD R{d}, R10, R10"),
)
ok = True
for name, fmt in tests:
    v = m(fmt)
    delta = v - nop
    print(f"  {name:<8} {v:.3f} cyc/op   delta={delta:+.3f}")
    # FFMA should ride the baseline: |delta| < 0.5 (unlike MUFU's +2.01)
    if abs(delta) > 0.5:
        ok = False

print(f"\n=== FFMA rides issue baseline (delta ~0, not MUFU's +2): {'YES' if ok else 'NO'} ===")
print("FFMA = 0 marginal throughput cost over NOP; contrast MUFU = +2.01 cyc/op")
sys.exit(0 if ok else 1)
