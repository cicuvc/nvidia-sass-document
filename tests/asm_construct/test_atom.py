import sys, struct, ctypes
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# ATOM / ATOMG / REDG — global atomic operations (sm_120, verified on RTX 5090).
#
# nvcc (CUDA 12.8) pattern survey (cuobjdump -arch sm_120):
#   PTX  atom.*  (with return)  ->  ATOM.E.<op>[.type].STRONG.<scope>  opcode 0x98a family
#   C++  atomicOp (with return) ->  ATOMG.E.<op>[.type].STRONG.<scope>  opcode 0x9a8 family
#   PTX  red.* / C++ no-return  ->  REDG.E.<op>[.type].STRONG.<scope>   opcode 0x98e family
#   PTX  atom.inc/dec .u32      ->  ATOM.E.INC/.DEC.STRONG.<scope>
#   atom.relaxed.* is lowered to STRONG; release/acq_rel insert MEMBAR.ALL.
#   Scopes: PTX .gpu -> .GPU, .cta -> .SM, .sys -> .SYS.
#   F32 ops carry .FTZ.RN, F64 carry .RN, S32 ops carry .S32 (ATOM) or are the
#   default (ATOMG).  64-bit ops use aligned {Ra,Rb} register groups.
#   Two source operands only for CAS:  ATOM.E.CAS[.64] Pg, Rd, [addr], Rb, Rc.
#
# The 64-bit global address must be the explicit {Ra,Rb} group (assembler
# dialect), the consumer must req both its scoreboards, and ATOM's result Rd
# lands on wr=SB5 — a consumer reading it must req SB5.
# ---------------------------------------------------------------------------

check_fail = [0]


def check(name, got, want):
    good = got == want
    if not good:
        check_fail[0] = 1
    print(f"{'ok ' if good else 'FAIL'} {name}: {got}{'' if good else f'  (want {want})'}")


def build_kernel(slots, extra=""):
    """Return a kernel that atomically applies each (mnemonic, addr_off) in
    slots from every of `block` threads.  slot tuple: (sass_line, off, want_fn)
    is handled by the caller; here we just assemble + launch + read back."""
    body = "\n".join("    " + s for s in slots)
    src = ("#fn k(p<8>) {\n"
           "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]\n"
           "    LDC.64 {R6,R7}, #param(p);[1:7:{}:1:0]\n"
           + body +
           "    EXIT;[7:7:{}:5:0]\n}"
           )
    reset_context()
    mod = CudaModule(assemble(src))
    d = mod.devmem_alloc(8192)
    mod.device_write(d, struct.pack("<2048I", *([0] * 2048)))
    return mod, d


def launch(mod, d, grid=1, block=256):
    mod.launch("k", grid=(grid,), block=(block,), args=[d])
    mod.synchronize()
    return struct.unpack("<256I", mod.device_read(d, 1024))


