import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# UBLKRED — non-tensor cp.reduce.async.bulk (uniform datapath reduction).
#
# S2G (shared -> global, bulk_group completion): each destination element is
# reduced inline with the corresponding source element:
#     dst[i] = dst[i] <redOp> src[i]
# with UTMACMDFLUSH (commit_group) + DEPBAR.LE (wait_group.read) completion,
# exactly like UBLKCP.G.S.  URc is the copy SIZE in 16-byte units (URc=1 ->
# 16 bytes = 4 U32 elements), matching ptxas's USHF/UPRMT size transform.
#
# Verified on sm_120 (RTX 5090, CUDA 13.0 / driver 580.65) for all 8 U32
# redOps (ADD/MIN/MAX/INC/DEC/AND/OR/XOR).  INC/DEC follow the classic
# atomic semantics with the SOURCE element as the cap:
#     INC: dst = (dst < src) ? dst + 1 : 0
#     DEC: dst = (dst == 0 || dst > src) ? src : dst - 1
# (both return a result in [0..src] as the PTX spec states).
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<48} {got} (exp {want})")

try:
    _ = CudaModule(assemble("#fn k() { EXIT;[7:7:{}:5:0] }"))
    HAVE_GPU = True
except RuntimeError:
    HAVE_GPU = False
    print("--- no CUDA device; GPU semantic checks SKIPPED ---")

# --- offline: encodings ----------------------------------------------------
REDOP = {"ADD": 0, "MIN": 1, "MAX": 2, "INC": 3, "DEC": 4,
         "AND": 5, "OR": 6, "XOR": 7}
lo, hi = assemble_flat("UBLKRED.G.S.ADD.U32 [UR8], [UR10], UR11;[7:0:{1}:5:1]")[0]
assert lo & 0xFFF == 0x3bb and (hi >> 27) & 1 == 1, hex(lo)
for op, want in REDOP.items():
    lo, hi = assemble_flat(f"UBLKRED.G.S.{op}.U32 [UR8], [UR10], UR11;[7:0:{{1}}:5:1]")[0]
    got = (hi >> 23) & 7                      # Pnz [89:87] (hi bits 25:23)
    good = got == want
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} encode UBLKRED.G.S.{op:<3} Pnz={got} (exp {want})")
lo, hi = assemble_flat("UBLKRED.G.S.ADD.U64 [UR8], [UR10], UR11;[7:0:{1}:5:1]")[0]
got_sz = (hi >> 17) & 0xf                    # sz [84:81] (hi bits 20:17)
print(f"{'ok ' if got_sz == 2 else 'FAIL'} encode UBLKRED sz=U64 (field=2)")
ok &= got_sz == 2

if not HAVE_GPU:
    sys.exit(0)

# --- S2G reducer kernel -----------------------------------------------------
# body fills shared[0x800..) with src words, runs one UBLKRED.G.S op over
# 16 bytes (4 U32 elements) into the pre-initialized global dst, then
# commits + waits the bulk group.
def red_kernel(op, src_vals, dst_init):
    sts = "".join(
        f"    MOV32I R{8 + i}, 0x{v:08X};[7:7:{{}}:5:1]\n"
        f"    STS [RZ+0x{0x800 + 4 * i:X}], R{8 + i};[7:7:{{3}}:5:1]\n"
        for i, v in enumerate(src_vals))
    body = (
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]\n"
        "    R2UR UR8, R2;[1:7:{1}:5:1]\n"
        "    R2UR UR9, R3;[1:7:{1}:5:1]\n"
        "    UMOV UR10, 0x800;[1:7:{}:1:0]\n"
        "    UMOV UR11, 0x1;[1:7:{}:1:0]\n"
        + sts +
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        f"    UBLKRED.G.S.{op}.U32 [UR8], [UR10], UR11;[7:0:{{1}}:5:1]\n"
        "    UTMACMDFLUSH;[7:0:{1}:5:1]\n"
        "    DEPBAR.LE SB0, 0x0;[7:7:{1}:5:1]\n"
        "    EXIT;[7:7:{}:5:0]\n")
    return "#fn k(out<8>) {\n    #pragma SHARED(0x4000)\n" + body + "}\n"


