"""UBULKCP minimal probe for live debugging on the H20 — DIAGNOSTIC build.

Everything runs in ONE process by default (see sticky-context caveat in
assembler_sm90_port.md §5) — each *variant* is meant to be launched with its
own interpreter:

    ASSEMBLER_ARCH=sm90 ~/miniconda3/bin/python3 probe_ublkcp_min.py s2g
    ASSEMBLER_ARCH=sm90 ~/miniconda3/bin/python3 probe_ublkcp_min.py g2s_bounded
    ... variants below

Variants
--------
s2g          shared -> global UBLKCP.G.S (historically green on both gens);
             baseline sanity that the async engine + desc[] wiring work.
g2s_bounded  global -> shared with mbarrier completion, BUT the waiter is a
             BOUNDED spin (N iterations then bail) and every stage of the
             choreography leaves a heartbeat word in `out[]`:
                 out[0]=1 issued arrive.expect_tx
                 out[1]=1 cp.async.bulk issued
                 out[2]=spin iterations used (0x7FFFFFFF == gave up)
                 out[3]=phase value read back on bail
             So a hang becomes readable data instead of a stuck GPU.
g2s_noexpect same minus expect_tx folding (does count get consumed anyway?)
g2s_sm90cnt  count encoded via the USHF-smear form used in test_ublkcp vs
             plain UMOV imm — isolates encoding from semantics.

Run these one-per-process; DO NOT chain them.
"""

import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("ASSEMBLER_ARCH", "sm90")

from archutil import adapt_source  # noqa: E402
from assembler import assemble  # noqa: E402
from assembler.runner import reset_context, CudaModule  # noqa: E402


# ---------------------------------------------------------------------------
def build_s2g():
    """Shared(0x800..0x820) filled with 8 words -> UBLKCP.G.S 32 bytes."""
    body = (
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:2:0]\n"
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
        "    MOV32I R0, 0x11111111;[7:7:{}:5:1]\n"
        "    MOV32I R1, 0x22222222;[7:7:{}:5:1]\n"
        "    STS.64 [RZ+0x800], {R0,R1};[7:7:{}:5:1]\n"
        "    MOV32I R0, 0x33333333;[7:7:{}:5:1]\n"
        "    MOV32I R1, 0x44444444;[7:7:{}:5:1]\n"
        "    STS.64 [RZ+0x808], {R0,R1};[7:7:{}:5:1]\n"
        "    MOV32I R0, 0x55555555;[7:7:{}:5:1]\n"
        "    MOV32I R1, 0x66666666;[7:7:{}:5:1]\n"
        "    STS.64 [RZ+0x810], {R0,R1};[7:7:{}:5:1]\n"
        "    MOV32I R0, 0x77777777;[7:7:{}:5:1]\n"
        "    MOV32I R1, 0x88888888;[7:7:{}:5:1]\n"
        "    STS.64 [RZ+0x818], {R0,R1};[7:7:{}:5:1]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]\n"
        "    R2UR UR8, R2;[1:7:{1}:5:1]\n"
        "    R2UR UR9, R3;[1:7:{1}:5:1]\n"
        "    UMOV UR10, 0x800;[1:7:{}:1:0]\n"
        "    UMOV UR11, 0x2;[1:7:{}:1:0]           // 2 x 16-byte units\n"
        "    ELECT P1, URZ, PT;[1:7:{}:5:1]\n"
        "    UBLKCP.G.S [UR8], [UR10], UR11;[7:0:{1}:5:1]\n"
        "    UTMACMDFLUSH;[7:0:{1}:5:1]\n"
        "    DEPBAR.LE SB0, 0x0;[7:7:{1}:5:1]\n"
        "    EXIT;[7:7:{}:5:0]\n")
    return "#fn k(out<8>) {\n    #pragma SHARED(0x4000)\n" + body + "}\n"


