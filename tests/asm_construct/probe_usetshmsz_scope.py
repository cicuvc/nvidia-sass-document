"""Scope probes for USETSHMSZ on sm_120.

Each case runs in a child process because an expected 700/715 poisons the
CUDA context.  The interesting question is whether a uniform instruction
changes a CTA-wide shared window or only the issuing warp's window.
"""

import subprocess
import struct
import sys
import tempfile
from pathlib import Path


ROOT = str(Path(__file__).resolve().parents[2])


def run(body: str, block: int = 64) -> str:
    outfile = tempfile.mktemp(prefix="usetshmsz_scope_", suffix=".out")
    source = f"""#fn k(out<8>) {{
    #pragma SHARED(0x1000)
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6,R7}}, #param(out);[1:7:{{}}:1:0]
    S2R R0, SR_TID.X;[5:7:{{0,1}}:5:1]
    ISETP.LT.AND P0, PT, R0, 0x20, PT;[7:7:{{5}}:13:1]
{body}
#def_label(done)
    MOV32I R2, 0x12345678;[7:7:{{}}:5:1]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}], R2;[0:1:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""
    code = f"""
import struct, sys
sys.path.insert(0, {ROOT!r})
from assembler import assemble, CudaModule
src = {source!r}
out_file = {outfile!r}
try:
    mod = CudaModule(assemble(src))
    out = mod.devmem_alloc(4)
    mod.device_write(out, bytes(4))
    mod.launch('k', grid=(1,), block=({block},), args=[out])
    mod.synchronize()
    value = struct.unpack('<I', mod.device_read(out, 4))[0]
    open(out_file, 'w').write('OK 0x%08x' % value)
except Exception as exc:
    open(out_file, 'w').write('ERR ' + str(exc))
"""
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=20)
    try:
        result = Path(outfile).read_text().strip()
        Path(outfile).unlink()
        return result
    except FileNotFoundError:
        return "NOOUTPUT " + (proc.stderr or proc.stdout)[-200:]


# P0 is warp 0, !P0 is warp 1.  BAR.SYNC is deliberately at distinct PCs;
# CTA barriers are PC-independent and make the requested order unambiguous.
CASES = [
    ("decl 4K: set 0x1080", "    USETSHMSZ 0x1080;[7:7:{}:1:0]\n"),
    ("decl 4K: set 0x1380", "    USETSHMSZ 0x1380;[7:7:{}:1:0]\n"),
    ("decl 4K: set 0x1400", "    USETSHMSZ 0x1400;[7:7:{}:1:0]\n"),
    ("decl 4K: set 0x1480", "    USETSHMSZ 0x1480;[7:7:{}:1:0]\n"),
    ("warp0 shrink; warp1 high access", """
    @P0 BRA #label(shrink);[7:7:{}:5:1]
    BAR.SYNC 0;[7:7:{}:5:1]
    MOV32I R1, 0xA5A5A5A5;[7:7:{}:5:1]
    STS [RZ+0x800], R1;[7:7:{}:5:1]
    BRA #label(done);[7:7:{}:5:1]
#def_label(shrink)
    USETSHMSZ 0x200;[7:7:{}:1:0]
    BAR.SYNC 0;[7:7:{}:5:1]
    BRA #label(done);[7:7:{}:5:1]
"""),
    ("warp1 shrink; warp0 high access", """
    @P0 BRA #label(access);[7:7:{}:5:1]
    USETSHMSZ 0x200;[7:7:{}:1:0]
    BAR.SYNC 0;[7:7:{}:5:1]
    BRA #label(done);[7:7:{}:5:1]
#def_label(access)
    BAR.SYNC 0;[7:7:{}:5:1]
    MOV32I R1, 0xA5A5A5A5;[7:7:{}:5:1]
    STS [RZ+0x800], R1;[7:7:{}:5:1]
    BRA #label(done);[7:7:{}:5:1]