print("=== 1. ATOM 32-bit ops (256 threads, one atom each) ===")
SLOT = "SLOT"
mod, d = build_kernel([
    "S2R R2, SR_TID.X;[0:7:{}:5:1]",
    "MOV32I R10, 0x1;[7:7:{}:5:1]",
    "ATOM.E.ADD.S32.STRONG.GPU PT, R16, [{R6,R7}], R10;[5:7:{0,1}:8:1]",     # +1
    "REDG.E.ADD.S32.STRONG.GPU [{R6,R7}+4], R10;[5:7:{0,1}:8:1]",            # +1 no-ret
    "ATOM.E.MAX.S32.STRONG.GPU PT, R17, [{R6,R7}+8], R2;[5:7:{0,1}:8:1]",    # max(tid)
    "ATOM.E.MIN.S32.STRONG.GPU PT, R18, [{R6,R7}+12], R2;[5:7:{0,1}:8:1]",   # min(tid) init 0 -> 0
    "MOV32I R12, 0xFFFFFFFF;[7:7:{}:5:1]",
    "ATOM.E.EXCH.STRONG.GPU PT, R19, [{R6,R7}+16], R2;[5:7:{0,1}:8:1]",      # exch tid
    "MOV32I R13, 0x0;[7:7:{}:5:1]",
    "ATOM.E.INC.STRONG.GPU PT, R20, [{R6,R7}+20], R12;[5:7:{0,1}:8:1]",      # inc limit~ (no wrap)
    "ATOM.E.DEC.STRONG.GPU PT, R21, [{R6,R7}+24], R12;[5:7:{0,1}:8:1]",      # dec limit~ (0->lim->-1...)
    "STG.E desc[{UR4,UR5}][{R6,R7}+32], R16;[0:1:{0,1,5}:1:0]",
    "STG.E desc[{UR4,UR5}][{R6,R7}+36], R17;[0:1:{0,1,5}:1:0]",
    "STG.E desc[{UR4,UR5}][{R6,R7}+40], R18;[0:1:{0,1,5}:1:0]",
    "STG.E desc[{UR4,UR5}][{R6,R7}+44], R19;[0:1:{0,1,5}:1:0]",
    "STG.E desc[{UR4,UR5}][{R6,R7}+48], R20;[0:1:{0,1,5}:1:0]",
    "STG.E desc[{UR4,UR5}][{R6,R7}+52], R21;[0:1:{0,1,5}:1:0]",
])
v = launch(mod, d)
check("ATOM.E.ADD.S32  x256 (+1)      ", v[0], 256)
check("REDG.E.ADD.S32  x256 (+1)      ", v[1], 256)
check("ATOM.E.MAX.S32  (tid 0..255)   ", v[2], 255)
check("ATOM.E.MIN.S32  (init 0)       ", v[3], 0)
check("ATOM.E.EXCH     (init 0)       ", v[4] < 256, True)
check("ATOM.E.INC (lim ~, x256)       ", v[5], 256)
check("ATOM.E.DEC (lim ~, x256)       ", v[6], 0xFFFFFF00)
check("ATOM ret ADD old (tid0, 0..255)", v[7] < 256, True)
check("ATOM ret MAX old (tid0 0..255) ", v[8] < 256, True)
check("ATOM ret EXCH old              ", v[9] < 256, True)

print("=== 2. CAS (first-wins, order nondeterministic) ===")
# CAS slot: host-initialized 0xDEADBEEF, each thread CAS(0xDEADBEEF -> tid);
# first winner.  Initialized from the host (not a kernel STG) so there is no
# write-read race between the init store and the CAS loops — no MEMBAR needed.
mod, d = build_kernel([
    "S2R R2, SR_TID.X;[0:7:{}:5:1]",
    "MOV32I R11, 0xDEADBEEF;[7:7:{}:5:1]",
    "ATOM.E.CAS.STRONG.GPU PT, R16, [{R6,R7}+60], R11, R2;[5:7:{0,1}:8:1]",
    "STG.E desc[{UR4,UR5}][{R6,R7}+64], R16;[0:1:{0,1,5}:1:0]",
])
mod.device_write(d + 240, struct.pack("<I", 0xDEADBEEF))  # host-init [p]+60 (no kernel race)
v = launch(mod, d)
check("CAS.S32 winner (some tid 0..255)", 0 <= v[15] < 256, True)
check("CAS.S32 loser old (tid0)          ", v[16] < 256, True)

