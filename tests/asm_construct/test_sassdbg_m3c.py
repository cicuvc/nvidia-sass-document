"""sassdbg M3v3 multi-CTA breakpoint test: 2 CTAs x 2 warps, one site.

Multi-CTA support: warpid = SR_CTAID.X * warps_per_cta + (SR_TID.X>>5),
warps_per_cta passed to the prologue via ctrl+0x28 at launch.  All four
warps hit the SAME armed site; ONE resume() releases all four (per-warp
generation bump).  The kernel's warp-tagged magic values in R246-R251
and P0 must survive the park/resume intact on every warp, and each
warp's output must land in its own slice (indexed by the kernel's own
global-warp computation, independent of the debugger's).

NOTE: multi-CTA launches require ALL CTAs co-resident (parked warps
never exit; a grid exceeding resident capacity deadlocks the gate).

Run: python3 tests/asm_construct/test_sassdbg_m3c.py
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sassdbg.patch import Debugger            # noqa: E402

B = "[7:7:{}:5:1]"

# inst indices (original source, labels excluded):
#   0 LDCU  1 LDC  2 S2R(tid)  3 SHF(wict)  4 S2R(ctaid)  5 IMAD(warpid)
#   6 SHF(tag)  7-12 MOV32I/IADD3 magic into R246-R251
#   13 ISETP(P0=1)  14 MOV32I R0,0x7  <- BP SITE
#   15 IMAD.WIDE  16 STG.128  17 STG.64  18 @P0 STG  19 EXIT
SRC = f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    S2R R20, SR_TID.X;[5:7:{{}}:5:1]
    SHF.R.U32.HI R21, RZ, 0x5, R20;[7:7:{{5}}:5:1]
    S2R R22, SR_CTAID.X;[4:7:{{}}:5:1]
    IMAD R21, R22, 0x2, R21;[7:7:{{4}}:5:1]
    SHF.L.U32 R22, R21, 0xC, RZ;[7:7:{{}}:5:1]
    MOV32I R246, 0xAA0000;{B}
    IADD3 R246, R246, R22, RZ;[7:7:{{}}:5:1]
    MOV32I R247, 0xAA0001;{B}
    IADD3 R247, R247, R22, RZ;[7:7:{{}}:5:1]
    MOV32I R248, 0xAA0002;{B}
    IADD3 R248, R248, R22, RZ;[7:7:{{}}:5:1]
    MOV32I R249, 0xAA0003;{B}
    IADD3 R249, R249, R22, RZ;[7:7:{{}}:5:1]
    MOV32I R250, 0xAA0004;{B}
    IADD3 R250, R250, R22, RZ;[7:7:{{}}:5:1]
    MOV32I R251, 0xAA0005;{B}
    IADD3 R251, R251, R22, RZ;[7:7:{{}}:5:1]
    ISETP.EQ.AND P0, PT, R20, R20, PT;[7:7:{{}}:13:1]
    MOV32I R0, 0x7;{B}
    IMAD.WIDE.U32 {{R24,R25}}, R21, 0x20, {{R4,R5}};[7:7:{{1}}:13:1]
    STG.E.64 desc[{{UR4,UR5}}][{{R24,R25}}], {{R246,R247}};[7:7:{{0,1}}:8:0]
    STG.E.64 desc[{{UR4,UR5}}][{{R24,R25}}+0x8], {{R248,R249}};[7:7:{{0,1}}:8:0]
    STG.E.64 desc[{{UR4,UR5}}][{{R24,R25}}+0x10], {{R250,R251}};[7:7:{{0,1}}:8:0]
    @P0 STG.E desc[{{UR4,UR5}}][{{R24,R25}}+0x18], R0;[7:7:{{0,1}}:8:0]
    EXIT;{B}
}}
"""

SITE = 14                       # the MOV32I R0, 0x7
N_WARPS = 4                     # 2 CTAs x 2 warps

ok = True


def check(name, cond, extra=""):
    global ok
    if not cond:
        ok = False
    print(f"{'ok ' if cond else 'FAIL'} {name:<52} {extra}")


dbg = Debugger(SRC, max_warps=N_WARPS)
out = dbg.mod.devmem_alloc(N_WARPS * 0x20)
dbg.mod.device_write(out, bytes(N_WARPS * 0x20))

dbg.launch([out], grid=(2,), block=(64,))
base = dbg.base()
check("target reports code base", base != 0 and base % 16 == 0, hex(base))

bp = dbg.arm(SITE)
dbg.release()

warps_hit = set()
for _ in range(N_WARPS):
    h = dbg.wait_hit()
    check("hit is the site", h is bp, f"warp={h.warp}")
    warps_hit.add(h.warp)
check("all 4 warps hit (distinct)", warps_hit == {0, 1, 2, 3},
      str(warps_hit))

# all warps parked at the site: nothing written yet
pre = struct.unpack(f"<{N_WARPS * 8}I", dbg.mod.device_read(out,
                                                            N_WARPS * 0x20))
check("all warps parked before the site", all(v == 0 for v in pre))

dbg.resume(bp)                  # ONE resume releases ALL parked warps
dbg.wait_done()

v = struct.unpack(f"<{N_WARPS * 8}I", dbg.mod.device_read(out,
                                                          N_WARPS * 0x20))
for w in range(N_WARPS):
    got = list(v[w * 8:w * 8 + 8])
    want = [0xAA0000 + w * 0x1000 + k for k in range(6)] + [7, 0]
    check(f"warp{w} magics+P0 intact after resume", got == want,
          str(tuple(hex(x) for x in got)) if got != want else "")

print("\n=== sassdbg M3v3 multi-CTA: ALL PASS ===" if ok
      else "\n=== FAILURES ===")
sys.exit(0 if ok else 1)
