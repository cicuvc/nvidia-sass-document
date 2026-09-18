"""SASS assembler (sm70/sm80/sm90/sm100/sm120) — assemble GPU kernels.

Target arch is selected with ``arch=`` (for example "sm90" Hopper,
"sm100" datacenter Blackwell, or "sm120" RTX Blackwell; process default
sm120), or ``set_arch``/``assembler.arch`` for the default.

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

    # Or target Hopper: cubin = assemble(src, arch='sm90')

See also:
    assemble_kernel    — assemble a #fn block → KernelResult
    assemble_flat      — assemble plain instructions → list[(lo,hi)]
    CudaModule         — cubin loader + launcher wrapper
"""

from dataclasses import dataclass
from pathlib import Path
from contextlib import contextmanager
import json
import re

from . import arch as _arch
from .sass_parser import parse_sass, parse_kernel
from .sass_matcher import create_matcher, MatchError
from .sass_encoder import SassEncoder
from .sass_elf import CubinBuilder
from .operand import KernelDecl, ParamDecl
from .runner import CudaModule

# db / matcher / encoder are read-only once built; cache them per arch.
_DBS: dict[str, dict] = {}
_MATCHER_ENCS: dict[str, tuple] = {}


@contextmanager
def _using_arch(name: str | None):
    """Temporarily switch the process arch for the duration of a call."""
    if name is None or name == _arch.current().name:
        yield
        return
    old = _arch.current().name
    _arch.set_arch(name)
    try:
        yield
    finally:
        _arch.set_arch(old)


def _load_db():
    p = str(_arch.db_path())
    if p not in _DBS:
        with open(p) as f:
            _DBS[p] = json.load(f)
    return _DBS[p]


def _make_matcher_encoder():
    key = _arch.current().name
    if key not in _MATCHER_ENCS:
        db = _load_db()
        assert db is not None
        from .sass_matcher import SassMatcher as _Matcher
        _MATCHER_ENCS[key] = (_Matcher(db), SassEncoder(db))
    return _MATCHER_ENCS[key]