"""),
    ("warp0 shrink+FLUSH; warp1 high access", """
    @P0 BRA #label(shrink);[7:7:{}:5:1]
    BAR.SYNC 0;[7:7:{}:5:1]
    MOV32I R1, 0xA5A5A5A5;[7:7:{}:5:1]
    STS [RZ+0x800], R1;[7:7:{}:5:1]
    BRA #label(done);[7:7:{}:5:1]
#def_label(shrink)
    USETSHMSZ 0x200;[7:7:{}:1:0]
    USETSHMSZ.FLUSH;[7:7:{}:1:0]
    BAR.SYNC 0;[7:7:{}:5:1]
    BRA #label(done);[7:7:{}:5:1]
"""),
    ("same warp shrink then high access", """
    @!P0 BRA #label(wait);[7:7:{}:5:1]
    USETSHMSZ 0x200;[7:7:{}:1:0]
    BAR.SYNC 0;[7:7:{}:5:1]
    MOV32I R1, 0xA5A5A5A5;[7:7:{}:5:1]
    STS [RZ+0x800], R1;[7:7:{}:5:1]
    BRA #label(done);[7:7:{}:5:1]
#def_label(wait)
    BAR.SYNC 0;[7:7:{}:5:1]
    BRA #label(done);[7:7:{}:5:1]
"""),
    ("warp0 0x800; warp1 0x400; warp0 repeat 0x800", """
    @!P0 BRA #label(w1);[7:7:{}:5:1]
    USETSHMSZ 0x800;[7:7:{}:1:0]
    BAR.SYNC 0;[7:7:{}:5:1]
    BAR.SYNC 1;[7:7:{}:5:1]
    USETSHMSZ 0x800;[7:7:{}:1:0]
    BRA #label(done);[7:7:{}:5:1]
#def_label(w1)
    BAR.SYNC 0;[7:7:{}:5:1]
    USETSHMSZ 0x400;[7:7:{}:1:0]
    BAR.SYNC 1;[7:7:{}:5:1]
    BRA #label(done);[7:7:{}:5:1]
"""),
    ("half-warp shrink; sibling group high access", """
    LOP3.LUT R3, R0, 0x1F, RZ, 0xC0;[7:7:{}:5:1]
    ISETP.LT.AND P1, PT, R3, 0x10, PT;[7:7:{}:13:1]
    BSSY B0, #label(join1);[7:7:{}:5:1]
    @P1 BRA #label(do_shrink);[7:7:{}:5:1]
    BRA #label(sync1);[7:7:{}:5:1]
#def_label(do_shrink)
    USETSHMSZ 0x200;[7:7:{}:1:0]
#def_label(sync1)
    BSYNC B0;[7:7:{}:4:0]
#def_label(join1)
    BSSY B0, #label(join2);[7:7:{}:5:1]
    @P1 BRA #label(sync2);[7:7:{}:5:1]
    MOV32I R1, 0xA5A5A5A5;[7:7:{}:5:1]
    STS [RZ+0x800], R1;[7:7:{}:5:1]
#def_label(sync2)
    BSYNC B0;[7:7:{}:4:0]
#def_label(join2)
    BRA #label(done);[7:7:{}:5:1]
"""),
]


print("=== USETSHMSZ scope probes (SM120) ===")
for name, body in CASES:
    print(f"{name:<52} -> {run(body)}")


def occupancy_peak(control: str, shared: int = 0x10000, *, block: int = 32,
                   grid: int = 5000) -> int:
    """Return the GPU-wide peak number of live threads."""
    src = f"""#fn k(state<8>) {{
    #pragma SHARED(0x{shared:X})
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6,R7}}, #param(state);[1:7:{{}}:1:0]
{control}    MOV32I R10, 0x1;[7:7:{{}}:5:1]
    ATOM.ADD P0, RZ, [{{R6,R7}}], R10;[5:7:{{0,1}}:8:1]
    MOV32I R20, 500;[7:7:{{}}:5:1]
