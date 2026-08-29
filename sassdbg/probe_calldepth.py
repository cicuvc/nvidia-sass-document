"""Directly observe CALL_DEPTH / RET_DEPTH through CBU_STATE.API_CALL_DEPTH.

Each experiment records three words:

    out[0] = depth before CALL
    out[1] = depth in the callee
    out[2] = depth after RET

The four INC/NOINC x DEC/NODEC combinations run in subprocesses so a
possible API stack fault cannot poison the other experiments' CUDA context.
"""
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import CudaModule, assemble


B = "[7:7:{}:5:1]"
BB = "[7:7:{}:8:1]"
PAD = "\n".join("    IADD3 R30, R30, RZ, RZ;[7:7:{}:5:1]" for _ in range(8))
EDGE_PAD = "\n".join("    NOP;[7:7:{}:8:1]" for _ in range(16))


def source(call_depth: str, ret_depth: str, initial_depth: int = 0) -> str:
    # LEPC is instruction 2; the return point is instruction 16.
    return_offset = (16 - 2) * 16
    seed = ""
    if initial_depth:
        seed = f"""    MOV32I R31, 0x{initial_depth:x};{B}
    BMOV API_CALL_DEPTH, R31;[7:7:{{}}:5:1]
{EDGE_PAD}
"""
    return f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
{seed}    LEPC {{R22,R23}};[7:7:{{}}:4:0]
    BMOV R8, API_CALL_DEPTH;[0:7:{{}}:5:1]
{PAD}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R8;[0:1:{{0,1}}:8:0]
    MOV32I R25, 0x{return_offset:x};{B}
    IMAD.WIDE.U32 {{R20,R21}}, R25, 0x1, {{R22,R23}};[7:7:{{}}:13:1]
    CALL.REL.{call_depth} PT, #label(sub);{BB}
{EDGE_PAD}
    BMOV R9, API_CALL_DEPTH;[0:7:{{}}:5:1]
{PAD}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}+0x8], R9;[0:1:{{0,1}}:8:0]
    EXIT;{B}
#def_label(sub)
{EDGE_PAD}
    BMOV R10, API_CALL_DEPTH;[0:7:{{}}:5:1]
{PAD}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}+0x4], R10;[0:1:{{0,1}}:8:0]
    RET.ABS.{ret_depth} PT, {{R20,R21}}, 0x0;{BB}
}}"""


def seed_source() -> str:
    return f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    MOV32I R8, 0x5;{B}
    BMOV API_CALL_DEPTH, R8;[7:7:{{}}:5:1]
{EDGE_PAD}
    BMOV R9, API_CALL_DEPTH;[0:7:{{}}:5:1]
{PAD}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R9;[0:1:{{0,1}}:8:0]
    EXIT;{B}
}}"""


def run(call_depth: str, ret_depth: str, initial_depth: int = 0) -> None:
    src = source(call_depth, ret_depth, initial_depth)
    mod = CudaModule(assemble(src, check_deps=False))
    out = mod.devmem_alloc(64)
    mod.device_write(out, bytes(64))
    mod.launch("k", grid=(1,), block=(32,), args=[out])
    mod.synchronize()
    before, inside, after = struct.unpack("<3I", mod.device_read(out, 12))
    print(f"seed={initial_depth} {call_depth:5s} + {ret_depth:5s}: "
          f"before={before:#010x} inside={inside:#010x} after={after:#010x}")


def run_seed() -> None:
    mod = CudaModule(assemble(seed_source(), check_deps=False))
    out = mod.devmem_alloc(64)
    mod.device_write(out, bytes(64))
    mod.launch("k", grid=(1,), block=(32,), args=[out])
    mod.synchronize()
    value, = struct.unpack("<I", mod.device_read(out, 4))
    print(f"seed API_CALL_DEPTH=5, read back {value:#010x}")


