"""Condition-predicate evaluator for SASS encodings.

The sm120 ISA description attaches ``CONDITIONS`` blocks to each CLASS variant.
Each condition is ``<ERROR_TYPE> / <predicate> : "message"``: the predicate must
hold for the encoding to be legal; the named error fires when it is FALSE.

The predicate is a boolean expression over operand/modifier slot values.  See
``notes/sm90/arch/encoding_classification.md`` / ``AGENTS.md`` for the language:

    expr   := or
    or     := and ('||' and)*
    and    := cmp  ('&&' cmp)*
    impl   := or  ('->' or)?            # A->B == !A || B  (loosest)
    cmp    := add (('=='|'!='|'<='|'>='|'<'|'>') add)?
    add    := mul (('+'|'-') mul)*
    mul    := unary (('%'|'*'|'/') unary)*
    unary  := '!' unary | '-' unary | '(' expr ')' | atom
    atom   := slot | slot@attr | `Enum@Value | %param | $const | num
            | DEFINED TABLES_name(arg, ...)

Values are integers (booleans are 0/1).  ``DEFINED`` returns 1 if the argument
tuple appears as a row in the named table.

Unresolvable references are treated leniently (slot -> 0, unknown enum -> 0,
unknown table -> not defined) so an encoding is never falsely rejected just
because a field is absent from the slot_map.
"""

import re
from functools import lru_cache
from typing import Any, Optional


@lru_cache(maxsize=4096)
def tokenize(predicate: str) -> list[tuple[str, str]]:
    toks: list[tuple[str, str]] = []
    i, n = 0, len(predicate)
    while i < n:
        c = predicate[i]
        if c.isspace():
            i += 1
            continue
        if c == "`":  # enum literal `Type@Value ; Value = "quoted" or bareword
            j = i + 1
            while j < n and (predicate[j].isalnum() or predicate[j] == "_"):
                j += 1
            typ = predicate[i + 1:j]
            if j < n and predicate[j] == "@":
                j += 1
            if j < n and predicate[j] == '"':
                j += 1
                start = j
                while j < n and predicate[j] != '"':
                    j += 1
                val = predicate[start:j]
                if j < n:
                    j += 1  # closing quote
            else:
                start = j
                while j < n and (predicate[j].isalnum() or predicate[j] in "_."):
                    j += 1
                val = predicate[start:j]
            toks.append(("ENUM", f"{typ}@{val}"))
            i = j
            continue
        two = predicate[i:i + 2]
        if two in ("==", "!=", "<=", ">=", "&&", "||", "->", "<<", ">>"):
            toks.append(("OP", two))
            i += 2
            continue
        if c == "%" and i + 1 < n and (predicate[i + 1].isalnum() or predicate[i + 1] == "_"):
            j = i + 1
            while j < n and (predicate[j].isalnum() or predicate[j] == "_"):
                j += 1
            toks.append(("PARAM", predicate[i + 1:j]))
            i = j
            continue
        if c == "$" and i + 1 < n and (predicate[i + 1].isalnum() or predicate[i + 1] == "_"):
            j = i + 1
            while j < n and (predicate[j].isalnum() or predicate[j] == "_"):
                j += 1
            toks.append(("CONST", predicate[i + 1:j]))
            i = j
            continue
        if c in "()+-*%<>!@,&?:":
            toks.append(("OP", c))
            i += 1
            continue
        if c.isdigit() or (c == "-" and i + 1 < n and predicate[i + 1].isdigit()):
            if predicate[i:i + 2].lower() == "0x":
                j = i + 2
                while j < n and predicate[j] in "0123456789abcdefABCDEF":
                    j += 1
            else:
                j = i + 1
                while j < n and predicate[j].isdigit():
                    j += 1
            toks.append(("NUM", predicate[i:j]))
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i + 1
            while j < n and (predicate[j].isalnum() or predicate[j] == "_"):
                j += 1
            toks.append(("IDENT", predicate[i:j]))
            i = j
            continue
        i += 1  # unknown char — skip
    return toks


class ConditionError(Exception):
    """Raised when a condition's encoding fails (message from the spec)."""

    def __init__(self, error_type: str, message: str, predicate: str = ""):
        self.error_type = error_type
        self.message = message
        self.predicate = predicate
        super().__init__(f"{error_type}: {message}")