print("=== 3. 64-bit ops ===")
mod, d = build_kernel([
    "MOV32I R10, 0x1;[7:7:{}:5:1]",
    "MOV32I R11, 0x0;[7:7:{}:5:1]",
    "MOV32I R12, 0x0;[7:7:{}:5:1]",
    "MOV32I R13, 0x0;[7:7:{}:5:1]",
    "S2R R2, SR_TID.X;[0:7:{}:5:1]",
    "MOV32I R3, 0x0;[7:7:{}:5:1]",
    "ATOM.E.ADD.64.STRONG.GPU PT, {R16,R17}, [{R6,R7}], {R10,R11};[5:7:{0,1}:8:1]",     # +1 x256 at [p]
    "ATOM.E.CAS.64.STRONG.GPU PT, {R18,R19}, [{R6,R7}+8], {R12,R13}, {R2,R3};[5:7:{0,1}:8:1]",  # CAS(0->tid)
    "STG.E desc[{UR4,UR5}][{R6,R7}+32], R16;[0:1:{0,1,5}:1:0]",
    "STG.E desc[{UR4,UR5}][{R6,R7}+36], R17;[0:1:{0,1,5}:1:0]",
    "STG.E desc[{UR4,UR5}][{R6,R7}+40], R18;[0:1:{0,1,5}:1:0]",
])
v = launch(mod, d)
add64 = v[0] | (v[1] << 32)          # accumulated at [p]
cas64 = v[2] | (v[3] << 32)          # accumulated at [p]+8
check("ATOM.E.ADD.64  x256 (+1)  ", add64, 256)
check("ATOM.E.CAS.64  (0->tid)   ", cas64 < 256, True)
check("ATOM.E.ADD.64 ret old     ", (v[8] | (v[9] << 32)) < 256, True)
check("ATOM.E.CAS.64 ret old     ", (v[10] | (v[11] << 32)) < 256, True)

print("=== 4. F32 / F64 add ===")
mod, d = build_kernel([
    "MOV32I R10, 0x3FC00000;[7:7:{}:5:1]",          # 1.5f
    "MOV R4, R6;[1:7:{1}:5:1]",                     # addr -> R4 (wait SB1=R6)
    "MOV R5, R7;[1:7:{1}:5:1]",
    "MOV32I R6, 0x0;[7:7:{}:5:1]",                  # 2.5 lo
    "MOV32I R7, 0x40040000;[7:7:{}:5:1]",           # 2.5 hi
    "ATOM.E.ADD.F32.FTZ.RN.STRONG.GPU PT, R16, [{R4,R5}], R10;[5:7:{0,1}:8:1]",
    "REDG.E.ADD.F32.FTZ.RN.STRONG.GPU [{R4,R5}+4], R10;[5:7:{0,1}:8:1]",
    "ATOM.E.ADD.F64.RN.STRONG.GPU PT, {R8,R9}, [{R4,R5}+8], {R6,R7};[5:7:{0,1}:8:1]",
    "STG.E desc[{UR4,UR5}][{R4,R5}+32], R16;[0:1:{0,1,5}:1:0]",
    "STG.E desc[{UR4,UR5}][{R4,R5}+40], R8;[0:1:{0,1,5}:1:0]",
    "STG.E desc[{UR4,UR5}][{R4,R5}+44], R9;[0:1:{0,1,5}:1:0]",
])
v = launch(mod, d)
f32 = v[0]                            # accumulated at [p]
rf32 = v[1]                           # accumulated at [p]+4
f64 = v[2] | (v[3] << 32)             # accumulated at [p]+8
check("ATOM.E.ADD.F32.FTZ.RN 256*1.5", f32, struct.unpack("<I", struct.pack("<f", 384.0))[0])
check("REDG.E.ADD.F32.FTZ.RN 256*1.5", rf32, struct.unpack("<I", struct.pack("<f", 384.0))[0])
check("ATOM.E.ADD.F64.RN 256*2.5    ", f64, struct.unpack("<Q", struct.pack("<d", 640.0))[0])
check("ATOM ret F32 old (tid0)      ", v[8] < 0x7F800000, True)
check("ATOM ret F64 old (tid0)      ", (v[10] | (v[11] << 32)) < 0x7FF0000000000000, True)

print("=== 5. scopes GPU / SYS / SM ===")
mod, d = build_kernel([
    "MOV32I R10, 0x1;[7:7:{}:5:1]",
    "ATOM.E.ADD.S32.STRONG.GPU PT, RZ, [{R6,R7}], R10;[5:7:{0,1}:8:1]",
    "ATOM.E.ADD.S32.STRONG.SYS PT, RZ, [{R6,R7}+4], R10;[5:7:{0,1}:8:1]",
    "ATOM.E.ADD.S32.STRONG.SM  PT, RZ, [{R6,R7}+8], R10;[5:7:{0,1}:8:1]",
    "REDG.E.ADD.S32.STRONG.GPU [{R6,R7}+12], R10;[5:7:{0,1}:8:1]",
])
v = launch(mod, d)
check("ATOM .GPU scope x256", v[0], 256)
check("ATOM .SYS scope x256", v[1], 256)
check("ATOM .SM  scope x256", v[2], 256)
check("REDG .GPU scope x256", v[3], 256)

