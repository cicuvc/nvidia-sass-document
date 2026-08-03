import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_flat, assemble, CudaModule

# ---------------------------------------------------------------------------
# FSWZADD — FP32 swizzle-add, semantics re-probed with a CLEAN hand-built ELF
# (S2R lane-id + LDG per-lane Ra/Rc), SM120.
#
# Encoding (verified): opcode 0x822, Rd [23:16], Ra [31:24], npCtrl [39:32]
# (NP enum, 8-char P/N/Z string = 4 base-4 pairs), Rc [71:64], ftz [80],
# rnd [79:78], ndv [77].
#
# Empirical semantics (this test, clean encoding):
#   FSWZADD      (nondv): Rd = 0.0, regardless of Ra/Rc/npCtrl.  The NDV bit
#                 is required to make the instruction compute anything.
#   FSWZADD.NDV:        : Rd = s_a(Ra) + s_b(Rc), purely lane-local (NO
#                 cross-lane quad swizzle reachable from compute).  npCtrl is
#                 a per-quad-lane pair pattern: lane%4 selects pair k, and
#                 pair "ab" means a={P:+1,N:-1,Z:0} scales Ra, b={P:+1,N:-1}
#                 scales Rc.  Rounding per Round1 (RN default); FTZ flushes
#                 inputs and result.
#
# The earlier patch-based probe (FFMA->FSWZADD, reusing FFMA's hi64 control
# bits) reported "Rd = Ra pass-through" — that was an ARTIFACT of the bogus
# scheduling/control word; the clean encoding gives Rd=0 / signed add.
# ---------------------------------------------------------------------------

# --- encoding round-trip ---------------------------------------------------
def npval(s):
    pairs = {"PP": 0, "PN": 1, "NP": 2, "ZP": 3}
    v = 0
    for i in range(0, 8, 2):
        v = v * 4 + pairs[s[i:i + 2]]
    return v

for s, exp in (("PPPPPPPP", 0), ("PPPPPPPN", 1), ("PPPPPPNP", 2),
               ("NPPNNPPN", 0x99), ("ZPZPZPZP", 0xff), ("PPPPZPNP", 14)):
    lo, hi = assemble_flat(f'FSWZADD R5, R0, R7, {s};[7:7:{{}}:5:1]')[0]
    np_ctrl = (lo >> 32) & 0xFF
    assert np_ctrl == exp, f"{s}: npCtrl {np_ctrl:#x} != {exp:#x}"
    assert (lo >> 16) & 0xFF == 5          # Rd
    assert (lo >> 24) & 0xFF == 0          # Ra
    assert hi & 0xFF == 7                  # Rc [71:64]
    assert lo & 0xFFF == 0x822             # opcode
print("encoding round-trip OK (NP strings, opcode 0x822, Rc [71:64])")

# --- semantic probe: clean hand-built kernel -------------------------------
F = lambda b: struct.unpack("<f", struct.pack("<I", b))[0]

