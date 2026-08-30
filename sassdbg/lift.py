"""sassdbg.lift — cuobjdump SASS text -> assembler dialect (M2 round-trip).

cuobjdump does NOT print control codes, but they are readable from the raw
128-bit words (which cuobjdump prints as hex comments):

    req_bit_set  [121:116]  -> {req}          (6-bit wait mask, SB0..SB5)
    src_rel_sb   [115:113]  -> rd             (7 = none)
    dst_wr_sb    [112:110]  -> wr             (7 = none)
    opex         [124:122] ++ [109:105]       (TABLES_opex_N packed word)
        usched_info = opex[4:0]  -> stall/yield: ui==0 -> (0,1) DRAIN;
                                    ui<16 -> (ui,1) WnEG; ui>=16 -> (ui-16,0) Wn
        batch/reuse = opex[7:5]  -> 6th bracket field; the encoder routes it
                                    to batch_t or reuse_src_{a,b,c} per class.

Printer-syntax gotchas handled here (see AGENTS.md "Critical gotchas"):
    [R6.64+0x10]      -> [{R6,R7}+0x10]       (address groups, .64/.128)
    desc[UR4]         -> desc[{UR4,UR5}]
    LDC.64 R6, ...    -> LDC.64 {R6,R7}, ...  (load dest groups)
    STG.E.64 [...], R4-> ... {R4,R5}          (store data groups)
    MOV.64 R0, R2     -> MOV.64 {R0,R1}, {R2,R3}
    IMAD.WIDE Rd, ..  -> dest + addend groups
    1.5               -> 0f3fc00000           (exact f32 bits, decimal re-parse)
    BRA 0x60          -> BRA #label(L_60)     (branch targets become labels)

Round-trip check: assemble_flat(lifted) == original (lo64, hi64) words.
"""
from __future__ import annotations

import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

# ---------------------------------------------------------------------------
# cuobjdump output parsing
# ---------------------------------------------------------------------------
RE_FUNC = re.compile(r"^\s*Function : (\S+)")
RE_INST = re.compile(r"^\s*/\*([0-9a-f]+)\*/\s+(.*?)\s*;\s*/\* (0x[0-9a-f]+) \*/\s*$")
RE_WORD2 = re.compile(r"^\s*/\* (0x[0-9a-f]+) \*/\s*$")
RE_FLOAT = re.compile(r"^-?(?:\d+\.\d*|\.\d+|\d+\.\d*e[+-]?\d+|\d+e[+-]?\d+)$", re.I)


@dataclass
class RawInst:
    addr: int
    text: str           # cuobjdump text without guard/comment, no trailing ';'
    lo: int
    hi: int


