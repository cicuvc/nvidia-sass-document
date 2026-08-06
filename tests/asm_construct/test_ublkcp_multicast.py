import ctypes, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# UBLKCP multicast on sm_120 — does the SASS UBLKCP.S.G.MULTICAST work on
# Blackwell, even though ptxas downgrades `cp.async.bulk...multicast::cluster`
# to LDG + dshmem on sm_120 (no PTX target note for sm_120)?
#
# Mirrors the sm_90a ptxas lowering of the canonical multicast kernel
# (multicast.cu, __cluster_dims__(2,1,1)):
#   - per-CTA mbarrier at cga*0x800 + 0x600, tile dest at cga*0x800 + 0x400
#   - UCGABAR_ARV/WAIT cluster barrier before the copy
#   - ccta0: UBLKCP.S.G.MULTICAST {dest}, {gsrc}, URsize with
#     URsize = (ctaMask << 16) | (bytes / 16)   (0x30020 for mask 0x3, 512 B)
#   - SYNCS.ARRIVE.TRANS64.RED (expect_tx) on the issuing CTA's mbar,
#     then SYNCS.PHASECHK wait on each CTA's own mbar
#   - ccta1 copies its shared tile to gmem_out for host verification
#
# Cluster launch needs the cluster EIATTRs (#pragma CLUSTER(2,1,1) ->
# EIATTR_CTA_PER_CLUSTER 0x3d + EIATTR_EXPLICIT_CLUSTER 0x3e) and a
# cuLaunchKernelEx launch with CU_LAUNCH_ATTRIBUTE_CLUSTER_DIMENSION
# (CudaModule.launch_ex(..., cluster_dims=(2,1,1))).
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {name:<50} {got} (exp {want})")

try:
    _ = CudaModule(assemble("#fn k() { EXIT;[7:7:{}:5:0] }"))
    HAVE_GPU = True
except RuntimeError:
    HAVE_GPU = False
    print("--- no CUDA device; GPU checks SKIPPED ---")