def deep_source(depth: int, call_depth: str, ret_depth: str) -> str:
    """Build an unrolled nested-call chain with an explicit return pair/level."""
    if not 1 <= depth <= 100:
        raise ValueError("depth must be in [1, 100]")

    def pair(level: int) -> str:
        lo = 32 + 2 * level
        return f"{{R{lo},R{lo + 1}}}"

    def make_call(level: int, target: str) -> list[str]:
        p = pair(level)
        return [
            f"    LEPC {p};[7:7:{{}}:4:0]",
            f"    MOV32I R25, 0x40;{B}",
            f"    IMAD.WIDE.U32 {p}, R25, 0x1, {p};[7:7:{{}}:13:1]",
            f"    CALL.REL.{call_depth} PT, #label({target});{BB}",
        ]

    lines = [
        "#fn k(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]",
        f"    MOV32I R2, 0x0;{B}",
    ]
    lines += make_call(0, "level1")
    lines += [
        "    STG.E desc[{UR4,UR5}][{R4,R5}], R2;[0:1:{0,1}:8:0]",
        f"    EXIT;{B}",
    ]
    for level in range(1, depth):
        lines.append(f"    #def_label(level{level})")
        lines += make_call(level, f"level{level + 1}")
        lines.append(f"    RET.ABS.{ret_depth} PT, {pair(level - 1)}, 0x0;{BB}")
    lines += [
        f"    #def_label(level{depth})",
        f"    MOV32I R2, 0xcafe;{B}",
        f"    RET.ABS.{ret_depth} PT, {pair(depth - 1)}, 0x0;{BB}",
        "}",
    ]
    return "\n".join(lines)


def run_deep(depth: int, call_depth: str, ret_depth: str) -> None:
    mod = CudaModule(assemble(deep_source(depth, call_depth, ret_depth),
                              check_deps=False))
    out = mod.devmem_alloc(64)
    mod.device_write(out, bytes(64))
    mod.launch("k", grid=(1,), block=(32,), args=[out])
    mod.synchronize()
    value, = struct.unpack("<I", mod.device_read(out, 4))
    print(f"depth={depth:3d} {call_depth:5s}+{ret_depth:5s}: out={value:#x}")


def rpc_stack_source(outer_call: str, inner_call: str,
                     inner_ret: str) -> tuple[str, dict[str, int]]:
    """Nested ABS calls; observe whether inner RET restores the outer RPC."""
    ins: list[str] = []
    labels: dict[str, int] = {}

    def emit(line: str) -> None:
        ins.append("    " + line)

    def label(name: str) -> None:
        labels[name] = len(ins)
        ins.append(f"    #def_label({name})")

    emit("LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]")
    emit("LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]")
    base_idx = len(ins)
    emit("LEPC {R22,R23};[7:7:{}:4:0]")
    emit("STG.E desc[{UR4,UR5}][{R4,R5}+0x8], R22;[0:1:{0,1}:8:0]")
    emit(f"MOV32I R25, @OFF(after_outer);{B}")
    emit("IMAD.WIDE.U32 {R20,R21}, R25, 0x1, {R22,R23};[7:7:{}:13:1]")
    emit(f"MOV32I R25, @OFF(sub1);{B}")
    emit("IMAD.WIDE.U32 {R26,R27}, R25, 0x1, {R22,R23};[7:7:{}:13:1]")
    emit(f"CALL.ABS.{outer_call} PT, {{R26,R27}}, 0x0;{BB}")
    label("after_outer")
    emit(f"MOV32I R2, 0xcafe;{B}")
    emit("STG.E desc[{UR4,UR5}][{R4,R5}+0xc], R2;[0:1:{0,1}:8:0]")
    emit(f"EXIT;{B}")

    label("sub1")
    emit("RPCMOV.32 R8, Rpc.LO;[0:7:{}:13:1]")
    emit("STG.E desc[{UR4,UR5}][{R4,R5}], R8;[0:1:{0,1}:8:0]")
    emit(f"MOV32I R25, @OFF(after_inner);{B}")
    emit("IMAD.WIDE.U32 {R16,R17}, R25, 0x1, {R22,R23};[7:7:{}:13:1]")
    emit(f"MOV32I R25, @OFF(sub2);{B}")
    emit("IMAD.WIDE.U32 {R28,R29}, R25, 0x1, {R22,R23};[7:7:{}:13:1]")
    emit(f"CALL.ABS.{inner_call} PT, {{R28,R29}}, 0x0;{BB}")
    label("after_inner")
    for _ in range(16):
        emit("NOP;[7:7:{}:8:1]")
    emit("RPCMOV.32 R10, Rpc.LO;[0:7:{}:13:1]")
    emit("STG.E desc[{UR4,UR5}][{R4,R5}+0x4], R10;[0:1:{0,1}:8:0]")
    emit(f"RET.ABS.NODEC PT, {{R20,R21}}, 0x0;{BB}")

    label("sub2")
    # Do not read RPC here: RPCMOV itself is in RPC_WRITERS and the usual
    # LO/HI telemetry pair can perturb the state we want RET to consume.
    emit(f"RET.ABS.{inner_ret} PT, {{R16,R17}}, 0x0;{BB}")

    # Label directives do not encode instructions, so compute PCs after
    # removing them from the index space.
    encoded_index = 0
    encoded_labels: dict[str, int] = {}
    for line in ins:
        if "#def_label(" in line:
            name = line.split("#def_label(", 1)[1].split(")", 1)[0]
            encoded_labels[name] = encoded_index
        else:
            encoded_index += 1
    base_encoded_idx = 2
    rendered = []
    for line in ins:
        for name, idx in encoded_labels.items():
            line = line.replace(f"@OFF({name})",
                                hex((idx - base_encoded_idx) * 16))
        rendered.append(line)
    return "#fn k(out<8>) {\n" + "\n".join(rendered) + "\n}", encoded_labels


