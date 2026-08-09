import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# udp_pipe -> fe_pipe (DEPBAR) forwarding calibration (SM120, RTX 5090)
#
# Same stale/fresh boundary method, observed through the DEPBAR's counted-wait
# behavior (see notes/sm90/instr/depbar.md):
#   * arm SB0 with ONE cold LDG (wr=SB0) -> outstanding counter = 1.
#   * poison: UMOV UR3, 0x0  (DEPBAR.LE SB0, UR3=0 -> waits for the load)
#   * producer (udp_pipe): UMOV UR3, 0x1 (DEPBAR.LE SB0, UR3=1 -> proceeds
#     while the load is still in flight, counter 1 <= 1).
# R0 is seeded 0xCAFEBABE before the LDG; the LDG overwrites it with
# 0xDEADBEEF at completion.  So after the DEPBAR:
#   R0 == 0xDEADBEEF  -> DEPBAR WAITED  -> it read the poison (0) -> UR stale
#   R0 == 0xCAFEBABE  -> DEPBAR proceeded -> it read the producer (1) -> UR fresh
# Each instance reads a distinct cold 4KB page (i*0x1000) and ends with
# `DEPBAR {0}` so the next instance's scoreboard counter starts at 0.
#
# Spec sm120 UGPR TABLE_TRUE: UDP_subset -> DEPBAR_OP = 10.
# See notes/sm90/arch/pipe_forwarding.md.
# ---------------------------------------------------------------------------

LDG_DONE = 0xDEADBEEF          # R0 after the cold LDG completes
LDG_SEED = 0xCAFEBABE          # R0 while the LDG is still in flight
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)
SPEC_L = 10                    # UDP_subset -> DEPBAR_OP
BUFSZ = 16 * 1024 * 1024


def build_kernel(stalls):
    lines = ["#fn fwd(out<8>, src<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]",
             "    LDC.64 {R2, R3}, #param(src);[3:7:{}:2:0]"]
    for i, S in enumerate(stalls):
        off = 4 * i
        off8 = i * 0x1000       # distinct cold page per instance
        lines.append("    MOV32I R0, 0xcafebabe;[7:7:{}:5:1]")
        lines.append(f"    LDG.E R0, desc[{{UR4,UR5}}][{{R2,R3}}+0x{off8:x}];[0:7:{{1,3}}:5:1]")
        lines.append("    UMOV UR3, 0x0;[7:7:{}:5:1]")
        for _ in range(4):
            lines.append("    NOP;[7:7:{}:7:1]")
        if S != 0:
            lines.append("    UMOV UR3, 0x1;[7:7:{}:1:1]")
            for _ in range(S - 1):
                lines.append("    NOP;[7:7:{}:1:1]")
        lines.append("    DEPBAR.LE SB0, UR3;[7:7:{}:5:1]")
        lines.append("    IADD3 R20, R0, RZ, RZ;[7:7:{}:5:1]")
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R20;[0:1:{{2,1}}:1:0]")
        lines.append("    DEPBAR {0};[7:7:{}:5:1]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("}")
    return "\n".join(lines)


def run(stalls):
    reset_context()
    cubin = assemble(build_kernel(stalls), check_deps=False)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    buf = mod.devmem_alloc(BUFSZ)
    mod.device_write(buf, struct.pack("<%dI" % (BUFSZ // 4), *[LDG_DONE] * (BUFSZ // 4)))
    mod.launch("fwd", grid=(1,), block=(1,), args=[d, buf])
    mod.synchronize()
    vals = struct.unpack("<%dI" % len(stalls), mod.device_read(d, len(stalls) * 4))
    mod.devmem_free(buf)
    mod.devmem_free(d)
    return vals


def classify(v):
    return "F" if v == LDG_SEED else ("S" if v == LDG_DONE else "?")


try:
    run([8])
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("udp->fe (DEPBAR count) forwarding calibration (SM120); "
      "R0 after DEPBAR: 0xDEADBEEF=waited(stale UR), 0xCAFEBABE=early(fresh UR)")
print("stall  : " + " ".join(f"{s:3d}" for s in STALLS[SWEEP]))

reps = [run(STALLS) for _ in range(3)]
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
print(f"UMOV->DEPBAR  Lspec={SPEC_L} [{'det' if det else 'var'}]: {sweep}")
if minG is not None:
    print(f"        minG stall={minG} (real gap ~{minG + 0.4:.1f}cyc), "
          f"overlap Lspec-minG={SPEC_L - minG}")
print("        raw:", [classify(v) for v in reps[0]])

ok = True
if maj[0] != "S":                       # poison-only -> DEPBAR must wait
    ok = False
    print("        FAIL: poison-only control should read stale (DEPBAR waited)")
if maj[-1] != "F":                      # huge-gap -> DEPBAR must proceed early
    ok = False
    print("        FAIL: huge-gap control (stall 30) should be fresh (DEPBAR early)")
if minG is None or minG < 1 or minG > 16:
    ok = False
    print("        FAIL: could not resolve minG in the sweep range")
if minG is None or minG >= SPEC_L:
    ok = False
    print(f"        FAIL: expected minG < L_table ({SPEC_L})")
if not det:
    print("        WARN: boundary not deterministic across reps")

print("\n=== udp->fe forwarding calibration: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
