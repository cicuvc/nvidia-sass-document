import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# mio_pipe -> int_pipe / fmalighter_pipe forwarding calibration (SM120)
#
# The mio producer is MUFU.RCP (scoreboard-tracked, variable-latency): its
# result lands in R10.  poison R10 = 4.0 (0x40800000, settled by MOV32I+pad);
# producer writes R10 = rcp(2.0) = 0.5 (0x3F000000).  Consumers read R10
# WITHOUT a scoreboard req (deliberate undershoot) so a pure stall gap must
# make the value visible -> stale/fresh boundary.
#   consumer int  : IADD3 R20, R10, RZ, RZ
#   consumer fmal : FADD  R20, R10, RZ        (preserves 0.5 / 4.0 bits)
# Detection: R20 == 0.5 bits (fresh) vs 4.0 bits (stale).
#
# Spec sm120 TABLE_TRUE(GPR): MIO_CBU_OPS -> ALL_OPS = 2 (the catch-all row).
# NOTE: MUFU is scoreboard-tracked; real code must req its scoreboard.  This
# sweep only answers "is a pure stall gap enough" (it is at minG, but the
# scoreboard remains the safe mechanism for variable-latency mio ops).
# See notes/sm90/arch/pipe_forwarding.md.
# ---------------------------------------------------------------------------

POISON = 0x40800000          # 4.0f bits (stale R10)
FRESH  = 0x3F000000          # 0.5f bits = rcp(2.0)
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)
SPEC_L = 2                    # MIO_CBU_OPS -> ALL_OPS

CONSUMERS = {
    "int":  "IADD3 R20, R10, RZ, RZ",
    "fmal": "FADD R20, R10, RZ",
}


def build_kernel(cons, stalls):
    cons_text = CONSUMERS[cons]
    lines = ["#fn fwd(out<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]",
             "    MOV32I R1, 0x40000000;[7:7:{}:5:1]"]
    for i, S in enumerate(stalls):
        off = 4 * i
        lines.append("    MOV32I R10, 0x40800000;[7:7:{}:5:1]")
        lines += ["    NOP;[7:7:{}:7:1]"] * 2
        if S != 0:
            lines.append("    MUFU.RCP R10, R1;[7:7:{}:1:1]")
            for _ in range(S - 1):
                lines.append("    NOP;[7:7:{}:1:1]")
        lines.append(f"    {cons_text};[7:7:{{}}:5:1]")
        lines += ["    NOP;[7:7:{}:5:1]"] * 8
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R20;[0:1:{{1,2}}:1:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("}")
    return "\n".join(lines)


def run(cons, stalls):
    reset_context()
    cubin = assemble(build_kernel(cons, stalls), check_deps=False)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("fwd", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    vals = struct.unpack("<%dI" % len(stalls), mod.device_read(d, len(stalls) * 4))
    mod.devmem_free(d)
    return vals


def classify(v):
    return "F" if v == FRESH else ("S" if v == POISON else "?")


try:
    run("int", [8])
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("mio->int/fmal (MUFU producer, no scoreboard req) forwarding (SM120); "
      "poison=4.0f fresh=0.5f")
print("stall  : " + " ".join(f"{s:3d}" for s in STALLS[SWEEP]))

ok = True
for cons, tag in (("int", "MUFU->IADD3"), ("fmal", "MUFU->FADD ")):
    reps = [run(cons, STALLS) for _ in range(3)]
    maj = "".join("F" if sum(1 for r in reps if classify(r[i]) == "F") >= 2
                  else ("S" if sum(1 for r in reps if classify(r[i]) == "S") >= 2
                        else "?")
                  for i in range(len(STALLS)))
    det = all(r == reps[0] for r in reps)
    sweep = maj[SWEEP]
    minG = None
    for j in range(len(sweep)):
        if all(c == "F" for c in sweep[j:]):
            minG = STALLS[SWEEP][j]
            break
    print(f"{tag}  Lspec={SPEC_L} [{'det' if det else 'var'}]: {sweep}")
    if minG is not None:
        print(f"        minG stall={minG} (real gap ~{minG + 0.4:.1f}cyc), "
              f"overlap Lspec-minG={SPEC_L - minG}")
    good = True
    if maj[0] != "S":
        good = False
        print("        FAIL: poison-only control should read stale")
    if maj[-1] != "F":
        good = False
        print("        FAIL: huge-gap control (stall 30) should be fresh")
    if minG is None or minG < 1 or minG > 16:
        good = False
        print("        FAIL: could not resolve minG in the sweep range")
    # the point of this edge: mio does NOT fast-forward like the GPR producers
    # (int/fmal/udp forward in 2-3).  The spec's catch-all MIO_CBU->ALL_OPS=2
    # is too optimistic; measured minG is much larger (>=5).
    if minG is None or minG < 5:
        good = False
        print(f"        FAIL: expected mio->* to be slow (minG>=5, "
              f"not fast-forwarded like GPR producers)")
    if not det:
        print("        WARN: boundary not deterministic")
    ok &= good

print("\n=== mio->int/fmal forwarding calibration: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
