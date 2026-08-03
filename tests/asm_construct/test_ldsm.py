import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# LDSM (ldmatrix) — warp-cooperative shared-memory matrix load (mio_pipe,
# VQ_AGU, DECOUPLED_RD_WR_SCBD).  Verified SM120.
#
#   LDSM[.SZ].MODE[.NUM] Rd, [Ra+off]
#     SZ   = .16 | .U4TO8 | .S4TO8 | .U2TO4 | .S2TO4
#     MODE = .M88 (8x8 b16) | .MT88 (transposed) | .M816 | .M832
#     NUM  = .1/.2/.4 (one/two/four 8x8 matrices; Rd = first dest reg)
#
# Address model (verified empirically against nvcc-generated LDSM):
#   * Each thread supplies ONE address.  It names a matrix row:
#       .x1: addr_t = base + t*16            (matrix 0, row t, row-stride 16)
#       .x2/.x4: addr_t = base + (t//8)*128  + (t%8)*32
#                (matrix t//8 at +m*128, row t%8, row-stride 32)
#     Rows are 16 bytes of data; the .x2/.x4 32-byte stride leaves a 16-byte
#     gap between rows (row-stride differs from .x1's contiguous 16).
#   * Fragment: thread t's register for matrix m holds row (t/4) of that
#     matrix, bytes [4*(t%4)..+4) of the row.  The row's data is fetched
#     from the address supplied by thread t/4 (addr_{t/4}).  lo16 = element
#     at +4*(t%4), hi16 = +4*(t%4)+2 (row-major .M88).
#   * .MT88 transposes: register = a[(t%4)*2][t/4] (lo) and a[(t%4)*2+1][t/4]
#     (hi); the data rows come from addr_{(t%4)*2} and addr_{(t%4)*2+1}.
#
# Test: shared is filled with b16 values value[j] = j (so element [m][r][c] =
# 64*m + (r*STRIDE)/2 + c, uniquely identifying the bytes LDSM read).  Every
# lane fills 4 shared 16-byte rows via LDG+STS; addresses are computed on the
# host and passed in through global memory (avoids hand-SASS address math).
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = (list(got) if isinstance(got, (tuple, list)) else got) == \
           (list(want) if isinstance(want, (tuple, list)) else want)
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<46} {got}")