class ConditionEvaluator:
    def __init__(self, db: dict, slot_map: dict[str, Any]):
        self.db = db
        self.slot_map = slot_map
        self._toks: list[tuple[str, str]] = []
        self._pos = 0

    # ------------------------------------------------------------------
    def evaluate(self, predicate: str) -> bool:
        """Evaluate a single condition predicate. Conservative: any
        unresolved/parse failure returns True (does not reject)."""
        self._toks = tokenize(predicate)
        self._pos = 0
        try:
            return bool(self._impl())
        except Exception:
            return True

    def check_variant(self, variant: dict) -> list[tuple[str, str]]:
        """Return [(error_type, message), ...] for every FALSE condition."""
        failures: list[tuple[str, str]] = []
        for c in variant.get("conditions", []):
            if not self.evaluate(c["predicate"]):
                failures.append((c["error"], c.get("message", "")))
        return failures

    def eval_int(self, predicate: str) -> Optional[int]:
        """Evaluate a pure-arithmetic expression (size predicates) to an int.

        Returns None on any parse/resolve failure (caller treats as "no
        constraint").  Used for validating explicit register-group width
        against the matched variant's IDEST_SIZE/ISRC_*_SIZE."""
        self._toks = tokenize(predicate)
        self._pos = 0
        try:
            return self._impl()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Grammar
    # ------------------------------------------------------------------
    def _peek(self) -> Optional[tuple[str, str]]:
        return self._toks[self._pos] if self._pos < len(self._toks) else None

    def _peek2(self) -> Optional[tuple[str, str]]:
        return self._toks[self._pos + 1] if self._pos + 1 < len(self._toks) else None

    def _take(self) -> tuple[str, str]:
        t = self._toks[self._pos]
        self._pos += 1
        return t

    def _eat_op(self, *ops: str) -> Optional[str]:
        t = self._peek()
        if t and t[0] == "OP" and t[1] in ops:
            self._pos += 1
            return t[1]
        return None

    def _impl(self) -> int:
        left = self._or_expr()
        if self._eat_op("?"):
            # Ternary (sm90 size predicates use nested `a ? b : c`):
            # non-zero condition picks the then-branch.
            then = self._impl()
            if not self._eat_op(":"):
                raise ValueError("missing ':' in ternary predicate")
            els = self._impl()
            return then if left else els
        if self._eat_op("->"):
            right = self._or_expr()
            return 1 if (not left) or right else 0
        return left

    def _or_expr(self) -> int:
        v = self._and_expr()
        while self._eat_op("||"):
            r = self._and_expr()
            v = 1 if (v or r) else 0
        return v

    def _and_expr(self) -> int:
        v = self._bitand()
        while self._eat_op("&&"):
            r = self._bitand()
            v = 1 if (v and r) else 0
        return v

    def _bitand(self) -> int:
        v = self._cmp()
        while self._eat_op("&"):
            v = v & self._cmp()
        return v

    def _cmp(self) -> int:
        left = self._shift()
        t = self._peek()
        if t and t[0] == "OP" and t[1] in ("==", "!=", "<=", ">=", "<", ">"):
            op = t[1]
            self._pos += 1
            right = self._shift()
            return self._compare(left, op, right)
        return left

    def _shift(self) -> int:
        v = self._add()
        while True:
            t = self._peek()
            if t and t[0] == "OP" and t[1] in ("<<", ">>"):
                self._pos += 1
                r = self._add()
                v = v << r if t[1] == "<<" else v >> r
            else:
                return v

    def _add(self) -> int:
        v = self._mul()
        while True:
            t = self._peek()
            if t and t[0] == "OP" and t[1] in ("+", "-"):
                self._pos += 1
                r = self._mul()
                v = v + r if t[1] == "+" else v - r
            else:
                return v

    def _mul(self) -> int:
        v = self._unary()
        while True:
            t = self._peek()
            if t and t[0] == "OP" and t[1] in ("%", "*", "/"):
                self._pos += 1
                r = self._unary()
                if t[1] == "%":
                    v = v % r if r else 0
                elif t[1] == "*":
                    v = v * r
                else:
                    v = v // r if r else 0
            else:
                return v

    def _unary(self) -> int:
        t = self._peek()
        if t and t[0] == "OP" and t[1] == "!":
            self._pos += 1
            return 0 if self._unary() else 1
        if t and t[0] == "OP" and t[1] == "-":
            self._pos += 1
            return -self._unary()
        if t and t[0] == "OP" and t[1] == "(":
            self._pos += 1
            v = self._impl()
            self._eat_op(")")
            return v
        return self._atom()

    # ------------------------------------------------------------------
    # Atoms / values
    # ------------------------------------------------------------------
    def _atom(self) -> int:
        t = self._peek()
        if not t:
            return 0
        k, v = t
        if k == "IDENT" and v == "DEFINED":
            return self._defined()
        nxt = self._peek2()
        if k == "IDENT" and nxt and nxt[0] == "OP" and nxt[1] == "@":
            self._pos += 2  # consume IDENT + '@'
            attr_t = self._peek()
            self._pos += 1
            return self._slot_attr(v, attr_t[1] if attr_t else "")
        if k == "IDENT":
            self._pos += 1
            return self._slot(v)
        if k == "PARAM":
            self._pos += 1
            return self._param(v)
        if k == "CONST":
            self._pos += 1
            return self._const(v)
        if k == "ENUM":
            self._pos += 1
            return self._enum(v)
        if k == "NUM":
            self._pos += 1
            try:
                return int(v, 0)
            except ValueError:
                return 0
        self._pos += 1
        return 0

    def _defined(self) -> int:
        self._pos += 1  # consume 'DEFINED'
        name_t = self._peek()
        self._pos += 1  # consume table name
        if not name_t or name_t[0] != "IDENT":
            return 0
        table_name = name_t[1]
        self._eat_op("(")
        args: list[str] = []
        while True:
            args.append(self._resolve_arg())
            if not self._eat_op(","):
                break
        self._eat_op(")")
        table = self.db.get("tables", {}).get(table_name)
        if not table:
            return 0
        for row in table.get("rows", []):
            if list(row.get("in", [])) == args:
                return 1
        return 0

    def _resolve_arg(self) -> str:
        """Resolve a table argument to its canonical string form."""
        t = self._peek()
        if not t:
            return "0"
        k, v = t
        if k == "PARAM":
            self._pos += 1
            return str(self._param(v))
        if k == "CONST":
            self._pos += 1
            return str(self._const(v))
        if k == "ENUM":
            self._pos += 1
            return str(self._enum(v))
        if k == "NUM":
            self._pos += 1
            return str(int(v, 0))
        if k == "IDENT":
            self._pos += 1
            nxt = self._peek()
            if nxt and nxt[0] == "OP" and nxt[1] == "@":
                self._pos += 1
                attr_t = self._peek()
                self._pos += 1
                return str(self._slot_attr(v, attr_t[1] if attr_t else ""))
            return str(self._slot(v))
        self._pos += 1
        return "0"

    # ------------------------------------------------------------------
    # Value resolution
    # ------------------------------------------------------------------
    def _slot(self, name: str) -> int:
        val = self.slot_map.get(name)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return int(val)
        return 0

    def _slot_attr(self, slot: str, attr: str) -> int:
        # Predicate attr names map to slot_map flag suffixes (same as
        # SassEncoder._resolve_slot_attr).
        suffix = {"not": "not", "invert": "invert",
                  "negate": "negated", "absolute": "abs"}.get(attr, attr)
        val = self.slot_map.get(f"{slot}_{suffix}")
        return 1 if val else 0

    def _param(self, name: str) -> int:
        val = self.db.get("parameters", {}).get(name)
        if isinstance(val, bool):
            return 1 if val else 0
        if isinstance(val, (int, float)):
            return int(val)
        return 0

    def _const(self, name: str) -> int:
        val = self.db.get("constants", {}).get(name)
        if isinstance(val, bool):
            return 1 if val else 0
        if isinstance(val, (int, float)):
            return int(val)
        return 0

    def _enum(self, literal: str) -> int:
        """Resolve `Type@Value via db['enums'] (value may be quoted)."""
        if "@" not in literal:
            return 0
        etype, _, value = literal.partition("@")
        value = value.strip('"')
        enum_vals = self.db.get("enums", {}).get(etype, {})
        if value in enum_vals:
            return int(enum_vals[value])
        # AInteger-style aliases: '_64' vs '64'
        if value.startswith("_") and value[1:] in enum_vals:
            return int(enum_vals[value[1:]])
        if not value.startswith("_") and "_" + value in enum_vals:
            return int(enum_vals["_" + value])
        try:
            return int(value, 0)
        except ValueError:
            return 0

    @staticmethod
    def _compare(left: int, op: str, right: int) -> int:
        if op == "==":
            return 1 if left == right else 0
        if op == "!=":
            return 1 if left != right else 0
        if op == "<=":
            return 1 if left <= right else 0
        if op == ">=":
            return 1 if left >= right else 0
        if op == "<":
            return 1 if left < right else 0
        if op == ">":
            return 1 if left > right else 0
        return 0
