"""Probe: is SETLMEMBASE / the local-memory backing per-warp?

Each warp: SETLMEMBASE(blob_base + warpid*1MB) -> gate (host releases
only after ALL warps report LMB set) -> STL magic(0xA00+warpid) to
local [RZ+0] -> barrier (RED counter until all stored) -> LDL back ->
STG per-lane to out.  If out[w*32+lane] == 0xA00+w everywhere, LMB is
per-warp.  Any cross-value means SETLMEMBASE state is shared at some
coarser granularity (SM/SMSP/CTA) and last-writer-wins.

Configs:
  A  grid=(1,) block=(64,)    2 warps 1 CTA   (m3w geometry — control)
  B  grid=(1,) block=(128,)   4 warps 1 CTA
  C  grid=(2,) block=(32,)    2 CTAs x 1 warp
  D  grid=(2,) block=(64,)    2 CTAs x 2 warps

Driver: python3 sassdbg/probe_lmbshare.py
Worker: python3 sassdbg/probe_lmbshare.py A
"""
import faulthandler
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import CudaModule, assemble      # noqa: E402

B5 = "[7:7:{}:5:1]"

# inst: 0-2 LDC  3 S2R tid  4 SHF wict  5 S2R ctaid  6 IMAD gwarp
#       7 IMAD.WIDE blob  8 SETLMEMBASE  9-11 arrive(RED flag+4)
#       12-14 gate spin on flag+0  15 IADD magic  16 STL
#       17-19 ATOMG flag+8 (stored)  20-23 spin until flag+8 == nthreads
#       24 LDL  25 lane calc  26 IMAD addr  27 IMAD.WIDE out  28 STG  29 EXIT
def make_src(ctawarps: int, n_threads: int) -> str:
    return f"""#fn k(base<8>, flag<8>, out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(base);[1:7:{{}}:8:0]
    LDC.64 {{R6,R7}}, #param(flag);[2:7:{{}}:8:0]
    LDC.64 {{R8,R9}}, #param(out);[3:7:{{}}:8:0]
    S2R R20, SR_TID.X;[5:7:{{}}:5:1]
    SHF.R.U32.HI R21, RZ, 0x5, R20;[7:7:{{5}}:5:1]
    S2R R22, SR_CTAID.X;[4:7:{{}}:5:1]
    IMAD R21, R22, {ctawarps}, R21;[7:7:{{4}}:5:1]
    IMAD.WIDE.U32 {{R24,R25}}, R21, 0x100000, {{R4,R5}};[7:7:{{1}}:13:1]
    SETLMEMBASE {{R24,R25}};[7:7:{{}}:5:1]
    MOV32I R26, 0x1;{B5}
    ATOMG.E.ADD.STRONG.GPU PT, R27, desc[{{UR4,UR5}}][{{R6,R7}}+0x4], R26;[0:7:{{2}}:8:0]
#def_label(gate)
    LDG.E.STRONG.GPU R26, [{{R6,R7}}+0x0];[5:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R26, 0x0, PT;[7:7:{{5}}:13:1]
    @!P0 BRA #label(gate);[7:7:{{}}:6:0]
    IADD3 R26, R21, 0xA00, RZ;[7:7:{{}}:5:1]
    STL [RZ+0xfff9c0], R26;[7:7:{{}}:8:0]
    MOV32I R26, 0x1;{B5}
    ATOMG.E.ADD.STRONG.GPU PT, R27, desc[{{UR4,UR5}}][{{R6,R7}}+0x8], R26;[0:7:{{}}:8:0]
#def_label(wall)
    LDG.E.STRONG.GPU R26, [{{R6,R7}}+0x8];[5:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R26, {n_threads}, PT;[7:7:{{5}}:13:1]
    @P0 BRA #label(wall);[7:7:{{}}:6:0]
    LDL R27, [RZ+0xfff9c0];[4:7:{{}}:13:1]
    LOP3.LUT R23, R20, 0x1F, RZ, 0xC0;[7:7:{{}}:5:1]
    IMAD R23, R21, 0x20, R23;[7:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R28,R29}}, R23, 0x4, {{R8,R9}};[7:7:{{3}}:13:1]
    STG.E.STRONG.GPU [{{R28,R29}}], R27;[7:7:{{4}}:8:0]
    EXIT;{B5}
}}
"""


