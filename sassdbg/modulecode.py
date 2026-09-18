"""sassdbg.modulecode — M12a module / call-closure host-side model (CPU-only).

Implements the module/function/address model of SASSDBG_WARP_PRIVATE_PLAN.md
section "Module, function, and address model" ahead of the M12b local-call
closure:

  ModuleTemplate     one linked module: TextIslands + CallEdges + ownership
  TextIsland         one linked text/program-base domain (one .text section)
  FunctionTemplate   symbol range + words + relocation records inside an island
  CodeLoc            logical location (module, island, function, instruction)
  CallEdge           decoded direct call: target class + return ABI + policy
  Placement/Stepping policy and Tarjan SCC grouping (recursion is one unit)

The native direct call graph is built from *decoded finalized CALL targets*,
not from `.nv.callgraph`: in the tested CUDA 13.1 cubins that section is a
fixed 32-byte placeholder whose records are identical across modules with
different call structures, so it cannot serve as a cross-check.

M12 facts the model carries forward (probe_retrel.py):

1. **RET.REL program base.**  ptxas encodes `RET.REL.NODEC Rxx` with a
   displacement chosen so ``pc_link + 0x10 + sImm*4 == 0``.  Hardware
   evaluates the same expression at the runtime PC, so the term equals the
   image's placement delta (its program base) and the return target is
   ``Rxx + program_base``.
2. **Return-token materialization.**  The caller materializes the linked
   offset of its continuation in a GPR pair with an immediate MOV (`MOV
   R20, 0xf0` before a `CALL.REL.NOINC` at 0xe0); the high half must be
   provably zero (ptxas zeroes it in the caller or callee before the
   matching RET).  Both sides must move together when relocating.
3. **Island-qualified identities.**  Text sections commonly share
   ``sh_addr == 0``, so a raw VA cannot identify a function across islands;
   every function gets a stable ``fid`` and resolution is island-first.

No GPU or device state is touched here; everything is constructible and
unit-testable without CUDA (tests/asm_construct/test_modulecode.py).
"""
from __future__ import annotations

import dataclasses
import json
import re
import struct
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .cubin import (_sections, callgraph_records, capsule_relocations,
                    native_funcs, native_relocations, text_sections)
from .warpcode import _field_value, _opcode_of, _OPCODE_INDEX, WarpCodeError

_REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# classification enums (plan "Ownership and stepping policy")
# ---------------------------------------------------------------------------
class Placement(Enum):
    PRIVATE_EAGER = 0      # selected kernel: always copied
    PRIVATE_LAZY = 1       # eligible user function, materialized on demand
    SHARED_OPAQUE = 2      # undefined / driver range / explicit exclude
    INDIRECT_UNKNOWN = 3   # runtime target unknown; continue-only or reject


class Stepping(Enum):
    STEP_INTO = 0
    STEP_OVER = 1


class ReturnABI(Enum):
    REL_REG = 0            # CALL.REL.NOINC + RET.REL.NODEC Rxx (register token)
    ABS_REG = 1            # absolute register return (LEPC/CALL.ABS + RET.ABS)
    UNKNOWN = 2


class TargetClass(Enum):
    INTERNAL_DIRECT = 0    # in-module function, statically known
    EXTERNAL_RUNTIME = 1   # loader-resolved / out-of-module
    INDIRECT_UNKNOWN = 2   # register/uniform target, unresolved


class FunctionState(Enum):
    UNMATERIALIZED = 0
    MATERIALIZING = 1
    PRIVATE = 2
    OPAQUE = 3


# ---------------------------------------------------------------------------
# register spec (GPR vs uniform)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RegSpec:
    """An explicit GPR/uniform-register identity (bit 91 selects the file)."""
    kind: str            # "R" or "UR"
    index: int

    def __str__(self) -> str:
        return f"{self.kind}{self.index}"


# ---------------------------------------------------------------------------
# logical location
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CodeLoc:
    module: str
    island: str
    function: str | None = None
    instruction: int = 0
    fid: str | None = None          # island-qualified function identity

    def __str__(self) -> str:
        fn = self.function or "<section>"
        return f"{self.module}:{self.island}:{fn}[{self.instruction}]"


