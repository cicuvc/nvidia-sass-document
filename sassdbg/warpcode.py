"""sassdbg.warpcode — M11b warp-private code model (CPU-only).

Implements the host-side object model of SASSDBG_WARP_PRIVATE_PLAN.md
sections 4-7 ahead of the device bootstrap (M11c):

  CodeTemplate      one immutable template per target function
                    (words, replay plans, copyability classification)
  CodeInstance      per-global-warp executable state (base, stride,
                    WarpState, code_epoch, applied breakpoints)
  Breakpoint        logical site + per-warp Binding (armed, stop_mask,
                    patch word, epoch) with explicit-scope arm/disarm
  AddressMap        site_va(warp, orig_index) / orig_index(warp, va)
                    with alignment+bounds validation (hit decoding)
  Layout            explicit arena regions for (max_bps, max_warps,
                    code_size); 16B alignment everywhere, 0x100-aligned
                    warp code strides and thunk arenas; memory report
                    and configurable budget refusal
  CodeImageAnalyzer POSITION_INDEPENDENT / REWRITE / UNSUPPORTED
                    classification with fail-closed diagnostics

No GPU, driver, or device state is touched here: everything is
constructible and unit-testable without CUDA.  M11c will drive these
objects from the dispatcher bootstrap; M11d applies OverlayBatches to
device memory.

Analyzer decode notes (field targets are little-endian-concatenated in
ascending bit order, SCALE 4 divides the byte value by 4):
  BRA  sImm [81:34]||[23:16], signed: target = bra_pc + 16 + sImm*4
  BSSY Sa   [63:34],          signed: target = bssy_pc + 16 + sa*4
  JMP  imm  [80:34]||[23:16], unsigned absolute: target = imm*4
All three verified against assemble_flat round-trips in the unit tests.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------
class WarpCodeError(Exception):
    """Base class for warp-private code model errors."""


class CodeImageError(WarpCodeError):
    """A text image failed copyability preflight (fail-closed)."""


class CodeMapError(WarpCodeError):
    """An address did not decode to an in-function instruction."""


class ScopeError(WarpCodeError):
    """A breakpoint operation used an illegal warp scope."""


class LayoutError(WarpCodeError):
    """Arena geometry or budget violation."""


# ---------------------------------------------------------------------------
# warp states (plan section 4.2)
# ---------------------------------------------------------------------------
class WarpState(Enum):
    UNLAUNCHED = 0
    GATED = 1
    RUNNING = 2
    PARKED_COOPERATIVE = 3
    FREEZING = 4
    FROZEN = 5
    RESUMING = 6
    DONE = 7


# States in which host code writes to the warp's private text are legal
# (plan invariant 4) and an omitted breakpoint scope may be defaulted.
SAFE_BOUNDARY = frozenset({
    WarpState.UNLAUNCHED, WarpState.GATED, WarpState.PARKED_COOPERATIVE,
    WarpState.FROZEN, WarpState.DONE,
})


# ---------------------------------------------------------------------------
# copyability classification (plan section 7)
# ---------------------------------------------------------------------------
class Outcome(Enum):
    POSITION_INDEPENDENT = 0     # copy verbatim
    REWRITE = 1                  # internal absolute target: encode the
                                 # warp-private VA at overlay time
    UNSUPPORTED = 2              # reject before launch


@dataclass(frozen=True)
class Classification:
    index: int
    outcome: Outcome
    reason: str = ""
    rewrite_index: int | None = None   # in-function target instruction

    def fail(self) -> bool:
        return self.outcome is Outcome.UNSUPPORTED


# Mnemonics whose semantics depend on an absolute code address the
# private copy cannot reproduce unchanged.  Fail-closed: an opcode that
# decodes to *any* of these is rejected.
PC_SENSITIVE = frozenset({
    "JMP",      # absolute immediate/register jump
    "JMX",      # absolute computed jump
    "BRX",      # register-relative branch (kernel-relative Ra)
    "CALL",     # absolute/relative call, stack semantics
    "RET",      # absolute return target
    "LEPC",     # fetches own VA (LEPC of the private copy differs)
    "RPCMOV",   # RPC read/write (code-address construction)
    "CCTL",     # cache control carries address forms (self-modify
                # adjacent); v1 rejects fail-closed
})

_REL_FORMS = {"BRA", "BSSY"}     # PC-relative, bounds-checkable


def _opcode_of(lo: int, hi: int) -> int:
    """13-bit opcode: bit[91] << 12 | bits[11:0]."""
    return (((hi >> 27) & 1) << 12) | (lo & 0xFFF)


def _field_value(encoding: list[dict], name: str,
                 lo: int, hi: int, signed: bool) -> int:
    """Concatenate one encoding field's bit targets (ascending bit
    order) out of a 128-bit instruction word.  A target that spans the
    64-bit lo/hi boundary ([81:34]-style) continues from lo's high
    bits into hi's low bits (verified against assemble_flat round-
    trips for BRA/JMP/RET immediates).  SCALE is applied by the caller
    (the analyzer always decodes *4)."""
    rec = next((e for e in encoding if e["name"] == name), None)
    if rec is None:
        raise WarpCodeError(f"field {name!r} not in encoding")
    v = 0
    shift = 0
    for hi_bit, lo_bit in sorted(rec["targets"]):
        width = hi_bit - lo_bit + 1
        if hi_bit < 64:
            part = (lo >> lo_bit) & ((1 << width) - 1)
        elif lo_bit >= 64:
            part = (hi >> (lo_bit - 64)) & ((1 << width) - 1)
        else:                        # crosses the lo/hi boundary
            lo_w = 64 - lo_bit
            hi_w = width - lo_w
            part = ((lo >> lo_bit) & ((1 << lo_w) - 1)) | \
                ((hi & ((1 << hi_w) - 1)) << lo_w)
        v |= part << shift
        shift += width
    if signed and (v >> (rec["width"] - 1)) & 1:
        v -= 1 << rec["width"]
    return v


class _OpcodeIndex:
    """Lazy opcode -> frozenset(mnemonics) from the assembler's ISA DB."""

    def __init__(self):
        self._map: dict[int, frozenset[str]] | None = None

    def _build(self) -> dict[int, frozenset[str]]:
        import sys
        sys.path.insert(0, str(_REPO))
        from assembler import arch
        with open(arch.db_path()) as f:
            db = json.load(f)
        out: dict[int, set[str]] = {}
        for v in db["variants"]:
            out.setdefault(v["opcode"], set()).add(v["mnemonic"])
        return {op: frozenset(ms) for op, ms in out.items()}

    def mnemonics(self, opcode: int) -> frozenset[str]:
        if self._map is None:
            self._map = self._build()
        return self._map.get(opcode, frozenset())

    def encoding(self, mnemonic: str) -> list[dict] | None:
        if self._map is None:
            self._map = self._build()
        if not hasattr(self, "_enc"):
            import sys
            sys.path.insert(0, str(_REPO))
            from assembler import arch
            with open(arch.db_path()) as f:
                db = json.load(f)
            self._enc = {v["mnemonic"]: v["encoding"]
                         for v in db["variants"]}
        return self._enc.get(mnemonic)


