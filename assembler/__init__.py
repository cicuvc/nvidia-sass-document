"""SM120 SASS assembler — assemble and run GPU kernels from Python.

Quick start:
    from assembler import assemble, CudaModule

    # Assemble a kernel declaration → cubin bytes
    cubin = assemble('''
        #fn fill(data<8>) {
            LDC.64 {R0,R1}, #param(data);
            MOV32I R1, 0x3f800000;
            STG.E desc[{URZ,URZ}][{R0,R1}], R1;
            EXIT;
        }
    ''')

    # Load and launch on GPU
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(256 * 4)
    mod.launch("fill", grid=(1,), block=(256,), args=[d])
    mod.synchronize()

    # Read results
    result = mod.device_read(d, 256 * 4)

See also:
    assemble_kernel    — assemble a #fn block → KernelResult
    assemble_flat      — assemble plain instructions → list[(lo,hi)]
    CudaModule         — cubin loader + launcher wrapper
"""

from dataclasses import dataclass
from pathlib import Path
import json

from .sass_parser import parse_sass, parse_kernel
from .sass_matcher import create_matcher, MatchError
from .sass_encoder import SassEncoder
from .sass_elf import CubinBuilder
from .operand import KernelDecl, ParamDecl
from .runner import CudaModule

_DB_PATH = Path(__file__).resolve().parent.parent / "sm120.json"


def _load_db():
    with open(_DB_PATH) as f:
        return json.load(f)


def _make_matcher_encoder():
    db = _load_db()
    from .sass_matcher import SassMatcher as _Matcher
    return _Matcher(db), SassEncoder(db)


def _resolve_labels_and_encode(insts, matcher, encoder, *,
                               check_deps=False, strict_deps=False,
                               kernel_name=""):
    """Two-pass encode with PC-relative label resolution.

    Pass 1: each non-label instruction occupies 16 bytes; build the
    label→byte-offset map.  Pass 2: replace every LABEL operand with the
    relative byte offset ``target - next_pc`` (branch fields are scaled
    PC-relative, base = the following instruction), then match + encode.
    When ``check_deps`` is set, run the CFG scoreboard dependency checker
    over the matched instructions (warnings to stderr; ``strict_deps``
    promotes them to errors).
    """
    from .operand import OperandKind

    addrs = []
    labels = {}
    addr = 0
    for inst in insts:
        if inst.mnemonic == "_label_":
            labels.setdefault(inst.label, addr)
            addrs.append(addr)
        else:
            addrs.append(addr)
            addr += 16

    encoded = []
    results = []
    for inst, ia in zip(insts, addrs):
        if inst.mnemonic == "_label_":
            results.append(None)
            continue
        for op in inst.operands:
            if op.kind == OperandKind.LABEL:
                target = labels.get(op.value)
                if target is None:
                    raise ValueError(f"undefined label {op.value!r}")
                op.kind = OperandKind.IMM_S
                op.value = target - (ia + 16)
        r = matcher.match(inst)
        results.append(r)
        lo, hi = encoder.encode(r, inst.sched)
        encoded.append((lo, hi))

    if check_deps:
        from .sass_depcheck import run_depcheck
        run_depcheck(matcher.db, insts, results, addrs,
                     kernel_name=kernel_name, strict=strict_deps)
    return encoded


# ---------------------------------------------------------------------------
@dataclass
class AssembleResult:
    """Result of assembling a kernel declaration."""
    code: bytes
    kernel_name: str
    encoded: list[tuple[int, int]]
    params: list[tuple[int, int, int]]


def assemble(source: str, kernel_name: str = "", *,
             check_deps: bool = True, strict_deps: bool = False) -> bytes:
    """Assemble SASS source → cubin bytes.

    Accepts either a ``#fn name(params) {{ ... }}`` kernel declaration or
    standalone SASS instructions (requires ``kernel_name`` for the latter).
    ``check_deps`` (default on) runs the scoreboard dependency checker over
    the kernel; warnings go to stderr.  ``strict_deps`` turns warnings into
    errors.
    """
    if source.lstrip().startswith("#fn"):
        result = assemble_kernel(source, check_deps=check_deps,
                                 strict_deps=strict_deps)
        return result.code
    if not kernel_name:
        raise ValueError("kernel_name required for standalone instructions")
    insts = parse_sass(source)
    matcher, encoder = _make_matcher_encoder()
    cb = CubinBuilder()
    encoded = _resolve_labels_and_encode(insts, matcher, encoder)
    cb.set_code(encoded, kernel_name=kernel_name)
    cb.set_regcount(8)
    return cb.build()


def assemble_kernel(source: str, *, check_deps: bool = True,
                    strict_deps: bool = False) -> AssembleResult:
    """Assemble a ``#fn name(params) {{ ... }}`` block → AssembleResult."""
    k = parse_kernel(source)
    matcher, encoder = _make_matcher_encoder()
    cb = CubinBuilder()
    encoded = _resolve_labels_and_encode(k.instructions, matcher, encoder,
                                         check_deps=check_deps,
                                         strict_deps=strict_deps,
                                         kernel_name=k.name)
    cb.set_code(encoded, kernel_name=k.name)
    if k.params:
        cb.set_params([(i, p.ordinal, p.size)
                       for i, p in enumerate(k.params)])
    cb.set_regcount(int(k.attributes.get("MAXREG_COUNT", 8)))
    if "SHARED" in k.attributes:
        cb.set_shared_mem(int(k.attributes["SHARED"]))
    if "SHADER_TYPE" in k.attributes:
        cb.set_shader_type(int(k.attributes["SHADER_TYPE"]))
    for attr_name, attr_val in k.attributes.items():
        if attr_name.startswith("MBARRIER_") or attr_name == "NUM_MBARRIERS":
            cb.set_pragma(attr_name, str(attr_val))
    return AssembleResult(
        code=cb.build(),
        kernel_name=k.name,
        encoded=encoded,
        params=[(p.ordinal, 0x380 + p.ordinal, p.size) for p in k.params],
    )


def assemble_flat(source: str) -> list[tuple[int, int]]:
    """Assemble plain SASS (no ``#fn``) → list of ``(lo64, hi64)``."""
    insts = parse_sass(source)
    matcher, encoder = _make_matcher_encoder()
    return _resolve_labels_and_encode(insts, matcher, encoder)
