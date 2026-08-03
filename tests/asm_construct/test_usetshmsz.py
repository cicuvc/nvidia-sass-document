import sys, os, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# USETSHMSZ — set shared-memory size (udp_pipe, sm90 opcode 0x19c9 / UR 0x13c9).
#
# Empirically verified on SM120 (RTX 5090), per case in a clean subprocess:
#   1. It SHRINKS the CTA's shared-memory window to the given byte size.
#   2. Monotone decrease ONLY: a value > the CURRENT window -> ILLEGAL_INSTRUCTION
#      (CUDA 715).  You cannot grow it back, but you can keep shrinking.
#   3. The constraint is relative to the CURRENT size, not the initial one
#      (0x200->0x400 is illegal, 0x200->0x100 is fine).
#   4. Granularity is 128 bytes: 0x0, 0x80, 0x100, 0x180, 0x1000 are legal;
#      0x40, 0x7F, 0x101, 0x1C0 are illegal (715).
#   5. The shrink really takes effect: after setting 0x200, LDS/STS @0x80 is OK
#      but @0x400 (beyond the new window) faults with ILLEGAL_ADDRESS (700).
#   6. Initial window = the size the driver allocated for the CTA (the cubin
#      SHARED declaration).  USETSHMSZ > that is illegal.
#   7. Per-launch: the window resets on the next kernel launch — a shrink in
#      one kernel does not affect a later kernel's initial window.
#   8. .FLUSH executes cleanly and does NOT lift the monotone constraint.
#   9. UR form: size comes from a uniform register, same monotone rule.
#
# ptxas/nvcc never emit this instruction (absent from cublas/cublasLt); it is a
# runtime shrink-only knob on the uniform datapath.
# ---------------------------------------------------------------------------

import subprocess as _sp
import tempfile

ASSEMBLER = str(Path(__file__).resolve().parents[2])


def run_case(body, *, shared=0x1000, sig="out<8>", args=None):
    """Run one USETSHMSZ variant in a clean CUDA context (subprocess) so a 715
    /700 fault doesn't poison the rest."""
    outfile = tempfile.mktemp(suffix=".out")
    code = f'''
import sys, struct
sys.path.insert(0, {ASSEMBLER!r})
from assembler import assemble, CudaModule
body = {body!r}
src = "#fn k({sig}) {{\\n" \\
      "    #pragma SHARED(0x{shared:X})\\n" \\
      "    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]\\n" \\
      "    LDC.64 {{R6,R7}}, #param(out);[1:7:{{}}:1:0]\\n" \\
      + body + \\
      "    MOV32I R2, 0x12345678;[7:7:{{}}:5:1]\\n" \\
      "    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[0:1:{{0,1}}:1:0]\\n" \\
      "    EXIT;[7:7:{{}}:5:0]\\n" \\
      "}}"
cubin = assemble(src)
mod = CudaModule(cubin)
d = mod.devmem_alloc(16)
mod.device_write(d, struct.pack("<4I", 0,0,0,0))
try:
    mod.launch("k", grid=(1,), block=(32,), args=[d{(", " + repr(list(args))[1:-1]) if args else ""}])
    mod.synchronize()
    res = struct.unpack("<I", mod.device_read(d+0x0, 4))[0]
    open({outfile!r}, "w").write("OK 0x%08x" % res)
except RuntimeError as e:
    open({outfile!r}, "w").write("ERR " + str(e)[:60])
'''
    _sp.run([sys.executable, "-c", code], capture_output=True, text=True)
    try:
        with open(outfile) as f:
            return f.read().strip()
    except FileNotFoundError:
        r = _sp.run([sys.executable, "-c", code], capture_output=True, text=True)
        return "NOOUTPUT: " + (r.stderr or "")[-120:]


def SZ(v):
    return f"    USETSHMSZ 0x{v:X};[7:7:{{}}:1:0]\n"


def STS(off):
    return (f"    MOV32I R0, 0xDEADBEEF;[7:7:{{}}:5:1]\n"
            f"    STS [RZ+0x{off:X}], R0;[7:7:{{}}:5:1]\n"
            f"    LDS R2, [RZ+0x{off:X}];[7:7:{{0}}:8:1]\n")


def SZ_UR():
    return "    USETSHMSZ UR6;[7:7:{}:1:0]\n"