# ---------------------------------------------------------------------------
# Shared-memory layout for the g2s family:
#   0x400 .. 0x420 : destination buffer (32 bytes)
#   0x800          : mbarrier (8-byte aligned)
#   Flags go to GLOBAL out[] so we can inspect them even after bail-out.
_G2S_COMMON = {
    "EXP": "",      # place-holder replaced per-variant
}


def build_g2s_source(*, use_expect=True, phase_poll=False,
                     fence_chain=False, units=1):
    """G2S with observable choreography. All addresses staged on uniforms
    exactly like the repo's green-on-sm120 skeleton:

        UBLKCP.S.G [UR10], [UR8], URc      (dst-smem, src-global, units)

    Heartbeats land in global out[] so a hang is always diagnosable:
        out[0]=init+expect issued   out[1]=bulk issued   out[2]=post
        out[4]=PHASECHK parity snapshot (no spin!) if phase_poll
    """
    assert not use_expect or units >= 1
    lines = [
        "    ULDC.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[7:7:{}:2:0]",
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]",
        "    LDC.64 {R2,R3}, #param(gsrc);[2:7:{}:1:0]",
        "    R2UR UR8, R2;[1:7:{1}:5:1]",       # global src -> UR8:UR9
        "    R2UR UR9, R3;[1:7:{1}:5:1]",
        "    UMOV UR10, 0x400;[7:7:{}:1:0]",    # smem dst
        "    UMOV UR6, 0x800;[7:7:{}:1:0]",     # mbarrier smem addr
        # heartbeat 0
        "    MOV32I R11, 1;[7:7:{}:1:0]",
        "    STG.E desc[{UR4,UR5}][{R6,R7}], R11;[0:1:{1}:1:0]",
        # mbarrier init: EXCH.64 URZ,[mb],count(smear(1))
        "    MOV32I R12, 0x1;[7:7:{}:1:0]",
        "    UIADD3 UR12, UPT, UPT, -UR12, 0x100000, UR13;[7:7:{2}:5:1]",
        "    USHF.L.U32 UR13, UR12, 0xb, UR13;[7:7:{2}:5:1]",
        "    USHF.L.U32 UR12, UR12, 0x1, UR12;[7:7:{2}:5:1]",
        "    SYNCS.EXCH.64 URZ, [UR6], UR12;[2:1:{2}:5:1]\n"
        "        // H20 rule (user finding): consumer blocks must not observe the\n"
        "        // barrier before initialization; nvcc emits BAR.SYNC right after\n"
        "        // the init to order every lane's subsequent ARRIVE/WAIT behind it.\n"
        "    BAR.SYNC.DEFER_BLOCKING 0x0;[7:7:{2}:13:1]",
        "    MOV32I R0, %d;[7:7:{}:1:0]" % (units * 16),
        *(["    SYNCS.ARRIVE.TRANS64 {RZ,RZ}, [RZ+UR6], R0;[1:7:{2}:5:1]"
           ] if use_expect else []),
        # heartbeat 1
        "    MOV32I R11, 2;[7:7:{}:1:0]",
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R11;[0:1:{1}:1:0]",
        "    ELECT P1, URZ, PT;[1:7:{}:5:1]",
        "    MOV32I R15, %d;[7:7:{}:1:0]" % units,
        "    @UP1 UBLKCP.S.G [UR10], [UR8], UR15;[0:7:{2}:5:1]",
        # heartbeat 2
        "    MOV32I R11, 3;[7:7:{}:1:0]",
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R11;[0:1:{1}:1:0]",
    ]
    if phase_poll:
        # single non-spinning try_wait snapshot -> parity word readable
        lines += [
            "    SYNCS.PHASECHK.TRANS64.TRYWAIT P2, [UR6], UR13;[2:7:{2}:1:1]",
            "    P2R R20, PR, RZ, 0x7f;[7:7:{2}:8:1]",
            "    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R20;[0:1:{1}:1:0]",
        ]
    lines += [
        # bounded DATA poll (mirror of the green sm120 waiter): 0x20000 max
        "    MOV32I R14, 0x20000;[7:7:{}:1:0]",
        "    #def_label(spin)",
        "    LDS R10, [RZ+UR10];[1:7:{2}:8:1]   // addr via smem window",
        "    ISETP.EQ.U32.AND P0, PT, R10, 0xDEAD0000, PT;[7:7:{2}:5:1]",
        "    @P0 BRA #label(datadone);[7:7:{}:5:1]",
        "    IADD3 R14, R14, -1, RZ;[7:7:{2}:5:1]",
        "    ISETP.GT.U32.AND P1, PT, R14, RZ, PT;[7:7:{2}:5:1]",
        "    @P1 BRA #label(spin);[7:7:{}:5:1]",
        "    #def_label(datadone)",
        "    LDS.64 {R10,R11}, [RZ+UR10];[1:7:{2}:5:1]",
        "    LDS.64 {R12,R13}, [RZ+UR10+0x8];[1:7:{2}:5:1]",
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]",
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0xC], R14;[0:1:{1}:1:0]",   # iters left
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R10;[0:1:{1}:1:0]",
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x14], R11;[0:1:{1}:1:0]",
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x18], R12;[0:1:{1}:1:0]",
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x1C], R13;[0:1:{1}:1:0]",
        "    EXIT;[7:7:{}:5:0]",
    ]
    return ("#fn k(out<8>, gsrc<8>) {\n"
            "    #pragma NUM_MBARRIERS(1)\n"
            "    #pragma SHARED(0x4000)\n"
            + "\n".join(lines) + "\n}\n")