KERNEL = """#fn k(gmem<8>, gmem_out<8>) {
    #pragma CLUSTER(2,1,1)
    #pragma NUM_MBARRIERS(2)
    #pragma SHARED(0x800)
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]
    LDC.64 {R6,R7}, #param(gmem_out);[1:7:{}:1:0]
    S2UR UR7, SR_CgaCtaId;[1:7:{}:1:0]
    ELECT P1, URZ, PT;[1:7:{}:1:0]
    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]
    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]
    @!P1 BRA #label(consumer1);[7:7:{}:5:1]
    # --- elected thread: init own mbar at cga*0x800 + 0x600 ---
    UMOV UR6, 0x600;[1:7:{}:1:0]
    ULEA UR11, UR7, UR6, 0x18;[1:7:{1}:1:0]
    UMOV UR12, 0x1;[1:7:{}:1:0]
    UIADD3 UR12, UPT, UPT, -UR12, 0x100000, URZ;[7:7:{1}:5:1]
    USHF.L.U32 UR13, UR12, 0xb, URZ;[7:7:{1}:5:1]
    USHF.L.U32 UR12, UR12, 0x1, URZ;[7:7:{1}:5:1]
    FENCE.VIEW.ASYNC.S;[1:7:{}:5:1]
    SYNCS.EXCH.64 {URZ,URZ}, [UR11], UR12;[3:1:{1}:5:1]
    MEMBAR.ALL.CTA;[7:7:{3}:5:1]
    MEMBAR.ALL.GPU;[7:7:{3}:5:1]
    FENCE.VIEW.ASYNC.S;[2:7:{}:5:1]
    #def_label(consumer1)
    # --- cluster barrier: all threads of both CTAs ---
    UCGABAR_ARV;[7:7:{}:5:1]
    UCGABAR_WAIT;[7:7:{}:5:1]
    # --- ccta0 only: multicast UBLKCP ---
    LDCU.64 {UR8,UR9}, #param(gmem);[1:7:{}:1:0]
    UISETP.NE.AND UP0, UPT, UR7, 0x0, UPT;[1:7:{1}:1:0]
    PLOP3.LUT P0, PT, PT, PT, UP0, 0x80, 0x0;[7:7:{1}:5:1]
    @P0 BRA #label(skip_issue);[7:7:{}:5:1]
    UMOV UR6, 0x400;[1:7:{}:1:0]
    ULEA UR14, UR7, UR6, 0x18;[7:7:{1}:5:1]
    UMOV UR10, 0x30020;[1:7:{}:1:0]
    UBLKCP.S.G.MULTICAST {UR14,UR15}, {UR8,UR9}, UR10;[7:3:{1}:12:1]
    MOV32I R0, 0x200;[7:7:{}:5:1]
    SYNCS.ARRIVE.TRANS64.RED {RZ,RZ}, [RZ+UR11], R0;[7:1:{}:1:0]
    #def_label(skip_issue)
    # --- all threads: wait own mbar ---
    #def_label(poll)
    SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR11], RZ;[1:7:{}:2:0]
    @!P0 BRA #label(poll);[7:7:{1}:5:0]
    # --- ccta1: copy its smem to gmem_out ---
    UISETP.NE.AND UP0, UPT, UR7, 0x1, UPT;[1:7:{1}:1:0]
    PLOP3.LUT P0, PT, PT, PT, UP0, 0x80, 0x0;[7:7:{1}:5:1]
    @!P0 EXIT;[7:7:{}:5:0]
    S2R R2, SR_TID.X;[1:7:{}:1:0]
    IMAD.WIDE.U32 {R4,R5}, R2, 0x10, {R6,R7};[1:7:{1}:8:1]
    IMAD R2, R2, 0x10, RZ;[1:7:{1}:8:1]
    IADD3 R2, R2, 0x400, RZ;[1:7:{1}:8:1]
    LDS.128 {R8,R9,R10,R11}, [R2];[1:7:{2}:8:1]
    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R4,R5}+0x0], R8;[0:1:{1}:1:0]
    STG.E desc[{UR4,UR5}][{R4,R5}+0x4], R9;[0:1:{1}:1:0]
    STG.E desc[{UR4,UR5}][{R4,R5}+0x8], R10;[0:1:{1}:1:0]
    STG.E desc[{UR4,UR5}][{R4,R5}+0xc], R11;[0:1:{1}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""

# offline: the kernel must contain exactly one UBLKCP.S.G.MULTICAST with the
# multicast bit [75] set, and the cubin must carry the cluster EIATTRs.
from assembler import assemble_kernel
enc = assemble_kernel(KERNEL).encoded
mc = [e for e in enc
      if (e[0] & 0xFFF) == 0x3ba and ((e[1] >> 11) & 1) == 1]
check("offline: UBLKCP.S.G.MULTICAST present (bit 75)", len(mc), 1)

import re
import struct
import subprocess
cubin = assemble(KERNEL)
open("/tmp/ublkcp_mc_test.cubin", "wb").write(cubin)
out = subprocess.run(["readelf", "-x", ".nv.info._Z1k", "/tmp/ublkcp_mc_test.cubin"],
                     capture_output=True, text=True).stdout
data = bytearray()
for line in out.splitlines():
    m = re.match(r'\s*0x[0-9a-f]+ ([0-9a-f]{8}(?: [0-9a-f]{8})*)', line)
    if m:
        for g in m.group(1).split():
            data += bytes.fromhex(g)
blob = b""
i = 0
while i + 4 <= len(data):
    fmt, etype, size = data[i], data[i+1], struct.unpack_from("<H", data, i+2)[0]
    if etype == 0x1b:          # MAXREG blob — nested records
        blob = bytes(data[i+4:i+4+size])
    i += 4 + size
check("offline: EIATTR_CTA_PER_CLUSTER (0x3d) = (2,1,1)",
      b"\x04\x3d\x0c\x00\x02\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00"
      in blob, True)
check("offline: EIATTR_EXPLICIT_CLUSTER (0x3e) present",
      b"\x01\x3e\x00\x00" in blob, True)

if not HAVE_GPU:
    sys.exit(0 if ok else 1)

# --- host setup --------------------------------------------------------------
mod0 = CudaModule(assemble("#fn k() { EXIT;[7:7:{}:5:0] }"))
d_in = mod0.devmem_alloc(512)
data = struct.pack("<128I", *range(0x1000, 0x1000 + 128))
mod0.device_write(d_in, data)
d_out = mod0.devmem_alloc(512)
mod0.device_write(d_out, bytes(512))

m = CudaModule(cubin)
m.launch_ex("k", grid=(2, 1, 1), block=(32, 1, 1),
            args=[d_in, d_out], shared_mem=0x800, cluster_dims=(2, 1, 1))
m.synchronize()
got = struct.unpack("<128I", m.device_read(d_out, 512))
exp = list(range(0x1000, 0x1000 + 128))
bad = [i for i in range(128) if got[i] != exp[i]]
check("cluster launch: ccta1 smem == gmem source", len(bad), 0)
if bad:
    print("      first mismatches:", bad[:5], [hex(got[i]) for i in bad[:3]])

print(f"\n=== UBLKCP multicast: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