def run(nps, Ra, Rc, mods="", nlanes=8):
    """Per-lane LDG Ra/Rc, FSWZADD, STG result at buf+lane*4+0x100."""
    lines = ["#fn fswz(buf<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[0:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             "    IADD3 R4, R2, R2, RZ;[7:7:{0}:5:1]",
             "    IADD3 R4, R4, R4, RZ;[7:7:{}:5:1]",
             "    IADD3 R16, R6, R4, RZ;[7:7:{}:5:1]",
             "    IADD3 R17, R7, RZ, RZ;[7:7:{}:5:1]",
             "    LDG.E R10, desc[{UR4,UR5}][{R16,R17}];[1:7:{0}:5:1]",        # Ra, wr=SB1
             "    IADD3 R18, R10, RZ, RZ;[7:7:{1}:5:1]",
             "    LDG.E R11, desc[{UR4,UR5}][{R16,R17}+0x80];[2:7:{0}:5:1]",   # Rc, wr=SB2
             "    IADD3 R19, R11, RZ, RZ;[7:7:{2}:5:1]",
            f"    FSWZADD{mods} R22, R10, R11, {nps};[7:7:{{}}:5:1]",
             "    IADD3 R23, R22, RZ, RZ;[7:7:{}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R16,R17}+0x100], R23;[0:1:{0}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    cubin = assemble("\n".join(lines))
    mod = CudaModule(cubin)
    init = [0] * 128
    Ra = list(Ra) + [1.0] * (nlanes - len(Ra))
    Rc = list(Rc) + [10.0] * (nlanes - len(Rc))
    for i in range(nlanes):
        init[i] = struct.unpack("<I", struct.pack("<f", Ra[i]))[0]
        init[32 + i] = struct.unpack("<I", struct.pack("<f", Rc[i]))[0]
    d = mod.devmem_alloc(4096)
    mod.device_write(d, struct.pack("<128I", *init))
    mod.launch("fswz", grid=(1,), block=(nlanes,), args=[d])
    mod.synchronize()
    res = struct.unpack("<8I", mod.device_read(d + 0x100, 32))
    mod.devmem_free(d)
    return [F(v) for v in res]

ok = True
def check(name, got, want):
    global ok
    if got != want:
        ok = False
        print(f"FAIL {name}: {got} != {want}")
    else:
        print(f"ok   {name}: {got}")

# 1. nondv (default) => 0.0 regardless
for nps in ("PPPPPPPP", "NPPNNPPN", "ZPZPZPZP"):
    check(f"nondv {nps}", run(nps, [1 + i for i in range(8)], [100 + i for i in range(8)]),
          [0.0] * 8)
# 2. NDV PPPP... => Ra + Rc (all +)
check("NDV PPPPPPPP", run("PPPPPPPP", [1 + i for i in range(8)], [100 + i for i in range(8)], ".NDV"),
      [101 + 2 * i for i in range(8)])
# 3. NDV pair semantics, per-quad-lane (lane%4), powers of two
Ra8 = [2.0 ** l for l in range(8)]
Rc8 = [2.0 ** (l + 4) for l in range(8)]
# NPPNNPPN = pairs NP PN NP PN => -Ra+Rc, +Ra-Rc, -Ra+Rc, +Ra-Rc
check("NDV NPPNNPPN", run("NPPNNPPN", Ra8, Rc8, ".NDV"),
      [15, -30, 60, -120, 240, -480, 960, -1920])
# NPNPNPNP = all NP => Rc - Ra (nlanes=4: single quad, pairs repeat per lane)
check("NDV NPNPNPNP", run("NPNPNPNP", [1, 2, 4, 8], [16, 32, 64, 128], ".NDV", nlanes=4)[:4],
      [15, 30, 60, 120])
# ZPZPZPZP = Z on Ra, P on Rc => Rc only (nlanes=4)
check("NDV ZPZPZPZP", run("ZPZPZPZP", [1, 2, 4, 8], [16, 32, 64, 128], ".NDV", nlanes=4)[:4],
      [16, 32, 64, 128])
# 4. no cross-lane: all lanes share Rc=100 => lane-local Ra+100
check("NDV cross-lane?", run("PPPPPPPP", Ra8, [100.0] * 8, ".NDV"),
      [100 + 2.0 ** l for l in range(8)])
# 5. rounding: 1e8 + 1 (not representable in FP32, ulp=8)
check("NDV .RN 1e8+1", run("PPPPPPPP", [1e8], [1.0], ".NDV")[:1], [100000000.0])
check("NDV .RP 1e8+1", run("PPPPPPPP", [1e8], [1.0], ".NDV.RP")[:1], [100000008.0])
check("NDV .RM 1e8+1", run("PPPPPPPP", [1e8], [1.0], ".NDV.RM")[:1], [100000000.0])
# 6. FTZ flushes denormals (1e-40 is denormal in FP32; nearest FP32 denormal)
DEN = 1.0e-40
check("NDV noFTZ denorm", run("PPPPPPPP", [DEN], [0.0], ".NDV", nlanes=4)[:1],
      [struct.unpack("<f", struct.pack("<f", DEN))[0]])
check("NDV .FTZ denorm", run("PPPPPPPP", [DEN], [0.0], ".NDV.FTZ", nlanes=4)[:1], [0.0])

print(f"=== FSWZADD clean-kernel semantic probe: {'ALL OK' if ok else 'FAILED'} ===")
print("FSWZADD(nondv)=0; FSWZADD.NDV = s_a(Ra)+s_b(Rc) lane-local (pair signs, lane%4)")
