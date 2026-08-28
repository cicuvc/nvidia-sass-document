"""probe: CALL.ABS into heap-resident SASS + RET stack semantics.

Run: python3 sassdbg/probe_callheap2.py
"""
import struct
import sys
import time
import faulthandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import assemble, assemble_flat, CudaModule    # noqa: E402
from assembler.runner import reset_context                  # noqa: E402

faulthandler.dump_traceback_later(180, exit=True)

B = "[7:7:{}:5:1]"
BB = "[7:7:{}:8:1]"


def heap_words(body: str) -> bytes:
    """Assemble a bare instruction sequence to 16-byte words."""
    enc = assemble_flat(body)
    return b"".join(struct.pack("<QQ", lo, hi) for lo, hi in enc)


def run(name, main_body: str, heap_body: str, park_ms: float = 0,
        expect=None):
    reset_context()
    try:
        cubin = assemble(f"#fn k(out<8>, code<8>) {{\n{main_body}\n}}",
                         check_deps=False)
    except Exception as e:
        print(f"{name}: ASSEMBLE FAIL {str(e)[:100]}")
        return
    try:
        mod = CudaModule(cubin)
        out = mod.devmem_alloc(4096)
        code = mod.devmem_alloc(4096)
        mod.device_write(out, bytes(4096))
        mod.device_write(code, heap_words(heap_body))
        stream = CudaModule.stream_create()
        mod.launch("k", grid=(1,), block=(32,), args=[out, code],
                   stream=stream)
        if park_ms:
            time.sleep(park_ms / 1000)
            mod.device_write(out + 0x10, struct.pack("<I", 1))
        t0 = time.time()
        while not CudaModule.stream_query(stream):
            if time.time() - t0 > 10:
                print(f"{name}: TIMEOUT (parked?)")
                return
            time.sleep(0.005)
        CudaModule.stream_sync(stream)
        v = struct.unpack("<32I", mod.device_read(out, 128))
        verdict = ""
        if expect is not None:
            verdict = ("  (match!)" if v[0] == expect
                       else f"  (want {hex(expect)})")
        print(f"{name}: OK out[0]={hex(v[0])}{verdict} out[1]={hex(v[1])}"
              f" out[2]={hex(v[2])}, out[8]={hex(v[8])}, out[9]={hex(v[9])}")
    except Exception as e:
        print(f"{name}: FAULT {str(e)[:90]}")


# Main-kernel prologue: UR4/5 = cdesc, R4/5 = out, R26/27 = heap code VA,
# R22/23 = own code base (LEPC at idx 2), R20/21 = return VA.
MAIN_HDR = f"""\
    LEPC {{R22,R23}};[7:7:{{}}:4:0]
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LDC.64 {{R26,R27}}, #param(code);[2:7:{{}}:8:0]
"""


def main_with(call_line: str, ret_idx: int) -> str:
    """hdr + marker + retVA store at out+8 + call_line + return point."""
    off = ret_idx * 16   # LEPC at idx 0: base = LEPC VA
    # idx: 0 LDCU,1 LDC out,2 LDC code -- wait, LEPC must stay at a known
    # idx; hdr is 4 insts (0..3), then:
    # 4 MOV32I R2, 5 MOV32I R25, 6 IMAD.WIDE, 7 STG.64 retVA,
    # 8 call_line, 9 = return point
    assert ret_idx == 9
    return MAIN_HDR + f"""\
    MOV32I R2, 0x1111;{B}
    MOV32I R25, 0x{off:x};{B}
    IMAD.WIDE.U32 {{R20,R21}}, R25, 0x1, {{R22,R23}};{B}
    STG.E.64 desc[{{UR4,UR5}}][{{R4,R5}}+0x8], {{R20,R21}};[0:1:{{0,1,2,3}}:8:0]
    {call_line}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R2;[0:1:{{}}:8:0]
    EXIT;{B}
"""

heap_e0 = f"""\
    MOV32I R2, 0xBBBB;{B}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R2;[0:1:{{}}:8:0]
    LDG.E.64 {{R24,R25}}, desc[{{UR4,UR5}}][{{R4,R5}}+0x8];[3:7:{{}}:8:0]
    RPCMOV.32 R10, Rpc.LO;[0:7:{{}}:13:1]
    RPCMOV.32 R11, Rpc.HI;[0:7:{{}}:13:1]
    STG.E.64 desc[{{UR4,UR5}}][{{R4,R5}}+0x20], {{R10,R11}};[0:1:{{0}}:8:0] #R10,R11 holds address of CALL instruction, not the next
    RET.ABS.NODEC {{R24,R25}}, 0x10;[7:7:{{3}}:5:1] #add 16bytes offset to go to next instuction (STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R2;[0:1:{{}}:8:0])
"""
run("CALL->heap->RPC back", main_with("CALL.ABS.NOINC {R26,R27};[7:7:{}:5:1]", 9), heap_e0,
    expect=0xBBBB)


run("NOP fallthrough", main_with("NOP;[7:7:{}:5:1]", 9), heap_e0,
    expect=0x1111)
