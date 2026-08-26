r"""Per-arch source adaptation helpers for asm_construct tests.

The two ISA targets differ in ways a single hand-written kernel string cannot
express:

* **Cache-policy descriptor load**: sm_120 `LDCU` is DECOUPLED_WR_SCBD — the
  kernel claims wr=SBx on the load and every desc[] consumer carries
  `req={x}`.  On sm_90 `ULDC` is COUPLED_MATH with dst_wr_sb=\*7 — no write
  scoreboard ever fires, so consumers must NOT req-wait; readiness comes from
  stall/yield instead (see notes/sm90/arch/assembler_sm90_port.md,
  "ULDC timing investigation") — ULDC dst_wr_sb is *7 (never claims a
  scoreboard).
* **Encoding reference tuples**: several tests pin byte-exact (lo64,hi64)
  vectors captured once from one arch's assembly.  Those pins are meaningless
  under the other arch's control-word layout — compare them only on the
  capturing arch (`same_as_capture()`).

`adapt_source()` rewrites the sm_120 idioms in a finished kernel string so the
same text assembles correctly on both arches.  Call it right before
`assemble(...)` / `assemble_kernel(...)`.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler.arch import current

_CDESC_RE = re.compile(
    r"(?P<lead>[ \t]*)"
    r"(?:ULDC|LDCU)\.(?P<sz>64|128|32)?"
    r"[ \t]*(?P<regs>\{[^};]*\}|[^,;\s][^;,]*)"
    r",[ \t]*(?P<src>#spec_const\([A-Z_0-9]+\)|#param\([^)]*\)|c\[[^\]]*\]\[[^\]]*\])"
    r";(?P<bracket>[^\n]*)"
)

_BRACKET_RE = re.compile(
    r"\[(?P<wr>\d+):(?P<rd>\d+):(?P<wait>\{[^}]*\}|[^:\]]*):(?P<stall>\d+):(?P<yield>\d+)(?P<rest>:[^\]]*)?\]"
)


def arch() -> str:
    """Active assembler arch name ('sm90' | 'sm120')."""
    return current().name


def is_sm90() -> bool:
    return arch() == "sm90"


def same_as_capture(capture: str = "sm120") -> bool:
    """True when the active arch matches the arch a REF table was captured on."""
    return current().name == capture


_MOV64_RE = re.compile(
    r"^(?P<lead>[ \t]*)(?:MOV|UMOV)\.64[ \t]*(?P<dst>\{[^}]+\})[ \t]*,[ \t]*(?P<src>.+?)(?P<br>;\[[^]]*\])[ \t]*$")

def _split_mov64(m):
    """sm_90 spec has no MOV.64: split pair-move into two scalar MOVs."""
    lead, dst, src, br = m.group("lead"), m.group("dst"), m.group("src"), m.group("br")
    lo_reg, hi_reg = [x.strip() for x in dst.strip("{}").split(",")]
    src = src.strip()
    if src.startswith("{"):
        s_lo, s_hi = [x.strip() for x in src.strip("{}").split(",")]
        l1 = f"{lead}MOV {lo_reg}, {s_lo}{br}"
        l2 = f"{lead}MOV {hi_reg}, {s_hi}{br}"
    else:
        imm = int(src, 16) if src.lower().startswith("0x") else int(src)
        l1 = f"{lead}MOV {lo_reg}, 0x{imm & 0xFFFFFFFF:X}{br}"
        l2 = f"{lead}MOV {hi_reg}, 0x{(imm >> 32) & 0xFFFFFFFF:X}{br}"
    return l1 + "\n" + l2


_VIADD_U32_RE = re.compile(r"(\bVIADD(?:X|XU)?)\.U32\b")


_ELECT_RE = re.compile(r"\bELECT\s+(P\d+)\s*,\s*(UR\w+)\s*,\s*PT\b")


def _prune_wait(inner: str, alive: set) -> str:
    """Keep only wait ids whose producer scoreboard still exists on sm90."""
    body = inner.strip("{} ")
    if not body:
        return inner
    keep = [tok for tok in re.split(r"[ ,]+", body)
            if tok and int(tok, 0) in alive]
    return "{" + ",".join(keep) + "}"


def adapt_source(src: str, *, verbose: bool = False) -> str:
    """Make an sm_120-dialect kernel string valid for the active arch."""
    if not is_sm90():
        return src

    lines_in = src.split("\n")
    # pass 1: classify every write-scoreboard claim — wrs from uniform loads
    # vanish under ULDC; everything else stays live.
    alive_sbs: set[int] = set()
    for line in lines_in:
        head, sep, bracket = line.partition(";")
        if not sep:
            continue
        mm = _BRACKET_RE.match(
            bracket if bracket.startswith("[") else "[" + bracket.rstrip("]") + "]")
        if not mm or not (mm.group("wr")).isdigit():
            continue
        wr = int(mm.group("wr"))
        is_uniform_load = ((("LDCU" in head) or ("ULDC." in head))
                           and re.search(r"SLOT_DEFAULT_CDESC|#param\(|c\[", head))
        if is_uniform_load:
            continue                        # will be rewritten to no-wr below
        if wr != 7:
            alive_sbs.add(wr)

    out_lines = []
    for line in lines_in:
        head, sep, bracket = line.partition(";")
        if is_sm90():
            new, nsub = _VIADD_U32_RE.subn(r"\1.32", head)
            if nsub:
                line = new + sep + bracket
                head, sep, bracket = line.partition(";")
            mmov = _MOV64_RE.match(line)
            if mmov:
                out_lines.extend(_split_mov64(mmov).split("\n"))
                continue
        if sep and "ELECT" in head:
            # sm120 dialect prints `ELECT Pd, URa, PT`; sm90 slots are
            # `ELECT Pu, URd, [~]URa` — a literal PT cannot fill URa.
            new = _ELECT_RE.sub(r"ELECT \1, \2, URZ", head)
            if new != head:
                line = new + sep + bracket
            head, sep, bracket = line.partition(";")
        if sep and "desc[" in head:
            m = _BRACKET_RE.match(
                bracket if bracket.startswith("[") else "[" + bracket.rstrip("]") + "]")
            if m:
                wait = _prune_wait(m.group("wait"), alive_sbs)
                st = max(int(m.group("stall")), 3)
                yl = max(int(m.group("yield")), 1)
                br2 = f"[{m.group('wr')}:{m.group('rd')}:{wait}:{st}:{yl}{m.group('rest') or ''}]"
                line = f"{head};{br2}"
                if verbose:
                    print(f"[archutil] desc-consumer -> {line.strip()}")
        elif sep and ("LDCU." in head or "ULDC." in head or re.search(r"\bLDCU\b", head)) \
                and re.search(r"SLOT_DEFAULT_CDESC|#param\(|c\[", line):
            def _load(m):
                lead = m.group("lead")
                sz = m.group("sz") or "64"
                regs, dst = m.group("regs"), m.group("src")
                mm = _BRACKET_RE.match(m.group("bracket"))
                old_wr = int(mm.group("wr")) if mm else None
                st = max(int(mm.group("stall")) if mm else 1, 3)
                yl = max(int(mm.group("yield")) if mm else 0, 1)
                br2 = f"[7:7:{{}}:{st}:{yl}]"
                if verbose:
                    print(f"[archutil] LDCU->ULDC (wr={old_wr}->none) {br2}")
                return f"{lead}ULDC.{sz} {regs}, {dst};{br2}"
            new = _CDESC_RE.sub(_load, line)
            line = new if new != line else line
        out_lines.append(line)
    return "\n".join(out_lines)


# --- convenience wrappers around assembler entry points ---------------------
from assembler import assemble as _assemble, assemble_kernel as _ak  # noqa: E402


def assemble(src, *a, **kw):
    """assembler.assemble with per-arch source adaptation applied."""
    return _assemble(adapt_source(src, verbose=kw.pop("verbose", False)), *a, **kw)


def assemble_kernel(src, *a, **kw):
    return _ak(adapt_source(src, verbose=kw.pop("verbose", False)), *a, **kw)
