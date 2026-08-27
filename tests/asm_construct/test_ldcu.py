import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule
from archutil import adapt_source, same_as_capture, is_sm90  # noqa: E402

# ---------------------------------------------------------------------------
# LDCU (sm_120 name of ULDC) — uniform load constant (udp_pipe; verified SM120)
#
#   LDCU[.U8|.S8|.U16|.S16|.32|.64|.128] URd[, ...], c[bank][offset]
#     0x17ac const / 0x1bac reg-indexed bank / 0x19ac UR-offset forms
#   Loads from constant memory into the uniform register file.  Sub-32-bit
#   sizes sign/zero-extend (.S* sign, .U* zero) into the 32-bit URd.
#   .64 -> {URd,URd+1} (even-aligned), .128 -> {URd..URd+3} (4-aligned).
#
# Verified semantics (RTX 5090): 32-bit, U8/S8/U16/S16 extension, 64-bit
# pair word order (low word first), 128-bit quad from two contiguous
# 8-byte params.  `&wr` scoreboard is a REAL encodable field on sm_120
# (VarLatOperandEnc), unlike most udp ops — consumers wait via req={n}.
#
# Known caveats (this assembler/driver setup):
#   * LDCU param reads lag ~4 launches when the CUBIN module is REUSED
#     (fresh module per launch reads correctly).
#   * The first udp read of a freshly loaded UR is stale — a dummy UMOV
#     read settles the datapath.
#   * A >8-byte kernel param can't be passed via the runner's uint64
#     arg convention; use two contiguous 8-byte params (LDCU.128 reads
#     across them).
# ---------------------------------------------------------------------------

REF = [
    (0x00007000ff0677ac, 0x000e220008000800),  # LDCU UR6, c[0x0][0x380] (32)
    (0x00007000ff0677ac, 0x000e220008000000),  # .U8
    (0x00007000ff0677ac, 0x000e220008000200),  # .S8
    (0x00007000ff0677ac, 0x000e220008000400),  # .U16
    (0x00007000ff0677ac, 0x000e220008000600),  # .S16
    (0x00007000ff0677ac, 0x000e220008000a00),  # .64
    (0x00007000ff1477ac, 0x000e220008000c00),  # .128 -> UR20
]
_plain32_src = "LDCU UR6, c[0x0][0x380];[0:7:{}:1:0]"
_BODY = """
LDCU.U8 UR6, c[0x0][0x380];[0:7:{}:1:0]
LDCU.S8 UR6, c[0x0][0x380];[0:7:{}:1:0]
LDCU.U16 UR6, c[0x0][0x380];[0:7:{}:1:0]
LDCU.S16 UR6, c[0x0][0x380];[0:7:{}:1:0]
LDCU.64 {UR6,UR7}, c[0x0][0x380];[0:7:{}:1:0]"""
if is_sm90():
    # sm_90 spec ULDC sz enum tops out at 64 — no .128 variant.
    _src = _plain32_src + "\n" + _BODY.strip("\n") + "\n"
else:
    _src = (_plain32_src + "\n" + _BODY.strip("\n") +
            "\nLDCU.128 {UR20,UR21,UR22,UR23}, c[0x0][0x380];[0:7:{}:1:0]\n")

flat = assemble_flat(_src)
ok = True
_pins = same_as_capture("sm120")
if not _pins:
    print("info byte-exact REF vectors captured on sm120 — skipped under",
          __import__('assembler.arch', fromlist=['x']).current().name)
