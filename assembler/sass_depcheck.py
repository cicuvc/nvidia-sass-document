"""Scoreboard/dependency checking for hand-built SASS.

Implements AUTO_DEP_ANALYSIS.md §8 (V2, CFG): a product of two lattices —
an identity lattice of outstanding scoreboard claims (gen/kill reaching-
definitions) and a per-SB count upper-bound lattice (for DEPBAR.LE partial
drains).  Runs after matching, before encoding, on every kernel assembly.

Diagnostics (all warning-level by default; strict turns them into errors):
    missing_req        consumer reads a variable-latency result without a
                       covering `req` on the producer's SB
    anti_dep           writer clobbers a register a late reader (store /
                       gather) still needs, without waiting its `rd` SB
    missing_wr_sb      variable-latency result is not given a `wr` SB yet is
                       consumed
    divergent_retarget SB re-targeted while a *predicated* claim on it is
                       still outstanding (ITS warp-split hazard)
    sb_capacity        per-SB in-flight upper bound exceeds the 6-bit tally
                       cap without an intervening drain
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Optional

from .sass_cond import ConditionEvaluator

# --------------------------------------------------------------------------
# Latency classes (from INST_TYPE_* in the instruction DB)
# --------------------------------------------------------------------------
COUPLED = 0            # COUPLED_MATH / COUPLED_EMULATABLE — no SB protocol
RD_SCBD = 1            # DECOUPLED_RD_SCBD / MIO_RD_SCBD — late-read `rd`
RD_WR_SCBD = 2         # DECOUPLED_RD_WR_SCBD / MIO_RD_WR_SCBD
BRU = 3                # DECOUPLED_BRU_DEPBAR_RD_SCBD — branch
WR_SCBD = 4            # DECOUPLED_WR_SCBD — result `wr`, no read obligation
RD_NOREQ = 5           # DECOUPLED_RD_NOREQ_SCBD / BRU_DEPBAR_RD_NOREQ
WR_NOREQ = 6           # DECOUPLED_WR_NOREQ_SCBD

_INST_CLASS = {
    "INST_TYPE_COUPLED_MATH": COUPLED,
    "INST_TYPE_COUPLED_EMULATABLE": COUPLED,
    "INST_TYPE_COUPLED_EMULATABLE_NORD_SCBD": COUPLED,
    "INST_TYPE_COUPLED_EMULATABLE_NOWR_SCBD": COUPLED,
    "INST_TYPE_COUPLED_EMULATABLE_NORD_NOWR_SCBD": COUPLED,
    "INST_TYPE_MATH": COUPLED,
    "INST_TYPE_DECOUPLED_RD_SCBD": RD_SCBD,
    "INST_TYPE_MIO_RD_SCBD": RD_SCBD,
    "INST_TYPE_DECOUPLED_RD_WR_SCBD": RD_WR_SCBD,
    "INST_TYPE_MIO_RD_WR_SCBD": RD_WR_SCBD,
    "INST_TYPE_DECOUPLED_WR_SCBD": WR_SCBD,
    "INST_TYPE_DECOUPLED_RD_NOREQ_SCBD": RD_NOREQ,
    "INST_TYPE_DECOUPLED_WR_NOREQ_SCBD": WR_NOREQ,
    "INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD": BRU,
    "INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_NOREQ_SCBD": RD_NOREQ,
}
# classes whose result must carry a `wr` SB
_WR_CLASSES = {RD_WR_SCBD, WR_SCBD}
# classes whose register reads are "late" (after issue → anti-dep exposure)
_LATE_RD_CLASSES = {RD_SCBD, RD_WR_SCBD}
# classes that may carry a `rd` scoreboard for late reads
_RD_CLASSES = {RD_SCBD, RD_WR_SCBD}

# --------------------------------------------------------------------------
# Def/use slot-name conventions (see AUTO_DEP_ANALYSIS §7.2)
# --------------------------------------------------------------------------
_DEF_REG_SLOTS = {"Rd", "Rd2", "URd"}
_DEF_PRED_SLOTS = {"Pd", "Pu", "Pv", "Pnz", "Pp"}
_USE_REG_SLOTS = {
    "Ra", "Rb", "Rc", "Re", "URa", "URb", "URc", "Sb",
    "Ra_URb", "Ra_URc", "Ra_URd",
}
_GUARD_SLOTS = {"Pg", "UPg"}
_SRC_SIZE_KEY = {"Ra": "ISRC_A_SIZE", "Rb": "ISRC_B_SIZE", "Rc": "ISRC_C_SIZE",
                 "Re": "ISRC_E_SIZE"}

# address slots (read at issue, not late) for memory/DECOUPLED-RD instructions
_ADDR_SLOTS = {"Ra", "Ra_URb", "Ra_URc", "URa", "URb", "URc"}

# branch mnemonics for CFG edge construction
_BRANCH_MN = {"BRA", "BRX", "BSSY", "BSYNC", "JMP", "JMC"}
_UNCOND_BRANCH = {"BRA", "BRX", "JMP", "JMC"}   # no fall-through when unpredicated
_INDIRECT = {"BRX", "JMP"}                       # conservative any-successor

REG = "R"
UREG = "UR"
PRED = "P"


def _rk(file: str, index: int) -> tuple[str, int]:
    return (file, index)


@dataclass
class Claim:
    """An outstanding scoreboard usage (wr or rd)."""
    idx: int                 # producing instruction index
    kind: str                # 'wr' | 'rd'
    sb: int                  # 0..5 (7 = none never reaches here)
    regs: set                # covered registers (RegKey)
    predicated: bool = False

    def __hash__(self):
        return hash((self.idx, self.kind, self.sb))


@dataclass
class Diagnostic:
    instr_idx: int
    code: str
    message: str
    reg: Optional[str] = None
    sb: Optional[int] = None
    producer_idx: Optional[int] = None


@dataclass
class InstrInfo:
    idx: int
    mnemonic: str
    cls: int
    defs: set = field(default_factory=set)        # RegKey
    def_preds: set = field(default_factory=set)   # RegKey (predicate defs)
    uses: set = field(default_factory=set)        # RegKey (all reads)
    late_uses: set = field(default_factory=set)   # data reads exposed to anti-dep
    guards: set = field(default_factory=set)      # predicate guards read
    wr_sb: int = 7
    rd_sb: int = 7
    req_bits: set = field(default_factory=set)
    predicated: bool = False
    depbar_targets: list = field(default_factory=list)  # (sb, cnt_or_None)
    branch: dict = field(default_factory=dict)    # CFG edge info
    stall: int = 1


# --------------------------------------------------------------------------
# extract per-instruction def/use/latency from (inst, match)
# --------------------------------------------------------------------------
def _slot_regs(slot_name: str, slot_map: dict) -> Optional[int]:
    """Starting register number for a slot, or None if RZ/unset."""
    v = slot_map.get(slot_name)
    if v is None:
        return None
    return v if v != 255 else None


def _eval_size(db: dict, variant: dict, slot_map: dict, key: str) -> Optional[int]:
    preds = variant.get("predicates", {})
    expr = preds.get(key)
    if not expr:
        return None
    return ConditionEvaluator(db, slot_map).eval_int(expr)


def classify(inst_type: str) -> int:
    return _INST_CLASS.get(inst_type, COUPLED)


def extract_instr(inst, match, db: dict) -> InstrInfo:
    variant = match.variant
    slot_map = match.slot_map
    cls = classify(variant["properties"].get("INSTRUCTION_TYPE", ""))
    info = InstrInfo(idx=0, mnemonic=inst.mnemonic, cls=cls)
    info.predicated = inst.pred is not None

    # dest width (bits) from IDEST_SIZE; None -> 32
    idest = _eval_size(db, variant, slot_map, "IDEST_SIZE")
    n_dest = (idest or 32) // 32

    # def registers: first FORMAT def-reg slot (type Register/Uniform) that
    # has a value expands to n_dest registers.  Only trust slots that exist
    # in FORMAT — slot_map may carry default filler names (e.g. LDCU's "Rd").
    for s in variant["format"]["slots"]:
        nm = s["name"]
        if nm not in _DEF_REG_SLOTS:
            continue
        if s["type"] not in ("Register", "NonZeroRegister", "UniformRegister"):
            continue
        start = _slot_regs(nm, slot_map)
        if start is None:
            continue
        if nm.startswith("UR"):
            info.defs = {_rk(UREG, start + k) for k in range(n_dest)}
        else:
            info.defs = {_rk(REG, start + k) for k in range(n_dest)}
        break

    # def predicates: Pu/Pv/Pnz/Pp/Pd with value != 7 (PT = not written)
    for s in variant["format"]["slots"]:
        nm = s["name"]
        if nm not in _DEF_PRED_SLOTS:
            continue
        if s["type"] != "Predicate":
            continue
        v = slot_map.get(nm)
        if v is not None and v != 7 and v < 8:
            info.def_preds.add(_rk(PRED, v))

    # uses: source register slots (incl. desc UR, address base).  Address
    # slots read at issue; for DECOUPLED_RD instructions the *data* sources
    # are late reads (anti-dependency exposure).
    for s in variant["format"]["slots"]:
        nm = s["name"]
        st = s["type"]
        if nm not in _USE_REG_SLOTS:
            continue
        if st not in ("Register", "NonZeroRegister", "UniformRegister"):
            continue
        v = slot_map.get(nm)
        if v is None or v == 255:
            continue
        base = _rk(UREG if st == "UniformRegister" else REG, v)
        key = _SRC_SIZE_KEY.get(nm)
        if key is not None:
            sz = _eval_size(db, variant, slot_map, key)
            n = (sz or 32) // 32
            rset = {_rk(base[0], v + k) for k in range(n)}
        else:
            rset = {base}
        info.uses |= rset
        # data sources (late) for DECOUPLED_RD; address slots are early
        if info.cls in _RD_CLASSES and nm in _ADDR_SLOTS:
            continue
        info.late_uses |= rset

    # guard predicates
    for nm in _GUARD_SLOTS:
        v = slot_map.get(nm)
        if v is not None and v < 8:
            info.guards.add(_rk(PRED, v))

    info.wr_sb = inst.sched.wr_sb
    info.rd_sb = inst.sched.rd_sb
    info.req_bits = set(inst.sched.req_bits)
    info.stall = inst.sched.stall

    # DEPBAR wait targets: sbidx/cnt/scoreboard_list operands
    if inst.mnemonic == "DEPBAR":
        sbidx = slot_map.get("sbidx")
        cnt = slot_map.get("cnt")
        if sbidx is not None and sbidx < 6:
            info.depbar_targets.append((sbidx, cnt if cnt is not None else None))
        sl = slot_map.get("scoreboard_list")
        if isinstance(sl, int) and sl:
            for b in range(6):
                if sl & (1 << b):
                    info.depbar_targets.append((b, cnt if cnt is not None else None))

    return info


# --------------------------------------------------------------------------
# CFG construction (BRA + fall-through, BSSY/BSYNC pairing, BRX any-succ)
# --------------------------------------------------------------------------
def build_cfg(insts, infos, addrs):
    """insts/results/addrs are aligned lists (label entries have info=None).

    Returns (blocks, succ) where blocks = list of instr-index lists, succ = {b: [b2]}.
    """
    n = len(insts)
    # leaders: instr 0, every branch fall-through, every resolved branch target
    is_leader = [False] * n
    is_leader[0] = True
    # compute targets per branch instruction
    targets = {}          # idx -> list of target idx (None for any-succ)
    ft = {}               # idx -> has fall-through
    bssy_stack = []       # (barReg, target_idx)
    for i in range(n):
        info = infos[i]
        if info is None:
            continue
        mn = info.mnemonic
        if mn == "DEPBAR" or mn not in _BRANCH_MN:
            continue
        # resolve target from operands (labels already -> relative IMM_S)
        tgt = None
        barreg = None
        for op in insts[i].operands:
            from .operand import OperandKind
            if op.kind == OperandKind.IMM_S:
                target_addr = addrs[i] + 16 + op.value
                tgt = target_addr // 16
        # BSSY: barReg + target (linear fall-through; BSYNC jumps to target)
        if mn == "BSSY":
            bssy_stack.append((insts[i].pred, tgt))
            ft[i] = True
        elif mn == "BSYNC":
            if bssy_stack:
                _, tgt = bssy_stack.pop()
            ft[i] = False
        elif mn in _INDIRECT:
            tgt = None
            ft[i] = not info.predicated
        else:  # BRA (JMC)
            ft[i] = (info.predicated) or mn == "JMC"
        if tgt is not None and tgt < n:
            is_leader[tgt] = True
        if tgt is None:
            targets[i] = None        # any-successor
        else:
            targets[i] = [tgt]
        # fall-through successor is a leader
        if ft[i] and i + 1 < n:
            is_leader[i + 1] = True

    # build blocks from leaders
    blocks = []
    inst_block = [None] * n
    cur = None
    for i in range(n):
        if is_leader[i] or cur is None:
            cur = [i]
            blocks.append(cur)
        else:
            cur.append(i)
        inst_block[i] = len(blocks) - 1

    # edges
    succ = [[] for _ in blocks]
    for i in range(n):
        info = infos[i]
        b = inst_block[i]
        if info is None:
            continue
        mn = info.mnemonic
        # last real instruction in the block (skip trailing labels) decides edges
        if mn == "_label_":
            continue
        # find the block-terminal instruction = last non-label in this block
        nxt = None
        for j in range(i, n):
            if inst_block[j] != b:
                break
            if infos[j] is not None and infos[j].mnemonic != "_label_":
                nxt = j
        if nxt != i:
            continue  # only the terminal instruction adds edges
        if mn == "DEPBAR" or mn not in _BRANCH_MN:
            if i + 1 < n and inst_block[i + 1] == b:
                continue  # not terminal
            if i + 1 < n:
                succ[b].append(inst_block[i + 1])
            continue
        if mn == "BSSY":
            if i + 1 < n:
                succ[b].append(inst_block[i + 1])
            continue
        if mn == "BSYNC":
            t = targets.get(i)
            if t:
                succ[b].append(inst_block[t[0]])
            continue
        if targets.get(i) is None:
            succ[b] = list(range(len(blocks)))   # any-successor (BRX/JMP)
            continue
        for t in targets[i]:
            if t < n:
                succ[b].append(inst_block[t])
        if ft.get(i):
            if i + 1 < n:
                succ[b].append(inst_block[i + 1])
        # dedup
        succ[b] = list(dict.fromkeys(succ[b]))

    return blocks, succ, inst_block


# --------------------------------------------------------------------------
# Dataflow + diagnostics
# --------------------------------------------------------------------------
def _kill_claims(claims: set, sb: int):
    return {c for c in claims if c.sb != sb}


def _register(claims: set, ub: dict, info: InstrInfo, track_count: bool):
    """Register wr/rd claims (and count) for an instruction.  Shared by the
    dataflow transfer and the diagnostic pass so both stay in sync."""
    if info.cls in _WR_CLASSES and info.defs and info.wr_sb != 7:
        claims.add(Claim(info.idx, 'wr', info.wr_sb, set(info.defs),
                         info.predicated))
        if track_count:
            ub[info.wr_sb] = ub.get(info.wr_sb, 0) + 1
    if info.cls in _RD_CLASSES and info.rd_sb != 7:
        claims.add(Claim(info.idx, 'rd', info.rd_sb, set(info.late_uses),
                         info.predicated))
        if track_count:
            ub[info.rd_sb] = ub.get(info.rd_sb, 0) + 1


class DepChecker:
    def __init__(self, db: dict, kernel_name: str = ""):
        self.db = db
        self.kernel_name = kernel_name
        self.diags: list[Diagnostic] = []
        self._track_count = False   # count lattice only when DEPBAR.LE cnt>0 present

    # -- fixpoint ----------------------------------------------------------
    def _block_transfer(self, block, infos, in_claims, in_ub):
        """Fold a block: return (out_claims, out_ub)."""
        claims = set(in_claims)
        ub = dict(in_ub)
        for i in block:
            info = infos[i]
            if info is None:
                continue
            # 1. req settlement + DEPBAR kills
            for sb in info.req_bits:
                claims = _kill_claims(claims, sb)
                ub[sb] = 0
            for sb, cnt in info.depbar_targets:
                if cnt == 0:
                    claims = _kill_claims(claims, sb)
                    ub[sb] = 0
                elif self._track_count and cnt is not None and cnt >= 0:
                    ub[sb] = min(ub.get(sb, 0), cnt)
            # 2. register claims + count updates
            _register(claims, ub, info, self._track_count)
        return claims, ub

    def _fixpoint(self, blocks, succ, infos):
        n = len(blocks)
        pred = [[] for _ in range(n)]
        for b in range(n):
            for s in succ[b]:
                if s not in pred[s]:
                    pred[s].append(b)
        IN = [set() for _ in range(n)]
        ub_in = [dict() for _ in range(n)]
        OUT = [set() for _ in range(n)]
        ub_out = [dict() for _ in range(n)]
        # init OUT empty; iterate to fixpoint
        changed = True
        it = 0
        while changed and it < 64:
            changed = False
            for b in range(n):
                o = set()
                u = {}
                for p in pred[b]:
                    o |= OUT[p]
                    for sb, c in ub_out[p].items():
                        u[sb] = max(u.get(sb, 0), c)
                if o != IN[b] or u != ub_in[b]:
                    changed = True
                IN[b] = o
                ub_in[b] = u
                o2, u2 = self._block_transfer(blocks[b], infos, IN[b], ub_in[b])
                if o2 != OUT[b] or u2 != ub_out[b]:
                    changed = True
                OUT[b] = o2
                ub_out[b] = u2
            it += 1
        return IN, ub_in

    # -- diagnostics -------------------------------------------------------
    def check(self, insts, infos, addrs, strict=False):
        blocks, succ, inst_block = build_cfg(insts, infos, addrs)
        IN, ub_in = self._fixpoint(blocks, succ, infos)
        for b, block in enumerate(blocks):
            self._diagnose_block(b, block, insts, infos, IN[b], ub_in[b])
        return self.diags

    def _warn(self, idx, code, message, reg=None, sb=None, prod=None):
        self.diags.append(Diagnostic(idx, code, message, reg, sb, prod))

    def _diagnose_block(self, b, block, insts, infos, in_claims, in_ub):
        claims = set(in_claims)
        ub = dict(in_ub)
        # later-use scan for missing_wr_sb (any subsequent instruction)
        for i in block:
            info = infos[i]
            if info is None:
                continue
            # ---- req settlement / DEPBAR ----
            for sb in info.req_bits:
                claims = _kill_claims(claims, sb)
                ub[sb] = 0
            for sb, cnt in info.depbar_targets:
                if cnt == 0:
                    claims = _kill_claims(claims, sb)
                    ub[sb] = 0
                elif self._track_count and cnt is not None and cnt >= 0:
                    ub[sb] = min(ub.get(sb, 0), cnt)

            # ---- true-dependency: every use needs covering req ----
            for r in sorted(info.uses | info.guards):
                for c in claims:
                    if c.kind == 'wr' and r in c.regs:
                        if c.sb not in info.req_bits:
                            self._warn(
                                i, "missing_req",
                                f"reads {_regname(r)} produced by inst {c.idx} "
                                f"(wr=SB{c.sb}) without req covering SB{c.sb}",
                                reg=_regname(r), sb=c.sb, prod=c.idx)
                        break   # one covering claim is enough

            # ---- anti-dependency: defs vs outstanding rd claims ----
            for r in sorted(info.defs | info.def_preds):
                for c in claims:
                    if c.kind == 'rd' and r in c.regs:
                        if c.sb not in info.req_bits:
                            self._warn(
                                i, "anti_dep",
                                f"defines {_regname(r)} while inst {c.idx} "
                                f"still reads it (rd=SB{c.sb}); add req={{SB{c.sb}}}",
                                reg=_regname(r), sb=c.sb, prod=c.idx)
                        break

            # ---- divergent re-targeting (predicated outstanding claim) ----
            for sb in (info.wr_sb, info.rd_sb):
                if sb == 7:
                    continue
                if any(c.predicated for c in claims if c.sb == sb):
                    self._warn(
                        i, "divergent_retarget",
                        f"retargets SB{sb} while a predicated claim from "
                        f"inst {next(c.idx for c in claims if c.sb == sb and c.predicated)} "
                        f"is outstanding", sb=sb)

            # ---- register claims ----
            if info.cls in _WR_CLASSES and info.defs and info.wr_sb == 7:
                # missing_wr_sb: variable-latency result consumed later
                if self._def_used_later(i, info.defs, infos):
                    self._warn(
                        i, "missing_wr_sb",
                        f"variable-latency result {_regset(info.defs)} has "
                        f"wr=7 (no scoreboard) but is consumed",
                        reg=_regset(info.defs))
            _register(claims, ub, info, self._track_count)

            # ---- capacity (only meaningful when DEPBAR.LE partial drains
            # make the count lattice observable) ----
            if self._track_count:
                for sb, c in ub.items():
                    if c > 63:
                        self._warn(i, "sb_capacity",
                                   f"SB{sb} in-flight upper bound {c} exceeds "
                                   f"the 6-bit tally cap without a drain", sb=sb)

    def _def_used_later(self, i, defs, infos):
        for j in range(i + 1, len(infos)):
            info = infos[j]
            if info is None:
                continue
            if defs & (info.uses | info.guards):
                return True
        return False


def _regname(rk) -> str:
    f, i = rk
    return f"{f}{i}"


def _regset(rs) -> str:
    return ",".join(_regname(r) for r in sorted(rs))


def _fmt_inst(inst) -> str:
    """Render an instruction as assembler text for diagnostics."""
    from .sass_asm import fmt_operand
    parts = [inst.mnemonic]
    if inst.modifiers:
        parts.append("." + ".".join(inst.modifiers))
    if inst.operands:
        parts.append(" ")
        parts.append(", ".join(fmt_operand(o) for o in inst.operands))
    return "".join(parts)


def run_depcheck(db: dict, insts, results, addrs, kernel_name="",
                 strict=False, out=None) -> list[Diagnostic]:
    """Run the checker over an aligned (inst, match_result) sequence.

    insts/results/addrs are parallel; label entries have results[i] = None.
    Diagnostics are written to `out` (stderr default) and returned.
    """
    out = out if out is not None else sys.stderr
    infos = []
    for i, (inst, res) in enumerate(zip(insts, results)):
        if res is None:
            infos.append(None)
            continue
        info = extract_instr(inst, res, db)
        info.idx = i
        infos.append(info)
    checker = DepChecker(db, kernel_name)
    checker._track_count = any(
        info is not None and info.mnemonic == "DEPBAR"
        and any(c is not None and c > 0 for _, c in info.depbar_targets)
        for info in infos)
    diags = checker.check(insts, infos, addrs)
    for d in diags:
        inst = insts[d.instr_idx]
        line = getattr(inst, "line", 0) or 0
        text = _fmt_inst(inst) if inst is not None else ""
        print(f"[depcheck] {kernel_name} line:{line} [{d.code}] {text}: "
              f"{d.message}", file=out)
    if diags:
        from collections import Counter
        c = Counter(d.code for d in diags)
        summary = ", ".join(f"{k}={v}" for k, v in sorted(c.items()))
        print(f"[depcheck] {kernel_name}: {len(diags)} diagnostic(s): {summary}",
              file=out)
    return diags