#def_label(spin)
    LDG.E R18, [{{R6,R7}}];[5:7:{{0,1}}:8:1]
    ATOM.MAX P2, RZ, [{{R6,R7}}+4], R18;[5:7:{{0,1,5}}:8:1]
    IADD3 R20, R20, -1, RZ;[7:7:{{0}}:5:1]
    ISETP.GT.AND P0, PT, R20, RZ, PT;[7:7:{{}}:13:1]
    @P0 BRA #label(spin);[7:7:{{}}:5:1]
    MOV32I R10, -1;[7:7:{{}}:5:1]
    ATOM.ADD P3, RZ, [{{R6,R7}}], R10;[5:7:{{0,1}}:8:1]
    EXIT;[7:7:{{}}:5:0]
}}"""
    outfile = tempfile.mktemp(prefix="usetshmsz_occ_", suffix=".out")
    code = f"""
import struct, sys
sys.path.insert(0, {ROOT!r})
from assembler import assemble, CudaModule
try:
    mod = CudaModule(assemble({src!r}))
    state = mod.devmem_alloc(16)
    mod.device_write(state, bytes(16))
    mod.launch('k', grid=({grid},), block=({block},), args=[state])
    mod.synchronize()
    peak = struct.unpack('<4I', mod.device_read(state, 16))[1]
    open({outfile!r}, 'w').write('OK %d' % peak)
except Exception as exc:
    open({outfile!r}, 'w').write('ERR ' + str(exc))
"""
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=30)
    try:
        result = Path(outfile).read_text().strip()
        Path(outfile).unlink()
    except FileNotFoundError:
        result = "NOOUTPUT " + (proc.stderr or proc.stdout)[-200:]
    if not result.startswith("OK "):
        raise RuntimeError(result)
    return int(result.split()[1])


print("\n=== occupancy / FLUSH probe (grid 5000, block 32) ===")
OCC_CONTROLS = [
    ("decl 64K, none", 0x10000, ""),
    ("decl 64K, shrink 4K", 0x10000,
     "    USETSHMSZ 0x1000;[7:7:{}:1:0]\n"),
    ("decl 64K, shrink 4K + FLUSH", 0x10000,
     "    USETSHMSZ 0x1000;[7:7:{}:1:0]\n"
     "    USETSHMSZ.FLUSH;[7:7:{}:1:0]\n"),
    ("decl 64K, FLUSH only", 0x10000,
     "    USETSHMSZ.FLUSH;[7:7:{}:1:0]\n"),
    ("decl 4K, none", 0x1000, ""),
]
for name, shared, control in OCC_CONTROLS:
    peak = occupancy_peak(control, shared)
    print(f"{name:<34} -> {peak} live threads ({peak // 32} CTAs GPU-wide)")


print("\n=== multi-warp aggregation (decl 64 KiB, grid 5000, block 64) ===")
MW_CONTROLS = [
    ("none", ""),
    ("all shrink 4K, no FLUSH",
     "    USETSHMSZ 0x1000;[7:7:{}:1:0]\n"),
    ("all shrink 4K, all FLUSH",
     "    USETSHMSZ 0x1000;[7:7:{}:1:0]\n"
     "    BAR.SYNC 0;[7:7:{}:5:1]\n"
     "    USETSHMSZ.FLUSH;[7:7:{}:1:0]\n"),
    ("all shrink 4K, all FLUSH, no BAR",
     "    USETSHMSZ 0x1000;[7:7:{}:1:0]\n"
     "    USETSHMSZ.FLUSH;[7:7:{}:1:0]\n"),
    ("all shrink 32K, all FLUSH",
     "    USETSHMSZ 0x8000;[7:7:{}:1:0]\n"
     "    BAR.SYNC 0;[7:7:{}:5:1]\n"
     "    USETSHMSZ.FLUSH;[7:7:{}:1:0]\n"),
    ("only warp0 shrink+FLUSH", """
    S2R R2, SR_TID.X;[2:7:{}:5:1]
    ISETP.LT.AND P4, PT, R2, 0x20, PT;[7:7:{2}:13:1]
    @!P4 BRA #label(mw_done_a);[7:7:{}:5:1]
    USETSHMSZ 0x1000;[7:7:{}:1:0]
    USETSHMSZ.FLUSH;[7:7:{}:1:0]
