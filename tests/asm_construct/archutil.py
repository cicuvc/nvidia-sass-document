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
    """sm_90 spec has no *.64 pair-move: split into scalar moves."""
    lead, dst, src, br = m.group("lead"), m.group("dst"), m.group("src"), m.group("br")
    lo_reg, hi_reg = [x.strip() for x in dst.strip("{}").split(",")]
    uni = lo_reg.upper().startswith("U")
    mnem = "UMOV" if uni else "MOV"
    src = src.strip()
    if src.startswith("{"):
        s_lo, s_hi = [x.strip() for x in src.strip("{}").split(",")]
        l1 = f"{lead}{mnem} {lo_reg}, {s_lo}{br}"
        l2 = f"{lead}{mnem} {hi_reg}, {s_hi}{br}"
    else:
        imm = int(src, 16) if src.lower().startswith("0x") else int(src)
        l1 = f"{lead}{mnem} {lo_reg}, 0x{imm & 0xFFFFFFFF:X}{br}"
        l2 = f"{lead}{mnem} {hi_reg}, 0x{(imm >> 32) & 0xFFFFFFFF:X}{br}"
    return l1 + "\n" + l2


_VIADD_U32_RE = re.compile(r"(\bVIADD(?:X|XU)?)\.U32\b")
_UI_URZ_ANCHOR = re.compile(r"^\s*(?:@\S+\s+)?(?:UIADD3|USHF|UIMAD|UISHL|UISETP)\b")
_UI_URZ_TOKEN = re.compile(r"\bURZ\b")

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
    """Minimal sm_120 -> sm_90 kernel-text adaptation.

    Empirically established on H20 (see notes/sm90/arch/assembler_sm90_port.md
    "ULDC timing investigation" + follow-up probe):

    * ``ULDC`` is **synchronous**: a directly-following consumer observes the
      loaded pair through ordinary issue-ordering (stall>=1 or yield>=1) even
      with no write-scoreboard involved.  Proven by poisoning UR5 with
      0xffffffff and watching the very next LDG fault until ULDC overwrote it.
    * Hence NO special sm90 scoreboard choreography is required.  We only
      (a) normalise the mnemonic (LDCU -> ULDC, dropping its fake wr claim —
      ULDC writes no scoreboard, claiming one would falsely satisfy
      unrelated consumers),
      (b) leave every OTHER line exactly as authored, so their documented
      depcheck-verified wait sets (e.g. LDG req-waiting the param-load SB)
      keep doing the real work,
      (c) apply matcher-level dialect fixes (ELECT arg order, MOV->UMOV for
      uniform targets, VIADD .U32->.32, MOV.64 split, UI-family URZ tails).

    All heavy custom waiting lives in the test sources themselves, where
    depcheck enforces consistency.
    """
    if not is_sm90():
        return src

    dropped_scratch_done = False
    lines_in = src.split("\n")

    # Which UR pairs does each uniform const-bank load write?  Used to scope
    # the stall>=2 empirical hint (LDC.64 needs >=2 on H20) to loads whose
    # result actually feeds a desc[] consumer nearby, so latency-calibration
    # sweeps that vary stall on unrelated loads stay untouched.
    def _dst_regs(regs_field):
        names = [x.strip() for x in regs_field.strip("{}").split(",")]
        return [n for n in names if n.upper().startswith("UR")]

    ur_reg_lines = {}   # idx -> [regs]
    for i, l in enumerate(lines_in):
        head_l, sep_l, _b = l.partition(";")
        if not sep_l:
            continue
        mm = _CDESC_RE.match(l.lstrip())
        if mm:
            ur_reg_lines[i] = _dst_regs(mm.group("regs"))

    def _feeds_desc(idx):
        pend = []
        for j in range(idx + 1, min(idx + 9, len(lines_in))):
            h2, s2, _b2 = lines_in[j].partition(";")
            pend += [tok for tok in re.findall(r"UR\d+", h2)]
            if "desc[" in h2 and any(r in pend for r in ur_reg_lines.get(idx, [])):
                return True
            if any(r in re.findall(r"UR\d+", h2) for r in ur_reg_lines.get(idx, [])
                   ) and "MOV" in h2:
                pend += []          # copies propagate reachability loosely
        return False

    out_lines = []
    for _idx, line in enumerate(lines_in):
        head, sep, bracket = line.partition(";")

        if sep and is_sm90():
            # --- dialect: MOV URx,... reads as GPR-move; use UMOV ----------
            new, n = re.subn(r"^(?P<lead>\s*)MOV\s+(UR\w+)", r"\g<lead>UMOV \2", head)
            if n:
                head = new
                line = head + sep + bracket

            # --- VIADD modifier token --------------------------------------
            new, n = _VIADD_U32_RE.subn(r"\1.32", head)
            if n:
                head = new
                line = head + sep + bracket

            # --- UI-family URZ tails -> pre-zeroed scratch ------------------
            if _UI_URZ_ANCHOR.search(head) and _UI_URZ_TOKEN.search(head):
                if not dropped_scratch_done:
                    out_lines.append("    UMOV UR13, 0x0;[7:7:{}:5:1]      # adapter: zeroed scratch")
                    dropped_scratch_done = True
                new = _UI_URZ_TOKEN.sub("UR13", head)
                line = new + sep + bracket
                head, _, bracket = line.partition(";")

            # --- ELECT slot order ------------------------------------------
            if "ELECT" in head:
                new = _ELECT_RE.sub(r"ELECT \1, \2, URZ", head)
                if new != head:
                    line = new + sep + bracket
                    head, _, bracket = line.partition(";")

            # --- MOV.64 split ----------------------------------------------
            mmov = _MOV64_RE.match(line)
            if mmov:
                out_lines.extend(_split_mov64(mmov).split("\n"))
                continue

        if sep and ("LDCU" in head or "ULDC." in head or re.search(r"\bLDCU\b", head)) \
                and re.search(r"SLOT_DEFAULT_CDESC|#param\(|c\[", head):
            def _load(m):
                lead = m.group("lead")
                sz = m.group("sz") or "64"
                regs, dst = m.group("regs"), m.group("src")
                mm = _BRACKET_RE.match(m.group("bracket"))
                base_stall = int(mm.group("stall")) if mm else 1
                st = max(base_stall, 2) if _feeds_desc(_idx) else base_stall
                yl = max(int(mm.group("yield")) if mm else 0, 1)
                br2 = f"[7:7:{{}}:{st}:{yl}]"
                if verbose:
                    print(f"[archutil] {mnem_of(m.group('bracket'))}->ULDC (no wr) {br2}")
                return f"{lead}ULDC.{sz} {regs}, {dst};{br2}"
            def mnem_of(old_bracket):
                return "LDCU"
            line = _CDESC_RE.sub(_load, line)

        out_lines.append(line)
    return "\n".join(out_lines)


# --- convenience wrappers around assembler entry points ---------------------
from assembler import assemble as _assemble, assemble_kernel as _ak  # noqa: E402


def assemble(src, *a, **kw):
    """assembler.assemble with per-arch source adaptation applied."""
    return _assemble(adapt_source(src, verbose=kw.pop("verbose", False)), *a, **kw)


def assemble_kernel(src, *a, **kw):
    return _ak(adapt_source(src, verbose=kw.pop("verbose", False)), *a, **kw)