# ---------------------------------------------------------------------------
# function / island templates
# ---------------------------------------------------------------------------
@dataclass
class FunctionTemplate:
    fid: str                       # island-qualified stable id
    name: str
    island_name: str
    offset: int                    # byte offset within the island text
    size: int
    index_base: int                # island-relative instruction index
    n_insts: int
    sym_index: int = 0             # native symbol table index
    relocations: tuple = ()
    return_reg: RegSpec | None = None
    return_abi: ReturnABI = ReturnABI.UNKNOWN
    return_rel_base: int | None = None
    words: tuple = ()              # island word slice, set by the builder

    @property
    def end_offset(self) -> int:
        return self.offset + self.size

    def exclusive_range(self, island) -> tuple[int, int]:
        """[lo, hi) byte range of instructions OWNED by this function, i.e.
        excluding nested function symbols that overlap its range."""
        lo = self.offset
        hi = self.end_offset
        for fn in island.functions:
            if fn is self:
                continue
            if fn.offset > self.offset and fn.end_offset <= hi:
                hi = min(hi, fn.offset)
        return lo, hi


@dataclass
class TextIsland:
    """One linked text/program-base domain: a native `.text[.<func>]` section.

    Copying the whole island preserves every original section-relative offset,
    so linked CALL/RET conventions stay valid (the M12b correctness oracle).
    """
    index: int                     # ordinal within the module
    name: str
    link_base: int                 # sh_addr: link-time VA of instruction 0
    size: int
    words: tuple = ()
    functions: list[FunctionTemplate] = field(default_factory=list)
    native_relocs: tuple = ()

    @property
    def n_insts(self) -> int:
        return len(self.words)

    def word_at(self, idx: int) -> tuple[int, int]:
        return self.words[idx]

    def link_va(self, idx: int) -> int:
        """Link-time VA of island-relative instruction `idx`."""
        return self.link_base + idx * 16

    def function_at(self, off: int) -> FunctionTemplate | None:
        """Innermost (narrowest) function whose range contains `off`.

        A kernel FUNC symbol often spans the whole section and would mask the
        nested `$kernel$fn` sub-functions; the smallest range wins.
        """
        best = None
        for fn in self.functions:
            if fn.offset <= off < fn.end_offset:
                if best is None or fn.size < best.size:
                    best = fn
        return best

    def function_named(self, name: str) -> FunctionTemplate | None:
        for fn in self.functions:
            if fn.name == name:
                return fn
        return None

    def function_by_fid(self, fid: str) -> FunctionTemplate | None:
        for fn in self.functions:
            if fn.fid == fid:
                return fn
        return None


# ---------------------------------------------------------------------------
# call edge
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CallEdge:
    src: CodeLoc
    target_class: TargetClass
    abi: ReturnABI = ReturnABI.UNKNOWN
    dst: CodeLoc | None = None
    return_reg: RegSpec | None = None
    return_token: tuple[RegSpec, int] | None = None   # (pair base, linked token)
    placement: Placement = Placement.PRIVATE_LAZY
    stepping: Stepping = Stepping.STEP_OVER
    reason: str = ""

    @property
    def callee_name(self) -> str | None:
        return self.dst.function if self.dst else None

    @property
    def callee_fid(self) -> str | None:
        return self.dst.fid if self.dst else None


# ---------------------------------------------------------------------------
# Tarjan SCC over the direct call graph
# ---------------------------------------------------------------------------
def sccs(edges, nodes=()) -> list[set[str]]:
    """Strongly connected components over the complete function node set.

    `nodes` supplies the full set of function identities; `edges` is an
    iterable of (caller, callee) pairs or CallEdge objects.  Every node
    (including isolated functions with no edges) belongs to exactly one
    component.  Recursion / mutual recursion collapse into one SCC unit.
    """
    graph: dict[str, set[str]] = {}
    for node in nodes:
        graph.setdefault(node, set())
    for e in edges:
        if isinstance(e, CallEdge):
            a = e.src.fid or e.src.function
            b = e.dst.fid if e.dst else None
        else:
            a, b = e
        if a is None:
            continue
        graph.setdefault(a, set())
        if b is not None:
            graph.setdefault(b, set())
            graph[a].add(b)
    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    onstack: set[str] = set()
    comps: list[set[str]] = []

    def strongconnect(v: str) -> None:
        nonlocal index
        indices[v] = low[v] = index
        index += 1
        stack.append(v)
        onstack.add(v)
        for w in graph.get(v, ()):
            if w not in indices:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif w in onstack:
                low[v] = min(low[v], indices[w])
        if low[v] == indices[v]:
            comp = set()
            while True:
                w = stack.pop()
                onstack.discard(w)
                comp.add(w)
                if w == v:
                    break
            comps.append(comp)

    for node in graph:
        if node not in indices:
            strongconnect(node)
    return comps


