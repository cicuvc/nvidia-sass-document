"""probe 3: CALL/RET/RPCMOV semantics for the slot-less breakpoint redesign.

Established by this probe (see git log / notes for the full saga):

  * RET's jump target is ALWAYS Ra + disp (disp in BYTES).  CALL_DEPTH
    INC / RET_DEPTH DEC only maintain a hardware call-depth counter —
    they neither save nor restore the PC.  Nested INC/DEC chains with
    correct register VAs work (S4); RET with Ra=RZ faults 700 (S1).
    => a handler must obtain its return VA from RPCMOV (or be told).
  * RPCMOV.32 Rd, Rpc.LO/Rpc.HI reads the RPC register = VA of the CALL
    instruction itself; return to the next instruction = RPC + 0x10.
    Nesting overwrites RPC (S3): a callee that CALLs again must spill
    RPC first.  Outside any active CALL, RPCMOV reads garbage (R0).
  * GPU fetches/executes SASS from plain device memory ("heap code"):
    CALL.ABS into a devmem buffer works; the buffer is written by the
    host with a plain cuMemcpy (no icache issues: fresh pages).
  * SCOREBOARD RULE (empirical, cost a day): explicit barrier waits MUST
    go in the {req} bitset.  The rd field does NOT reliably wait —
    rd=2 on a MOV32I did not wait, req={2} on the same MOV32I did;
    rd=1 on an STG.64 did not wait the LDC address pair (700).  An
    unwaited LDC/LDCU result is a garbage address/descriptor -> 700; an
    unwaited CALL target register -> 718 INVALID_PC.

Per-experiment subprocess isolation: a faulting kernel poisons its
context, and a hung kernel makes cuCtxDestroy deadlock — so each
experiment runs as its own process.

Run all:   python3 sassdbg/probe_callheap3.py
Run one:   python3 sassdbg/probe_callheap3.py <name>   (in-process)
"""
import struct
import subprocess
import sys
import time
import faulthandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

faulthandler.dump_traceback_later(120, exit=True)

B = "[7:7:{}:5:1]"
BB = "[7:7:{}:8:1]"


def heap_words(body: str) -> bytes:
    from assembler import assemble_flat
    enc = assemble_flat(body)
    return b"".join(struct.pack("<QQ", lo, hi) for lo, hi in enc)


def run(name, src, heap=None, expect=None, block=(32,)):
    from assembler import assemble, CudaModule
    mod = CudaModule(assemble(src, check_deps=False))
    out = mod.devmem_alloc(4096)
    mod.device_write(out, bytes(4096))
    args = [out]
    if heap is not None:
        code = mod.devmem_alloc(4096)
        mod.device_write(code, heap_words(heap))
        args.append(code)
    stream = CudaModule.stream_create()
    mod.launch("k", grid=(1,), block=block, args=args, stream=stream)
    t0 = time.time()
    while not CudaModule.stream_query(stream):
        if time.time() - t0 > 6:
            print(f"{name}: TIMEOUT", flush=True)
            sys.exit(2)      # leave GPU cleanup to process teardown
        time.sleep(0.005)
    CudaModule.stream_sync(stream)
    v = struct.unpack("<32I", mod.device_read(out, 128))
    tag = ""
    if expect is not None:
        tag = "  (match!)" if v[0] == expect else f"  (WANT {hex(expect)})"
    print(f"{name}: OK out0={hex(v[0])}{tag} "
          + " ".join(f"w{i}={hex(v[i])}" for i in (8, 9, 10, 11, 12, 13)),
          flush=True)
    return v


# ---------------------------------------------------------------------------
# Heap handler used by the P-series: report RPC, clobber R2, RET to
# RPC+0x10 (the instruction after the CALL site).
# RPCMOVs re-claim SB0 so the report STG's req={0,1} covers
# LDCU + both RPCMOVs (SB0) and the LDC address pair (SB1).
# ---------------------------------------------------------------------------
HANDLER = f"""\
    MOV32I R2, 0xBBBB;{B}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R2;[0:1:{{0,1}}:8:0]
    RPCMOV.32 R10, Rpc.LO;[0:7:{{}}:13:1]
    RPCMOV.32 R11, Rpc.HI;[0:7:{{}}:13:1]
    STG.E.64 desc[{{UR4,UR5}}][{{R4,R5}}+0x20], {{R10,R11}};[0:1:{{0,1}}:8:0]
    RET.ABS.NODEC {{R10,R11}}, 0x10;{BB}
"""


def matrix_src(call_form, ret_form):
    # idx: 0 LDCU, 1 LDC, 2 LEPC, 3 MOV R2, 4 MOV R25, 5 IMAD.WIDE,
    #      6 CALL, 7 STG (return point), 8 EXIT, 9 sub: MOV, 10 RET
    off = (7 - 2) * 16
    return f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LEPC {{R22,R23}};[7:7:{{}}:4:0]
    MOV32I R2, 0x1111;{B}
    MOV32I R25, 0x{off:x};{B}
    IMAD.WIDE.U32 {{R20,R21}}, R25, 0x1, {{R22,R23}};[7:7:{{}}:13:1]
    {call_form} PT, #label(sub);{BB}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R2;[0:1:{{0,1}}:8:0]
    EXIT;{B}