def run_ldsm(addrfn, num, mode="M88", block=32):
    """Kernel: LDG 4 rows of b16 values -> STS; BAR; LDG addr -> LDSM -> STG."""
    rg = "{R20,R21}" if num == 2 else "{R20,R21,R22,R23}" if num == 4 else "R20"
    stores = {"2": "    STG.E desc[{UR4,UR5}][{R16,R17}+0x80], R21;[0:1:{1}:1:0]\n",
              "4": ("    STG.E desc[{UR4,UR5}][{R16,R17}+0x80], R21;[0:1:{1}:1:0]\n"
                    "    STG.E desc[{UR4,UR5}][{R16,R17}+0x100], R22;[0:1:{1}:1:0]\n"
                    "    STG.E desc[{UR4,UR5}][{R16,R17}+0x180], R23;[0:1:{1}:1:0]\n")}.get(str(num), "")
    body = f"""    LDCU.64 {{UR4,UR5}}, c[0x0][0x358];[1:7:{{}}:2:0]
    LDC.64 {{R6,R7}}, #param(out);[1:7:{{}}:1:0]
    LDC.64 {{R8,R9}}, #param(inj);[1:7:{{}}:1:0]
    LDC.64 {{R10,R11}}, #param(addr);[1:7:{{}}:1:0]
    S2R R0, SR_TID.X;[1:7:{{}}:5:1]
    SHF.L.U32 R1, R0, 2, RZ;[7:7:{{1}}:5:1]
    IADD3 R12, R8, R1, RZ;[7:7:{{}}:5:1]
    IADD3 R13, R9, RZ, RZ;[7:7:{{}}:5:1]
    IADD3 R3, R1, 0x400, RZ;[7:7:{{}}:5:1]
    LDG.E R2, desc[{{UR4,UR5}}][{{R12,R13}}+0x0];[1:7:{{}}:8:1]
    STS [R3+0x0], R2;[1:7:{{1}}:5:1]
    LDG.E R2, desc[{{UR4,UR5}}][{{R12,R13}}+0x80];[1:7:{{}}:8:1]
    STS [R3+0x80], R2;[1:7:{{1}}:5:1]
    LDG.E R2, desc[{{UR4,UR5}}][{{R12,R13}}+0x100];[1:7:{{}}:8:1]
    STS [R3+0x100], R2;[1:7:{{1}}:5:1]
    LDG.E R2, desc[{{UR4,UR5}}][{{R12,R13}}+0x180];[1:7:{{}}:8:1]
    STS [R3+0x180], R2;[1:7:{{1}}:5:1]
    LDG.E R2, desc[{{UR4,UR5}}][{{R12,R13}}+0x200];[1:7:{{}}:8:1]
    STS [R3+0x200], R2;[1:7:{{1}}:5:1]
    LDG.E R2, desc[{{UR4,UR5}}][{{R12,R13}}+0x280];[1:7:{{}}:8:1]
    STS [R3+0x280], R2;[1:7:{{1}}:5:1]
    LDG.E R2, desc[{{UR4,UR5}}][{{R12,R13}}+0x300];[1:7:{{}}:8:1]
    STS [R3+0x300], R2;[1:7:{{1}}:5:1]
    LDG.E R2, desc[{{UR4,UR5}}][{{R12,R13}}+0x380];[1:7:{{}}:8:1]
    STS [R3+0x380], R2;[1:7:{{1}}:5:1]
    BAR.SYNC 0;[1:7:{{1}}:2:1]
    IADD3 R14, R10, R1, RZ;[7:7:{{1}}:5:1]
    IADD3 R15, R11, RZ, RZ;[7:7:{{1}}:5:1]
    LDG.E R5, desc[{{UR4,UR5}}][{{R14,R15}}+0x0];[1:7:{{1}}:8:1]
    LDSM.16.{mode}.{num} {rg}, [R5];[1:7:{{1}}:8:1]
    IADD3 R16, R6, R1, RZ;[7:7:{{1}}:5:1]
    IADD3 R17, R7, RZ, RZ;[7:7:{{1}}:5:1]
    STG.E desc[{{UR4,UR5}}][{{R16,R17}}+0x0], R20;[7:7:{{1}}:1:0]
{stores}
"""
    src = ("#fn k(out<8>, inj<8>, addr<8>) {\n    #pragma SHARED(0x4000)\n" + body
           + "    EXIT;[7:7:{}:5:0]\n}")
    mod = CudaModule(assemble(src))
    dout = mod.devmem_alloc(1024)
    dinj = mod.devmem_alloc(4096)
    daddr = mod.devmem_alloc(128)
    inj = list(range(2048))
    mod.device_write(dinj, struct.pack("<2048H", *inj))
    addrs = addrfn(0x400)
    mod.device_write(daddr, struct.pack("<32I", *addrs))
    mod.launch("k", grid=(1,), block=(block,), args=[dout, dinj, daddr])
    mod.synchronize()
    v = struct.unpack("<128I", mod.device_read(dout, 512))
    try:
        mod.devmem_free(dout); mod.devmem_free(dinj); mod.devmem_free(daddr)
    except Exception:
        pass
    return v

# element [m][r][c] = 64*m + 8*r + c (x1, row-stride 16)
def m88x1(m, t):
    r, lane = t // 4, t % 4
    lo = 64*m + 8*r + 2*lane
    return lo | ((lo + 1) << 16)
# element [m][r][c] = 64*m + 16*r + c (x2/x4, row-stride 32)
def m88xN(m, t):
    r, lane = t // 4, t % 4
    lo = 64*m + 16*r + 2*lane
    return lo | ((lo + 1) << 16)
