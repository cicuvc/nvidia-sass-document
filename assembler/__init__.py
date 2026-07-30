"""SM120 SASS assembler — assemble and run GPU kernels from Python.

Quick start:
    from assembler import assemble, CudaModule

    # Assemble a kernel declaration → cubin bytes
    cubin = assemble('''
        #fn fill(data<8>) {
            LDC.64 R0, #param(data);
            MOV32I R1, 0x3f800000;
            STG.E desc[URZ][R0.64], R1;
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


# ---------------------------------------------------------------------------
@dataclass
class AssembleResult:
    """Result of assembling a kernel declaration."""
    code: bytes
    kernel_name: str
    encoded: list[tuple[int, int]]
    params: list[tuple[int, int, int]]


def assemble(source: str, kernel_name: str = "") -> bytes:
    """Assemble SASS source → cubin bytes.

    Accepts either a ``#fn name(params) {{ ... }}`` kernel declaration or
    standalone SASS instructions (requires ``kernel_name`` for the latter).
    """
    if source.lstrip().startswith("#fn"):
        result = assemble_kernel(source)
        return result.code
    if not kernel_name:
        raise ValueError("kernel_name required for standalone instructions")
    insts = parse_sass(source)
    matcher, encoder = _make_matcher_encoder()
    cb = CubinBuilder()
    encoded = []
    for inst in insts:
        if inst.mnemonic == "_label_":
            continue
        r = matcher.match(inst)
        lo, hi = encoder.encode(r, inst.sched)
        encoded.append((lo, hi))
    cb.set_code(encoded, kernel_name=kernel_name)
    cb.set_regcount(8)
    return cb.build()


def assemble_kernel(source: str) -> AssembleResult:
    """Assemble a ``#fn name(params) {{ ... }}`` block → AssembleResult."""
    k = parse_kernel(source)
    matcher, encoder = _make_matcher_encoder()
    cb = CubinBuilder()
    encoded = []
    for inst in k.instructions:
        r = matcher.match(inst)
        lo, hi = encoder.encode(r, inst.sched)
        encoded.append((lo, hi))
    cb.set_code(encoded, kernel_name=k.name)
    if k.params:
        cb.set_params([(i, p.ordinal, p.size)
                       for i, p in enumerate(k.params)])
    cb.set_regcount(int(k.attributes.get("MAXREG_COUNT", 8)))
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
    return [(encoder.encode(matcher.match(inst), inst.sched))
            for inst in insts if inst.mnemonic != "_label_"]