@dataclass
class RawFunc:
    name: str
    insts: list[RawInst] = field(default_factory=list)
    # kernel parameters: (ordinal, byte offset in param space, size in bytes)
    params: list[tuple[int, int, int]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# kernel parameter extraction (per-function .nv.info.<func> ELF sections)
# ---------------------------------------------------------------------------
_KPARAM_PAT = b"\x04\x17\x0c\x00\x00\x00\x00\x00"


def _elf_sections(data: bytes) -> dict[str, bytes]:
    """Minimal ELF64-LE section table walk -> {section_name: contents}."""
    import struct as _st
    if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        return {}
    e_shoff, = _st.unpack_from("<Q", data, 0x28)
    e_shentsize, e_shnum, e_shstrndx = _st.unpack_from("<HHH", data, 0x3A)
    shdrs = []
    for i in range(e_shnum):
        base = e_shoff + i * e_shentsize
        name, _typ = _st.unpack_from("<II", data, base)
        off, size = _st.unpack_from("<QQ", data, base + 24)
        shdrs.append((name, off, size))
    if not (0 <= e_shstrndx < len(shdrs)):
        return {}
    strtab_off, strtab_size = shdrs[e_shstrndx][1], shdrs[e_shstrndx][2]
    strtab = data[strtab_off:strtab_off + strtab_size]
    out = {}
    for name, off, size in shdrs:
        end = strtab.find(b"\x00", name)
        if end < 0:
            continue
        sec_name = strtab[name:end].decode("utf-8", "replace")
        out[sec_name] = data[off:off + size]
    return out


def extract_params(cubin_data: bytes, func: str) -> list[tuple[int, int, int]]:
    """(ordinal, offset, size) triples for one kernel, from its
    .nv.info.<func> section's EIATTR_KPARAM_INFO records.

    Record layout (16 bytes, probed from nvcc cubins):
      +0  04 17 0c 00 00 00 00 00   (attribute tag)
      +8  u32 = (offset << 16) | ordinal
      +12 u32 = size code; size = ((code >> 16) - 1) >> 2  (low 0xf000 flags)
    """
    import struct as _st
    sec = _elf_sections(cubin_data).get(f".nv.info.{func}")
    if not sec:
        return []
    params: dict[int, tuple[int, int]] = {}
    i = 0
    while True:
        j = sec.find(_KPARAM_PAT, i)
        if j < 0 or j + 16 > len(sec):
            break
        off_ord, code = _st.unpack_from("<II", sec, j + 8)
        if (code & 0xf000) == 0xf000:
            ordinal, offset = off_ord & 0xFFFF, off_ord >> 16
            size = ((code >> 16) - 1) >> 2
            if 1 <= size <= (1 << 16):
                params[ordinal] = (offset, size)
        i = j + 1
    return [(o, *params[o]) for o in sorted(params)]


def dump_cubin(cubin: str, cuda_arch: str = "sm_120") -> list[RawFunc]:
    cuobjdump = shutil.which("cuobjdump")
    if cuobjdump is None:
        default = Path("/usr/local/cuda/bin/cuobjdump")
        if default.is_file():
            cuobjdump = str(default)
        else:
            raise FileNotFoundError(
                "cuobjdump not found in PATH or /usr/local/cuda/bin")
    out = subprocess.run([cuobjdump, "-sass", cubin],
                         capture_output=True, text=True, check=True).stdout
    try:
        cubin_data = open(cubin, "rb").read()
    except OSError:
        cubin_data = b""
    funcs: list[RawFunc] = []
    cur: RawFunc | None = None
    pending: tuple[int, str, int] | None = None
    for line in out.splitlines():
        m = RE_FUNC.match(line)
        if m:
            cur = RawFunc(m.group(1))
            cur.params = extract_params(cubin_data, cur.name)
            funcs.append(cur)
            continue
        m = RE_INST.match(line)
        if m and cur is not None:
            pending = (int(m.group(1), 16), m.group(2), int(m.group(3), 16))
            continue
        m = RE_WORD2.match(line)
        if m and pending is not None and cur is not None:
            cur.insts.append(RawInst(pending[0], pending[1], pending[2],
                                     int(m.group(1), 16)))
            pending = None
    return funcs


# ---------------------------------------------------------------------------
# control-code decode (raw words -> scheduling bracket)
# ---------------------------------------------------------------------------
def decode_bracket(lo: int, hi: int) -> str:
    req = (hi >> 52) & 0x3F
    rd = (hi >> 49) & 0x7
    wr = (hi >> 46) & 0x7
    ui = (hi >> 41) & 0x1F
    batch3 = (hi >> 58) & 0x7
    if ui == 0:
        stall, y = 0, 1            # DRAIN
    elif ui < 16:
        stall, y = ui, 1           # WAITn_END_GROUP
    else:
        stall, y = ui - 16, 0      # WAITn (transient)
    reqs = ",".join(str(b) for b in range(6) if req >> b & 1)
    b = f"[{wr}:{rd}:{{{reqs}}}:{stall}:{y}"
    if batch3:
        b += f":{batch3}"
    return b + "]"


# ---------------------------------------------------------------------------
# text conversion
# ---------------------------------------------------------------------------
LOAD_MNEMS = {"LDG", "LDS", "LDL", "LDC", "LDCU", "ULDC", "LDGSTS", "UBLKCP",
              "LD", "ATOM", "ATOMG", "ATOMS"}
STORE_MNEMS = {"STG", "STS", "STL", "ST", "RED", "REDG"}
BRANCH_MNEMS = {"BRA", "BSSY", "BMOV", "CALL", "JMP", "RET", "BRX"}
LABEL_MNEMS = {"BRA", "BSSY"}       # immediate targets -> labels

# Instructions with a packed f16x2/bf16x2 immediate pair (two F64Imm
# half-slots in the FORMAT), printed by cuobjdump as two adjacent decimals.
PAIR_MNEMS = {"HFMA2", "HADD2", "HMUL2", "HMNMX2", "HSET2", "HSETP2"}
RE_NUM = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")
# an f16 pair half prints as a decimal *or* a raw 0fXXXXXXXX word
RE_NUMISH = re.compile(r"^(?:[+-]?(?:\d+(?:\.\d+)?|\.\d+)|0f[0-9a-fA-F]{8})$")

_SZ_MOD = {"U8": 1, "S8": 1, "U16": 2, "S16": 2,
           "64": 8, "128": 16}      # "" (no size) = 4


def _mem_size(mods: list[str]) -> int:
    for m in mods:
        if m in _SZ_MOD:
            return _SZ_MOD[m]
    return 4


# f64-immediate instructions (DADD/DMUL/...): the 32-bit field holds the
# HIGH word of the f64 value — cuobjdump prints it as a decimal ("2.5").
_D_MNEMS = {"DADD", "DMUL", "DFMA", "DSETP", "DMNMX", "DSET"}


def _f64hi_bits(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0] >> 32


def _expand_group(tok: str, width: int) -> str:
    """R6 -> {R6,R7} (width 8) or {R6..R9} (width 16); UR likewise."""
    m = re.fullmatch(r"(U?R)(\d+)(.*)", tok)
    if not m:
        return tok
    pre, n, rest = m.group(1), int(m.group(2)), m.group(3)
    if pre == "R" and n >= 255:
        return tok
    if pre == "UR" and n >= 63:
        return tok
    nregs = width // 4
    return "{" + ",".join(f"{pre}{n + i}" for i in range(nregs)) + "}" + rest


def _convert_addr(tok: str) -> str:
    """[R6.64+0x10] -> [{R6,R7}+0x10]; desc[UR4] -> desc[{UR4,UR5}]."""
    # width annotation on a 32-bit address base ([RZ.U32+UR4]) is redundant
    # in the explicit-group dialect
    tok = re.sub(r"\b(U?R\d+|RZ|URZ)\.U32(?=[+\]])", r"\1", tok)

    def desc_sub(m):
        return f"desc[{{UR{m.group(1)},UR{int(m.group(1)) + 1}}}]"
    tok = re.sub(r"desc\[UR(\d+)\]", desc_sub, tok)

    def grp_sub(m):
        base, w, rest = m.group(1), int(m.group(2)), m.group(3)
        mm = re.match(r"(U?R)(\d+)$", base)
        if not mm:
            return m.group(0)
        pre, n = mm.group(1), int(mm.group(2))
        nregs = w // 32   # .64 = 2 regs, .128 = 4 regs
        return "[{" + ",".join(f"{pre}{n + i}" for i in range(nregs)) + "}" + rest + "]"
    return re.sub(r"\[((?:U?R)\d+)\.(64|128)([^\]]*)\]", grp_sub, tok)


def convert(raw: RawInst, targets: set[int] | None = None) -> str:
    """One cuobjdump instruction -> dialect line (without indent)."""
    text = raw.text.strip()
    guard = ""
    m = re.match(r"^(@!?(?:U?P\d|PT))\s+(.*)$", text)
    if m:
        guard, text = m.group(1) + " ", m.group(2)

    parts = text.split(None, 1)
    mnem_full = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    base = mnem_full.split(".")[0]
    mods = mnem_full.split(".")[1:]

    # split operands at top-level commas (respect [], {}, ())
    ops, depth, cur = [], 0, ""
    for ch in rest:
        if ch in "[{(":
            depth += 1
        if ch in "]})":
            depth -= 1
        if ch == "," and depth == 0:
            ops.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        ops.append(cur.strip())

    # cuobjdump space-separates the register and offset for RET (absolute
    # target printed) and BRX (relative offset printed); the dialect spells
    # both as reg±byte-offset (R2-0x340).
    if base in ("RET", "BRX") and ops and " " in ops[-1]:
        parts = ops[-1].split()
        if len(parts) == 2 and re.fullmatch(r"-?0x[0-9a-f]+", parts[1]):
            if base == "RET":
                rel = int(parts[1], 16) - (raw.addr + 16)
            else:
                rel = int(parts[1], 16)
            ops[-1] = parts[0] + \
                (f"-0x{-rel:x}" if rel < 0 else f"+0x{rel:x}")

    # f16x2/bf16x2 packed immediate (HFMA2-family imm forms): cuobjdump
    # prints the packed 32-bit pair as two adjacent decimals (hi, lo) in
    # FORMAT order.  Merge them into one raw 0fXXXXXXXX operand at the same
    # text position — the position disambiguates imm-middle (RIR) from
    # imm-last (RRI) classes, and the raw bits come straight from lo64[63:32]
    # so the round-trip is exact by construction.
    if base in PAIR_MNEMS:
        imm32 = (raw.lo >> 32) & 0xFFFFFFFF
        for j in range(len(ops) - 1):
            if RE_NUMISH.match(ops[j]) and RE_NUMISH.match(ops[j + 1]):
                ops[j:j + 2] = [f"0f{imm32:08x}"]
                break

    is_load = base in LOAD_MNEMS
    is_store = base in STORE_MNEMS
    is_atom = base.startswith("ATOM")
    wide = any(m.startswith("WIDE") for m in mods)
    # IMAD/UIMAD .HI and .WIDE: the spec gives the addend (last operand)
    # ISRC_C_SIZE=64 — cuobjdump prints the bare base register but the
    # dialect requires the explicit pair (RZ stays bare: wide placeholder).
    imad_c64 = base in ("IMAD", "UIMAD") and \
        any(m == "HI" or m.startswith("WIDE") for m in mods)
    mov64 = base in ("MOV", "UMOV") and "64" in mods
    sz = _mem_size(mods)

    out_ops: list[str] = []
    for i, op in enumerate(ops):
        # reuse flags: carried by the raw opex bits (6th bracket field), not
        # expressible in the dialect — strip from text
        op = op.replace(".reuse", "")
        # cuobjdump prints negative address offsets as "+-0x20"
        op = op.replace("+-", "-")
        # float immediates -> exact bit form (incl. cuobjdump's +INF/-INF/NAN)
        m_sp = re.fullmatch(r"([+-]?)(INF|NAN)", op)
        if m_sp:
            bits = 0x7F800000 if m_sp.group(2) == "INF" else 0x7FC00000
            if m_sp.group(1) == "-":
                bits |= 0x80000000
            op = f"0f{bits:08x}"
        elif RE_FLOAT.match(op):
            if base in _D_MNEMS:
                op = f"0f{_f64hi_bits(float(op)):08x}"
            else:
                bits = struct.unpack("<I", struct.pack("<f", float(op)))[0]
                op = f"0f{bits:08x}"
        # branch immediate -> label
        if base in LABEL_MNEMS and re.fullmatch(r"0x[0-9a-f]+", op):
            tgt = int(op, 16)
            if targets is not None:
                targets.add(tgt)
            op = f"#label(L_{tgt:x})"
        # CALL prints the absolute target; the encoding is PC-relative
        # (base = the following instruction), and the target often lives in
        # another function — emit the raw relative byte offset instead of a
        # label.  LEPC (get PC + imm) likewise stores PC-relative.
        elif base in ("CALL", "LEPC") and re.fullmatch(r"0x[0-9a-f]+", op):
            rel = int(op, 16) - (raw.addr + 16)
            op = f"-0x{-rel:x}" if rel < 0 else f"0x{rel:x}"
        # address operands
        if "[" in op:
            op = _convert_addr(op)
        # width expansions on bare register operands
        elif re.fullmatch(r"U?R\d+", op):
            if mov64:
                op = _expand_group(op, 8)
            elif wide and (i == 0 or i == len(ops) - 1):
                op = _expand_group(op, 8)
            elif imad_c64 and i == len(ops) - 1:
                op = _expand_group(op, 8)
            elif (is_load or is_atom) and i == 0 and sz > 4:
                op = _expand_group(op, sz)
            elif is_store and i == len(ops) - 1 and sz > 4:
                op = _expand_group(op, sz)
            elif is_atom and i == len(ops) - 1 and sz > 4:
                op = _expand_group(op, sz)
        out_ops.append(op)

    line = guard + mnem_full + (" " if out_ops else "") + ", ".join(out_ops)
    return line + ";" + decode_bracket(raw.lo, raw.hi)


def lift_function(fn: RawFunc) -> str:
    targets: set[int] = set()
    lines = [convert(r, targets) for r in fn.insts]
    params = ", ".join(f"p{o}<{sz}>" for o, _off, sz in fn.params)
    # sanity: the assembler lays params out sequentially with natural
    # alignment; warn if ptxas's recorded offsets diverge (the lifted body
    # reads params by absolute c[0x0][...] offset, so a mismatch would read
    # the wrong slots)
    expected = 0
    for o, off, sz in fn.params:
        align = min(max(sz, 1), 16)
        align = 1 << (align.bit_length() - 1)     # largest pow2 <= size, <=16
        expected = (expected + align - 1) & ~(align - 1)
        if off != expected:
            import sys as _sys
            print(f"lift: warning: {fn.name} param p{o} at offset {off:#x}, "
                  f"sequential layout would put it at {expected:#x}",
                  file=_sys.stderr)
            break
        expected += sz
    out = [f"#fn {fn.name}({params}) {{"]
    for raw, line in zip(fn.insts, lines):
        if raw.addr in targets:
            out.append(f"    #def_label(L_{raw.addr:x})")
        out.append("    " + line)
    out.append("}")
    return "\n".join(out)


def lift(cubin: str, func: str | None = None) -> dict[str, str]:
    return {f.name: lift_function(f) for f in dump_cubin(cubin)
            if func is None or f.name == func}


# ---------------------------------------------------------------------------
# round-trip validation
# ---------------------------------------------------------------------------
_RE_REPAIR = re.compile(
    r"inst (\d+): .*operand #(\d+) \((?:((?:U?R))(\d+)|\{([^}]+)\})\) is "
    r"(?:a single \w+ register|\d+-bit) but this variant expects a "
    r"\d+-bit operand — list every register explicitly, e\.g\. "
    r"\{([^}]+)\}")
_RE_NOMATCH = re.compile(
    r"inst (\d+): no matching variant for (\w+) \(operands=\[([^\]]*)\]")
# cuobjdump prints integral float immediates as bare ints (`FMUL R5, R9, 4`
# = 0f40800000); these mnemonics take float immediates in any IMM slot.
_FLOAT_IMM_MNEMS = {
    "FFMA", "FMUL", "FADD", "FSETP", "FSEL", "FCHK", "F2F", "F2FP", "FMNMX",
    "DADD", "DFMA", "DMUL", "DSETP", "DMNMX",
    "HADD2", "HFMA2", "HMUL2", "HSET2", "HSETP2", "HMNMX2",
    "UFFMA", "UFMUL", "UFADD", "UFSEL", "UFMNMX",
}


def _split_ops(text: str) -> list[str]:
    """Split an instruction's operand string at top-level commas."""
    ops, depth, cur = [], 0, ""
    for ch in text:
        if ch in "[{(":
            depth += 1
        if ch in "]})":
            depth -= 1
        if ch == "," and depth == 0:
            ops.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        ops.append(cur.strip())
    return ops


def _inst_line(lines: list[str], inst_i: int) -> tuple[int, str] | None:
    """Map an instruction index (non-label, non-blank lines) to its line."""
    idx = -1
    for li, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        idx += 1
        if idx == inst_i:
            return li, ln
    return None


def _repair_lines(lines: list[str]) -> list[str]:
    """Bounded repair loop for cuobjdump spellings the dialect doesn't take
    literally:
      - bare base register where the encoding has a 64/128-bit operand
        (the matcher's error names the exact {Ra,Rb} group to write);
      - integral float immediates printed as bare ints (`FMUL R5, R9, 4`).
    Returns the repaired source lines."""
    from assembler import assemble_flat

    for _ in range(4 * len(lines) + 16):
        try:
            assemble_flat("\n".join(lines))
            return lines
        except Exception as e:
            msg = str(e)
            # -- repair 1: bare register for a wide operand
            m = _RE_REPAIR.search(msg)
            if m:
                inst_i, op_i, sugg = int(m.group(1)), int(m.group(2)), \
                    m.group(6)
                found = _inst_line(lines, inst_i)
                if found is None:
                    raise
                li, tl = found
                head, tail = tl.split(";", 1)
                parts = head.split(None, 1)
                if len(parts) < 2:
                    raise
                # predicated line: "@P0 SEL.64 R2, ..." — skip the @P
                # token before the mnemonic
                if parts[0].startswith("@"):
                    sub = parts[1].split(None, 1)
                    if len(sub) < 2:
                        raise
                    prefix, ops_src = parts[0] + " " + sub[0], sub[1]
                else:
                    prefix, ops_src = parts[0], parts[1]
                ops = _split_ops(ops_src)
                # preserve decorations: -/|..| neg/abs and a PC-relative
                # offset suffix (RET.REL.NODEC R2-0x340)
                om = re.fullmatch(
                    r"(-?)(\|?)(U?R\d+|RZ|URZ|\{[^{}]*\})(\|?)"
                    r"([+-]0x[0-9a-f]+)?",
                    ops[op_i]) if op_i < len(ops) else None
                if om is None:
                    raise
                if m.group(5) is not None:
                    # already a group, but the wrong width — verify the
                    # base register matches the suggestion's first reg
                    if not om.group(3).startswith("{") or \
                            om.group(3)[1:].split(",")[0] != \
                            sugg.split(",")[0]:
                        raise
                elif om.group(3) != f"{m.group(3)}{m.group(4)}":
                    raise
                ops[op_i] = (om.group(1) + om.group(2) + "{" + sugg + "}"
                             + om.group(4) + (om.group(5) or ""))
                lines[li] = prefix + " " + ", ".join(ops) + ";" + tail
                continue
            # -- repair 2: float immediate printed as a bare integer
            m = _RE_NOMATCH.search(msg)
            if m and m.group(2) in _FLOAT_IMM_MNEMS:
                inst_i = int(m.group(1))
                kinds = [k.strip().strip("'")
                         for k in m.group(3).split(",") if k.strip()]
                found = _inst_line(lines, inst_i)
                if found is None:
                    raise
                li, tl = found
                head, tail = tl.split(";", 1)
                parts = head.split(None, 1)
                if len(parts) > 1 and parts[0].startswith("@"):
                    sub = parts[1].split(None, 1)
                    if len(sub) < 2:
                        raise
                    prefix, ops_src = parts[0] + " " + sub[0], sub[1]
                else:
                    prefix = parts[0]
                    ops_src = parts[1] if len(parts) > 1 else ""
                ops = _split_ops(ops_src) if ops_src else []
                done = False
                for oi, k in enumerate(kinds):
                    if k not in ("IMM_U", "IMM_S") or oi >= len(ops):
                        continue
                    try:
                        v = int(ops[oi], 0)
                    except ValueError:
                        continue
                    if m.group(2) in _D_MNEMS:
                        bits = _f64hi_bits(float(v))
                    else:
                        bits = struct.unpack("<I", struct.pack("<f",
                                                               float(v)))[0]
                    ops[oi] = f"0f{bits:08x}"
                    lines[li] = prefix + " " + ", ".join(ops) + ";" + tail
                    done = True
                    break
                if done:
                    continue
            raise
    raise RuntimeError("repair loop did not converge")


def _assemble_with_repair(body: str):
    """Assemble a lifted function body, normalizing cuobjdump spellings the
    dialect rejects (see _repair_lines)."""
    from assembler import assemble_flat
    return assemble_flat("\n".join(_repair_lines(body.splitlines())))


def normalize_source(src: str) -> str:
    """Run the repair loop over a #fn-wrapped lifted source so downstream
    consumers (instrument) see dialect-clean register groups/immediates."""
    lines = src.splitlines()
    # keep the #fn header / #pragma / closing brace untouched; repair the rest
    head = lines[:1]
    tail = lines[-1:]
    body = _repair_lines(lines[1:-1])
    return "\n".join(head + body + tail)


def roundtrip(cubin: str, func: str | None = None, verbose: bool = False):
    from assembler import assemble_flat

    fns = dump_cubin(cubin)
    total, ok = 0, 0
    for f in fns:
        if func is not None and f.name != func:
            continue
        src = lift_function(f)
        body = "\n".join(src.splitlines()[1:-1])   # strip #fn wrapper
        total += 1
        try:
            enc = _assemble_with_repair(body)
        except Exception as e:
            print(f"FAIL {f.name}: assemble error: {str(e)[:200]}")
            continue
        want = [(r.lo, r.hi) for r in f.insts]
        if len(enc) != len(want):
            print(f"FAIL {f.name}: {len(enc)} insts vs {len(want)} original")
            continue
        bad = [(i, e, w) for i, (e, w) in enumerate(zip(enc, want)) if e != w]
        if not bad:
            ok += 1
            if verbose:
                print(f"ok   {f.name} ({len(want)} insts)")
        else:
            print(f"FAIL {f.name}: {len(bad)} word mismatch(es):")
            for i, e, w in bad[:5]:
                print(f"  [{i:3}] got {e[0]:016x} {e[1]:016x}  want {w[0]:016x} {w[1]:016x}")
                print(f"        text: {f.insts[i].text}")
    print(f"round-trip: {ok}/{total} functions exact")
    return ok == total


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cubin")
    ap.add_argument("--func")
    ap.add_argument("--roundtrip", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    if a.roundtrip:
        sys.exit(0 if roundtrip(a.cubin, a.func, a.verbose) else 1)
    for name, src in lift(a.cubin, a.func).items():
        print(src)