_OPCODE_INDEX = _OpcodeIndex()


class CodeImageAnalyzer:
    """Classifies every instruction of a function image for copying.

    v1 (plan section 7): relocation-free, single-function kernels whose
    internal *relative* control flow (BRA/BSSY) stays in-function.
    Everything else fails closed with an instruction index and reason.
    """

    def __init__(self, opcode_index: _OpcodeIndex | None = None):
        self.idx = opcode_index or _OPCODE_INDEX

    def analyze(self, words, *, link_base: int | None = None,
                reloc_offsets: tuple[int, ...] = ()) \
            -> tuple[Classification, ...]:
        """`link_base` is the function's link-time VA (cubin sh_addr +
        entry offset); None means absolute-target rewrite is impossible
        (source-dialect images).  `reloc_offsets` are r_offsets relative
        to the .text section; the caller passes entry-relative ones."""
        size = len(words) * 16
        reloc_insts = {off // 16 for off in reloc_offsets
                       if 0 <= off < size}
        out: list[Classification] = []
        for i, (lo, hi) in enumerate(words):
            out.append(self._classify_one(i, lo, hi, size, link_base,
                                          i in reloc_insts))
        return tuple(out)

    def _classify_one(self, i, lo, hi, size, link_base, has_reloc):
        if has_reloc:
            return Classification(i, Outcome.UNSUPPORTED,
                                  "relocation writes the copied text")
        mnems = self.idx.mnemonics(_opcode_of(lo, hi))
        if not mnems:
            return Classification(i, Outcome.UNSUPPORTED,
                                  f"unknown opcode {_opcode_of(lo, hi):#05x}")
        pc = i * 16
        if not (mnems & PC_SENSITIVE) and not (mnems & _REL_FORMS):
            return Classification(i, Outcome.POSITION_INDEPENDENT)
        # A relative form shared with a PC-sensitive mnemonic (none
        # known today) still fails closed:
        if mnems & PC_SENSITIVE:
            # JMP with a decodable in-function absolute target is the
            # one REWRITE case; every other PC-sensitive hit rejects.
            if "JMP" in mnems:
                rw = self._jmp_rewrite(i, lo, hi, size, link_base)
                if rw is not None:
                    return rw
            return Classification(
                i, Outcome.UNSUPPORTED,
                "PC-sensitive " + "/".join(sorted(mnems & PC_SENSITIVE)))
        # pure relative form: bounds-check the target
        if "BRA" in mnems:
            enc = self.idx.encoding("BRA")
            off = _field_value(enc, "sImm", lo, hi, signed=True) * 4
            tgt = pc + 16 + off
        else:                                   # BSSY
            enc = self.idx.encoding("BSSY")
            off = _field_value(enc, "Sa", lo, hi, signed=True) * 4
            tgt = pc + 16 + off
        if 0 <= tgt < size:
            return Classification(i, Outcome.POSITION_INDEPENDENT)
        return Classification(
            i, Outcome.UNSUPPORTED,
            f"{'BRA' if 'BRA' in mnems else 'BSSY'} target leaves the "
            f"function ({tgt:#x} outside [0, {size:#x}))")

    def _jmp_rewrite(self, i, lo, hi, size, link_base):
        if link_base is None:
            return None
        enc = self.idx.encoding("JMP")
        if enc is None:
            return None
        try:                       # slot name per the ISA DB: "Sa"
            va = _field_value(enc, "Sb", lo, hi, signed=False) * 4
        except WarpCodeError:
            return None           # fail closed on schema drift
        if link_base <= va < link_base + size:
            return Classification(
                i, Outcome.REWRITE,
                f"internal absolute JMP {va:#x}",
                rewrite_index=(va - link_base) // 16)
        return None

    def validate(self, words, **kw) -> tuple[Classification, ...]:
        """analyze() + raise CodeImageError listing every failure."""
        cls = self.analyze(words, **kw)
        fails = [c for c in cls if c.fail()]
        if fails:
            detail = "; ".join(
                f"[{c.index}] {c.reason}" for c in fails[:8])
            more = "" if len(fails) <= 8 else f" (+{len(fails) - 8} more)"
            raise CodeImageError(f"image rejected: {detail}{more}")
        return cls


# ---------------------------------------------------------------------------
# replay plans (M8c rules, template-relative)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReplayPlan:
    """How the displaced instruction at orig_index re-executes inside a
    per-warp thunk.  `lines` may contain a `{tgt}` placeholder expanded
    with the warp-private absolute target VA."""
    orig_index: int
    kind: str                    # verbatim | bra_abs | label_local
    lines: tuple[str, ...] = ()
    target_index: int | None = None

    def expand(self, code_base: int) -> tuple[str, ...]:
        if self.kind != "bra_abs" or self.target_index is None:
            return self.lines
        tgt = code_base + self.target_index * 16
        # plain replace: the lines carry literal scoreboard braces and
        # must not go through str.format
        return tuple(ln.replace("{tgt}", f"0x{tgt:x}")
                      for ln in self.lines)

    def key(self, template_id: int) -> tuple:
        """Stable thunk-cache key: the same logical site in the same
        template with the same plan shape shares one thunk VA."""
        return (template_id, self.orig_index, self.kind, self.target_index)


def _replay_plans_from_cfg(cfg) -> tuple[ReplayPlan, ...]:
    """One ReplayPlan per instruction, M8c rules: plain instructions
    replay verbatim; label BRA becomes absolute JMP(s) to the warp-
    private target (predication preserved, fall-through appended by the
    thunk builder); BSSY's Sa is architecturally inert so it replays
    with a thunk-local label."""
    plans = []
    for ci in cfg.insts:
        if ci.mnemonic == "BRA" and ci.label is not None:
            tgt_idx = cfg.target(ci.label)
            guard = ci.text.split()[0] if ci.predicated else ""
            line = f"{guard} JMP {{tgt}};[7:7:{{}}:6:0]".strip()
            plans.append(ReplayPlan(ci.idx, "bra_abs", (line,), tgt_idx))
        elif ci.mnemonic == "BSSY":
            ln = ci.text
            import re
            ln = re.sub(r"#label\([^)]*\)", "#label(tk)", ln)
            plans.append(ReplayPlan(ci.idx, "label_local", (ln,)))
        else:
            plans.append(ReplayPlan(ci.idx, "verbatim", (ci.text,)))
    return tuple(plans)


# ---------------------------------------------------------------------------
# CodeTemplate / CodeInstance / Breakpoint
# ---------------------------------------------------------------------------
_TEMPLATE_IDS = itertools.count(1)


@dataclass(frozen=True)
class CodeTemplate:
    """Immutable per-function image (plan section 4.1)."""
    name: str
    words: tuple[tuple[int, int], ...]
    template_id: int
    classifications: tuple[Classification, ...]
    replay_plans: tuple[ReplayPlan, ...]
    source_lines: tuple[str, ...] | None = None

    @property
    def n_insts(self) -> int:
        return len(self.words)

    @property
    def size(self) -> int:
        return len(self.words) * 16

    @classmethod
    def from_source(cls, source: str, name: str = "k",
                    analyzer: CodeImageAnalyzer | None = None) \
            -> "CodeTemplate":
        """Assemble a dialect #fn kernel into a validated template.
        (assemble_flat takes PLAIN SASS and silently encodes ZERO words
        for a #fn-wrapped source — the M7 gotcha — so the encoding goes
        through assemble_kernel, which also runs the dep checker.)"""
        import sys
        sys.path.insert(0, str(_REPO))
        from assembler import assemble_kernel
        from sassdbg.stepper import Cfg
        cfg = Cfg(source)
        words = tuple(assemble_kernel(source).encoded)
        cls_ = analyzer or CodeImageAnalyzer()
        classifications = cls_.validate(words)
        plans = _replay_plans_from_cfg(cfg)
        assert len(plans) == len(words)
        return cls(name, words, next(_TEMPLATE_IDS), classifications,
                   plans, tuple(source.splitlines()))

    @classmethod
    def from_cubin(cls, path: str, func: str | None = None,
                   analyzer: CodeImageAnalyzer | None = None) \
            -> "CodeTemplate":
        """Load a kernel's .text from a cubin and validate it."""
        from sassdbg.cubin import load_kernel
        kt = load_kernel(path, func)
        cls_ = analyzer or CodeImageAnalyzer()
        classifications = cls_.validate(
            kt.words, link_base=kt.link_addr,
            reloc_offsets=tuple(r - kt.entry_off for r in kt.relocs
                                if r >= kt.entry_off))
        # cubin images have no dialect source: verbatim replay only.
        plans = tuple(ReplayPlan(i, "verbatim")
                      for i in range(len(kt.words)))
        return cls(kt.func, tuple(kt.words), next(_TEMPLATE_IDS),
                   classifications, plans)


class AddressMap:
    """Explicit per-warp address mapping (plan section 4.4)."""

    def __init__(self, template: CodeTemplate):
        self.template = template
        self._bases: list[int | None] = []

    def set_base(self, warp: int, base: int | None) -> None:
        while len(self._bases) <= warp:
            self._bases.append(None)
        if base is not None and base % 16:
            raise CodeMapError(f"code base {base:#x} not 16B aligned")
        self._bases[warp] = base

    def code_base(self, warp: int) -> int:
        try:
            b = self._bases[warp]
        except IndexError:
            b = None
        if b is None:
            raise CodeMapError(f"warp {warp} has no placed code base")
        return b

    def site_va(self, warp: int, orig_index: int) -> int:
        if not 0 <= orig_index < self.template.n_insts:
            raise CodeMapError(
                f"instruction index {orig_index} out of range "
                f"[0, {self.template.n_insts})")
        return self.code_base(warp) + orig_index * 16

    def orig_index(self, warp: int, va: int) -> int:
        """Hit decoding: validate alignment and bounds BEFORE any
        breakpoint lookup."""
        delta = va - self.code_base(warp)
        if delta % 16:
            raise CodeMapError(f"hit VA {va:#x} is not 16B aligned")
        idx = delta // 16
        if not 0 <= idx < self.template.n_insts:
            raise CodeMapError(
                f"hit VA {va:#x} outside the private copy "
                f"[0, {self.template.size:#x})")
        return idx


@dataclass
class Binding:
    armed: bool = False
    stop_mask: int = 0xFFFFFFFF
    patch_word: tuple[int, int] | None = None
    epoch: int = 0


class Breakpoint:
    """Logical breakpoint with per-warp bindings (plan section 4.3)."""

    _next_id = itertools.count(1)

    def __init__(self, orig_index: int, canonical_word: tuple[int, int],
                 stub_slot: int):
        self.id = next(Breakpoint._next_id)
        self.orig_index = orig_index
        self.canonical_word = canonical_word
        self.stub_slot = stub_slot
        self.bindings: dict[int, Binding] = {}

    def binding(self, warp: int) -> Binding:
        b = self.bindings.get(warp)
        if b is None:
            b = Binding()
            self.bindings[warp] = b
        return b


@dataclass
class OverlayBatch:
    """One code-mutation transaction: device words first, commit
    generations last (plan invariant 6)."""
    writes: list[tuple[int, int, tuple[int, int]]] = field(default_factory=list)
    epochs: list[tuple[int, int]] = field(default_factory=list)


class CodeInstance:
    """Per-global-warp executable state (plan section 4.2)."""

    def __init__(self, warp: int, template: CodeTemplate,
                 amap: AddressMap, stride: int):
        self.warp = warp
        self.template = template
        self.amap = amap
        self.stride = stride
        self.state = WarpState.UNLAUNCHED
        self.code_epoch = 0
        self.applied: dict[int, int] = {}       # orig_index -> bp id
        self.applied_words: dict[int, tuple[int, int]] = {}
        self.dirty = False
        self.parked_groups: list[tuple[int, int]] = []   # (mask, index)
        amap.set_base(warp, None)

    def place(self, base: int) -> None:
        """Assign the executable device VA (M11c launch path)."""
        self.amap.set_base(self.warp, base)

    @property
    def base(self) -> int:
        return self.amap.code_base(self.warp)

    def word_at(self, idx: int) -> tuple[int, int]:
        """The word the device copy currently holds at idx."""
        return self.applied_words.get(idx, self.template.words[idx])

    def image(self) -> list[tuple[int, int]]:
        img = list(self.template.words)
        for idx, w in self.applied_words.items():
            img[idx] = w
        return img


class PrivateCodeSet:
    """Owns one template's per-warp instances and its breakpoints;
    enforces the scope rules of plan section 4.3."""

    def __init__(self, template: CodeTemplate, max_warps: int,
                 max_bps: int = 16,
                 patch_word_fn=None):
        self.template = template
        self.max_warps = max_warps
        self.max_bps = max_bps
        self.amap = AddressMap(template)
        self.instances = [
            CodeInstance(w, template, self.amap, 0x100)
            for w in range(max_warps)]
        self.breakpoints: list[Breakpoint] = []
        self.by_index: dict[int, Breakpoint] = {}
        # patch_word_fn(stub_slot) -> 128-bit patch word; the default
        # builds an absolute JMP (heap stub) via the assembler.
        self._patch_word_fn = patch_word_fn or self._default_patch_word

    @staticmethod
    def _default_patch_word(stub_slot: int, stub_base: int = 0) \
            -> tuple[int, int]:
        import sys
        sys.path.insert(0, str(_REPO))
        from assembler import assemble_flat
        va = stub_base + stub_slot * 0x200
        return assemble_flat(f"JMP 0x{va:x};[7:7:{{}}:6:0]")[0]

    # -- scope helpers ----------------------------------------------------
    def _resolve_warps(self, warps) -> list[int]:
        if warps is None:
            if not all(i.state in SAFE_BOUNDARY
                       for i in self.instances):
                raise ScopeError(
                    "omitted scope: some warps are past the entry gate; "
                    "pass explicit warps=")
            return list(range(self.max_warps))
        if isinstance(warps, int):
            warps = [warps]
        out = []
        for w in warps:
            if not 0 <= w < self.max_warps:
                raise ScopeError(f"warp {w} out of range")
            out.append(w)
        return out

    def _check_write_legal(self, warps: list[int]) -> None:
        for w in warps:
            st = self.instances[w].state
            if st not in SAFE_BOUNDARY:
                raise ScopeError(
                    f"warp {w} is {st.name}: host code writes are legal "
                    "only at a safe boundary (GATED/FROZEN/PARKED/DONE)")

    # -- public breakpoint API -------------------------------------------
    def arm(self, index: int, warps=None, lane_masks=None) -> Breakpoint:
        """Arm `index` on `warps` (all pre-gate warps when omitted).
        `lane_masks` is a mask int or {warp: mask}; the default
        0xffffffff stops every execution group of the warp."""
        if not 0 <= index < self.template.n_insts:
            raise WarpCodeError(f"instruction index {index} out of range")
        if index in self.by_index:
            raise WarpCodeError(
                f"index {index} already armed (bp "
                f"{self.by_index[index].id})")
        if len(self.breakpoints) >= self.max_bps:
            raise WarpCodeError(f"max_bps={self.max_bps} exhausted")
        ws = self._resolve_warps(warps)
        self._check_write_legal(ws)
        if isinstance(lane_masks, int) or lane_masks is None:
            masks = {w: lane_masks if lane_masks is not None
                     else 0xFFFFFFFF for w in ws}
        else:
            masks = dict(lane_masks)
        bp = Breakpoint(index, self.template.words[index],
                        len(self.breakpoints))
        self.by_index[index] = bp
        self.breakpoints.append(bp)
        for w in ws:
            b = bp.binding(w)
            b.armed = True
            b.stop_mask = masks.get(w, 0xFFFFFFFF)
            b.patch_word = self._patch_word_fn(bp.stub_slot) \
                if b.stop_mask else None
        return bp

    def disarm(self, bp: Breakpoint, warps=None) -> None:
        ws = self._resolve_warps(warps)
        self._check_write_legal(ws)
        for w in ws:
            if w in bp.bindings:
                bp.bindings[w].armed = False
        if not any(b.armed for b in bp.bindings.values()):
            self.breakpoints.remove(bp)
            del self.by_index[bp.orig_index]

    def set_break_mask(self, bp: Breakpoint, warp: int, mask: int) -> None:
        if not 0 <= warp < self.max_warps:
            raise ScopeError(f"warp {warp} out of range")
        self._check_write_legal([warp])
        b = bp.binding(warp)
        b.armed = True
        b.stop_mask = mask & 0xFFFFFFFF
        b.patch_word = self._patch_word_fn(bp.stub_slot) \
            if b.stop_mask else None

    # -- overlay machinery (plan section 9) ------------------------------
    def compute_overlay(self, warps=None) -> OverlayBatch:
        """Diff the desired image (canonical + armed bindings) against
        each instance's APPLIED device image.  Only changed words are
        published; a warp's code_epoch bumps once per batch, after all
        its words (plan invariants 6/10)."""
        ws = self._resolve_warps(warps) if warps is not None \
            else list(range(self.max_warps))
        batch = OverlayBatch()
        for w in ws:
            inst = self.instances[w]
            desired: dict[int, tuple[int, int]] = {}
            for idx, bp in self.by_index.items():
                b = bp.bindings.get(w)
                if b is not None and b.armed and b.stop_mask \
                        and b.patch_word is not None:
                    desired[idx] = b.patch_word
            for idx, word in sorted(desired.items()):
                if inst.word_at(idx) == word:
                    continue
                batch.writes.append((w, idx, word))
            for idx in sorted(set(inst.applied) - set(desired)):
                batch.writes.append(
                    (w, idx, self.template.words[idx]))
            if any(wa == w for wa, _, _ in batch.writes):
                inst.code_epoch += 1
                inst.dirty = True
                batch.epochs.append((w, inst.code_epoch))
        return batch

    def commit(self, batch: OverlayBatch) -> None:
        """Host-side state transition after the device writes landed."""
        for w, idx, word in batch.writes:
            inst = self.instances[w]
            bp = self.by_index.get(idx)
            b = bp.bindings.get(w) if bp else None
            if b is not None and b.armed and b.patch_word == word:
                inst.applied[idx] = bp.id
                inst.applied_words[idx] = word
            else:
                inst.applied.pop(idx, None)
                inst.applied_words.pop(idx, None)
        for w, epoch in batch.epochs:
            self.instances[w].code_epoch = epoch


# ---------------------------------------------------------------------------
# Layout (plan section 5)
# ---------------------------------------------------------------------------
def _align(x: int, a: int) -> int:
    return (x + a - 1) & ~(a - 1)


class Layout:
    """Explicit arena regions for (max_bps, max_warps, code_size).

    Region order follows plan section 5.  Every region start is 16B
    aligned; warp code strides and the per-warp thunk arenas are
    0x100-aligned so host writes for adjacent warps never share an
    instruction-fetch line.  Construction reports memory use and
    refuses to exceed a configurable budget.
    """

    CTRL_SZ = 0x100             # module base, gate, launch dims
    PARK_MODE_SZ = 0x10         # requested/observed mode generations
    FREEZE_STRIDE = 0x100       # cache-line-separated ack/go per warp
    STUB_SZ = 0x200
    HANDLER_STRIDE = 0x1000
    THUNK_ARENA = 0x10000       # per-warp thunk arena (0x100 multiple)
    CMDBUF_SZ = 0x400
    RESULTS_SZ = 0x400
    DISPATCHER_SZ = 0x400
    FRAME = 0x80

    def __init__(self, max_bps: int, max_warps: int, code_size: int, *,
                 budget: int | None = None,
                 thunk_arena: int = THUNK_ARENA):
        if max_bps < 0 or max_warps < 1 or code_size < 16:
            raise LayoutError("need max_bps>=0, max_warps>=1, "
                              f"code_size>=16 (got {max_bps}, "
                              f"{max_warps}, {code_size})")
        if thunk_arena % 0x100:
            raise LayoutError("thunk arena must be 0x100-aligned")
        self.max_bps = max_bps
        self.max_warps = max_warps
        self.thunk_arena = thunk_arena
        # executable code stride: 0x100-aligned, covers the template
        self.code_stride = max(0x100, _align(code_size, 0x100))

        off = _align(self.CTRL_SZ, 16)
        self.ctrl = 0
        self.code_base_table = off; off = _align(off + max_warps * 8, 16)
        self.code_epoch = off;       off = _align(off + max_warps * 4, 16)
        self.park_mode = off;        off = _align(
            off + max_warps * self.PARK_MODE_SZ, 16)
        self.freeze_ctl = off;       off = _align(
            off + max_warps * self.FREEZE_STRIDE, 0x100)
        self.bp_masks = off;         off = _align(
            off + max_warps * max_bps * 4, 16)
        self.stubs = off;            off = _align(
            off + max_bps * self.STUB_SZ, 0x100)
        self.handlers = off;         off = _align(
            off + max_warps * self.HANDLER_STRIDE, 0x100)
        self.thunks = off;           off = _align(
            off + max_warps * thunk_arena, 0x100)
        self.hslots = off;           off = _align(
            off + max_warps * 32 * 16, 16)
        self.cmdseq = off;           off = _align(off + max_warps * 16, 16)
        self.cmdbuf = off;           off = _align(
            off + max_warps * self.CMDBUF_SZ, 16)
        self.results = off;          off = _align(
            off + max_warps * self.RESULTS_SZ, 16)
        self.frames = off;           off = _align(
            off + max_warps * 32 * self.FRAME, 16)
        self.dispatcher = off;       off = _align(
            off + self.DISPATCHER_SZ, 0x100)
        self.code = off
        self.total = off + max_warps * self.code_stride
        if budget is not None and self.total > budget:
            raise LayoutError(
                f"arena {self.total:#x} exceeds budget {budget:#x} "
                f"({max_warps} warps x code_stride {self.code_stride:#x})")

    # -- accessors --------------------------------------------------------
    def code_va(self, arena: int, warp: int) -> int:
        if not 0 <= warp < self.max_warps:
            raise LayoutError(f"warp {warp} out of range")
        return arena + self.code + warp * self.code_stride

    def handler_va(self, arena: int, warp: int) -> int:
        return arena + self.handlers + warp * self.HANDLER_STRIDE

    def thunk_va(self, arena: int, warp: int) -> int:
        return arena + self.thunks + warp * self.thunk_arena

    def stub_va(self, arena: int, slot: int) -> int:
        if not 0 <= slot < self.max_bps:
            raise LayoutError(f"stub slot {slot} out of range")
        return arena + self.stubs + slot * self.STUB_SZ

    def region_sizes(self) -> dict[str, int]:
        """Byte size of every region (for the memory report)."""
        m = {
            "ctrl": self.CTRL_SZ,
            "code_base_table": self.max_warps * 8,
            "code_epoch": self.max_warps * 4,
            "park_mode": self.max_warps * self.PARK_MODE_SZ,
            "freeze_ctl": self.max_warps * self.FREEZE_STRIDE,
            "bp_masks": self.max_warps * self.max_bps * 4,
            "stubs": self.max_bps * self.STUB_SZ,
            "handlers": self.max_warps * self.HANDLER_STRIDE,
            "thunks": self.max_warps * self.thunk_arena,
            "hslots": self.max_warps * 32 * 16,
            "cmdseq": self.max_warps * 16,
            "cmdbuf": self.max_warps * self.CMDBUF_SZ,
            "results": self.max_warps * self.RESULTS_SZ,
            "frames": self.max_warps * 32 * self.FRAME,
            "dispatcher": self.DISPATCHER_SZ,
            "code": self.max_warps * self.code_stride,
        }
        return m

    def report(self) -> str:
        m = self.region_sizes()
        lines = [f"arena total {self.total:#x} "
                 f"({self.max_warps} warps, code_stride "
                 f"{self.code_stride:#x})"]
        for k in m:
            lines.append(f"  {k:<16} {m[k]:#010x} @ {getattr(self, k):#010x}")
        return "\n".join(lines)
