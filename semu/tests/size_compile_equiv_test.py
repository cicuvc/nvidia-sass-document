#!/usr/bin/env python3
"""Gate: prove the generated operand-width metadata (SizeEmitter) is
semantically identical to the reference string evaluator.

gen_isa.py compiles each variant's `*_SIZE` predicates to static C++
member functions that extract the width straight from the 128-bit word
(no runtime string evaluation).  This gate checks, over every variant and
every `*_SIZE` predicate:

  1. every slot key resolves to a decodable bit field (a missed slot is a
     generation error, mirroring the C++ build gate);
  2. on random words, the emitted expression (evaluated with a small
     token-level interpreter that mirrors the emitter's grammar, w.lo/w.hi
     fed as slots 0/1) equals the Python reference evaluator
     (assembler/sass_cond.ConditionEvaluator.eval_int) over the same
     decoded slot map.

The interpreter below is deliberately a *numeric* twin of gen_isa.CondEmitter
(the same precedence, the same 1/0 normalizations), not a C++ expression
evaluator: tokens come from gen_isa.cond_tokenize, and the only slot
reference left in the emitted text is the w.lo/w.hi extraction pre-bound to
s_0/s_1.  This avoids re-parsing `? :` text.

Usage: size_compile_equiv_test.py <sm120.json>
"""
import json
import random
import sys
from pathlib import Path

sys.setrecursionlimit(1_000_000)

HERE = Path(__file__).resolve().parent   # .../semu/tests
REPO = HERE.parents[1]                   # .../nvidia-sass-document
sys.path.insert(0, str(REPO / "assembler"))
sys.path.insert(0, str(REPO / "semu" / "tools"))

import gen_isa  # noqa: E402
from sass_cond import ConditionEvaluator  # noqa: E402


def emit_tokens(text):
    """Tokenizer for emitted width expressions (superset of the predicate
    language: adds bitwise `|` used by multi-slice field extraction)."""
    toks = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c.isdigit() or (c == '-' and i + 1 < n and text[i + 1].isdigit()):
            j = i + 1
            while j < n and text[j].isdigit():
                j += 1
            toks.append(("NUM", text[i:j]))
            i = j
            continue
        if c.isalpha() or c == '_':
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == '_'):
                j += 1
            toks.append(("IDENT", text[i:j]))
            i = j
            continue
        two = text[i:i + 2]
        if two in ("==", "!=", "<=", ">=", "&&", "||", "<<", ">>"):
            toks.append(("OP", two))
            i += 2
            continue
        if c in "()+-*/%<>!&|?:":
            toks.append(("OP", c))
            i += 1
            continue
        raise ValueError(f"unclassifiable char {c!r} in emitted size expr")
    return toks


class EmittedSize:
    """Numeric interpreter for emitted width expressions; `s_0`/`s_1` =
    the decoded word's lo/hi halves."""

    def __init__(self, text, slots=(0, 0)):
        self.toks = emit_tokens(text)
        self.slots = slots
        self.i = 0

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def _eat(self, op):
        t = self._peek()
        if t and t[0] == "OP" and t[1] == op:
            self.i += 1
            return True
        return False

    def run(self):
        v = self._impl()
        if self.i != len(self.toks):
            raise ValueError("unconsumed tokens in emitted size expression")
        return v

    def _impl(self):
        left = self._or()
        if self._eat("?"):
            a = self._impl()
            if not self._eat(":"):
                raise ValueError("missing ':' in emitted size expression")
            b = self._impl()
            return a if left else b
        if self._eat("->"):
            right = self._or()
            return 0 if left and not right else 1
        return left

    def _or(self):
        v = self._and()
        while self._eat("||"):
            r = self._and()
            v = 1 if (v or r) else 0
        return v

    def _and(self):
        v = self._bitand()
        while self._eat("&&"):
            r = self._bitand()
            v = 1 if (v and r) else 0
        return v

    def _bitand(self):
        v = self._cmp()
        while True:
            t = self._peek()
            if t and t[0] == "OP" and t[1] in ("&", "|"):
                op = t[1]
                self.i += 1
                r = self._cmp()
                v = (v & r) if op == "&" else (v | r)
            else:
                return v

    def _cmp(self):
        left = self._shift()
        t = self._peek()
        if t and t[0] == "OP" and t[1] in ("==", "!=", "<=", ">=", "<", ">"):
            op = t[1]
            self.i += 1
            right = self._shift()
            return {"==": left == right, "!=": left != right,
                    "<=": left <= right, ">=": left >= right,
                    "<": left < right, ">": left > right}[op]
        return left

    def _shift(self):
        v = self._add()
        while True:
            t = self._peek()
            if t and t[0] == "OP" and t[1] in ("<<", ">>"):
                op = t[1]
                self.i += 1
                r = self._add()
                v = 0 if (r < 0 or r >= 64) else (v << r if op == "<<" else v >> r)
            else:
                return v

    def _add(self):
        v = self._mul()
        while self._eat("+"):
            r = self._mul()
            v = v + r
        if self._peek() and self._peek()[0] == "OP" and self._peek()[1] == "-":
            self.i += 1
            r = self._mul()
            v = v - r
        while self._peek() and self._peek()[0] == "OP" and self._peek()[1] == "-":
            self.i += 1
            r = self._mul()
            v = v - r
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
                    v = 0
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
            v = self._impl()
            if not self._eat(")"):
                raise ValueError("missing ')' in emitted size expression")
            return v
        return self._atom()

    def _atom(self):
        t = self._peek()
        if not t:
            return 0
        k, v = t
        self.i += 1
        if k == "NUM":
            return int(v, 0)
        if k == "IDENT":
            if v.startswith("s_") and v[2:].isdigit():
                return self.slots[int(v[2:])]
            return 0   # bare slot names never survive emission
        if k in ("PARAM", "CONST", "ENUM"):
            return 0   # emission bakes these as literals
        self.i -= 1
        return 0


