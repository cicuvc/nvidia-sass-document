"""Probe the architecturally visible effect of latency-table RPC_WRITERS.

Each case seeds Rpc.LO with SENTINEL, executes one candidate operation, waits
well beyond the 9-cycle RPC dependency, then performs exactly one Rpc.LO read.
"""
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import CudaModule, assemble, assemble_flat, assemble_kernel


SENTINEL = 0x12345000
B = "[7:7:{}:5:1]"
BB = "[7:7:{}:8:1]"
PAD16 = "\n".join("    NOP;[7:7:{}:8:1]" for _ in range(16))
PAD8 = "\n".join("    IADD3 R30, R30, RZ, RZ;[7:7:{}:5:1]" for _ in range(8))


CASES = {
    "nop": {
        "prep": "",
        "op": f"NOP;{BB}",
        "opcode": 0x918,
    },
    "bra": {
        "prep": "",
        "op": f"BRA #label(land);{BB}",
        "opcode": 0x947,
    },
    "break": {
        "prep": "",
        "op": "",
        "opcode": 0x942,
    },
    "jmp": {
        "prep": "",
        "op": "",
        "opcode": 0x94A,
    },
    "yield": {
        "prep": "",
        "op": f"YIELD;{BB}",
        "opcode": 0x946,
    },
    "nanosleep": {
        "prep": "",
        "op": f"NANOSLEEP 0x0;{BB}",
        "opcode": 0x95D,
    },
    "warpsync": {
        "prep": "",
        "op": f"WARPSYNC.ALL;{BB}",
        "opcode": 0x948,
    },
    "bsync": {
        "prep": f"    BSSY B0, #label(land);{BB}\n",
        "op": f"BSYNC B0;{BB}",
        "opcode": 0x941,
    },
    "jmx": {
        "prep": f"    LEPC {{R24,R25}}, #label(land);{B}\n",
        "op": f"JMX {{R24,R25}}, 0x0;{BB}",
        "opcode": 0x94C,
    },
    "jmxu": {
        "prep": f"    ULEPC {{UR6,UR7}}, #label(land);{B}\n",
        "op": f"JMXU UR6, 0x0;{BB}",
        "opcode": 0x1959,
    },
    "brx": {
        "prep": "",
        "op": f"BRX RZ, #label(land);{BB}",
        "opcode": 0x949,
    },
    "brxu": {
        "prep": (f"    UMOV UR6, URZ;{B}\n"
                 f"    UMOV UR7, URZ;{B}\n"),
        "op": f"BRXU UR6, #label(land);{BB}",
        "opcode": 0x1958,
    },
    "ret": {
        "prep": f"    LEPC {{R20,R21}}, #label(land);{B}\n",
        "op": f"RET.ABS.NODEC PT, {{R20,R21}}, 0x0;{BB}",
        "opcode": 0x950,
    },
    "retu": {
        "prep": f"    ULEPC {{UR6,UR7}}, #label(land);{B}\n",
        "op": f"RET.ABS.NODEC PT, {{UR6,UR7}}, 0x0;{BB}",
        "opcode": 0x1950,
    },
    "call_r": {
        "prep": f"    LEPC {{R26,R27}}, #label(land);{B}\n",
        "op": f"CALL.ABS.NOINC PT, {{R26,R27}}, 0x0;{BB}",
        "opcode": 0x343,
    },
    "call_ur": {
        "prep": f"    ULEPC {{UR6,UR7}}, #label(land);{B}\n",
        "op": f"CALL.ABS.NOINC PT, {{UR6,UR7}}, 0x0;{BB}",
        "opcode": 0x1943,
    },
    "call_imm": {
        "prep": "",
        "op": "",
        "opcode": 0x943,
    },
}


def source(name: str) -> str:
    case = CASES[name]
    return f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LEPC {{R22,R23}};[7:7:{{}}:4:0]
{case['prep']}    RPCMOV.32 Rpc.LO, 0x{SENTINEL:x};[7:7:{{}}:5:1]
    RPCMOV.32 Rpc.HI, 0x0;[7:7:{{}}:5:1]
{PAD16}
    {case['op']}
    MOV32I R31, 0xbad0bad0;{B}
    #def_label(land)
{PAD16}
    RPCMOV.32 R8, Rpc.LO;[0:7:{{}}:13:1]
{PAD8}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R8;[0:1:{{0,1}}:8:0]
    STG.E.64 desc[{{UR4,UR5}}][{{R4,R5}}+0x8], {{R22,R23}};[7:1:{{}}:8:0]
    EXIT;{B}
}}"""


def opcode(lo: int, hi: int) -> int:
    return (((hi >> 27) & 1) << 12) | (lo & 0xFFF)


def run_heap_imm(name: str) -> None:
    handler = f"""{PAD16}
    RPCMOV.32 R8, Rpc.LO;[0:7:{{}}:13:1]
{PAD8}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R8;[0:1:{{0,1}}:8:0]
    STG.E.64 desc[{{UR4,UR5}}][{{R4,R5}}+0x8], {{R22,R23}};[7:1:{{}}:8:0]
    EXIT;{B}
