import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble
from assembler.runner import reset_context


# Direct XU/MUFU self-forwarding probe for sm_120.
#
# R10 is first settled to 4.0f.  The producer computes rcp(2.0)=0.5f into
# R10, and the dependent consumer computes rcp(R10) without a scoreboard
# wait.  A stale read produces 0.25f; a fresh read produces 2.0f.
#
# Comparing this boundary with MUFU->IADD3/FADD (first fresh near gap 8)
# distinguishes an XU-local result path from ordinary RF visibility.  Gap S
# means the consumer is issued S nominal stall cycles after the producer.

POISON_IN = 0x40800000       # 4.0f
PRODUCER_IN = 0x40000000     # 2.0f
STALE_OUT = 0x3E800000       # rcp(4.0) = 0.25f
FRESH_OUT = 0x40000000       # rcp(rcp(2.0)) = 2.0f
GAPS = [0] + list(range(1, 17)) + [24, 32]


CONSUMERS = {
    "mufu": "MUFU.RCP R20, R10",
    "int": "IADD3 R20, R10, RZ, RZ",
    "fp": "FADD R20, R10, RZ",
    "lsu": "",
}


def kernel(gaps, consumer="mufu"):
    lines = [
        "#fn mufu_self(out<8>) {",
        "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
        "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]",
             f"    MOV32I R1, 0x{PRODUCER_IN:08x};[7:7:{{1,2}}:5:1]",
    ]
    for i, gap in enumerate(gaps):
        lines += [
            f"    MOV32I R10, 0x{POISON_IN:08x};[7:7:{{}}:5:1]",
            "    NOP;[7:7:{}:8:1]",
            "    NOP;[7:7:{}:8:1]",
        ]
        if gap:
            # No wr barrier: deliberately test physical visibility.
            lines.append("    MUFU.RCP R10, R1;[7:7:{}:1:1]")
            lines += ["    NOP;[7:7:{}:1:1]"] * (gap - 1)
        if consumer == "lsu":
            # Direct LSU late-data-collector consumer.  No read barrier is
            # claimed and there is no producer scoreboard wait.
            lines.append(
                f"    STG.E.STRONG.GPU [{{R6,R7}}+0x{4*i:x}], "
                "R10;[7:7:{}:1:1]")
        else:
            # Wait only for the consumer, so the stored observation is valid.
            lines += [
                f"    {CONSUMERS[consumer]};[1:7:{{}}:5:1]",
                "    IADD3 R21, R20, RZ, RZ;[7:7:{1}:5:1]",
                f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{4*i:x}], R21;[0:1:{{2}}:1:0]",
            ]
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def run(gaps, consumer="mufu"):
    reset_context()
    mod = CudaModule(assemble(kernel(gaps, consumer), check_deps=False))
    ptr = mod.devmem_alloc(4096)
    mod.device_write(ptr, bytes(4096))
    mod.launch("mufu_self", grid=(1,), block=(1,), args=[ptr])
    mod.synchronize()
    vals = struct.unpack(f"<{len(gaps)}I", mod.device_read(ptr, 4 * len(gaps)))
    mod.devmem_free(ptr)
    return vals


def cls(value, stale, fresh):
    if value == stale:
        return "S"
    if value == fresh:
        return "F"
    return "?"


try:
    # One gap per kernel avoids phase carry-over from a preceding XU request.
    # That carry-over is itself observable (and deliberately studied by the
    # queue probes), but would obscure the producer->consumer boundary here.
    results = {}
    for consumer in CONSUMERS:
        results[consumer] = [[run([gap], consumer)[0] for gap in GAPS]
                             for _ in range(3)]
except RuntimeError as exc:
    print(f"skip GPU checks (no CUDA driver/GPU): {exc}")
    raise SystemExit(0)

print("MUFU.RCP producer, deliberately no producer scoreboard wait")
print("gap       : " + " ".join(f"{x:2d}" for x in GAPS))
ok = True
for consumer, reps in results.items():
    stale = STALE_OUT if consumer == "mufu" else POISON_IN
    fresh = FRESH_OUT if consumer == "mufu" else 0x3F000000
    states = [cls(x, stale, fresh) for x in reps[0]]
    det = all(row == reps[0] for row in reps[1:])
    min_gap = next((GAPS[i] for i in range(1, len(GAPS))
                    if all(x == "F" for x in states[i:])), None)
    print(f"{consumer:10}: " + "  ".join(states)
          + f"  det={det} permanent={min_gap}")
    unknown = [(GAPS[i], hex(x)) for i, x in enumerate(reps[0])
               if cls(x, stale, fresh) == "?"]
    if unknown:
        print("unknown:", unknown)
    ok &= states[0] == "S" and states[-1] == "F" and det and min_gap is not None
raise SystemExit(0 if ok else 1)
