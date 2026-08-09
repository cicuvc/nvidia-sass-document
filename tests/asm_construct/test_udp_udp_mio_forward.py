import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# udp_pipe -> udp_pipe (same) and udp_pipe -> mio_pipe (UR address offset)
# forwarding calibration (SM120)
#
# udp->udp: producer UIADD3 UR10 = TRUE (0x12345678), consumer UIADD3 UR20
# reads UR10 (same pipe); tail UR20 -> MOV R20 decoupled by a big pad.
# Spec: UDP_subset -> UDP_subset = 4.
#
# udp->mio: a UDP producer writes UR14 (an address OFFSET), an LDG's AGU reads
# it in the uniform-address form `[R12 + UR14 + 0x0]` (R12 = 64-bit base).
#   poison UR14 = 0x400000 -> loads marker MA at base+4MB
#   producer UIADD3 UR14 = 0  -> loads marker MB at base+0
# Spec: UDP_subset -> MIO_CBU_OPS = 12.
# See notes/sm90/arch/pipe_forward_survey.md.
# ---------------------------------------------------------------------------

TRUE_I = 0x12345678
POISON_I = 0xAAAAAAAA
MA = 0x11111111              # marker at base + 0x400000 (stale offset)
MB = 0x22222222              # marker at base + 0x0 (true offset)
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)


def build_udpudp(stalls):
    lines = ["#fn fwd(out<8>, poison<4>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]",
             "    UMOV UR11, 0x12345678;[7:7:{}:5:1]"]
    for i, S in enumerate(stalls):
        off = 4 * i
        lines.append("    LDCU UR10, #param(poison);[0:7:{}:2:0]")
        if S == 0:
            lines += ["    NOP;[7:7:{}:7:1]"] * 6
            lines.append("    MOV RZ, UR10;[7:7:{0}:5:1]")
        else:
            lines.append("    UIADD3 UR10, UPT, UPT, UR11, URZ, URZ;[7:7:{0}:1:1]")
            for _ in range(S - 1):
                lines.append("    NOP;[7:7:{}:1:1]")
        lines.append("    UIADD3 UR20, UPT, UPT, UR10, URZ, URZ;[7:7:{}:5:1]")
        lines += ["    NOP;[7:7:{}:5:1]"] * 8
        lines.append("    MOV R20, UR20;[7:7:{}:5:1]")
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R20;[0:1:{{1,2}}:1:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("}")
    return "\n".join(lines)


def build_udpmio(stalls):
    lines = ["#fn fwd(out<8>, base<8>, offpoison<4>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]",
             "    LDC.64 {R12, R13}, #param(base);[3:7:{}:2:0]"]
    for i, S in enumerate(stalls):
        off = 4 * i
        lines.append("    LDCU UR14, #param(offpoison);[0:7:{}:2:0]")
        if S == 0:
            lines += ["    NOP;[7:7:{}:7:1]"] * 6
            lines.append("    MOV RZ, UR14;[7:7:{0}:5:1]")
        else:
            lines.append("    UIADD3 UR14, UPT, UPT, URZ, URZ, URZ;[7:7:{0}:1:1]")
            for _ in range(S - 1):
                lines.append("    NOP;[7:7:{}:1:1]")
        lines.append("    LDG.E PT, R20, [R12 + UR14 + 0x0];[4:7:{0,3}:5:1]")
        lines += ["    NOP;[7:7:{}:5:1]"] * 4
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R20;[0:1:{{4,2,1}}:1:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("}")
    return "\n".join(lines)


def run(kind, stalls):
    reset_context()
    if kind == "udpudp":
        cubin = assemble(build_udpudp(stalls), check_deps=False)
        mod = CudaModule(cubin)
        d = mod.devmem_alloc(1024)
        mod.device_write(d, bytes(1024))
        mod.launch("fwd", grid=(1,), block=(1,), args=[d, POISON_I])
    else:
        cubin = assemble(build_udpmio(stalls), check_deps=False)
        mod = CudaModule(cubin)
        d = mod.devmem_alloc(1024)
        mod.device_write(d, bytes(1024))
        buf = mod.devmem_alloc(8 * 1024 * 1024)
        mod.device_write(buf, struct.pack("<I", MB))
        mod.device_write(buf + 4 * 1024 * 1024, struct.pack("<I", MA))
        mod.launch("fwd", grid=(1,), block=(1,),
                   args=[d, buf, 0x400000])
        mod.devmem_free(buf)
    mod.synchronize()
    vals = struct.unpack("<%dI" % len(stalls), mod.device_read(d, len(stalls) * 4))
    mod.devmem_free(d)
    return vals


try:
    run("udpudp", [8])
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("udp->udp / udp->mio forwarding calibration (SM120)")
print("stall  : " + " ".join(f"{s:3d}" for s in STALLS[SWEEP]))

ok = True
for kind, tag, lspec, fresh_v, stale_v in (
        ("udpudp", "UIADD3->UIADD3", 4, TRUE_I, POISON_I),
        ("udpmio", "UIADD3->LDG(UR off)", 12, MB, MA)):
    def cl(v):
        return "F" if v == fresh_v else ("S" if v == stale_v else "?")
    reps = [run(kind, STALLS) for _ in range(3)]
    maj = "".join("F" if sum(1 for r in reps if cl(r[i]) == "F") >= 2
                  else ("S" if sum(1 for r in reps if cl(r[i]) == "S") >= 2
                        else "?")
                  for i in range(len(STALLS)))
    det = all(r == reps[0] for r in reps)
    sweep = maj[SWEEP]
    minG = None
    for j in range(len(sweep)):
        if all(c == "F" for c in sweep[j:]):
            minG = STALLS[SWEEP][j]
            break
    print(f"{tag}  Lspec={lspec} [{'det' if det else 'var'}]: {sweep}")
    if minG is not None:
        print(f"        minG stall={minG} (real gap ~{minG + 0.4:.1f}cyc), "
              f"overlap Lspec-minG={lspec - minG}")
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
    if minG is None or minG >= lspec:
        good = False
        print(f"        FAIL: expected minG < L_table ({lspec})")
    if not det:
        print("        WARN: boundary not deterministic")
    ok &= good

print("\n=== udp->udp / udp->mio forwarding calibration: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
