"""sassdbg M3v3 multi-warp breakpoint test: two warps, one site.

Both warps hit the SAME armed site; wait_hit reports the hitting warp
(bp.warp); ONE resume() releases both parked warps (per-warp generation
bump).  The handler spills/restores R246-R251 + PR via the per-warp
local backing (permanent SETLMEMBASE), and RETs through the
self-constructed RET.ABS.NODEC RZ, imm word — the kernel's warp-tagged
magic values in R246-R251 and P0 must survive the park/resume intact.

Run: python3 tests/asm_construct/test_sassdbg_m3w.py
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sassdbg.patch import Debugger            # noqa: E402

B = "[7:7:{}:5:1]"

# inst indices (original source, labels excluded):
#   0 LDCU  1 LDC  2 S2R  3 SHF(warpid)  4 SHF(tag)  5-10 MOV32I/IADD3
#   magic into R246-R251  11 ISETP(P0=1)  12 MOV32I R0,0x7  <- BP SITE
#   13 IMAD.WIDE  14 STG.128  15 STG.64  16 @P0 STG  17 EXIT
SRC = f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    S2R R20, SR_TID.X;[5:7:{{}}:5:1]
    SHF.R.U32.HI R21, RZ, 0x5, R20;[7:7:{{5}}:5:1]
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

SITE = 12                       # the MOV32I R0, 0x7

ok = True


def check(name, cond, extra=""):
    global ok
    if not cond:
        ok = False
    print(f"{'ok ' if cond else 'FAIL'} {name:<52} {extra}")


dbg = Debugger(SRC, max_warps=2)
out = dbg.mod.devmem_alloc(64)
dbg.mod.device_write(out, bytes(64))

dbg.launch([out], block=(64,))
base = dbg.base()
check("target reports code base", base != 0 and base % 16 == 0, hex(base))

bp = dbg.arm(SITE)
dbg.release()

h1 = dbg.wait_hit()
w1 = h1.warp
check("first hit is the site", h1 is bp, f"warp={w1}")
h2 = dbg.wait_hit()
w2 = h2.warp
check("second hit is the same site, other warp",
      h2 is bp and w2 is not None and w2 != w1, f"warp={w2}")

# both warps are parked at the site: nothing written yet
pre = struct.unpack("<16I", dbg.mod.device_read(out, 64))
check("both warps parked before the site", all(v == 0 for v in pre))

dbg.resume(bp)                  # ONE resume releases BOTH warps
dbg.wait_done()

v = struct.unpack("<16I", dbg.mod.device_read(out, 64))
for w in range(2):
    got = list(v[w * 8:w * 8 + 8])
    want = [0xAA0000 + w * 0x1000 + k for k in range(6)] + [7, 0]
    check(f"warp{w} magics+P0 intact after resume", got == want,
          str(tuple(hex(x) for x in got)) if got != want else "")

print("\n=== sassdbg M3v3 multi-warp: ALL PASS ===" if ok
      else "\n=== FAILURES ===")
sys.exit(0 if ok else 1)