def recursive_scc(comp: set[str], edges) -> bool:
    """True when an SCC is recursive: more than one node (mutual recursion)
    or a single node with a direct self-call."""
    if len(comp) > 1:
        return True
    for e in edges:
        if isinstance(e, CallEdge):
            a = e.src.fid or e.src.function
            b = e.dst.fid if e.dst else None
        else:
            a, b = e
        if a in comp and b == a:
            return True
    return False


# ---------------------------------------------------------------------------
# ownership policy (plan "Ownership and stepping policy")
# ---------------------------------------------------------------------------
class OwnershipPolicy:
    """Name/scope-based placement and stepping decisions.

    Symbol names are hints, not ownership proof (DEVICE_PRINT.md: undefined
    `vprintf` resolves to `syscall_trampoline_vprintf`).  The policy combines
    the static target class with explicit include/exclude regexes and the
    just-my-code toggle; the runtime module address-range check is a later,
    separate stage.

    `just_my_code=True` (default) is a filter: only root + include-matched
    internal functions become private/steppable; non-included internal
    functions are SHARED_OPAQUE and stepped over.  `just_my_code=False`
    disables that filter (all internal functions are PRIVATE_LAZY /
    STEP_INTO) while loader-resolved EXTERNAL_RUNTIME targets stay opaque —
    they cannot be materialized per-warp in M12.
    """

    def __init__(self, *, just_my_code: bool = True,
                 include: str | None = None, exclude: str | None = None,
                 root_functions: frozenset[str] = frozenset()):
        self.just_my_code = just_my_code
        self.root_functions = frozenset(root_functions)
        self._include = re.compile(include) if include else None
        self._exclude = re.compile(exclude) if exclude else None

    def included(self, name: str) -> bool:
        if self._exclude and self._exclude.search(name):
            return False
        if self._include:
            return bool(self._include.search(name))
        return True

    def classify(self, name: str, target_class: TargetClass,
                 *, in_module: bool = True) -> Placement:
        if not in_module:
            if target_class is TargetClass.INDIRECT_UNKNOWN:
                return Placement.INDIRECT_UNKNOWN
            return Placement.SHARED_OPAQUE
        if name in self.root_functions:
            return Placement.PRIVATE_EAGER
        if target_class is TargetClass.INDIRECT_UNKNOWN:
            return Placement.INDIRECT_UNKNOWN
        if target_class is TargetClass.EXTERNAL_RUNTIME:
            return Placement.SHARED_OPAQUE
        if self.just_my_code and not self.included(name):
            return Placement.SHARED_OPAQUE
        return Placement.PRIVATE_LAZY

    def stepping_for(self, placement: Placement) -> Stepping:
        if placement in (Placement.PRIVATE_EAGER, Placement.PRIVATE_LAZY):
            return Stepping.STEP_INTO
        return Stepping.STEP_OVER


# ---------------------------------------------------------------------------
# ISA decode tables (per-opcode layouts from the assembler DB)
# ---------------------------------------------------------------------------
def _db_variants() -> list[dict]:
    sys.path.insert(0, str(_REPO))
    from assembler import arch
    with open(arch.db_path()) as f:
        return json.load(f)["variants"]


_DB: list[dict] | None = None


def _db() -> list[dict]:
    global _DB
    if _DB is None:
        _DB = _db_variants()
    return _DB