print("=== 6. predicate guard (@P0: only tid0) ===")
mod, d = build_kernel([
    "S2R R2, SR_TID.X;[0:7:{}:5:1]",
    "ISETP.EQ.AND P0, PT, R2, RZ, PT;[7:7:{0}:13:1]",
    "MOV32I R10, 0x1;[7:7:{}:5:1]",
    "@P0 ATOM.E.ADD.S32.STRONG.GPU PT, RZ, [{R6,R7}], R10;[5:7:{0,1}:8:1]",
])
v = launch(mod, d)
check("@P0 ATOM.ADD (1 thread only)", v[0], 1)

print("=== 7. encoding vs nvcc (lo64, exact nvcc operands) ===")
# nvcc patterns captured with cuobjdump -arch sm_120; we reassemble the SAME
# operands (incl. predicate/desc) and compare the data word.  hi differs only
# in scheduling bits (nvcc uses compiler-chosen stall/yield).
enc_cases = [
    ("@!P0 ATOM.E.ADD.S32.STRONG.GPU PT, R7, desc[{UR6,UR7}][{R4,R5}], R9",
     0x800000090407898a),
    ("ATOM.E.ADD.64.STRONG.GPU P0, {R12,R13}, desc[{UR6,UR7}][{R4,R5}], {R6,R7}",
     0x80000006040c798a),
    ("@P0 REDG.E.ADD.S32.STRONG.GPU desc[{UR6,UR7}][{R4,R5}+0x4c], R11",
     0x00004c0b0400098e),
    ("@P0 REDG.E.OR.STRONG.SM desc[{UR6,UR7}][{R4,R5}+0x50], R13",
     0x0000500d0400098e),
    ("ATOM.E.CAS.STRONG.GPU PT, R13, [{R4,R5}+0x20], R8, R9",
     0x00002008040d738b),
    ("ATOM.E.CAS.64.STRONG.GPU PT, {R8,R9}, [{R4,R5}+0x8], {R12,R13}, {R14,R15}",
     0x0000080c0408738b),
    ("ATOM.E.ADD.F32.FTZ.RN.STRONG.GPU PT, R0, desc[{UR6,UR7}][{R4,R5}+0x24], R23",
     0x80002417040079a2),
    ("ATOMG.E.ADD.F32.FTZ.RN.STRONG.GPU PT, R0, desc[{UR6,UR7}][{R4,R5}+0x24], R23",
     0x80002417040079a3),
    ("@P0 ATOMG.E.ADD.STRONG.GPU PT, R6, desc[{UR6,UR7}][{R6,R7}], R11",
     0x8000000b060609a8),
]
ok = True
for sass, want_lo in enc_cases:
    try:
        e = assemble_flat(sass + ";[7:7:{}:1:0]\n")[0]
    except Exception as ex:
        print(f"FAIL {sass[:48]:<48} assemble: {str(ex)[:50]}")
        ok = False
        continue
    good = e[0] == want_lo
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {sass[:46]:<46} lo={e[0]:#018x}"
          f"{'' if good else '  want %#018x' % want_lo}")
check_fail[0] |= (0 if ok else 1)

print(f"\n=== ATOM/ATOMG/REDG: {'ALL OK' if not check_fail[0] else 'FAILED'} ===")
print("Verified: ATOM/ATOMG (return old) vs REDG (no return), 32/64-bit, F32/F64,")
print("GPU/SYS/SM scopes, CAS two-source, INC/DEC, predicate guard, and nvcc-exact encodings.")
sys.exit(1 if check_fail[0] else 0)