#def_label(mw_done_a)
"""),
    ("all shrink 4K, only warp0 FLUSH", """
    USETSHMSZ 0x1000;[7:7:{}:1:0]
    BAR.SYNC 0;[7:7:{}:5:1]
    S2R R2, SR_TID.X;[2:7:{}:5:1]
    ISETP.LT.AND P4, PT, R2, 0x20, PT;[7:7:{2}:13:1]
    @!P4 BRA #label(mw_done_b);[7:7:{}:5:1]
    USETSHMSZ.FLUSH;[7:7:{}:1:0]
#def_label(mw_done_b)
"""),
    ("only warp0 shrink, all FLUSH", """
    S2R R2, SR_TID.X;[2:7:{}:5:1]
    ISETP.LT.AND P4, PT, R2, 0x20, PT;[7:7:{2}:13:1]
    @!P4 BRA #label(mw_skip_shrink);[7:7:{}:5:1]
    USETSHMSZ 0x1000;[7:7:{}:1:0]
#def_label(mw_skip_shrink)
    BAR.SYNC 0;[7:7:{}:5:1]
    USETSHMSZ.FLUSH;[7:7:{}:1:0]
"""),
    ("warp0 4K, warp1 32K, no FLUSH", """
    S2R R2, SR_TID.X;[2:7:{}:5:1]
    ISETP.LT.AND P4, PT, R2, 0x20, PT;[7:7:{2}:13:1]
    @!P4 BRA #label(mw_32k_nf);[7:7:{}:5:1]
    USETSHMSZ 0x1000;[7:7:{}:1:0]
    BRA #label(mw_sizes_done_nf);[7:7:{}:5:1]
#def_label(mw_32k_nf)
    USETSHMSZ 0x8000;[7:7:{}:1:0]
#def_label(mw_sizes_done_nf)
    BAR.SYNC 0;[7:7:{}:5:1]
"""),
    ("warp0 4K, warp1 32K, all FLUSH", """
    S2R R2, SR_TID.X;[2:7:{}:5:1]
    ISETP.LT.AND P4, PT, R2, 0x20, PT;[7:7:{2}:13:1]
    @!P4 BRA #label(mw_32k);[7:7:{}:5:1]
    USETSHMSZ 0x1000;[7:7:{}:1:0]
    BRA #label(mw_sizes_done);[7:7:{}:5:1]
#def_label(mw_32k)
    USETSHMSZ 0x8000;[7:7:{}:1:0]
#def_label(mw_sizes_done)
    BAR.SYNC 0;[7:7:{}:5:1]
    USETSHMSZ.FLUSH;[7:7:{}:1:0]
"""),
]
for name, control in MW_CONTROLS:
    try:
        peak = occupancy_peak(control, block=64)
        result = f"{peak} live threads ({peak // 64} CTAs GPU-wide)"
    except RuntimeError as exc:
        result = "ERR " + str(exc)
    print(f"{name:<40} -> {result}")

for shared in (0x8000, 0x1000):
    peak = occupancy_peak("", shared, block=64)
    label = f"static {shared // 1024}K control"
    print(f"{label:<40} -> {peak} live threads ({peak // 64} CTAs GPU-wide)")

print("\n=== malformed collective vs CTA turnover (block 64) ===")
mw_by_name = dict(MW_CONTROLS)
for case_name in ("only warp0 shrink+FLUSH",
                  "warp0 4K, warp1 32K, no FLUSH"):
    results = []
    for grid in (1, 170, 171, 340):
        try:
            peak = occupancy_peak(mw_by_name[case_name], block=64, grid=grid)
            results.append(f"g{grid}=OK({peak // 64})")
        except RuntimeError as exc:
            code = "700" if "700" in str(exc) else "ERR"
            results.append(f"g{grid}={code}")
    print(f"{case_name:<40} -> {' '.join(results)}")