def _enc_for(mnemonic: str, opcode: int) -> list[dict]:
    """Encoding (field targets) of the first variant matching
    `mnemonic`/`opcode`; fail closed if absent."""
    for v in _db():
        if v["mnemonic"] == mnemonic and (v["opcode"] & 0x1FFF) == opcode:
            return v["encoding"]
    raise WarpCodeError(f"no {mnemonic} variant for opcode {opcode:#x}")


def _mnemonics(opcode: int) -> frozenset[str]:
    return _OPCODE_INDEX.mnemonics(opcode)


def _predicated(lo: int, hi: int) -> bool:
    """True unless the guard predicate is unconditional @PT."""
    return ((lo >> 12) & 0x7) != 7 or ((lo >> 15) & 1) != 0


# -- CALL -------------------------------------------------------------
# opcode -> (family, kind, target-field, register file for reg forms)
_CALL_KINDS = {
    0x943: ("ABS", "imm", "Sb", None),
    0xb43: ("ABS", "const", None, None),
    0x343: ("ABS", "reg", "sImm", "R"),
    0x1943: ("ABS", "ureg", "sImm", "UR"),
    0x944: ("REL", "imm", "sImm", None),
    0x344: ("REL", "reg", "sImm", "R"),
    0x1944: ("REL", "ureg", "sImm", "UR"),
}


@dataclass(frozen=True)
class CallDecode:
    family: str                    # ABS | REL
    kind: str                      # imm | const | reg | ureg
    target_class: TargetClass
    target: int | None = None      # link VA for immediate forms
    reg: RegSpec | None = None     # register target for reg/ureg forms
    reason: str = ""


def decode_call(lo: int, hi: int, *, link_base: int, inst_off: int) \
        -> CallDecode | None:
    """Decode a CALL word using the opcode-specific layout.  Returns None
    when the word is not a CALL."""
    opcode = _opcode_of(lo, hi)
    info = _CALL_KINDS.get(opcode)
    if info is None:
        return None
    family, kind, tfield, regfile = info
    enc = _enc_for("CALL", opcode)
    if kind == "const":
        return CallDecode(family, kind, TargetClass.EXTERNAL_RUNTIME,
                          reason="const-bank (loader-resolved)")
    if kind in ("reg", "ureg"):
        ra = _extract_field(enc, "Ra", lo, hi)
        rs = RegSpec(regfile, ra)
        return CallDecode(family, kind, TargetClass.INDIRECT_UNKNOWN,
                          reg=rs, reason=f"{family} {regfile} target")
    if family == "REL":
        s = _extract_field(enc, "sImm", lo, hi, signed=True)
        target = link_base + inst_off + 0x10 + s * 4
        return CallDecode(family, kind, TargetClass.INTERNAL_DIRECT, target,
                          reason=f"CALL.REL sImm={s:#x}")
    s = _extract_field(enc, "Sb", lo, hi)
    return CallDecode(family, kind, TargetClass.INTERNAL_DIRECT, s * 4,
                      reason=f"CALL.ABS imm={s * 4:#x}")


def _extract_field(enc: list[dict], name: str, lo: int, hi: int, *,
                   signed: bool = False) -> int:
    return _field_value(enc, name, lo, hi, signed=signed)


@dataclass(frozen=True)
class RetDecode:
    abi: ReturnABI
    reg: RegSpec | None
    rel_base: int | None = None    # pc_link+0x10+sImm*4 for REL_REG
    depth: int | None = None
    reason: str = ""


def decode_return(lo: int, hi: int, *, link_base: int, inst_off: int) \
        -> RetDecode | None:
    """Decode a RET word using the opcode-specific layout (GPR vs UR)."""
    opcode = _opcode_of(lo, hi)
    if opcode not in (0x950, 0x1950):
        return None
    regfile = "UR" if opcode == 0x1950 else "R"
    enc = _enc_for("RET", opcode)
    addr_bit = _extract_field(enc, "ignoreKill", lo, hi)
    ra = _extract_field(enc, "Ra", lo, hi)
    s = _extract_field(enc, "sImm", lo, hi, signed=True)
    depth = _extract_field(enc, "depth", lo, hi)
    reg = None if ra == 0xFF else RegSpec(regfile, ra)
    if addr_bit:
        return RetDecode(ReturnABI.ABS_REG, reg, depth=depth)
    return RetDecode(ReturnABI.REL_REG, reg,
                     link_base + inst_off + 0x10 + s * 4, depth)