CONFIGS = {
    "A": dict(grid=(1,), block=(64,), ctawarps=2, n_warps=2),
    "B": dict(grid=(1,), block=(128,), ctawarps=4, n_warps=4),
    "C": dict(grid=(2,), block=(32,), ctawarps=1, n_warps=2),
    "D": dict(grid=(2,), block=(64,), ctawarps=2, n_warps=4),
}


def run(name: str) -> bool:
    faulthandler.dump_traceback_later(60, exit=True)
    cfg = CONFIGS[name]
    nw = cfg["n_warps"]
    nthreads = cfg["grid"][0] * cfg["block"][0]
    mod = CudaModule(assemble(make_src(cfg["ctawarps"], nthreads),
                              check_deps=False))
    base = mod.devmem_alloc(nw * 0x100000)
    flag = mod.devmem_alloc(0x20)
    out = mod.devmem_alloc(nw * 32 * 4)
    mod.device_write(flag, bytes(0x20))
    mod.device_write(out, bytes(nw * 32 * 4))
    stream = CudaModule.stream_create()
    mod.launch("k", grid=cfg["grid"], block=cfg["block"],
               args=[base, flag, out], stream=stream)
    # wait until all warps report LMB set (per-lane atomic: +=1/thread)
    t0 = time.time()
    while struct.unpack("<I", mod.device_read(flag + 4, 4))[0] != nthreads:
        if time.time() - t0 > 20:
            print(f"[{name}] TIMEOUT waiting arrive")
            return False
        time.sleep(0.001)
    mod.device_write(flag, struct.pack("<I", 1))     # release gate
    # observe how far the stored-counter gets before completion/fault
    t0 = time.time()
    last = -1
    while time.time() - t0 < 15:
        try:
            c = struct.unpack("<I", mod.device_read(flag + 8, 4))[0]
        except RuntimeError as e:
            print(f"[{name}] fault while polling wall counter: {e}")
            break
        if c != last:
            print(f"[{name}] wall counter = {c}/{nthreads}")
            last = c
        if c == nthreads:
            break
        time.sleep(0.001)
    try:
        mod.stream_sync(stream)
    except RuntimeError as e:
        print(f"[{name}] stream_sync: {e}")
        return False
    v = struct.unpack(f"<{nw * 32}I", mod.device_read(out, nw * 32 * 4))
    bad = []
    for w in range(nw):
        for lane in range(32):
            got = v[w * 32 + lane]
            if got != 0xA00 + w:
                bad.append((w, lane, hex(got)))
    if bad:
        print(f"[{name}] SHARED LMB? {len(bad)} bad lanes, "
              f"first: {bad[:6]}")
        # summarize: which value did each warp read back?
        seen = {w: sorted({v[w * 32 + l] for l in range(32)})
                for w in range(nw)}
        for w, s in seen.items():
            print(f"[{name}]   warp{w} read: {[hex(x) for x in s]}")
        return False
    print(f"[{name}] per-warp LMB OK ({nw} warps)")
    return True


def main() -> None:
    fails = []
    for name in CONFIGS:
        r = subprocess.run([sys.executable, __file__, name],
                           capture_output=True, text=True, timeout=120)
        print(r.stdout, end="")
        if r.returncode != 0:
            fails.append(name)
            print(f"[{name}] rc={r.returncode}")
            print(r.stderr[-1500:])
    print("FAILS:", fails if fails else "none")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(0 if run(sys.argv[1]) else 1)
    main()