cases = [
    ("equal 0x1000",          SZ(0x1000),                              "OK", None),
    ("decrease chain",        SZ(0x800)+SZ(0x400)+SZ(0x200),           "OK", None),
    ("step to 0",             SZ(0x200)+SZ(0x100)+SZ(0x80)+SZ(0x0),    "OK", None),
    ("gran 0x180",            SZ(0x180),                               "OK", None),
    ("gran 0x0",              SZ(0x0),                                 "OK", None),
    ("shrink in-window",      SZ(0x200)+STS(0x80),                     "OK", None),
    ("flush",                 SZ(0x200)+"    USETSHMSZ.FLUSH;[7:7:{}:1:0]\n", "OK", None),
    ("flush then shrink",     SZ(0x200)+"    USETSHMSZ.FLUSH;[7:7:{}:1:0]\n"+SZ(0x100), "OK", None),
    ("ur form 0x200",         "    LDCU.32 UR6, #param(sz);[7:7:{1}:5:1]\n"+SZ_UR(), "OK", "ur"),
    ("grow-back",             SZ(0x800)+SZ(0x1000),                    "ERR 715", None),
    ("grow relative",         SZ(0x200)+SZ(0x400),                     "ERR 715", None),
    ("grow beyond decl",      SZ(0x2000),                              "ERR 715", None),
    ("gran 0x40",             SZ(0x40),                                "ERR 715", None),
    ("gran 0x7F",             SZ(0x7F),                                "ERR 715", None),
    ("gran 0x101",            SZ(0x101),                               "ERR 715", None),
    ("gran 0x1C0",            SZ(0x1C0),                               "ERR 715", None),
    ("shrink out-of-window",  SZ(0x200)+STS(0x400),                    "ERR 700", None),
    ("flush then grow",       SZ(0x200)+"    USETSHMSZ.FLUSH;[7:7:{}:1:0]\n"+SZ(0x400), "ERR 715", None),
]


def ur_args():
    return (0x200,)


print("=== USETSHMSZ (SM120): shrink-only shared-memory window ===")
ok = True
for name, body, expect, tag in cases:
    args = ur_args() if tag == "ur" else None
    sig = "out<8>, sz<4>" if tag == "ur" else "out<8>"
    res = run_case(body, sig=sig, args=args)
    good = res.startswith("OK") if expect == "OK" else (expect[4:] in res)
    ok &= good
    print(f"  {name:<22} expect {expect:<9} -> {res[:44]}  {'ok' if good else 'FAIL'}")

# per-launch reset: a shrink in one kernel must not affect the next launch
sys.path.insert(0, ASSEMBLER)
from assembler.runner import reset_context

def mk(pre):
    return ("#fn k(out<8>) {\n"
            "    #pragma SHARED(0x1000)\n"
            "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]\n"
            "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
            + pre +
            "    MOV32I R2, 0x12345678;[7:7:{}:5:1]\n"
            "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R2;[0:1:{0,1}:1:0]\n"
            "    EXIT;[7:7:{}:5:0]\n}"
            )

reset_context()
m1 = CudaModule(assemble(mk("USETSHMSZ 0x200;[7:7:{}:1:0]\n")))
d1 = m1.devmem_alloc(16)
m1.device_write(d1, struct.pack("<4I", 0, 0, 0, 0))
m1.launch("k", grid=(1,), block=(32,), args=[d1])
m1.synchronize()
m2 = CudaModule(assemble(mk("USETSHMSZ 0x1000;[7:7:{}:1:0]\n")))
d2 = m2.devmem_alloc(16)
m2.device_write(d2, struct.pack("<4I", 0, 0, 0, 0))
try:
    m2.launch("k", grid=(1,), block=(32,), args=[d2])
    m2.synchronize()
    per = True
    print(f"  {'per-launch reset':<22} expect OK     -> OK  ok")
except RuntimeError as e:
    per = False
    print(f"  {'per-launch reset':<22} expect OK     -> ERR {str(e)[:44]}  FAIL")
ok &= per

print(f"\n=== USETSHMSZ shrink-only semantics: {'ALL OK' if ok else 'FAILED'} ===")
print("USETSHMSZ shrinks the CTA shared window (128B granule); growing -> 715,"
      "\nshrink persists within the launch only, .FLUSH does not unlock growth.")
sys.exit(0 if ok else 1)