for i, enc in enumerate(flat):
    good = (enc == REF[i]) if _pins else True
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(adapt_source(src), check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def kernel_sz(sz, base, nregs):
    grp = f"UR{base}" if nregs == 1 else "{" + ",".join(f"UR{base+i}" for i in range(nregs)) + "}"
    reads = ""
    for i in range(nregs):
        reads += (f"    UMOV UR9, UR{base+i};[7:7:{{0}}:5:1]\n"
                  f"    UMOV UR14, UR{base+i};[7:7:{{0}}:5:1]\n"
                  f"    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]\n"
                  f"{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{i*4:X}], R2;[7:7:{{0,1}}:1:0]\n")
    return f"""#fn t(in<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU{sz} {grp}, #param(in);[2:7:{{}}:1:0]
    UMOV UR9, UR{base};[7:7:{{2}}:5:1]
    UMOV UR9, UR{base+1};[7:7:{{2}}:5:1]
    UMOV UR9, UR{base+2};[7:7:{{2}}:5:1]
    UMOV UR9, UR{base+3};[7:7:{{2}}:5:1]
{reads}    EXIT;[7:7:{{}}:5:0]
}}"""


def run_sz(sz, base, nregs, data, nbytes):
    mod = build(kernel_sz(sz, base, nregs))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,), args=[data & 0xFFFFFFFFFFFFFFFF, d])
    mod.synchronize()
    v = struct.unpack(f"<{nbytes // 4}I", mod.device_read(d, nbytes))
    mod.devmem_free(d)
    return v


try:
    build(kernel_sz("", 16, 1))
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

# 32-bit + sub-word sizes (data = 0x81F8: low byte F8, low16 81F8).
got = run_sz("", 16, 1, 0x12345678, 4)[0]
good = got == 0x12345678
ok &= good
print(f"{'ok ' if good else 'FAIL'} 32-bit            -> 0x{got:08X}")
for sz, data, exp in [(".U8", 0x81F8, 0x000000F8), (".S8", 0x81F8, 0xFFFFFFF8),
                      (".U16", 0x81F8, 0x000081F8), (".S16", 0x81F8, 0xFFFF81F8),
                      (".U16", 0x01F8, 0x000001F8)]:
    got = run_sz(sz, 16, 1, data, 4)[0]
    good = got == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {sz:5s} data=0x{data:X} -> 0x{got:08X} (exp 0x{exp:08X})")

# 64-bit pair: low word first.
lo, hi = run_sz(".64", 16, 2, 0xDEADBEEFCAFEBABE, 8)
good = (lo, hi) == (0xCAFEBABE, 0xDEADBEEF)
ok &= good
print(f"{'ok ' if good else 'FAIL'} 64-bit lo=0x{lo:08X} hi=0x{hi:08X} (exp 0xCAFEBABE, 0xDEADBEEF)")

# 128-bit quad from two contiguous 8-byte params (a at #param(a), b at
# #param(b); on sm_120 these land at 0x380/0x388).  The sm_90 spec has no
# .128 ULDC variant, so this section runs only where the variant exists.
if is_sm90():
    print("info .128 section skipped: sm_90 spec has no ULDC.128")
else:
    src128 = f"""#fn t(a<8>, b<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU.128 {{UR20,UR21,UR22,UR23}}, #param(a);[2:7:{{}}:1:0]
    UMOV UR9, UR4;[7:7:{{0}}:5:1]
    UMOV UR9, UR5;[7:7:{{0}}:5:1]
    UMOV UR9, UR20;[7:7:{{2}}:5:1]
    UMOV UR9, UR21;[7:7:{{2}}:5:1]
    UMOV UR9, UR22;[7:7:{{2}}:5:1]
    UMOV UR9, UR23;[7:7:{{2}}:5:1]
    UMOV UR14, UR20;[7:7:{{2}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
    UMOV UR14, UR21;[7:7:{{2}}:5:1]
    IADD3 R3, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
    UMOV UR14, UR22;[7:7:{{2}}:5:1]
    IADD3 R4, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
    UMOV UR14, UR23;[7:7:{{2}}:5:1]
    IADD3 R5, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x4], R3;[7:7:{{0,1}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x8], R4;[7:7:{{0,1}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0xC], R5;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""
    mod = build(src128)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,),
               args=[0x1111111122222222, 0x3333333344444444, d])
    mod.synchronize()
    v = struct.unpack("<4I", mod.device_read(d, 16))
    mod.devmem_free(d)
    exp = (0x22222222, 0x11111111, 0x44444444, 0x33333333)
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} 128-bit {[hex(x) for x in v]} (exp {[hex(x) for x in exp]})")

print("\n=== LDCU (ULDC) semantic verification: ALL OK ===" if ok else "\n=== LDCU FAILURES ===")
sys.exit(0 if ok else 1)