# MT88.x1: a[(t%4)*2][t/4], a[(t%4)*2+1][t/4]  (row-stride 16)
def mt88x1(m, t):
    lo = 8*((t % 4) * 2) + t // 4
    hi = 8*((t % 4) * 2 + 1) + t // 4
    return lo | (hi << 16)

# --- 1. M88.x1 ------------------------------------------------------------
addr_x1 = lambda b: [b + t*16 for t in range(32)]
v = run_ldsm(addr_x1, 1)
check("M88.x1 row-major fragment", v[0:32], [m88x1(0, t) for t in range(32)])

# --- 2. M88.x2 ------------------------------------------------------------
addr_xN = lambda b: [b + (t//8)*128 + (t%8)*32 for t in range(32)]
v = run_ldsm(addr_xN, 2)
bad = [t for t in range(32) if v[t] != m88xN(0, t) or v[32+t] != m88xN(1, t)]
check("M88.x2 regs = matrices 0/1", "ok" if not bad else bad[:5], "ok")

# --- 3. M88.x4 ------------------------------------------------------------
v = run_ldsm(addr_xN, 4)
bad = [t for t in range(32) for k in range(4) if v[k*32+t] != m88xN(k, t)]
check("M88.x4 regs = matrices 0..3", "ok" if not bad else bad[:5], "ok")

# --- 4. MT88.x1 (transposed) ----------------------------------------------
v = run_ldsm(addr_x1, 1, mode="MT88")
check("MT88.x1 transposed fragment", v[0:32], [mt88x1(0, t) for t in range(32)])

# --- 4b. MT88.x2 / MT88.x4: group->register mapping survives transpose ------
def mt88xN(g, t):                    # a[g][(t%4)*2][t//4] (lo), ...+1 (hi)
    lo = 64*g + 16*((t % 4) * 2) + t // 4
    hi = 64*g + 16*((t % 4) * 2 + 1) + t // 4
    return lo | (hi << 16)
v = run_ldsm(addr_xN, 2, mode="MT88")
bad = [t for t in range(32) for g in range(2) if v[g*32+t] != mt88xN(g, t)]
check("MT88.x2 group g -> reg g", "ok" if not bad else bad[:5], "ok")
v = run_ldsm(addr_xN, 4, mode="MT88")
bad = [t for t in range(32) for g in range(4) if v[g*32+t] != mt88xN(g, t)]
check("MT88.x4 group g -> reg g", "ok" if not bad else bad[:5], "ok")

# --- 5. address model is user-driven: X4 is the base case ------------------
# X1/X2 just take the first N 8-thread groups.  Each group reads the 8×16B
# at its 8 addresses, splits into 32 32-bit words written to lanes 0..31.
# So the SAME matrix can be read with stride-16 (contiguous) or stride-32
# (X4-group-0) addresses, or even a scrambled row order.
def m88_s32(t):                       # stride-32 layout: value = 16r + c
    r, lane = t // 4, t % 4
    lo = 16*r + 2*lane
    return lo | ((lo + 1) << 16)
addr_s32 = lambda b: [b + (t % 8) * 32 for t in range(32)]
v = run_ldsm(addr_s32, 1)
check("M88.x1 stride-32 addrs (X4-group0 layout)", v[0:32],
      [m88_s32(t) for t in range(32)])

# scrambled per-row addresses: lane t%8 supplies row (t*3+1)%8 of a
# stride-16 matrix; fragment row (t//4) reads the row that lane (t//4) named.
def m88_sc(t):
    row = (t // 4 * 3 + 1) % 8
    lo = 8*row + 2*(t % 4)
    return lo | ((lo + 1) << 16)
v = run_ldsm(lambda b: [b + 16*((t * 3 + 1) % 8) for t in range(32)], 1)
check("M88.x1 scrambled row addresses", v[0:32],
      [m88_sc(t) for t in range(32)])

print(f"\n=== LDSM (ldmatrix): {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