# ---------------------------------------------------------------------------
def run_s2g():
    src = adapt_source(build_s2g())
    mod = CudaModule(assemble(src))
    d = mod.devmem_alloc(64)
    mod.device_write(d, bytes(64))
    mod.launch("k", grid=(1,), block=(1,), args=[d], shared_mem=0x4000)
    mod.synchronize()
    v = struct.unpack("<8I", mod.device_read(d, 32))
    exp = [0x11111111, 0x22222222, 0x33333333, 0x44444444,
           0x55555555, 0x66666666, 0x77777777, 0x88888888]
    ok = list(v) == exp
    print(f"[s2g] {'OK' if ok else 'FAIL'} got={list(map(hex, v))}")


def run_g2s(**kw):
    name = kw.pop("name", "g2s")
    src = adapt_source(build_g2s_source(**kw))
    reset_context()
    mod = CudaModule(assemble(src))
    d_out = mod.devmem_alloc(64)
    d_src = mod.devmem_alloc(64)
    payload = struct.pack("<4I", 0xDEAD0000, 0xDEAD0001, 0xDEAD0002, 0xDEAD0003)
    mod.device_write(d_src, payload + bytes(48))
    mod.device_write(d_out, b"\xFF" * 64)
    mod.launch("k", grid=(1,), block=(1,), args=[d_out, d_src])
    mod.synchronize()
    words = struct.unpack("<16I", mod.device_read(d_out, 64))
    print(f"[{name}] hb(issue stages)=" + str(words[0:3]) +
          f"  parity_snap={words[4]:#010x}" if kw.get("phase_poll") else
          f"[{name}] hb(issue stages)=" + str(words[0:3]))
    print(f"[{name}] iters_left={words[3]} first_words=" +
          str([hex(w) for w in words[4:8]]))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "help"
    if what == "s2g":
        run_s2g()
    elif what == "g2s_bounded":
        run_g2s(name="g2s_bounded", use_expect=True, use_ushf_count=False)
    elif what == "g2s_noexpect":
        run_g2s(name="g2s_noexpect", use_expect=False)
    elif what == "g2s_sm90cnt":
        run_g2s(name="g2s_sm90cnt", use_expect=True, use_ushf_count=True)
    else:
        print(__doc__)
