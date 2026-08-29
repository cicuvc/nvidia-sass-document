"""Probe JMP.DIV / JMP.CONV / JMP.U.{ALL,ANY} per lane on SM90/SM120."""
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import CudaModule, assemble, assemble_flat, assemble_kernel


B = "[7:7:{}:5:1]"
BB = "[7:7:{}:8:1]"
PAD16 = "\n".join("    NOP;[7:7:{}:8:1]" for _ in range(16))


CASES = {
    "nop_all":          ("NOP",                    0,          "all"),
    "plain_off":        ("@P0 JMP",                0,          "none"),
    "plain_half":       ("@P0 JMP",               0,          "half"),
    "u_all_half":       ("@P0 JMP.U.ALL",         0,          "half"),
    "u_any_half":       ("@P0 JMP.U.ANY",         0,          "half"),
    "u_all_all":        ("@P0 JMP.U.ALL",         0,          "all"),
    "u_any_all":        ("@P0 JMP.U.ANY",         0,          "all"),
    "u_all_none":       ("@P0 JMP.U.ALL",         0,          "none"),
    "u_any_none":       ("@P0 JMP.U.ANY",         0,          "none"),
    "u_any_up_true":    ("@P0 JMP.U.ANY UP0,",    0,          "half"),
    "u_any_up_false":   ("@P0 JMP.U.ANY UP0,",    0,          "half"),
    "u_any_nup_false":  ("@P0 JMP.U.ANY !UP0,",   0,          "half"),
    "u_all_up_true":    ("@P0 JMP.U.ALL UP0,",    0,          "half"),
    "div_base":         ("JMP.DIV",               0,          "all"),
    "conv_base":        ("JMP.CONV",              0,          "all"),
    "div_fullmask":     ("JMP.DIV UR6,",          0xFFFFFFFF, "all"),
    "conv_fullmask":    ("JMP.CONV UR6,",         0xFFFFFFFF, "all"),
    "div_halfmask":     ("JMP.DIV UR6,",          0x0000FFFF, "all"),
    "conv_halfmask":    ("JMP.CONV UR6,",         0x0000FFFF, "all"),
    "div_invzero":      ("JMP.DIV ~UR6,",         0,          "all"),
    "conv_invzero":     ("JMP.CONV ~UR6,",        0,          "all"),
    "div_pp_half":      ("JMP.DIV P0,",           0,          "half"),
    "conv_pp_half":     ("JMP.CONV P0,",          0,          "half"),
    "div_pp_all":       ("JMP.DIV P0,",           0,          "all"),
    "conv_pp_all":      ("JMP.CONV P0,",          0,          "all"),
    "split_div_base":   ("JMP.DIV",               0,          "half"),
    "split_conv_base":  ("JMP.CONV",              0,          "half"),
    "split_div_full":   ("JMP.DIV UR6,",          0xFFFFFFFF, "half"),
    "split_conv_full":  ("JMP.CONV UR6,",         0xFFFFFFFF, "half"),
    "split_div_half":   ("JMP.DIV UR6,",          0x0000FFFF, "half"),
    "split_conv_half":  ("JMP.CONV UR6,",         0x0000FFFF, "half"),
    "split_div_zero":   ("JMP.DIV UR6,",          0x00000000, "half"),
    "split_conv_zero":  ("JMP.CONV UR6,",         0x00000000, "half"),
    "split_div_quarter":("JMP.DIV UR6,",          0x000000FF, "half"),
    "split_conv_quarter":("JMP.CONV UR6,",        0x000000FF, "half"),
    "split_div_high":   ("JMP.DIV UR6,",          0xFFFF0000, "half"),
    "split_conv_high":  ("JMP.CONV UR6,",         0xFFFF0000, "half"),
    "split_div_invhigh":("JMP.DIV ~UR6,",         0xFFFF0000, "half"),
    "split_conv_invhigh":("JMP.CONV ~UR6,",       0xFFFF0000, "half"),
    "split_u_all":      ("@P0 JMP.U.ALL",         0,          "half"),
    "split_u_any":      ("@P0 JMP.U.ANY",         0,          "half"),
}