def run_rpc_stack(outer_call: str, inner_call: str, inner_ret: str) -> None:
    src, labels = rpc_stack_source(outer_call, inner_call, inner_ret)
    mod = CudaModule(assemble(src, check_deps=False))
    out = mod.devmem_alloc(64)
    mod.device_write(out, bytes(64))
    mod.launch("k", grid=(1,), block=(32,), args=[out])
    mod.synchronize()
    outer_rpc, after_rpc, base, success = struct.unpack(
        "<4I", mod.device_read(out, 16))
    print(f"RPC outer={outer_call:5s} inner={inner_call:5s}/{inner_ret:5s}: "
          f"outer={(outer_rpc-base)&0xffffffff:#x} "
          f"expect-inner={(labels['after_inner']-1)*16:#x} "
          f"after={(after_rpc-base)&0xffffffff:#x} success={success:#x}")


CASES = {
    "ii_dd": ("INC", "DEC"),
    "ii_nd": ("INC", "NODEC"),
    "ni_dd": ("NOINC", "DEC"),
    "ni_nd": ("NOINC", "NODEC"),
}


if __name__ == "__main__":
    if len(sys.argv) == 2:
        if sys.argv[1] == "seed":
            run_seed()
        elif sys.argv[1].startswith("deep_"):
            _, depth, call_depth, ret_depth = sys.argv[1].split("_")
            run_deep(int(depth), call_depth, ret_depth)
        elif sys.argv[1].startswith("rpc_"):
            _, outer_call, inner_call, inner_ret = sys.argv[1].split("_")
            run_rpc_stack(outer_call, inner_call, inner_ret)
        else:
            name = sys.argv[1]
            seeded = name.startswith("seed_")
            if seeded:
                name = name[5:]
            run(*CASES[name], initial_depth=5 if seeded else 0)
    else:
        deep_cases = tuple(
            f"deep_{depth}_{call_depth}_{ret_depth}"
            for depth in (8, 32, 64, 100)
            for call_depth, ret_depth in (("INC", "DEC"),
                                          ("INC", "NODEC"),
                                          ("NOINC", "NODEC")))
        rpc_cases = tuple(
            f"rpc_{outer_call}_{inner_call}_{inner_ret}"
            for outer_call in ("INC", "NOINC")
            for inner_call in ("INC", "NOINC")
            for inner_ret in ("DEC", "NODEC"))
        for name in (*CASES, *(f"seed_{name}" for name in CASES), "seed",
                     *deep_cases, *rpc_cases):
            result = subprocess.run(
                [sys.executable, __file__, name], capture_output=True,
                text=True, timeout=30)
            print(result.stdout, end="")
            if result.returncode:
                print(f"{name}: FAILED rc={result.returncode}")
                print(result.stderr[-1000:], end="")