#def_label(sub)
    MOV32I R2, 0xAAAA;{B}
    {ret_form} PT, {{R20,R21}}, 0x0;{BB}
}}"""


def nested_src(ret1, ret2, rpcmov=False):
    """Nested INC/DEC.  ret1/ret2 = register operand text for the RETs.
    idx: 0 LDCU,1 LDC,2 LEPC,3 MOV R2,4 MOV25,5 IMAD,6 CALL,7 STG,8 EXIT
    sub1: 9 IADD3,10 [RPCMOV,RPCMOV,STG],13 MOV25,14 IMAD,15 CALL,
          16 IADD3 +0x2000, 17 RET
    sub2: 18 IADD3 +0x20, [RPCMOV,RPCMOV,STG], 22 RET
    """
    s1_rpc = f"""\
    RPCMOV.32 R10, Rpc.LO;[0:7:{{}}:13:1]
    RPCMOV.32 R11, Rpc.HI;[0:7:{{}}:13:1]
    STG.E.64 desc[{{UR4,UR5}}][{{R4,R5}}+0x20], {{R10,R11}};[0:1:{{0,1}}:8:0]
""" if rpcmov else ""
    s2_rpc = f"""\
    RPCMOV.32 R12, Rpc.LO;[0:7:{{}}:13:1]
    RPCMOV.32 R13, Rpc.HI;[0:7:{{}}:13:1]
    STG.E.64 desc[{{UR4,UR5}}][{{R4,R5}}+0x28], {{R12,R13}};[0:1:{{0,1}}:8:0]
""" if rpcmov else ""
    pad = 3 if rpcmov else 0
    main_ret = (7 - 2) * 16            # idx7, LEPC at idx2
    sub1_ret = (13 + pad - 2) * 16     # IADD3 +0x2000 position
    return f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LEPC {{R22,R23}};[7:7:{{}}:4:0]
    MOV32I R2, 0x0;{B}
    MOV32I R25, 0x{main_ret:x};{B}
    IMAD.WIDE.U32 {{R20,R21}}, R25, 0x1, {{R22,R23}};[7:7:{{}}:13:1]
    CALL.REL.INC PT, #label(sub1);{BB}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R2;[0:1:{{0,1}}:8:0]
    EXIT;{B}
#def_label(sub1)
    IADD3 R2, R2, 0x100, RZ;{B}
{s1_rpc}    MOV32I R25, 0x{sub1_ret:x};{B}
    IMAD.WIDE.U32 {{R16,R17}}, R25, 0x1, {{R22,R23}};[7:7:{{}}:13:1]
    CALL.REL.INC PT, #label(sub2);{BB}
    IADD3 R2, R2, 0x2000, RZ;{B}
    RET.ABS.DEC PT, {ret1}, 0x0;{BB}
#def_label(sub2)
    IADD3 R2, R2, 0x20, RZ;{B}
{s2_rpc}    RET.ABS.DEC PT, {ret2}, 0x0;{BB}
}}"""


MAIN_UNIFORM = f"""#fn k(out<8>, code<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LDC.64 {{R26,R27}}, #param(code);[2:7:{{}}:8:0]
    MOV32I R2, 0xEEEE;{B}
    MOV32I R15, 0x0;[7:7:{{2}}:5:1]
    CALL.ABS.NOINC {{R26,R27}};[7:7:{{}}:5:1]
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R2;[0:1:{{0,1}}:8:0]
    EXIT;{B}
}}"""

MAIN_DIVERGENT = f"""#fn k(out<8>, code<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LDC.64 {{R26,R27}}, #param(code);[2:7:{{}}:8:0]
    S2R R6, SR_TID.X;[3:7:{{}}:5:1]
    ISETP.LT.AND P0, PT, R6, 0x10, PT;[7:7:{{0,3}}:13:1]
    MOV32I R2, 0xEEEE;{B}
    MOV32I R15, 0x0;[7:7:{{2}}:5:1]
    @P0 CALL.ABS.NOINC {{R26,R27}};[7:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R8,R9}}, R6, 0x4, {{R4,R5}};{B}
    IADD3 R8, R8, 0x100, RZ;{B}
    STG.E desc[{{UR4,UR5}}][{{R8,R9}}], R2;[0:7:{{}}:8:0]
    EXIT;{B}
}}"""

MAIN_IMM_TEMPLATE = """#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    MOV32I R2, 0x1111;{B}
    CALL.ABS.NOINC PT, 0x{handler_va:x};{BB}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R2;[0:1:{{0,1}}:8:0]
    EXIT;{B}
}}"""

