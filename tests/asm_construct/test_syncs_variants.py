"""Real-device semantics for SYNCS modifiers not directly exposed by PTX."""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble, assemble_flat  # noqa: E402
from archutil import adapt_source, is_sm90  # noqa: E402


HEAD = (
    "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
    "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
    "    UMOV UR6, 0x400;[1:7:{}:1:0]\n"
)


def init(n):
    return (
        f"    UMOV UR8, 0x{n:x};[1:7:{{}}:1:0]\n"
        "    UIADD3 UR8, UPT, UPT, -UR8, 0x100000, URZ;[7:7:{1}:5:1]\n"
        "    USHF.L.U32 UR9, UR8, 0xb, URZ;[7:7:{1}:5:1]\n"
        "    USHF.L.U32 UR8, UR8, 0x1, URZ;[7:7:{1}:5:1]\n"
        "    SYNCS.EXCH.64 URZ, [UR6], UR8;[2:1:{1}:5:1]\n"
    )


def run(body, nwords, block=1):
    src = ("#fn k(out<8>) {\n"
           "    #pragma NUM_MBARRIERS(2)\n"
           "    #pragma SHARED(0x4000)\n" + HEAD + body
           + "    EXIT;[7:7:{0,1,2,3,4,5}:5:0]\n}\n")
    mod = CudaModule(assemble(adapt_source(src)))
    out = mod.devmem_alloc(nwords * 8)
    mod.device_write(out, bytes(nwords * 8))
    mod.launch("k", grid=(1,), block=(block,), args=[out], shared_mem=0x4000)
    mod.synchronize()
    return struct.unpack("<" + "Q" * nwords, mod.device_read(out, nwords * 8))


ok = True


def check(name, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {name:<42} {got!r} (exp {want!r})")


try:
    CudaModule(assemble(adapt_source("#fn k() { EXIT;[7:7:{}:5:0] }")))
except RuntimeError:
    print("--- no CUDA device; SYNCS semantic checks SKIPPED ---")
    sys.exit(0)


# OLDSTATE and TMASK share the old high word.  TMASK additionally returns the
# issuing active-lane mask in the low word.  OPTOUT is arrive_drop.
for mods, token_low, backing in [
    (".TMASK", 1, 0x7FFFF000001FFFF8),
    (".TMASK.OPTOUT", 1, 0x7FFFF000001FFFFC),
]:
    body = init(4) + (
        "    MOV32I R2, 2;[7:7:{}:5:1]\n"
        f"    SYNCS.ARRIVE.TRANS64{mods}.ART0 {{R0,R1}}, [RZ+UR6], R2;[2:7:{{2}}:5:1]\n"
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R0,R1};[0:2:{1,2}:1:0]\n"
        "    SYNCS.CCTL.IV [RZ+UR6];[1:7:{2}:5:1]\n"
        "    LDS.64 {R8,R9}, [RZ+UR6];[2:7:{1}:8:1]\n"
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+8], {R8,R9};[0:2:{1,2}:1:0]\n"
    )
    token, word = run(body, 2)
    check(f"{mods} token low = active mask", token & 0xFFFFFFFF, token_low)
    check(f"{mods} token old high word", token >> 32, 0x7FFFE000)
    check(f"{mods} backing state", word, backing)

# A nonzero leader lane proves TMASK is MACTIVE rather than a constant flag.
body = (
    "    UMOV UR8, 0x1ffffc;[1:7:{}:1:0]\n"
    "    UMOV UR9, 0x7ffff000;[1:7:{}:1:0]\n"
    "    SYNCS.EXCH.64 {URZ,URZ}, [UR6], {UR8,UR9};[2:7:{1}:5:1]\n"
    "    S2R R20, SR_TID.X;[5:7:{2}:5:1]\n"
    "    ISETP.EQ.AND P0, PT, R20, 5, PT;[7:7:{5}:13:1]\n"
    "    @P0 MOV32I R2, 1;[7:7:{}:5:1]\n"
    "    @P0 SYNCS.ARRIVE.TRANS64.TMASK.ART0 {R0,R1}, [RZ+UR6], R2;[2:7:{2}:5:1]\n"
    "    @P0 STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R0,R1};[0:2:{1,2}:1:0]\n"
)
check("TMASK with only lane 5 active", run(body, 1, block=32)[0] & 0xFFFFFFFF, 1 << 5)


# The otherwise PTX-unexposed A0T1 form adds exactly one tx credit.
body = init(3) + (
    "    SYNCS.ARRIVE.TRANS64.RED.A0T1 {RZ,RZ}, [RZ+UR6], RZ;[2:7:{2}:5:1]\n"
    "    SYNCS.CCTL.IV [RZ+UR6];[3:7:{2}:5:1]\n"
    "    LDS.64 {R8,R9}, [RZ+UR6];[2:7:{3}:8:1]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R8,R9};[0:2:{1,2}:1:0]\n"
)
check("A0T1 adds one tx credit", run(body, 1), (0x7FFFEBFFFFFFFFFA,))