# -- register-writing instruction sets (for token/clobber analysis) ----
_CTRL_MNEMONICS = frozenset({
    "BRA", "BSSY", "BSYNC", "BSYNCU", "JMP", "JMPU", "JMX", "JMXU",
    "BRX", "BRXU", "CALL", "CALLU", "RET", "RETU", "EXIT", "KILL",
    "WARPSYNC", "BAR", "SYNC", "BREAK", "LONGJMP",
    "GRIDDEPCONTROL", "PREEXIT",
})
_STORE_MNEMONICS = frozenset({
    "STG", "STS", "STL", "ST", "STAG", "STAS", "RED", "REDX", "REDS",
    "REDUX", "ATOMS", "STB", "STU",
})


def _writer_opcodes() -> frozenset[int]:
    """Opcodes that WRITE a GPR via the Rd field at [23:16], excluding
    stores/atomics whose `Rd` slot is a data source rather than a dest."""
    rd_ops = set()
    by_op: dict[int, set[str]] = {}
    for v in _db():
        op = v["opcode"] & 0x1FFF
        by_op.setdefault(op, set()).add(v["mnemonic"])
        if any(e["name"] == "Rd" for e in (v.get("encoding") or [])):
            rd_ops.add(op)
    return frozenset(op for op in rd_ops
                     if not (by_op[op] & _STORE_MNEMONICS))


_WRITERS: frozenset[int] | None = None


def _writers() -> frozenset[int]:
    global _WRITERS
    if _WRITERS is None:
        _WRITERS = _writer_opcodes()
    return _WRITERS


def _is_ctrl_barrier(lo: int, hi: int) -> bool:
    return bool(_mnemonics(_opcode_of(lo, hi)) & _CTRL_MNEMONICS)


def _writer_reg(lo: int, hi: int) -> int | None:
    """GPR written via Rd [23:16] for a GPR-writing instruction, else None."""
    op = _opcode_of(lo, hi)
    if op not in _writers():
        return None
    return (lo >> 16) & 0xFF


def _mov_imm(lo: int, hi: int) -> tuple[int, int] | None:
    """(rd, imm32) for MOV32I / MOV-imm (32-bit token materialization)."""
    op = _opcode_of(lo, hi)
    mnems = _mnemonics(op)
    if "MOV32I" in mnems:
        enc = _enc_for("MOV32I", op)
        rd = _extract_field(enc, "Rd", lo, hi)
        imm = _extract_field(enc, "Ra_offset", lo, hi) & 0xFFFFFFFF
        return rd, imm
    if "MOV" in mnems and (op & 0x1FFF) == 0x402:
        enc = _enc_for("MOV", op)
        rd = _extract_field(enc, "Rd", lo, hi)
        imm = _extract_field(enc, "Sb", lo, hi)
        return rd, imm & 0xFFFFFFFF
    return None


def _is_zero_op(lo: int, hi: int, rd: int) -> bool:
    """True when the word writes register `rd` to a provably-zero value."""
    op = _opcode_of(lo, hi)
    mnems = _mnemonics(op)
    mov = _mov_imm(lo, hi)
    if mov is not None and mov[0] == rd and mov[1] == 0:
        return True
    # MOV Rd, RZ
    if "MOV" in mnems and (op & 0x1FFF) == 0x202:
        enc = _enc_for("MOV", op)
        d = _extract_field(enc, "Rd", lo, hi)
        b = _extract_field(enc, "Rb", lo, hi)
        if d == rd and b == 0xFF:
            return True
    # HFMA2 Rd, -RZ, RZ, 0, 0 — the ptxas zero idiom (empirically == 0x0)
    if (op & 0x1FFF) == 0x431:
        enc = _enc_for("HFMA2", op)
        d = _extract_field(enc, "Rd", lo, hi)
        a = _extract_field(enc, "Ra", lo, hi)
        c = (lo >> 32) & 0xFFFFFFFF            # Sb, Sc immediates
        if d == rd and a == 0xFF and c == 0:
            return True
    return False