def _resolve_labels_and_encode(insts, matcher, encoder, *,
                               check_deps=False, strict_deps=False,
                               kernel_name="", layout_meta=None):
    """Two-pass encode with PC-relative label resolution.

    Pass 1: each real instruction occupies 16 bytes; labels and metadata
    annotations occupy zero bytes.  Build the label→byte-offset map and
    layout-derived EIATTR lists.  Pass 2: replace every LABEL operand with the
    relative byte offset ``target - next_pc`` (branch fields are scaled
    PC-relative, base = the following instruction), then match + encode.
    When ``check_deps`` is set, run the CFG scoreboard dependency checker
    over the matched instructions (warnings to stderr; ``strict_deps``
    promotes them to errors).
    """
    from .operand import OperandKind

    addrs = []
    labels = {}
    int_warp_wide_offsets = []
    coop_group_offsets = []
    coop_group_mask_regids = []
    addr = 0
    for inst in insts:
        if inst.mnemonic == "_label_":
            labels.setdefault(inst.label, addr)
            addrs.append(addr)
        elif inst.mnemonic == "_coop_group_":
            if coop_group_offsets and coop_group_offsets[-1] == addr:
                raise ValueError(
                    f"duplicate #coop_group annotation at offset {addr:#x}")
            coop_group_offsets.append(addr)
            coop_group_mask_regids.append(int(inst.label))
            addrs.append(addr)
        else:
            addrs.append(addr)
            if inst.mnemonic.upper() in ("VOTEU", "REDUX"):
                int_warp_wide_offsets.append(addr)
            addr += 16

    if coop_group_offsets and coop_group_offsets[-1] == addr:
        raise ValueError("#coop_group must be followed by a real instruction")
    if layout_meta is not None:
        layout_meta["int_warp_wide_offsets"] = int_warp_wide_offsets
        layout_meta["coop_group_offsets"] = coop_group_offsets
        layout_meta["coop_group_mask_regids"] = coop_group_mask_regids

    encoded = []
    results = []
    for inst, ia in zip(insts, addrs):
        if inst.mnemonic in ("_label_", "_coop_group_"):
            results.append(None)
            continue
        for op in inst.operands:
            if op.kind == OperandKind.LABEL:
                target = labels.get(op.value)
                if target is None:
                    raise ValueError(f"undefined label {op.value!r}")
                op.kind = OperandKind.IMM_S
                op.value = target - (ia + 16)
        try:
            r = matcher.match(inst)
            lo, hi = encoder.encode(r, inst.sched)
        except Exception as e:
            # annotate with the instruction index, preserving the exception
            # type (tests match on MatchError/EncodeError/...)
            raise type(e)(f"inst {len(encoded)}: {e}") from e
        results.append(r)
        encoded.append((lo, hi))

    if check_deps:
        from .sass_depcheck import run_depcheck
        # Metadata annotations are not CFG nodes.  Labels remain because the
        # dependency checker already understands them, but feeding it a new
        # zero-width pseudo-node would skew its physical-PC target mapping.
        dep_rows = [(inst, result, ia)
                    for inst, result, ia in zip(insts, results, addrs)
                    if inst.mnemonic != "_coop_group_"]
        run_depcheck(matcher.db,
                     [row[0] for row in dep_rows],
                     [row[1] for row in dep_rows],
                     [row[2] for row in dep_rows],
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
             check_deps: bool = True, strict_deps: bool = False,
             arch: str | None = None) -> bytes:
    """Assemble SASS source → cubin bytes.

    Accepts either a ``#fn name(params) {{ ... }}`` kernel declaration or
    standalone SASS instructions (requires ``kernel_name`` for the latter).
    ``check_deps`` (default on) runs the scoreboard dependency checker over
    the kernel; warnings go to stderr.  ``strict_deps`` turns warnings into
    errors.  ``arch`` selects the ISA db / const-bank layout (default: the
    process arch, normally "sm120").
    """
    with _using_arch(arch):
        if re.search(r"(?m)^\s*#fn\b", source):
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
                    strict_deps: bool = False,
                    arch: str | None = None) -> AssembleResult:
    """Assemble a ``#fn name(params) {{ ... }}`` block → AssembleResult."""
    with _using_arch(arch):
        k = parse_kernel(source)
        from .sass_builtins import expand_builtins
        expand_builtins(k)
        matcher, encoder = _make_matcher_encoder()
        cb = CubinBuilder()
        layout_meta = {}
        encoded = _resolve_labels_and_encode(k.instructions, matcher, encoder,
                                             check_deps=check_deps,
                                             strict_deps=strict_deps,
                                             kernel_name=k.name,
                                             layout_meta=layout_meta)
        cb.set_code(encoded, kernel_name=k.name)

        def _attr_values(name):
            value = k.attributes.get(name)
            if value is None:
                return None
            return [int(v, 0) for v in str(value).split(",")]

        # These EIATTR lists are layout properties.  Infer them after labels
        # and zero-width directives have been resolved.  Legacy numeric
        # pragmas remain accepted, but annotations/opcode inference win and a
        # stale manual list is rejected rather than silently emitted.
        inferred_int = layout_meta["int_warp_wide_offsets"]
        manual_int = _attr_values("INT_WARP_WIDE_OFFSETS")
        if manual_int is not None and manual_int != inferred_int:
            raise ValueError(
                "INT_WARP_WIDE_OFFSETS does not match final VOTEU/REDUX "
                f"layout: pragma={manual_int}, inferred={inferred_int}")
        if inferred_int:
            cb.set_pragma("INT_WARP_WIDE_OFFSETS",
                          ",".join(hex(v) for v in inferred_int))

        inferred_coop = layout_meta["coop_group_offsets"]
        inferred_masks = layout_meta["coop_group_mask_regids"]
        manual_coop = _attr_values("COOP_GROUP_INSTR_OFFSETS")
        manual_masks = _attr_values("COOP_GROUP_MASK_REGIDS")
        if inferred_coop:
            if manual_coop is not None and manual_coop != inferred_coop:
                raise ValueError(
                    "COOP_GROUP_INSTR_OFFSETS does not match #coop_group "
                    f"annotations: pragma={manual_coop}, "
                    f"inferred={inferred_coop}")
            if manual_masks is not None and manual_masks != inferred_masks:
                raise ValueError(
                    "COOP_GROUP_MASK_REGIDS does not match #coop_group "
                    f"annotations: pragma={manual_masks}, "
                    f"inferred={inferred_masks}")
            coop_values, mask_values = inferred_coop, inferred_masks
        else:
            coop_values = manual_coop or []
            mask_values = (manual_masks if manual_masks is not None
                           else [0xffffffff] * len(coop_values))
        if len(mask_values) != len(coop_values):
            raise ValueError(
                "COOP_GROUP_MASK_REGIDS count must match "
                "COOP_GROUP_INSTR_OFFSETS count")
        if coop_values:
            cb.set_pragma("COOP_GROUP_INSTR_OFFSETS",
                          ",".join(hex(v) for v in coop_values))
            cb.set_pragma("COOP_GROUP_MASK_REGIDS",
                          ",".join(hex(v) for v in mask_values))
        if k.params:
            cb.set_params([(i, p.ordinal, p.size)
                           for i, p in enumerate(k.params)])
        cb.set_regcount(int(k.attributes.get(
            "REGCOUNT", k.attributes.get("MAXREG_COUNT", 8))))
        if "REGCOUNT" in k.attributes:
            cb.set_pragma("REGCOUNT", str(k.attributes["REGCOUNT"]))
        if "MAXREG_COUNT" in k.attributes:
            # Dynamic register allocation (USETMAXREG / PTX setmaxnreg)
            # requires the per-kernel EIATTR_MAXREG_COUNT to describe the
            # warp's entry allocation.  ptxas writes the same value as the
            # kernel REGCOUNT selected by -maxrregcount.
            cb.set_pragma("MAXREG_COUNT", str(k.attributes["MAXREG_COUNT"]))
        if "SHARED" in k.attributes:
            cb.set_shared_mem(int(k.attributes["SHARED"]))
        if "SHADER_TYPE" in k.attributes:
            cb.set_shader_type(int(k.attributes["SHADER_TYPE"]))
        if "CLUSTER" in k.attributes:
            dims = tuple(int(v, 0) for v in k.attributes["CLUSTER"].split(","))
            cb.set_cluster_dims(dims)
        for attr_name, attr_val in k.attributes.items():
            if (attr_name.startswith("MBARRIER_") or
                    attr_name in ("NUM_MBARRIERS", "TCGEN05_1CTA_USED",
                                  "AT_ENTRY_FRAGMENT_TMEM_CTA1",
                                  "AT_ENTRY_FRAGMENT_TMEM_CTA1_V2",
                                  "REGCOUNT",
                                  )):
                cb.set_pragma(attr_name, str(attr_val))
        return AssembleResult(
            code=cb.build(),
            kernel_name=k.name,
            encoded=encoded,
            params=[(p.ordinal, _arch.current().param_base + p.ordinal, p.size)
                    for p in k.params],
        )


def assemble_flat(source: str, arch: str | None = None) -> list[tuple[int, int]]:
    """Assemble plain SASS (no ``#fn``) → list of ``(lo64, hi64)``."""
    with _using_arch(arch):
        insts = parse_sass(source)
        matcher, encoder = _make_matcher_encoder()
        return _resolve_labels_and_encode(insts, matcher, encoder)
