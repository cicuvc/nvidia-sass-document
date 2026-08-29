"""Probe whether CALL.ABS R/UR/IMM forms populate RPC on SM90/SM120.

The heap-resident handler reports RPC at out+8 and returns through RPC+0x10.
The caller reports a LEPC value at out+0x10, allowing an exact comparison
between RPC and the encoded CALL instruction's VA.
"""
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import CudaModule, assemble, assemble_flat, assemble_kernel


B = "[7:7:{}:5:1]"
BB = "[7:7:{}:8:1]"

HANDLER = f"""\
    MOV32I R2, 0xbbbb;{B}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R2;[0:1:{{0,1}}:8:0]
    RPCMOV.32 R10, Rpc.LO;[0:7:{{}}:13:1]
    RPCMOV.32 R11, Rpc.HI;[0:7:{{}}:13:1]
    STG.E.64 desc[{{UR4,UR5}}][{{R4,R5}}+0x8], {{R10,R11}};[0:1:{{0,1}}:8:0]
    RET.ABS.NODEC PT, {{R20,R21}}, 0x0;[7:7:{{0}}:8:1]
"""


def heap_words() -> bytes:
    encoded = assemble_flat(HANDLER)
    return b"".join(struct.pack("<QQ", lo, hi) for lo, hi in encoded)


def caller_source(form: str, handler_va: int) -> str:
    if form == "r":
        params = "out<8>, code<8>"
        load = "LDC.64 {R26,R27}, #param(code);[2:7:{}:8:0]"
        call = f"CALL.ABS.NOINC PT, {{R26,R27}}, 0x0;[7:7:{{2}}:8:1]"
    elif form == "ur":
        params = "out<8>, code<8>"
        load = "LDCU.64 {UR6,UR7}, #param(code);[2:7:{}:8:0]"
        call = f"CALL.ABS.NOINC PT, {{UR6,UR7}}, 0x0;[7:7:{{2}}:8:1]"
    elif form == "ur_inc":
        params = "out<8>, code<8>"
        load = "LDCU.64 {UR6,UR7}, #param(code);[2:7:{}:8:0]"
        call = f"CALL.ABS.INC PT, {{UR6,UR7}}, 0x0;[7:7:{{2}}:8:1]"
    elif form == "ur_local":
        params = "out<8>"
        load = "ULEPC {UR6,UR7}, #label(sub);[7:7:{}:5:1]"
        call = f"CALL.ABS.NOINC PT, {{UR6,UR7}}, 0x0;{BB}"
    elif form == "imm":
        params = "out<8>"
        load = "NOP;[7:7:{}:8:1]"
        call = f"CALL.ABS.NOINC PT, 0x{handler_va:x};{BB}"
    elif form == "imm_inc":
        params = "out<8>"
        load = "NOP;[7:7:{}:8:1]"
        call = f"CALL.ABS.INC PT, 0x{handler_va:x};{BB}"
    else:
        raise ValueError(form)

    pad = "\n".join("    NOP;[7:7:{}:8:1]" for _ in range(8))
    tail = "\n    #def_label(sub)\n" + HANDLER if form == "ur_local" else ""
    return f"""#fn k({params}) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    {load}
    LEPC {{R22,R23}};[7:7:{{}}:4:0]
{pad}
    STG.E.64 desc[{{UR4,UR5}}][{{R4,R5}}+0x10], {{R22,R23}};[0:1:{{0,1}}:8:0]
    MOV32I R25, 0xe0;{B}
    IMAD.WIDE.U32 {{R20,R21}}, R25, 0x1, {{R22,R23}};[7:7:{{}}:13:1]
    MOV32I R2, 0x1111;{B}
    {call}
    MOV32I R3, 0xdddd;{B}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}+0x4], R3;[0:1:{{}}:8:0]
    EXIT;{B}
{tail}
}}"""


def opcode(lo: int, hi: int) -> int:
    return (((hi >> 27) & 1) << 12) | (lo & 0xfff)


