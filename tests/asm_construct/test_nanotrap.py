import sys, struct, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# NANOTRAP — hardware trap injection probe (SM120).
#
# Opcode 0x35a (R) / 0x95a (I), cbu_pipe, INST_TYPE_DECOUPLED_RD_SCBD,
# VQ_UNORDERED.  /RAND (depth[86]) + optional predicate Pp + a trap address
# (register or immediate).  Not emitted by ptxas — driver/runtime primitive.
#
# Empirical findings (single-warp probe, CS2R SR_CLOCKLO timing):
#   - Execution ALWAYS continues: no user-visible fault, registers/result
#     stores unchanged (store after NANOTRAP succeeds).
#   - Single NANOTRAP latency ~20 cyc (vs ~13 for 2 NOPs) — cheap in
#     isolation.
#   - Repeated NANOTRAP to a "trap-active" address occasionally triggers a
#     ~10k-cycle device event (a genuine hardware trap injection):
#         addr    trigger rate   event cost
#         0x00    25/25 (100%)   ~54k cyc when many, ~11k for one
#         0x7f    25/25 (100%)   ~10.7k
#         0x80    17/25 (68%)    ~10.8k
#         0x81    11/25 (44%)    ~10.8k
#         0x100+  0/25           0 (no-op)
#   - 0x7f/0x80/0x81 events do NOT stack (1 trap == 64 traps ~10.7k cyc —
#     trap suppression after the first); 0x00 DOES stack (~+700-1800 cyc per
#     additional trap).
#   - .RAND modifier does not change the observed cost in this probe.
#
# Interpretation: NANOTRAP injects a hardware trap whose effect (and whether
# it fires at all) depends on the address.  In a plain CUDA compute launch
# the injected trap is swallowed by the runtime (no fault visible), but the
# device-side trap handler still runs, costing ~10k cycles.  Trap vector 0
# behaves differently (each injection handled separately).  Addresses >= 0x100
# appear to be treated as no-op (not a recognized trap selector).
# ---------------------------------------------------------------------------

def build_kernel(insts):
    lines = ["#fn k(buf<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
             "    NOP;[7:7:{}:5:0]"]
    lines += list(insts)
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


def run_total(insts):
    cubin = build_kernel(insts)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.launch("k", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    res = struct.unpack("<4I", mod.device_read(d + 0x0, 16))
    mod.devmem_free(d)
    t0 = (res[1] << 32) | res[0]
    t1 = (res[3] << 32) | res[2]
    return (t1 - t0) & ((1 << 64) - 1)


# --- 1. execution continues / no side effect --------------------------------
def build_continue():
    lines = ["#fn k(buf<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    MOV32I R10, 0x00001000;[7:7:{}:5:1]",
             "    NANOTRAP R10;[7:7:{}:5:1]",
             "    MOV32I R22, 0xdeadbeef;[7:7:{}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R22;[0:1:{0}:1:0]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R10;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.launch("k", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    res = struct.unpack("<2I", mod.device_read(d + 0x0, 8))
    mod.devmem_free(d)
    return res

store, rb = build_continue()
print("NANOTRAP continues: store=0x%08x (deadbeef), Rb unchanged=0x%08x (0x1000)"
      % (store, rb))
assert store == 0xdeadbeef and rb == 0x00001000, "NANOTRAP had a side effect!"

# --- 2. trap trigger probability + cost by address --------------------------
print("\nNANOTRAP trigger probe (32-trap loop, 25 runs, slow = >5000 cyc total):")
for addr in (0x00, 0x7f, 0x80, 0x81, 0x100):
    runs = []
    for _ in range(25):
        insts = [f"NANOTRAP 0x{addr:x};[7:7:{{}}:5:1]", "NOP;[7:7:{}:5:1]"] * 32
        runs.append(run_total(insts))
    slow = [v for v in runs if v > 5000]
    fast = [v for v in runs if v <= 5000]
    print(f"  0x{addr:03x}: {len(slow)}/25 slow  (slow~{statistics.median(slow) if slow else 0}, "
          f"fast~{statistics.median(fast) if fast else 0})")

# --- 3. 0x00 stacks, 0x7f does not ------------------------------------------
print("\nstacking test:")
for addr in (0x7f, 0x00):
    vals = []
    for nt in (1, 2, 4, 8):
        insts = [f"NANOTRAP 0x{addr:x};[7:7:{{}}:5:1]"] * nt + \
                ["NOP;[7:7:{}:5:1]"] * (32 - nt)
        d = run_total(insts)
        vals.append(d)
    print(f"  0x{addr:02x}: {vals}  "
          f"({'stacks (+per trap)' if vals[-1]-vals[0]>2000 else 'flat (suppressed)'})")