"""
    encoded = assemble_flat(handler)
    heap_words = b"".join(struct.pack("<QQ", lo, hi) for lo, hi in encoded)
    boot = CudaModule(assemble(f"#fn boot() {{\n    EXIT;{B}\n}}",
                               check_deps=False))
    code = boot.devmem_alloc(4096)
    boot.device_write(code, heap_words)
    target_op = (f"JMP 0x{code:x};{BB}" if name == "jmp" else
                 f"CALL.ABS.NOINC PT, 0x{code:x};{BB}")
    target_opcode = 0x94A if name == "jmp" else 0x943
    src = f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LEPC {{R22,R23}};[7:7:{{}}:4:0]
    RPCMOV.32 Rpc.LO, 0x{SENTINEL:x};[7:7:{{}}:5:1]
    RPCMOV.32 Rpc.HI, 0x0;[7:7:{{}}:5:1]
{PAD16}
    {target_op}
    EXIT;{B}
}}"""
    result = assemble_kernel(src, check_deps=False)
    matches = [i for i, (lo, hi) in enumerate(result.encoded)
               if opcode(lo, hi) == target_opcode]
    assert len(matches) == 1, matches
    op_idx = matches[0]
    mod = CudaModule(result.code)
    out = mod.devmem_alloc(32)
    mod.device_write(out, bytes(32))
    mod.launch("k", grid=(1,), block=(32,), args=[out])
    mod.synchronize()
    rpc_lo, _pad, base = struct.unpack("<IIQ", mod.device_read(out, 16))
    op_pc = base + (op_idx - 2) * 16
    delta = (rpc_lo - (base & 0xFFFFFFFF)) & 0xFFFFFFFF
    kind = "SENTINEL" if rpc_lo == SENTINEL else f"base+{delta:#x}"
    print(f"{name:9s}: op_pc={op_pc:#x} rpc.lo={rpc_lo:#010x} {kind}",
          flush=True)


def run_break() -> None:
    src = f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LEPC {{R22,R23}};[7:7:{{}}:4:0]
    BSSY B0, #label(join);{BB}
    RPCMOV.32 Rpc.LO, 0x{SENTINEL:x};[7:7:{{}}:5:1]
    RPCMOV.32 Rpc.HI, 0x0;[7:7:{{}}:5:1]
{PAD16}
    BREAK B0;{BB}
{PAD16}
    RPCMOV.32 R8, Rpc.LO;[0:7:{{}}:13:1]
{PAD8}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R8;[0:1:{{0,1}}:8:0]
    STG.E.64 desc[{{UR4,UR5}}][{{R4,R5}}+0x8], {{R22,R23}};[7:1:{{}}:8:0]
    BSYNC B0;{BB}
    #def_label(join)
    EXIT;{B}
}}"""
    result = assemble_kernel(src, check_deps=False)
    matches = [i for i, (lo, hi) in enumerate(result.encoded)
               if opcode(lo, hi) == 0x942]
    assert len(matches) == 1, matches
    op_idx = matches[0]
    mod = CudaModule(result.code)
    out = mod.devmem_alloc(32)
    mod.device_write(out, bytes(32))
    mod.launch("k", grid=(1,), block=(32,), args=[out])
    mod.synchronize()
    rpc_lo, _pad, base = struct.unpack("<IIQ", mod.device_read(out, 16))
    op_pc = base + (op_idx - 2) * 16
    delta = (rpc_lo - (base & 0xFFFFFFFF)) & 0xFFFFFFFF
    kind = "SENTINEL" if rpc_lo == SENTINEL else f"base+{delta:#x}"
    print(f"{'break':9s}: op_pc={op_pc:#x} rpc.lo={rpc_lo:#010x} {kind}",
          flush=True)


def run(name: str) -> None:
    if name in ("jmp", "call_imm"):
        run_heap_imm(name)
        return
    if name == "break":
        run_break()
        return
    case = CASES[name]
    result = assemble_kernel(source(name), check_deps=False)
    matches = [i for i, (lo, hi) in enumerate(result.encoded)
               if opcode(lo, hi) == case["opcode"]]
    if name == "nop":
        # Header(3) + two RPC seed writes + 16 pre-padding NOPs.
        op_idx = 21
    else:
        assert len(matches) == 1, (name, matches)
        op_idx = matches[0]
    base_idx = 2

    mod = CudaModule(result.code)
    out = mod.devmem_alloc(32)
    mod.device_write(out, bytes(32))
    mod.launch("k", grid=(1,), block=(32,), args=[out])
    mod.synchronize()
    rpc_lo, _pad, base = struct.unpack("<IIQ", mod.device_read(out, 16))
    op_pc = base + (op_idx - base_idx) * 16
    delta = (rpc_lo - (base & 0xFFFFFFFF)) & 0xFFFFFFFF
    kind = "SENTINEL" if rpc_lo == SENTINEL else f"base+{delta:#x}"
    print(f"{name:9s}: op_pc={op_pc:#x} rpc.lo={rpc_lo:#010x} {kind}",
          flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        run(sys.argv[1])
    else:
        for name in CASES:
            result = subprocess.run([sys.executable, __file__, name],
                                    capture_output=True, text=True, timeout=30)
            print(result.stdout, end="")
            if result.returncode:
                print(f"{name}: FAILED rc={result.returncode}")
                print(result.stderr[-1200:], end="")