# ---------------------------------------------------------------------------
# ModuleTemplate
# ---------------------------------------------------------------------------
class ModuleTemplate:
    """Immutable host-side model of one linked cubin module.

    Built from native symbols/relocations; retained Mercury capsule records
    are held at module scope (`capsule_relocs`) and never projected onto
    native text or a specific island.
    """

    def __init__(self, name: str, islands: list[TextIsland],
                 edges: list[CallEdge], *, path: str = "",
                 callgraph: tuple = (), capsule_relocs: tuple = ()):
        self.name = name
        self.path = path
        self.islands = islands
        self.edges = edges
        self.callgraph = callgraph                 # raw .nv.callgraph records
        self.capsule_relocs = capsule_relocs
        self._by_fid: dict[str, FunctionTemplate] = {}
        self._by_name: dict[str, list[FunctionTemplate]] = {}
        for island in islands:
            for fn in island.functions:
                self._by_fid[fn.fid] = fn
                self._by_name.setdefault(fn.name, []).append(fn)

    # -- lookups -----------------------------------------------------------
    def function(self, name: str) -> FunctionTemplate | None:
        """Unique name lookup; None when duplicate local symbols collide."""
        hits = self._by_name.get(name, [])
        return hits[0] if len(hits) == 1 else None

    def function_by_fid(self, fid: str) -> FunctionTemplate | None:
        return self._by_fid.get(fid)

    def functions(self) -> list[FunctionTemplate]:
        out = []
        for island in self.islands:
            out.extend(island.functions)
        return out

    def island(self, name: str) -> TextIsland | None:
        for i in self.islands:
            if i.name == name:
                return i
        return None

    # -- call graph --------------------------------------------------------
    def outgoing(self, function: str) -> list[CallEdge]:
        return [e for e in self.edges if (e.src.function == function
                                          or e.src.fid == function)]

    def scc(self) -> list[set[str]]:
        """Every function (including isolated ones) is in exactly one SCC."""
        fids = [f.fid for f in self.functions()]
        return sccs(self.edges, fids)

    # -- builder -----------------------------------------------------------
    @classmethod
    def from_cubin(cls, path: str, *, policy: OwnershipPolicy | None = None,
                   root: str | None = None) -> "ModuleTemplate":
        data = Path(path).read_bytes()
        secs = _sections(data)
        funcs = native_funcs(data, secs)
        text_secs = text_sections(data, secs)
        capsule = tuple(capsule_relocations(data, secs))
        native = tuple(native_relocations(data, secs))

        islands: list[TextIsland] = []
        for i, sec in enumerate(text_secs):
            body = data[sec.off: sec.off + sec.size]
            assert len(body) % 16 == 0
            words = tuple(struct.unpack_from("<QQ", body, k)
                          for k in range(0, len(body), 16))
            island = TextIsland(
                i, sec.name, sec.addr, sec.size, words,
                native_relocs=tuple(r for r in native
                                    if r.target_section == sec.index))
            for sym in funcs:
                if sym.shndx != sec.index:
                    continue
                island.functions.append(_build_function(sym, island))
            island.functions.sort(key=lambda f: f.offset)
            _fix_zero_size_extents(island)
            islands.append(island)

        name = Path(path).name
        edges = _decode_edges(name, islands, policy=policy, root=root)
        return cls(name, islands, edges, path=path,
                   callgraph=tuple(callgraph_records(data, secs)),
                   capsule_relocs=capsule)


