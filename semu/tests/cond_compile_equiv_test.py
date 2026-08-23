#!/usr/bin/env python3
"""Gate: prove the compile-time condition emitter is semantically equivalent to
the reference string evaluator.

Compile-time hardening (tools/gen_isa.py) translates every legality-condition
predicate string into a generated C++ thunk (isa_data.cpp `cond_ev_*`,
`kConds[].eval`) so the decoder never runtime-parses a predicate.  This gate
checks the EMITTED C++ is correct: for every distinct sm120 predicate it

  1. emits the C++ expression (gen_isa.CondEmitter),
  2. evaluates that emitted C++ expression with a tiny interpreter over a
     randomized dense cond-slot array,
  3. compares the result to the reference evaluator
     (assembler/sass_cond.ConditionEvaluator) on the same slot values.

Predicates containing `<<` (the two `scoreboard_list & (1 << sbidx)` forms) are
excluded from the randomized sweep: the emitted C guards the shift count
against int64 UB (r<0 || r>=64 -> 0) and only diverges from the arbitrary-
precision Python reference on such impossible slot values; those two are still
covered by the real-corpus decoder_roundtrip/negative gates.

Usage: cond_compile_equiv_test.py <sm120.json>
"""
import json
import random
import re
import sys
from pathlib import Path

# some emitted predicates are deeply left-nested `||`/`->` chains; the tiny
# interpreter recurses on the parens, so raise the limit well above those.
sys.setrecursionlimit(1_000_000)

HERE = Path(__file__).resolve().parent   # .../semu/tests
REPO = HERE.parents[1]                   # .../nvidia-sass-document
sys.path.insert(0, str(REPO / "assembler"))
sys.path.insert(0, str(REPO / "semu" / "tools"))

import gen_isa  # noqa: E402
from sass_cond import ConditionEvaluator  # noqa: E402


# ---------------------------------------------------------------------------
# Tiny interpreter for the EMITTED C++ expression subset.  The generator emits
# fully parenthesized int64 expressions over `CS[N]`, integer literals,
# generated `tbl_*_NAME(args)` calls, and the operators:
#   + - % && || == != <= >= < > & << >> ! ? :
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(
    r"\s*(?:(CS)\[(\d+)\]|(s_)(\d+)|(tbl_defined_|tbl_value_)([A-Za-z0-9_.]+)|(\d+)|"
    r"(<<|>>|&&|\|\||<=|>=|==|!=)|([+\-*%/<>&|!?:(,=)])|\b(\w+)\b)")


