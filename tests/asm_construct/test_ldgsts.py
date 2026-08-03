import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat

# ---------------------------------------------------------------------------
# LDGSTS (cp.async) — asynchronous global→shared copy (mio_pipe, VQ_AGU).
#
# Verified SM120, mirroring the nvcc sequence:
#   LDGSTS.E.BYPASS.128 [Rshared], desc[UR4][Rsrc.64]    ; async 16B copy
#   LDGDEPBAR[wr=SB0]        ; bind ALL prior LDGSTS completions to SB0
#   DEPBAR.LE SB0, 0x0       ; wait until every LDGSTS has landed in shared
#   BAR.SYNC 0               ; warp-wide visibility
#   LDS ..., [Rshared]       ; read the copied data
#
# Key facts:
#   * dest [Rb] is a SHARED-window byte offset (0x400 with our 16KB window).
#   * source is desc[UR4][Ra.64+off] — 64-bit global address.
#   * LDGSTS itself does NOT set a result SB (it writes shared, IDEST=0);
#     LDGDEPBAR's wr=SB0 binds every prior LDGSTS completion to SB0, and
#     DEPBAR.LE SB0,0x0 drains it.  LDGSTS's rd_sb (e.g. 2) is an
#     anti-dependency on the source registers.
#   * .BYPASS requires sz=.128 (spec condition); .128 copies 16 bytes/lane.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = (list(got) if isinstance(got, (tuple, list)) else got) == \
           (list(want) if isinstance(want, (tuple, list)) else want)
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<46} {got}")


def run_ldgsts(block=1):
    """LDGSTS.E.BYPASS.128: lane t copies out[16t..16t+15] to shared
    [0x400 + 16t], waits (LDGDEPBAR→DEPBAR.LE SB0), reads 16B back (LDS.128)
    and stores them at out[16t + 0x200].  Returns the out words.
    Source address is computed in-place: R6 (out base) is bumped by t*16."""
    src = """#fn k(out<8>) {
    #pragma SHARED(0x4000)
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[3:7:{}:1:0]
    LDC.64 {R6,R7}, #param(out);[3:7:{}:1:0]
    S2R R0, SR_TID.X;[4:7:{}:5:1]
    SHF.L.U32 R1, R0, 4, RZ;[7:7:{4}:5:1]
    IADD3 R5, R1, 0x400, RZ;[7:7:{}:5:1]
    IADD3 R6, R6, R1, RZ;[7:7:{3}:5:1]
    LDGSTS.E.BYPASS.128 [R5], desc[{UR4,UR5}][{R6,R7}+0x0];[7:2:{}:5:1]
    LDGDEPBAR;[0:7:{}:5:0]
    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]
    BAR.SYNC 0;[7:7:{}:5:1]
    LDS.128 {R8,R9,R10,R11}, [R5];[1:7:{0}:8:1]
    STG.E.128 desc[{UR4,UR5}][{R6,R7}+0x200], {R8,R9,R10,R11};[0:1:{0,1}:1:0]
    EXIT;[7:7:{}:5:0]
}"""
    mod = CudaModule(assemble(src))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<256I", *list(range(256))))
    mod.launch("k", grid=(1,), block=(block,), args=[d])
    mod.synchronize()
    v = struct.unpack("<256I", mod.device_read(d, 1024))
    try:
        mod.devmem_free(d)
    except Exception:
        pass
    return v


# --- 1. full warp: 32 lanes copy 16B each = 512B ---------------------------
# single lane is the block=1 subset of the same kernel
v = run_ldgsts(block=32)
bad = [i for i in range(128) if v[i] != v[i + 128]]
check("LDGSTS warp 32×16B roundtrip", "ok" if not bad else bad[:5], "ok")
v1 = run_ldgsts(block=1)
bad = [i for i in range(4) if v1[i] != v1[i + 128]]
check("LDGSTS single lane 16B roundtrip", "ok" if not bad else bad[:5], "ok")

# --- 3. sz=.32 (4B) and sz=.64 (8B) per lane -------------------------------
def run_sz(sz, nwords):
    reads = "".join(
        f"    LDS R{10+i}, [R5+0x{i*4:X}];[1:7:{{0}}:8:1]\n" for i in range(nwords))
    stores = "".join(
        f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{0x40+i*4:X}], R{10+i};[0:1:{{0}}:1:0]\n"
        for i in range(nwords))
    src = f"""#fn k(out<1024>) {{
    #pragma SHARED(0x4000)
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{{}}:1:0]
    LDC.64 {{R6,R7}}, #param(out);[1:7:{{}}:1:0]
    S2R R0, SR_TID.X;[4:7:{{}}:5:1]
    SHF.L.U32 R1, R0, 4, RZ;[7:7:{{4}}:5:1]
    IADD3 R5, R1, 0x400, RZ;[7:7:{{4}}:5:1]
    IADD3 R8, R6, R1, RZ;[7:7:{{1,4}}:5:1]
    IADD3 R9, R7, RZ, RZ;[7:7:{{1}}:5:1]
    LDGSTS.E.{sz} [R5], desc[{{UR4,UR5}}][{{R8,R9}}+0x0];[1:7:{{1}}:5:1]
    LDGDEPBAR;[0:7:{{}}:5:1]
    DEPBAR.LE SB0, 0x0;[7:7:{{}}:5:1]
    BAR.SYNC 0;[7:7:{{}}:5:1]
{reads}
    NOP;[7:7:{{}}:5:1]  NOP;[7:7:{{}}:5:1]  NOP;[7:7:{{}}:5:1]  NOP;[7:7:{{}}:5:1]
{stores}
    EXIT;[7:7:{{}}:5:0]
}}"""
    mod = CudaModule(assemble(src))
    d = mod.devmem_alloc(1024)
    pat = list(range(256))
    mod.device_write(d, struct.pack("<256I", *pat))
    mod.launch("k", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    v = struct.unpack("<256I", mod.device_read(d, 1024))
    return list(v[0x40 // 4: 0x40 // 4 + nwords])

check("LDGSTS.E.32 copies 4B", run_sz("32", 1), [0])
check("LDGSTS.E.64 copies 8B", run_sz("64", 2), [0, 1])

# --- 4. encoding vs nvcc sm_120 ---------------------------------------------
# nvcc -arch=sm_120 LDGSTS.E.BYPASS.128: lo=0x0000000002057fae hi=0x0085e2000b981804
e = assemble_flat(
    "LDGSTS.E.BYPASS.128 [R5], desc[{UR4,UR5}][{R6,R7}+0x0];[1:7:{0}:5:1]\n")[0]
nv_lo, nv_hi = 0x0000000002057fae, 0x0085e2000b981804
def data_bits_diff(lo1, hi1, lo2, hi2):
    # compare non-scheduling, non-register bits (register numbers differ)
    return sorted(
        set(g for g in range(64, 105) if (hi1 >> (g - 64)) & 1 != (hi2 >> (g - 64)) & 1) |
        set(g for g in range(0, 16) if (lo1 >> g) & 1 != (lo2 >> g) & 1))
diff = data_bits_diff(e[0], e[1], nv_lo, nv_hi)
check("LDGSTS encode data bits match nvcc", diff, [])

print(f"\n=== LDGSTS (cp.async): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