def handler_words() -> bytes:
    src = f"""\
    S2R R6, SR_TID.X;[3:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R8,R9}}, R6, 0x4, {{R4,R5}};[7:7:{{1,3}}:13:1]
    MOV32I R2, 0x2222;{B}
    STG.E desc[{{UR4,UR5}}][{{R8,R9}}], R2;[0:1:{{}}:8:0]
    EXIT;{B}
"""
    encoded = assemble_flat(src)
    return b"".join(struct.pack("<QQ", lo, hi) for lo, hi in encoded)


def predicate_setup(mode: str) -> str:
    cmp = {"half": "LT", "all": "GE", "none": "LT"}[mode]
    rhs = {"half": "0x10", "all": "0x0", "none": "0x0"}[mode]
    return f"""    S2R R6, SR_TID.X;[3:7:{{}}:5:1]
    ISETP.{cmp}.U32.AND P0, PT, R6, {rhs}, PT;[7:7:{{3}}:13:1]
"""


def caller_source(name: str, target: int) -> str:
    mnemonic, mask, pred_mode = CASES[name]
    if mnemonic == "NOP":
        jmp = mnemonic
    elif mnemonic.endswith(","):
        jmp = f"{mnemonic} 0x{target:x}"
    else:
        jmp = f"{mnemonic} 0x{target:x}"
    split = name.startswith("split_")
    up_setup = ""
    if name in {"u_any_up_true", "u_all_up_true"}:
        up_setup = f"    UISETP.T UP0, UR6, UR6;{B}\n"
    elif name in {"u_any_up_false", "u_any_nup_false"}:
        up_setup = f"    UISETP.F UP0, UR6, UR6;{B}\n"
    split_before = (f"    @!P0 BRA #label(other);{BB}\n" if split else "")
    split_after = ""
    if split:
        split_after = f"""    #def_label(other)
    S2R R6, SR_TID.X;[3:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R8,R9}}, R6, 0x4, {{R4,R5}};[7:7:{{1,3}}:13:1]
    MOV32I R2, 0x3333;{B}
    STG.E desc[{{UR4,UR5}}][{{R8,R9}}], R2;[0:1:{{0,1}}:8:0]
    EXIT;{B}
"""
    return f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    UMOV UR6, 0x{mask:x};[7:7:{{}}:5:1]
{predicate_setup(pred_mode)}{up_setup}{PAD16}
{split_before}
    {jmp};{BB}
    S2R R6, SR_TID.X;[3:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R8,R9}}, R6, 0x4, {{R4,R5}};[7:7:{{1,3}}:13:1]
    MOV32I R2, 0x1111;{B}
    STG.E desc[{{UR4,UR5}}][{{R8,R9}}], R2;[0:1:{{0,1}}:8:0]
    EXIT;{B}
{split_after}
}}"""


def run(name: str) -> None:
    boot = CudaModule(assemble(f"#fn boot() {{\n    EXIT;{B}\n}}",
                               check_deps=False))
    target = boot.devmem_alloc(4096)
    boot.device_write(target, handler_words())
    result = assemble_kernel(caller_source(name, target), check_deps=False)
    mod = CudaModule(result.code)
    out = mod.devmem_alloc(128)
    mod.device_write(out, bytes(128))
    stream = CudaModule.stream_create()
    mod.launch("k", grid=(1,), block=(32,), args=[out], stream=stream)
    deadline = time.time() + 6
    while not CudaModule.stream_query(stream):
        if time.time() > deadline:
            print(f"{name}: TIMEOUT", flush=True)
            sys.exit(2)
        time.sleep(0.005)
    CudaModule.stream_sync(stream)
    vals = struct.unpack("<32I", mod.device_read(out, 128))
    fall = [i for i, x in enumerate(vals) if x == 0x1111]
    taken = [i for i, x in enumerate(vals) if x == 0x2222]
    alternate = [i for i, x in enumerate(vals) if x == 0x3333]
    other = [(i, hex(x)) for i, x in enumerate(vals)
             if x not in (0x1111, 0x2222, 0x3333)]
    print(f"{name:16s}: fall={fall} taken={taken} alt={alternate} other={other}", flush=True)


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
                print(result.stderr[-1400:], end="")