class EmittedExpr:
    def __init__(self, text, helpers):
        self.text = text
        self.helpers = helpers  # name -> (values_list, is_value)

    # ---- helpers: generated table functions ------------------------------
    def tbl(self, name, args):
        rows, is_value = self.helpers[name]
        for row in rows:
            if tuple(row["in"]) == tuple(args):
                return row["out"] if is_value else 1
        return 0 if is_value else 0

    # ---- tokenizer --------------------------------------------------------
    def _toks(self, text):
        toks = []
        pos = 0
        while pos < len(text):
            m = _TOKEN_RE.match(text, pos)
            if not m:
                raise ValueError(f"cannot tokenize {text!r} at {pos}")
            pos = m.end()
            if m.group(1):      # CS[i]
                toks.append(("CS", int(m.group(2))))
            elif m.group(3):    # s_<pos> local (merged lambda packed slot)
                toks.append(("CS", int(m.group(4))))
            elif m.group(5):    # tbl_*_NAME
                toks.append((m.group(5) + m.group(6), None))
            elif m.group(7):    # int literal
                toks.append(("NUM", int(m.group(7))))
            elif m.group(8) or m.group(9):  # operator (multi or single char)
                toks.append(("OP", m.group(8) or m.group(9)))
        return toks

    def evaluate(self, CS):
        self.CS = CS
        self.toks = self._toks(self.text)
        self.i = 0
        v = self._ternary()
        return v

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def _eat(self, op):
        t = self._peek()
        if t and t[0] == "OP" and t[1] == op:
            self.i += 1
            return True
        return False

    def _ternary(self):
        cond = self._or()
        if self._peek() and self._peek()[0] == "OP" and self._peek()[1] == "?":
            self.i += 1
            a = self._ternary()
            if not self._eat(":"):
                raise ValueError("missing : in emitted expr")
            b = self._ternary()
            return a if cond else b
        return cond

    def _or(self):
        v = self._and()
        while self._peek() and self._peek()[0] == "OP" and self._peek()[1] == "||":
            self.i += 1
            r = self._and()
            v = (v or r)
        return v

    def _and(self):
        v = self._bitand()
        while self._peek() and self._peek()[0] == "OP" and self._peek()[1] == "&&":
            self.i += 1
            r = self._bitand()
            v = (v and r)
        return v

    def _bitand(self):
        v = self._cmp()
        while self._peek() and self._peek()[0] == "OP" and self._peek()[1] == "&":
            self.i += 1
            r = self._cmp()
            v = v & r
        return v

    def _cmp(self):
        v = self._shift()
        t = self._peek()
        if t and t[0] == "OP" and t[1] in ("==", "!=", "<=", ">=", "<", ">"):
            op = t[1]
            self.i += 1
            r = self._shift()
            return {">": v > r, "<": v < r, ">=": v >= r, "<=": v <= r,
                    "==": v == r, "!=": v != r}[op]
        return v

    def _shift(self):
        v = self._add()
        while True:
            t = self._peek()
            if t and t[0] == "OP" and t[1] in ("<<", ">>"):
                op = t[1]
                self.i += 1
                r = self._add()
                if r < 0 or r >= 64:
                    v = 0          # matches the emitted guard
                else:
                    v = v << r if op == "<<" else v >> r
            else:
                return v

    def _add(self):
        v = self._mul()
        while True:
            t = self._peek()
            if t and t[0] == "OP" and t[1] in ("+", "-"):
                op = t[1]
                self.i += 1
                r = self._mul()
                v = v + r if op == "+" else v - r
            else:
                return v

    def _mul(self):
        v = self._unary()
        while True:
            t = self._peek()
            if t and t[0] == "OP" and t[1] in ("%", "*", "/"):
                op = t[1]
                self.i += 1
                r = self._unary()
                if r == 0:
                    v = 0          # emitted % / / guard
                elif op == "%":
                    v = v % r
                elif op == "*":
                    v = v * r
                else:
                    v = v // r
            else:
                return v

    def _unary(self):
        t = self._peek()
        if t and t[0] == "OP" and t[1] == "!":
            self.i += 1
            return 0 if self._unary() else 1
        if t and t[0] == "OP" and t[1] == "-":
            self.i += 1
            return -self._unary()
        if t and t[0] == "OP" and t[1] == "(":
            self.i += 1
            v = self._ternary()
            if not self._eat(")"):
                raise ValueError("missing ) in emitted expr")
            return v
        return self._atom()

    def _atom(self):
        t = self._peek()
        if not t:
            return 0
        kind, val = t
        if kind == "CS":
            self.i += 1
            return self.CS[val]
        if kind == "NUM":
            self.i += 1
            return val
        if kind.startswith("tbl_defined_") or kind.startswith("tbl_value_"):
            name = kind
            is_value = "tbl_value_" in name
            self.i += 1
            if not self._eat("("):
                raise ValueError("missing ( for table call")
            args = [self._ternary()]
            while self._eat(","):
                args.append(self._ternary())
            if not self._eat(")"):
                raise ValueError("missing ) for table call")
            return self.tbl(name, args) if is_value else self.tbl(name, args)
        self.i += 1
        return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: cond_compile_equiv_test.py <sm120.json>", file=sys.stderr)
        return 2
    db = json.load(open(sys.argv[1]))
    variants = gen_isa.build_variants(db)
    tables = set(db["tables"].keys())

    # Emit each distinct predicate in a per-variant slot context (the emitter
    # is per-variant; slot positions only change, operators are identical).
    em = gen_isa.CondEmitter(db, {})
    distinct = set()
    for v in variants:
        for c in v["conds"]:
            distinct.add(c["predicate"])

    emitted = {}
    for pred in sorted(distinct):
        if "<<" in pred:      # covered separately by real-corpus gates
            continue
        slots = gen_isa.variant_cond_slots(
            [{"predicate": pred, "error": "", "message": ""}], tables)
        em.slot_idx = {s: pos for pos, s in enumerate(slots)}
        emitted[pred] = (em.emit(pred), slots)

    # rebuild table helpers as data for the emitter interpreter (populated by
    # the emission above)
    helpers = {}
    for name in sorted(em.table_helpers):
        rows = [{"in": [int(str(a), 0) for a in r["in"]],
                 "out": int(str(r["out"]), 0)}
                for r in db["tables"][name]["rows"]]
        helpers[f"tbl_defined_{name}"] = (rows, False)
        helpers[f"tbl_value_{name}"] = (rows, True)

    rng = random.Random(20260813)
    pool = [0, 1, 2, 3, 4, 5, 7, 8, 15, 16, 31, 63, 127, 128, 254, 255, -1]

    mismatches = 0
    total = 0
    for pred, (expr, slots) in emitted.items():
        ev = EmittedExpr(expr, helpers)
        for _ in range(40):
            sm = {s: rng.choice(pool) for s in slots}
            cs = [sm.get(s, 0) for s in slots]
            ref = ConditionEvaluator(db, sm).evaluate(pred)
            mine = ev.evaluate(cs)
            total += 1
            if bool(ref) != bool(mine):
                mismatches += 1
                if mismatches <= 10:
                    print(f"MISMATCH {pred!r} slots={sm} "
                          f"ref={bool(ref)} emitted={bool(mine)}")

    print(f"cond_compile_equiv: {total} checks, {mismatches} mismatches "
          f"({len(distinct) - 1} predicates, excl 2 shift forms)")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
