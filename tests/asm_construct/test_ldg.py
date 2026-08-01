import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# LDG global load — hand-built ELF.
#
# Currently FAULTS with CUDA_ERROR_ILLEGAL_ADDRESS (700) in the hand-built
# ELF, unlike ptxas-compiled kernels.  LDG is variable-latency like S2R and
# ptxas emits:  `LDG.E R2, desc[UR4][R2.64] &req={0} &wr=0x2 ?trans1`
#   - &req={0} waits on the address source's scoreboard,
#   - &wr=0x2  sets SB2 when the load completes; the consumer waits &req={2}.
#
# This test tries that scoreboard pattern and reports the outcome so the
# remaining difference (address provenance / memory-pipeline setup ptxas
# provides) can be isolated.
# ---------------------------------------------------------------------------

FIVE = 0x40A00000   # 5.0


def build(variant):
    """Build a kernel that LDGs out[8] (pre-populated 5.0) and stores it back.

    variant: 'sb'  -> wr scoreboard on LDG + req on the first consumer
             'sb+addr-req' -> also wait the LDG's address source
    """
    lines = ["#fn ldg_test(out<1024>) {",
             "    LDCU.64 UR4, c[0x0][0x358];[0:7:{}:1:0]",
             "    LDC.64 R6, #param(out);[0:7:{}:1:0]"]
    if variant == "sb":
        lines += [
            # LDG writes SB1 on completion; address = R6.64 + 0x20
            "    LDG.E R20, desc[UR4][R6.64+0x20];[1:7:{}:5:1]",
            "    IADD3 R22, R20, RZ, RZ;[7:7:{1}:5:1]",   # first use waits SB1
            "    STG.E desc[UR4][R6.64+0x0], R22;[0:1:{0}:1:0]",
        ]
    elif variant == "sb+addr-req":
        # also let the LDG wait on the address (LDC fixed-latency, no SB, so
        # this req is a no-op for now — kept to mirror ptxas shape)
        lines += [
            "    LDG.E R20, desc[UR4][R6.64+0x20];[1:7:{0}:5:1]",
            "    IADD3 R22, R20, RZ, RZ;[7:7:{1}:5:1]",
            "    STG.E desc[UR4][R6.64+0x0], R22;[0:1:{0}:1:0]",
        ]
    else:
        lines += [
            "    LDG.E R20, desc[UR4][R6.64+0x20];[7:7:{}:5:1]",   # no SB
            "    IADD3 R22, R20, RZ, RZ;[7:7:{}:5:1]",
            "    STG.E desc[UR4][R6.64+0x0], R22;[0:1:{0}:1:0]",
        ]
    lines += ["    EXIT;[7:7:{}:5:0]",
              "}"]
    return assemble("\n".join(lines))


for variant in ("nosb", "sb", "sb+addr-req"):
    cubin = build(variant)
    try:
        mod = CudaModule(cubin)
        d = mod.devmem_alloc(64)
        # out[8] = 5.0 (pre-populated host-side)
        mod.device_write(d, struct.pack("<16I", *([0] * 8 + [FIVE] + [0] * 7)))
        mod.launch("ldg_test", grid=(1,), block=(1,), args=[d])
        mod.synchronize()
        v = struct.unpack("<I", mod.device_read(d, 4))[0]
        f = struct.unpack("<f", struct.pack("<I", v))[0]
        print(f"[{variant:>12}] loaded {f} (expect 5.0)")
        mod.devmem_free(d)
    except RuntimeError as e:
        print(f"[{variant:>12}] ERR {str(e)[:40]}")