def run_red(op, src_vals, dst_init):
    mod = CudaModule(assemble(red_kernel(op, src_vals, dst_init)))
    d = mod.devmem_alloc(64)
    mod.device_write(d, struct.pack("<4I", *dst_init))
    mod.launch("k", grid=(1,), block=(1,), args=[d], shared_mem=0x4000)
    mod.synchronize()
    return list(struct.unpack("<4I", mod.device_read(d, 16)))

# --- element-wise matrix: dst[i] redOp src[i] ------------------------------
SRC = [0x10, 0x30, 0x50, 0x70]
DST = [0x20, 0x20, 0x20, 0x20]

check("ADD  dst+src", run_red("ADD", SRC, DST),
      [0x30, 0x50, 0x70, 0x90])
check("MIN  min(dst,src)", run_red("MIN", SRC, DST),
      [0x10, 0x20, 0x20, 0x20])
check("MAX  max(dst,src)", run_red("MAX", SRC, DST),
      [0x20, 0x30, 0x50, 0x70])
check("AND  dst&src", run_red("AND", SRC, DST),
      [0x00, 0x20, 0x00, 0x20])
check("OR   dst|src", run_red("OR", SRC, DST),
      [0x30, 0x30, 0x70, 0x70])
check("XOR  dst^src", run_red("XOR", SRC, DST),
      [0x30, 0x10, 0x70, 0x50])

# --- INC / DEC: source element is the cap (classic atomic semantics) -------
# dst < src  -> dst+1 ; dst >= src -> 0            (result in [0..src])
check("INC  dst<src -> dst+1", run_red("INC", [0x40]*4, [0x10]*4),
      [0x11, 0x11, 0x11, 0x11])
check("INC  dst==src -> 0", run_red("INC", [0x40]*4, [0x40]*4),
      [0x00, 0x00, 0x00, 0x00])
check("INC  dst>src -> 0", run_red("INC", [0x40]*4, [0x50]*4),
      [0x00, 0x00, 0x00, 0x00])
# DEC: dst==0 -> src ; dst>src -> src ; else dst-1
check("DEC  dst=0 -> src", run_red("DEC", [0x40]*4, [0x00]*4),
      [0x40, 0x40, 0x40, 0x40])
check("DEC  dst>src -> src", run_red("DEC", [0x40]*4, [0x50]*4),
      [0x40, 0x40, 0x40, 0x40])
check("DEC  0<dst<=src -> dst-1", run_red("DEC", [0x40]*4, [0x20]*4),
      [0x1f, 0x1f, 0x1f, 0x1f])

# --- size in 16-byte units: URc=2 -> 32 bytes (8 elements) -----------------
src8 = [1, 2, 3, 4, 5, 6, 7, 8]
body8 = (
    "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
    "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
    "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]\n"
    "    R2UR UR8, R2;[1:7:{1}:5:1]\n"
    "    R2UR UR9, R3;[1:7:{1}:5:1]\n"
    "    UMOV UR10, 0x800;[1:7:{}:1:0]\n"
    "    UMOV UR11, 0x2;[1:7:{}:1:0]\n"
    + "".join(f"    MOV32I R{16 + i}, 0x{v:08X};[7:7:{{}}:5:1]\n"
              f"    STS [RZ+0x{0x800 + 4 * i:X}], R{16 + i};[7:7:{{3}}:5:1]\n"
              for i, v in enumerate(src8)) +
    "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
    "    UBLKRED.G.S.ADD.U32 [UR8], [UR10], UR11;[7:0:{1}:5:1]\n"
    "    UTMACMDFLUSH;[7:0:{1}:5:1]\n"
    "    DEPBAR.LE SB0, 0x0;[7:7:{1}:5:1]\n"
    "    EXIT;[7:7:{}:5:0]\n")
mod = CudaModule(assemble("#fn k(out<8>) {\n    #pragma SHARED(0x4000)\n" + body8 + "}\n"))
d = mod.devmem_alloc(64)
mod.device_write(d, bytes(64))
mod.launch("k", grid=(1,), block=(1,), args=[d], shared_mem=0x4000)
mod.synchronize()
v = struct.unpack("<8I", mod.device_read(d, 32))
check("ADD 32B (URc=2) 8 elements", list(v), src8)

print(f"\n=== UBLKRED S2G: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