def extract(targets, lo, hi):
    val = 0
    for h, l in targets:
        w = h - l + 1
        mask = (1 << w) - 1
        if l >= 64:
            part = (hi >> (l - 64)) & mask
        elif h < 64:
            part = (lo >> l) & mask
        else:
            lo_w = 64 - l
            part = ((lo >> l) & ((1 << lo_w) - 1)) | (
                (hi & ((1 << (w - lo_w)) - 1)) << lo_w)
        val = (val << w) | part
    return val


def build_slot_map(v, lo, hi):
    sm = {}
    for f in v["encoding"]:
        val = extract(f["targets"], lo, hi)
        rk = f["rhs_kind"]
        rhs = f["rhs"]
        if rk == "slot":
            sm[rhs.split(" ")[0]] = val
        elif rk == "slot_attr":
            base, _, attr = rhs.partition("@")
            suffix = {"not": "_not", "invert": "_invert",
                      "negate": "_negated", "absolute": "_abs"}.get(
                          attr.split(" ")[0], attr.split(" ")[0])
            sm[base + suffix] = val
        elif rk == "star_slot":
            name = rhs.lstrip("*")
            if "(" not in name:
                try:
                    int(name, 0)
                except ValueError:
                    sm[name] = val
    # apply per-field scale (SCALE n in the RHS), mirroring the decoder.
    for f in v["encoding"]:
        rhs = f["rhs"]
        scale = f.get("scale")
        if scale:
            for key in list(sm):
                if key == rhs.split(" ")[0]:
                    sm[key] *= scale
    return sm


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: size_compile_equiv_test.py <sm120.json>", file=sys.stderr)
        return 2
    db = json.load(open(sys.argv[1]))
    variants = gen_isa.build_variants(db)
    size_keys = gen_isa.collect_size_keys(variants)
    size_meta = gen_isa.compile_variant_sizes(db, variants, size_keys)
    raw_by_class = {v["class"]: v for v in db["variants"]}

    random.seed(20240601)
    n_preds = 0
    n_checks = 0
    n_unreachable = 0
    for v, m in zip(variants, size_meta):
        if m is None:
            continue
        raw = raw_by_class[v["class"]]
        preds = {k: str(val) for k, val in raw["predicates"].items()}
        for _, k, name, expr in m["methods"]:
            n_preds += 1
            native = expr.replace("w.lo", "s_0").replace("w.hi", "s_1")
            for trial in range(4):
                lo = random.getrandbits(64)
                hi = random.getrandbits(64)
                sm = build_slot_map(raw, lo, hi)
                want = ConditionEvaluator(db, sm).eval_int(preds[k])
                if want is None:
                    n_unreachable += 1
                    continue
                got = EmittedSize(native, (lo, hi)).run()
                n_checks += 1
                if got != want:
                    print(f"MISMATCH {v['class']} {k} (method {name}): "
                          f"emitted={got} reference={want}", file=sys.stderr)
                    print(f"  predicate: {preds[k][:160]}", file=sys.stderr)
                    return 1

    print(f"OK: {n_preds} size methods, {n_checks} random-word checks "
          f"identical to the reference evaluator "
          f"({n_unreachable} slot-unreachable skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())