R0_SRC = f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    RPCMOV.32 R10, Rpc.LO;[0:7:{{}}:13:1]
    RPCMOV.32 R11, Rpc.HI;[0:7:{{}}:13:1]
    STG.E.64 desc[{{UR4,UR5}}][{{R4,R5}}+0x20], {{R10,R11}};[0:1:{{0,1}}:8:0]
    MOV32I R2, 0x5555;{B}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R2;[0:1:{{}}:8:0]
    EXIT;{B}
}}"""


def exp_m():
    for cf in ("CALL.REL.NOINC", "CALL.REL.INC"):
        for rf in ("RET.ABS.NODEC", "RET.ABS.DEC"):
            run(f"M {cf}+{rf}", matrix_src(cf, rf), expect=0xAAAA)


def exp_s1():
    run("S1 nested INC/DEC, RZ (negative control)",
        nested_src("RZ", "RZ"), expect=0x2120)


def exp_s4():
    run("S4 nested INC/DEC, correct per-level Ra",
        nested_src("{R20,R21}", "{R16,R17}"), expect=0x2120)


def exp_s3():
    v = run("S3 nested + RPCMOV telemetry",
            nested_src("{R20,R21}", "{R16,R17}", rpcmov=True), expect=0x2120)
    if v:
        print("   w8/9 = RPC seen in sub1 (outer CALL VA)")
        print("   w10/11 = RPC seen in sub2 (inner CALL VA)")
        print("   compare: main CALL at base+0x60, inner at base+"
            f"{hex(15 * 16)}")


def exp_p3a():
    run("P3a uniform CALL->heap handler", MAIN_UNIFORM, heap=HANDLER,
        expect=0xBBBB)


def exp_p3b():
    v = run("P3b divergent CALL->heap handler", MAIN_DIVERGENT,
            heap=HANDLER)
    if v:
        from assembler import CudaModule  # lanes read skipped; see out+0x100
        print("   (lane markers at out+0x100 not re-read here)")


def exp_p4():
    # two-pass: heap handler VA must be known before assembling main
    from assembler import assemble, CudaModule
    boot = CudaModule(assemble(f"#fn boot(out<8>) {{\n    EXIT;{B}\n}}",
                               check_deps=False))
    code = boot.devmem_alloc(4096)
    boot.device_write(code, heap_words(HANDLER))
    src = MAIN_IMM_TEMPLATE.format(handler_va=code, B=B, BB=BB)
    run("P4 CALL.ABS imm -> heap", src, heap=None, expect=0xBBBB)


def exp_s5():
    # which CALL forms populate RPC?  in-kernel sub, RPCMOV report,
    # RET via LEPC-computed VA.
    # idx: 0 LDCU,1 LDC,2 LEPC,3 MOV,4 MOV25,5 IMAD,6 CALL,7 STG,8 EXIT
    # sub: 9 RPCMOV,10 RPCMOV,11 STG.64,12 RET
    for cf in ("CALL.REL.NOINC", "CALL.REL.INC", "CALL.ABS.NOINC",
               "CALL.ABS.INC"):
        ret_off = "0x50"
        if cf.startswith("CALL.REL"):
            call = f"{cf} PT, #label(sub);{BB}"
        else:
            ret_off = "0x70"
            # ABS with a register target: sub VA = LEPC + (9-2)*16
            call = (f"MOV32I R24, 0x90;{B}\n"
                    f"    IMAD.WIDE.U32 {{R18,R19}}, R24, 0x1, {{R22,R23}};"
                    f"[7:7:{{}}:13:1]\n"
                    f"    {cf} PT, {{R18,R19}}, 0x0;{BB}")
        src = f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LEPC {{R22,R23}};[7:7:{{}}:4:0]
    MOV32I R2, 0x1111;{B}
    MOV32I R25, {ret_off};{B}
    IMAD.WIDE.U32 {{R20,R21}}, R25, 0x1, {{R22,R23}};[7:7:{{}}:13:1]
    {call}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R2;[0:1:{{0,1}}:8:0]
    EXIT;{B}
#def_label(sub)
    RPCMOV.32 R10, Rpc.LO;[0:7:{{}}:13:1]
    RPCMOV.32 R11, Rpc.HI;[0:7:{{}}:13:1]
    STG.E.64 desc[{{UR4,UR5}}][{{R4,R5}}+0x20], {{R10,R11}};[0:1:{{0,1}}:8:0]
    RET.ABS.NODEC PT, {{R20,R21}}, 0x0;{BB}
}}"""
        # for the ABS-reg form the sub sits at idx 9 = LEPC + 0x70
        run(f"S5 RPCMOV after {cf}", src, expect=0x1111)


def exp_r0():
    run("R0 bare RPCMOV (no active CALL)", R0_SRC, expect=0x5555)


EXPERIMENTS = {"m": exp_m, "s5": exp_s5, "s1": exp_s1, "s4": exp_s4, "s3": exp_s3,
               "p3a": exp_p3a, "p3b": exp_p3b, "p4": exp_p4, "r0": exp_r0}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        EXPERIMENTS[sys.argv[1]]()
    else:
        for name in EXPERIMENTS:
            r = subprocess.run(
                [sys.executable, __file__, name],
                capture_output=True, text=True, timeout=60)
            print(r.stdout, end="")
            if r.returncode != 0:
                print(f"--- {name} rc={r.returncode} ---")
                print(r.stderr[-400:] if r.stderr else "")