# LD and LD.WATCH see the live cache state.  WB exposes the same word without
# invalidating it; the following ARRIVE proves that the object remains usable.
body = init(3) + (
    "    MOV32I R2, 64;[7:7:{}:5:1]\n"
    "    SYNCS.ARRIVE.TRANS64.RED.A0TR {RZ,RZ}, [RZ+UR6], R2;[2:7:{2}:5:1]\n"
    "    SYNCS.LD.64 {R8,R9}, [RZ+UR6];[3:7:{2}:5:1]\n"
    "    SYNCS.LD.64.WATCH {R10,R11}, [RZ+UR6];[4:7:{2}:5:1]\n"
    "    SYNCS.CCTL.WB [RZ+UR6];[5:7:{2}:5:1]\n"
    "    LDS.64 {R12,R13}, [RZ+UR6];[2:7:{5}:8:1]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R8,R9};[0:3:{1,3}:1:0]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+8], {R10,R11};[0:4:{1,4}:1:0]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+16], {R12,R13};[0:2:{1,2}:1:0]\n"
    "    SYNCS.ARRIVE.TRANS64.A1T0 {R0,R1}, [RZ+UR6], RZ;[2:7:{2}:5:1]\n"
    "    SYNCS.CCTL.IV [RZ+UR6];[3:7:{2}:5:1]\n"
    "    LDS.64 {R14,R15}, [RZ+UR6];[2:7:{3}:8:1]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+24], {R14,R15};[0:2:{1,2}:1:0]\n"
)
live = 0x7FFFEBFFF81FFFFA
check("LD/WATCH/WB/live-after-WB", run(body, 4),
      (live, live, live, 0x7FFFF3FFF81FFFFA))


# WATCH does not turn later barrier updates into shared-memory write-through.
# Both the watched and unwatched backing retain their pre-init sentinels.
body = (
    "    UMOV UR7, 0x408;[1:7:{}:1:0]\n"
    "    MOV32I R20, 0x11111111;[7:7:{}:5:1]\n"
    "    MOV32I R21, 0x22222222;[7:7:{}:5:1]\n"
    "    STS.64 [RZ+UR6], {R20,R21};[7:7:{}:5:1]\n"
    "    MOV32I R20, 0x33333333;[7:7:{}:5:1]\n"
    "    MOV32I R21, 0x44444444;[7:7:{}:5:1]\n"
    "    STS.64 [RZ+UR7], {R20,R21};[7:7:{}:5:1]\n" + init(3) +
    "    SYNCS.EXCH.64 {URZ,URZ}, [UR7], {UR8,UR9};[2:7:{2}:5:1]\n"
    "    SYNCS.LD.64.WATCH {R10,R11}, [RZ+UR6];[3:7:{2}:5:1]\n"
    "    SYNCS.ARRIVE.TRANS64.RED.A1T0 {RZ,RZ}, [RZ+UR6], RZ;[2:7:{2,3}:5:1]\n"
    "    SYNCS.ARRIVE.TRANS64.RED.A1T0 {RZ,RZ}, [RZ+UR7], RZ;[4:7:{2}:5:1]\n"
    "    LDS.64 {R12,R13}, [RZ+UR6];[2:7:{2,4}:8:1]\n"
    "    LDS.64 {R14,R15}, [RZ+UR7];[3:7:{2,4}:8:1]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R12,R13};[0:2:{1,2}:1:0]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+8], {R14,R15};[0:3:{1,3}:1:0]\n"
)
check("WATCH is not shared write-through", run(body, 2),
      (0x2222222211111111, 0x4444444433333333))


# Uniform shared atomics: EXCH returns old, CAS returns old and conditionally
# installs new, LD returns current.  CAS source pairs must be adjacent.
body = (
    "    MOV32I R20, 0;[7:7:{}:5:1]\n"
    "    MOV32I R21, 0;[7:7:{}:5:1]\n"
    "    STS.64 [RZ+UR6], {R20,R21};[7:7:{}:5:1]\n"
    "    UMOV UR8, 0x11111111;[1:7:{}:1:0]\n"
    "    UMOV UR9, 0x22222222;[1:7:{}:1:0]\n"
    "    SYNCS.EXCH.64 {UR12,UR13}, [UR6], {UR8,UR9};[2:7:{}:5:1]\n"
    "    UMOV UR10, 0x33333333;[1:7:{}:1:0]\n"
    "    UMOV UR11, 0x44444444;[1:7:{}:1:0]\n"
    "    SYNCS.CAS.64 {UR14,UR15}, [UR6], {UR8,UR9}, {UR10,UR11};[2:7:{2}:5:1]\n"
    "    SYNCS.LD.64 {UR16,UR17}, [UR6];[3:7:{2}:5:1]\n"
    "    MOV R8, UR12;[4:7:{2}:5:1]  MOV R9, UR13;[4:7:{2}:5:1]\n"
    "    MOV R10, UR14;[4:7:{2}:5:1] MOV R11, UR15;[4:7:{2}:5:1]\n"
    "    MOV R12, UR16;[4:7:{3}:5:1] MOV R13, UR17;[4:7:{3}:5:1]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R8,R9};[0:4:{1,4}:1:0]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+8], {R10,R11};[0:4:{1,4}:1:0]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+16], {R12,R13};[0:4:{1,4}:1:0]\n"
)
check("uniform EXCH/CAS/LD", run(body, 3),
      (0, 0x2222222211111111, 0x4444444433333333))