def _fix_zero_size_extents(island: TextIsland) -> None:
    """A zero-sized FUNC symbol must not consume the rest of the section:
    infer its end from the next compatible symbol at a higher offset."""
    fns = island.functions
    for fn in fns:
        if fn.size:
            continue
        end = island.size
        for other in fns:
            if other.offset > fn.offset and other.end_offset <= end:
                end = min(end, other.offset)
        object.__setattr__(fn, "size", end - fn.offset)
        object.__setattr__(fn, "n_insts", (end - fn.offset) // 16)


def _build_function(sym, island: TextIsland) -> FunctionTemplate:
    start = sym.value
    size = sym.size
    if start > island.size or start + size > island.size:
        raise WarpCodeError(
            f"symbol {sym.name!r} range [{start:#x}, {start + size:#x}) "
            f"outside island {island.name} ({island.size:#x})")
    relocs = tuple(r for r in island.native_relocs
                   if start <= r.offset < start + (size or island.size))
    fid = f"{island.name}:{start:#x}"
    fn = FunctionTemplate(fid, sym.name, island.name, start, size,
                          start // 16, size // 16, relocations=relocs)
    _analyze_return_abi(fn, island)
    fn.words = island.words[fn.index_base: fn.index_base + fn.n_insts]
    return fn


def _analyze_return_abi(fn: FunctionTemplate, island: TextIsland) -> None:
    """Collect the RETs owned by the function's exclusive range.

    The kernel FUNC symbol often spans the whole section and would absorb
    nested `$kernel$fn` RETs; only instructions not owned by a nested
    function count.  Conflicting protocols across multiple returns resolve
    to UNKNOWN; a container with no owned RET stays UNKNOWN."""
    lo, hi = fn.exclusive_range(island)
    seen: set[tuple] = set()
    reg = None
    abi = ReturnABI.UNKNOWN
    base_term = None
    for k in range(lo // 16, hi // 16):
        w = island.words[k]
        ret = decode_return(w[0], w[1], link_base=island.link_base,
                            inst_off=k * 16)
        if ret is None:
            continue
        seen.add((ret.abi, ret.reg))
        reg, abi, base_term = ret.reg, ret.abi, ret.rel_base
    if len(seen) == 1:
        fn.return_reg = reg
        fn.return_abi = abi
        fn.return_rel_base = base_term


# ---------------------------------------------------------------------------
# edge decoding
# ---------------------------------------------------------------------------
def _loc_at(module: str, island: TextIsland, inst_idx: int) -> CodeLoc:
    fn = island.function_at(inst_idx * 16)
    return CodeLoc(module, island.name, fn.name if fn else None,
                   inst_idx, fn.fid if fn else None)


def _decode_edges(module: str, islands: list[TextIsland],
                  *, policy: OwnershipPolicy | None,
                  root: str | None) -> list[CallEdge]:
    policy = policy or OwnershipPolicy(root_functions=(
        frozenset({root}) if root else frozenset()))
    edges: list[CallEdge] = []
    for island in islands:
        for idx, (lo, hi) in enumerate(island.words):
            cd = decode_call(lo, hi, link_base=island.link_base,
                             inst_off=idx * 16)
            if cd is None:
                continue
            src = _loc_at(module, island, idx)
            edge = _finalize_edge(policy, module, islands, island, idx,
                                  src, cd)
            edges.append(edge)
    return edges


def _finalize_edge(policy: OwnershipPolicy, module: str,
                   islands: list[TextIsland], island: TextIsland,
                   idx: int, src: CodeLoc, cd: CallDecode) -> CallEdge:
    """Resolve the call target against the module and finalize the target
    class, destination, return ABI, token, placement, and stepping."""
    dst = None
    callee_fn = None
    tclass = cd.target_class
    if cd.target is not None:
        tclass, dst, callee_fn = _resolve_target(islands, island, cd, module)
    abi = callee_fn.return_abi if callee_fn is not None else ReturnABI.UNKNOWN
    ret_reg = callee_fn.return_reg if callee_fn is not None else None
    if dst is not None and dst.fid is not None:
        place = policy.classify(dst.function or "", tclass)
    else:
        place = policy.classify("", tclass, in_module=False)
    edge = CallEdge(src, tclass, abi, dst, ret_reg,
                    placement=place,
                    stepping=policy.stepping_for(place),
                    reason=cd.reason)
    if ret_reg is not None and callee_fn is not None:
        edge = _attach_return_token(edge, islands, island, src, idx,
                                    callee_fn)
    return edge


def _resolve_target(islands: list[TextIsland], source_island: TextIsland,
                    cd: CallDecode, module: str):
    """Resolve an immediate CALL target island-first.

    CALL.REL is PC-relative: resolve in the source island first.  A target
    outside the source island is only accepted when the VA falls in exactly
    one other island with a distinct range; otherwise it is finalized as an
    out-of-module/ambiguous target (never left INTERNAL_DIRECT).
    """
    tgt = cd.target
    fn = source_island.function_at(tgt - source_island.link_base)
    if fn is not None:
        inst_idx = (tgt - source_island.link_base) // 16
        return (TargetClass.INTERNAL_DIRECT,
                CodeLoc(module, source_island.name, fn.name, inst_idx,
                        fn.fid), fn)
    hits = [isl for isl in islands
            if isl is not source_island
            and isl.link_base <= tgt < isl.link_base + isl.size]
    if len(hits) == 1:
        isl = hits[0]
        fn = isl.function_at(tgt - isl.link_base)
        inst_idx = (tgt - isl.link_base) // 16
        if fn is not None:
            return (TargetClass.INTERNAL_DIRECT,
                    CodeLoc(module, isl.name, fn.name, inst_idx, fn.fid), fn)
        return (TargetClass.INTERNAL_DIRECT,
                CodeLoc(module, isl.name, None, inst_idx, None), None)
    return (TargetClass.EXTERNAL_RUNTIME, None, None)


def _attach_return_token(edge: CallEdge, islands: list[TextIsland],
                         island: TextIsland, src: CodeLoc,
                         call_idx: int,
                         callee_fn: FunctionTemplate) -> CallEdge:
    """Prove the caller's return-token materialization for BOTH halves of the
    pair, or fail closed with an unknown token.

    - low half: a single unconditional MOV32I/MOV-imm reaching the call site
      (backward scan bounded by the caller's own instructions, stopping at
      any control-flow barrier / intervening write of the same register);
    - high half: provably zeroed either in the caller before the call or in
      the callee before its RET.
    """
    ret_reg = edge.return_reg
    if ret_reg is None or ret_reg.kind != "R":
        return edge
    fn = island.function_by_fid(src.fid) if src.fid else None
    if fn is None:
        return edge
    lo_idx = fn.exclusive_range(island)[0] // 16
    defd = _scan_back_def(island.words, call_idx, lo_idx, ret_reg.index)
    if defd is None:
        return edge
    j, w = defd
    mov = _mov_imm(*w)
    if mov is None or mov[0] != ret_reg.index or _predicated(*w):
        return edge
    high = ret_reg.index + 1
    high_def = _scan_back_def(island.words, call_idx, lo_idx, high)
    high_ok = high_def is not None and _is_zero_op(*high_def[1], high)
    if not high_ok:
        high_ok = _callee_zeroes_high(islands, callee_fn, high)
    if not high_ok:
        return edge
    return dataclasses.replace(edge, return_token=(ret_reg, mov[1]))


def _callee_zeroes_high(islands: list[TextIsland],
                        callee_fn: FunctionTemplate, high: int) -> bool:
    """The callee zeroes `high` between its entry and its first owned RET."""
    isl = _island_named(islands, callee_fn.island_name)
    if isl is None:
        return False
    ret_idx = _first_owned_ret(isl, callee_fn)
    if ret_idx is None:
        return False
    lo = callee_fn.offset // 16
    for k in range(lo, ret_idx):
        w = isl.words[k]
        if _is_ctrl_barrier(*w):
            return False
        rd = _writer_reg(*w)
        if rd == high:
            return _is_zero_op(*w, high)
    return False


def _first_owned_ret(island: TextIsland,
                     fn: FunctionTemplate) -> int | None:
    lo, hi = fn.exclusive_range(island)
    for k in range(lo // 16, hi // 16):
        ret = decode_return(*island.words[k], link_base=island.link_base,
                            inst_off=k * 16)
        if ret is not None:
            return k
    return None


def _island_named(islands: list[TextIsland], name: str) -> TextIsland | None:
    for isl in islands:
        if isl.name == name:
            return isl
    return None


def _scan_back_def(words, start: int, stop: int, reg: int):
    """Nearest definition of `reg` walking backward from start-1 to stop.

    Stops (returns None) at a control-flow barrier because the linear path
    is then not the only path.  Skips instructions that do not write a GPR;
    returns the first writer whose destination matches `reg`."""
    for j in range(start - 1, stop - 1, -1):
        w = words[j]
        if _is_ctrl_barrier(*w):
            return None
        rd = _writer_reg(*w)
        if rd == reg:
            return (j, w)
    return None