def verify_ur_target(code: int) -> None:
    src = """#fn verify(out<8>, code<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    LDCU.64 {UR6,UR7}, #param(code);[2:7:{}:8:0]
    MOV R8, UR6;[7:7:{2}:5:1]
    MOV R9, UR7;[7:7:{}:5:1]
    STG.E.64 desc[{UR4,UR5}][{R4,R5}], {R8,R9};[0:1:{0,1}:8:0]
    EXIT;[7:7:{}:5:1]
}"""
    mod = CudaModule(assemble(src, check_deps=False))
    out = mod.devmem_alloc(16)
    mod.device_write(out, bytes(16))
    mod.launch("verify", grid=(1,), block=(32,), args=[out, code])
    mod.synchronize()
    loaded, = struct.unpack("<Q", mod.device_read(out, 8))
    print(f"UR preflight: loaded={loaded:#x} expected={code:#x} "
          f"({'MATCH' if loaded == code else 'MISMATCH'})", flush=True)


def run(form: str) -> None:
    # Allocate executable heap memory first so the IMM source can embed its VA.
    boot = CudaModule(assemble(f"#fn boot() {{\n    EXIT;{B}\n}}",
                               check_deps=False))
    code = boot.devmem_alloc(4096)
    boot.device_write(code, heap_words())
    if form in ("ur", "ur_inc"):
        verify_ur_target(code)

    result = assemble_kernel(caller_source(form, code), check_deps=False)
    call_ops = {"r": 0x343, "ur": 0x1943, "ur_inc": 0x1943,
                "ur_local": 0x1943, "imm": 0x943, "imm_inc": 0x943}
    matches = [(i, lo, hi) for i, (lo, hi) in enumerate(result.encoded)
               if opcode(lo, hi) == call_ops[form]]
    assert len(matches) == 1, matches
    call_idx, call_lo, call_hi = matches[0]
    lepc_idx = 3
    call_word = call_lo | (call_hi << 64)
    depth_bit = (call_word >> 86) & 1
    if form.startswith("imm"):
        raw = (((call_word >> 34) & ((1 << 47) - 1)) << 8) \
              | ((call_word >> 16) & 0xff)
        print(f"{form.upper()} prelaunch: encoded_target={raw * 4:#x} "
              f"expected={code:#x} depth_bit={depth_bit}", flush=True)
    else:
        print(f"{form.upper()} prelaunch: target_UR/R="
              f"{(call_word >> 24) & (0x3f if form.startswith('ur') else 0xff)} "
              f"depth_bit={depth_bit}", flush=True)

    mod = CudaModule(result.code)
    out = mod.devmem_alloc(64)
    mod.device_write(out, bytes(64))
    args = [out, code] if form in ("r", "ur", "ur_inc") else [out]
    stream = CudaModule.stream_create()
    mod.launch("k", grid=(1,), block=(32,), args=args, stream=stream)
    deadline = time.time() + 6
    while not CudaModule.stream_query(stream):
        if time.time() > deadline:
            print(f"{form.upper()}: TIMEOUT", flush=True)
            sys.exit(2)
        time.sleep(0.005)
    CudaModule.stream_sync(stream)

    magic, returned, rpc, lepc = struct.unpack("<IIQQ", mod.device_read(out, 24))
    expected_rpc = lepc + (call_idx - lepc_idx) * 16
    print(f"{form.upper():3s}: opcode={call_ops[form]:#x} "
          f"word={call_hi:016x}:{call_lo:016x} magic={magic:#x} "
          f"returned={returned:#x} rpc={rpc:#x} expected={expected_rpc:#x} "
          f"({'RPC MATCH' if rpc == expected_rpc else 'RPC MISMATCH'})",
          flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        run(sys.argv[1].lower())
    else:
        for form in ("r", "ur", "ur_inc", "ur_local", "imm", "imm_inc"):
            result = subprocess.run([sys.executable, __file__, form],
                                    capture_output=True, text=True, timeout=30)
            print(result.stdout, end="")
            if result.returncode:
                print(f"{form.upper()}: FAILED rc={result.returncode}")
                print(result.stderr[-1200:], end="")