# TCNT is a disassembly alias of ARRIVE.RED.A0TR, not another encoding.
tcnt = assemble_flat("SYNCS.TCNT.TRANS64.RED [RZ+UR6], R2;[7:7:{}:5:1]")
a0tr = assemble_flat("SYNCS.ARRIVE.TRANS64.RED.A0TR {RZ,RZ}, [RZ+UR6], R2;[7:7:{}:5:1]")
check("TCNT alias equals RED.A0TR", tcnt, a0tr)


# Address-less cache control covers every resident entry.
body = init(3) + (
    "    UMOV UR7, 0x408;[1:7:{}:1:0]\n"
    "    UMOV UR8, 0x1ffffc;[1:7:{}:1:0]\n"
    "    UMOV UR9, 0x7ffff000;[1:7:{}:1:0]\n"
    "    SYNCS.EXCH.64 {URZ,URZ}, [UR7], {UR8,UR9};[2:7:{1}:5:1]\n"
    "    SYNCS.CCTL.WBALL;[3:7:{2}:5:1]\n"
    "    LDS.64 {R8,R9}, [RZ+UR6];[2:7:{3}:8:1]\n"
    "    LDS.64 {R10,R11}, [RZ+UR7];[2:7:{3}:8:1]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R8,R9};[0:2:{1,2}:1:0]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+8], {R10,R11};[0:2:{1,2}:1:0]\n"
)
check("WBALL writes all resident entries", run(body, 2),
      (0x7FFFE800001FFFFA, 0x7FFFF000001FFFFC))


# IVALL likewise exposes every resident entry.  Cache reuse after IVALL is not
# probed: PTX declares an invalidated mbarrier object unusable until re-init.
body = init(3) + (
    "    UMOV UR7, 0x408;[1:7:{}:1:0]\n"
    "    UMOV UR8, 0x1ffffc;[1:7:{}:1:0]\n"
    "    UMOV UR9, 0x7ffff000;[1:7:{}:1:0]\n"
    "    SYNCS.EXCH.64 {URZ,URZ}, [UR7], {UR8,UR9};[2:7:{1}:5:1]\n"
    "    SYNCS.CCTL.IVALL;[3:7:{2}:5:1]\n"
    "    LDS.64 {R8,R9}, [RZ+UR6];[2:7:{3}:8:1]\n"
    "    LDS.64 {R10,R11}, [RZ+UR7];[2:7:{3}:8:1]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R8,R9};[0:2:{1,2}:1:0]\n"
    "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+8], {R10,R11};[0:2:{1,2}:1:0]\n"
)
check("IVALL writes all resident entries", run(body, 2),
      (0x7FFFE800001FFFFA, 0x7FFFF000001FFFFC))


if not is_sm90():
    # FLUSH was added in sm_100.  Seed backing with a sentinel before init:
    # FLUSH leaves it untouched, proving this is not WBALL under another name.
    body = (
        "    MOV32I R20, 0x89abcdef;[7:7:{}:5:1]\n"
        "    MOV32I R21, 0x01234567;[7:7:{}:5:1]\n"
        "    STS.64 [RZ+UR6], {R20,R21};[7:7:{}:5:1]\n" + init(3)
        + "    SYNCS.FLUSH;[3:7:{2}:5:1]\n"
          "    LDS.64 {R8,R9}, [RZ+UR6];[2:7:{3}:8:1]\n"
          "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R8,R9};[0:2:{1,2}:1:0]\n"
          "    SYNCS.ARRIVE.TRANS64.A1T0 {R0,R1}, [RZ+UR6], RZ;[2:7:{2}:5:1]\n"
          "    SYNCS.CCTL.IV [RZ+UR6];[3:7:{2}:5:1]\n"
          "    LDS.64 {R10,R11}, [RZ+UR6];[2:7:{3}:8:1]\n"
          "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+8], {R10,R11};[0:2:{1,2}:1:0]\n"
    )
    check("FLUSH is not mbar cache writeback", run(body, 2),
          (0x0123456789ABCDEF, 0x7FFFF000001FFFFA))

print(f"\n=== SYNCS variants: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
