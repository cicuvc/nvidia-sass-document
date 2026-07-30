from __future__ import annotations
import re
from typing import Iterator

from .operand import Operand, OperandKind, ParsedInstruction, Sched

# --- Token types ---
from .operand import Operand, OperandKind, ParsedInstruction, Sched, ParamDecl, KernelDecl

TOKENS = [
    ("NEWLINE", r"\n|\r\n?"),
    ("SKIP", r"[ \t]+"),
    ("FN_DIRECTIVE", r"#fn\b"),
    ("PARAM_DIRECTIVE", r"#param\b"),
    ("PRAGMA_DIRECTIVE", r"#pragma\b"),
    ("COMMENT", r"#[^\n]*|//[^\n]*"),
    ("SEMICOLON", r";"),
    ("COMMA", r","),
    ("COLON", r":"),
    ("DOT", r"\."),
    ("PLUS", r"\+"),
    ("MINUS", r"-"),
    ("LBRACKET", r"\["),
    ("RBRACKET", r"\]"),
    ("LBRACE", r"\{"),
    ("RBRACE", r"\}"),
    ("EXCLAM", r"!"),
    ("PIPE", r"\|"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("LT", r"<"),
    ("GT", r">"),
    ("FLOAT_IMM", r"0f[0-9a-fA-F]{8}"),
    ("HEX", r"0x[0-9a-fA-F]+"),
    ("NUMBER", r"[0-9]+"),
    ("REG", r"R(?:Z|[0-9]+)\b"),
    ("UREG", r"UR(?:Z|[0-9]+)\b"),
    ("PRED", r"(?:P[0-6]|PT)\b"),
    ("UPRED", r"(?:UP[0-6]|UPT)\b"),
    ("IDENT", r"[A-Za-z_][A-Za-z0-9_]*"),
]

TOKEN_RE = re.compile("|".join(f"(?P<{name}>{pat})" for name, pat in TOKENS))


class Token:
    __slots__ = ("type", "text", "line", "col")

    def __init__(self, type: str, text: str, line: int = 0, col: int = 0):
        self.type = type
        self.text = text
        self.line = line
        self.col = col

    def __repr__(self) -> str:
        return f"Token({self.type}, {self.text!r})"


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        for m in TOKEN_RE.finditer(self.source):
            if m.lastgroup is None or m.lastgroup == "SKIP":
                continue
            if m.lastgroup == "COMMENT":
                continue
            tokens.append(Token(m.lastgroup, m.group()))
        return tokens


class Parser:
    """Recursive-descent parser for SASS assembly."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def pop(self) -> Token:
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def expect(self, *types: str) -> Token:
        t = self.peek()
        if t is None:
            got = "EOF"
            raise SyntaxError(f"expected {types}, got {got}")
        if t.type not in types:
            raise SyntaxError(f"expected {types}, got {t.type}({t.text!r})")
        return self.pop()

    def skip(self, *types: str) -> bool:
        if self.peek() and self.peek().type in types:
            self.pop()
            return True
        return False

    def parse(self) -> list[ParsedInstruction]:
        insts: list[ParsedInstruction] = []
        while self.pos < len(self.tokens):
            t = self.peek()
            if t.type == "NEWLINE":
                self.pop()
                continue
            if t.type == "IDENT" and self._is_label():
                insts.append(self._parse_label_only())
            else:
                insts.append(self._parse_instruction())
            # consume trailing newlines
            while self.peek() and self.peek().type == "NEWLINE":
                self.pop()
        return insts

    def _is_label(self) -> bool:
        # label is IDENT followed by ':'
        pos = self.pos
        if self.tokens[pos].type != "IDENT":
            return False
        pos += 1
        return pos < len(self.tokens) and self.tokens[pos].type == "COLON"

    def _parse_label_only(self) -> ParsedInstruction:
        t = self.pop()
        self.expect("COLON")
        return ParsedInstruction(mnemonic="_label_", label=t.text, operands=[])

    def _parse_instruction(self) -> ParsedInstruction:
        operands: list[Operand] = []
        # optional predicate prefix: @[!]Px
        if self.skip("EXCLAM"):
            pass
        if self.peek() and self.peek().type in ("PRED", "UPRED"):
            self.pop()  # skip predicate for now

        mn = self.expect("IDENT")
        mnemonic = mn.text

        # modifiers: .IDENT or .NUMBER+IDENT (e.g. .2D)
        modifiers: list[str] = []
        while self.peek() and self.peek().type == "DOT":
            self.pop()
            tok = self.peek()
            if tok and tok.type == "IDENT":
                modifiers.append(self.pop().text)
            elif tok and tok.type == "NUMBER":
                num = self.pop().text
                if self.peek() and self.peek().type == "IDENT":
                    modifiers.append(num + self.pop().text)
                else:
                    modifiers.append(num)
            elif tok and tok.type == "HEX":
                modifiers.append(self.pop().text)
            else:
                raise SyntaxError(f"expected modifier after '.', got {tok}")

        if self.peek() and self.peek().type not in ("SEMICOLON", "NEWLINE"):
            operands = self._parse_operands()

        if not (self.peek() and self.peek().type == "SEMICOLON"):
            raise SyntaxError("missing ';' and scheduling bracket [wr:rd:{req}:stall:yield]")
        self.pop()  # SEMICOLON
        if not (self.peek() and self.peek().type == "LBRACKET"):
            raise SyntaxError(
                "scheduling bracket required: [wr_sb:rd_sb:{req_bits}:stall:yield]")
        bracket = self._parse_bracket()
        sched = Sched.parse(bracket)

        return ParsedInstruction(mnemonic=mnemonic, modifiers=modifiers, operands=operands, sched=sched)

    def _parse_operands(self) -> list[Operand]:
        ops: list[Operand] = []
        first = True
        while True:
            if not first:
                if not self.skip("COMMA"):
                    break
            first = False
            if self.peek() is None or self.peek().type in ("SEMICOLON", "NEWLINE"):
                break
            ops.append(self._parse_operand())
        return ops

    def _parse_operand(self) -> Operand:
        # check for negated/absolute prefix
        negated = False
        absolute = False
        if self.peek() and self.peek().type == "MINUS":
            self.pop()
            negated = True
            if self.peek() and self.peek().type == "PIPE":
                self.pop()
                absolute = True
                op = self._parse_operand_inner()
                self.expect("PIPE")
                op.negated = True
                op.absolute = True
                return op
            op = self._parse_operand_inner()
            op.negated = True
            return op
        if self.peek() and self.peek().type == "PIPE":
            self.pop()
            op = self._parse_operand_inner()
            self.expect("PIPE")
            op.absolute = True
            return op

        return self._parse_operand_inner()

    def _parse_operand_inner(self) -> Operand:
        t = self.peek()
        if t is None:
            raise SyntaxError("unexpected EOF in operand")

        # immediate floats: 0fXXXXXXXX
        if t.type == "FLOAT_IMM":
            self.pop()
            val = int(t.text[2:], 16)
            import struct
            fval = struct.unpack(">f", struct.pack(">I", val))[0]
            return Operand.imm_f32(fval)

        # hex/number immediate
        if t.type in ("HEX", "NUMBER"):
            self.pop()
            val = int(t.text, 0)
            return Operand.imm_u(val)

        # minus followed by number => signed immediate
        if t.type == "MINUS":
            self.pop()
            t2 = self.expect("HEX", "NUMBER")
            val = -int(t2.text, 0)
            return Operand.imm_s(val)

        # registers
        if t.type == "REG":
            self.pop()
            width = self._parse_width_suffix()
            return Operand.reg(t.text, width=width)

        if t.type == "UREG":
            self.pop()
            width = self._parse_width_suffix()
            return Operand.ureg(t.text, width=width)

        if t.type == "PRED":
            self.pop()
            return Operand.pred(t.text)

        if t.type == "UPRED":
            self.pop()
            return Operand.upred(t.text)

        # memory descriptor: desc[URx.64]
        if t.type == "IDENT" and t.text == "desc":
            return self._parse_mem_desc()

        # const bank: c[bank][offset]
        if t.type == "IDENT" and t.text == "c":
            return self._parse_const_bank()

        # param reference: #param(name)
        if t.type == "PARAM_DIRECTIVE":
            return self._parse_param_ref()

        # memory address: [Rx.64+offset]
        if t.type == "LBRACKET":
            return self._parse_mem_addr()

        # special register: SR_NAME[.SUB]
        if t.type == "IDENT":
            ident = self.pop().text
            if self.peek() and self.peek().type == "DOT":
                self.pop()
                sub = self.expect("IDENT", "NUMBER").text
                ident += "." + sub
            return Operand(OperandKind.SPECIAL_REG, ident)

        raise SyntaxError(f"unexpected token {t.type}({t.text!r})")

    def _parse_width_suffix(self) -> int:
        if self.peek() and self.peek().type == "DOT":
            self.pop()
            w = self.expect("IDENT", "NUMBER", "HEX")
            return int(w.text) if w.text.isdigit() else 32
        return 32

    def _parse_mem_desc(self) -> Operand:
        self.pop()  # desc
        self.expect("LBRACKET")
        t = self.peek()
        if t and t.type == "REG":
            self.pop()
            ureg_val = 255 if t.text.upper() == "RZ" else int(t.text[1:])
            ureg_op = Operand(OperandKind.UREG, ureg_val)
        else:
            t = self.expect("UREG")
            ureg_op = Operand.ureg(t.text)
        width = self._parse_width_suffix()
        self.expect("RBRACKET")
        op = Operand.mem_desc(ureg_op)
        if self.peek() and self.peek().type == "LBRACKET":
            addr = self._parse_mem_addr()
            op.addr_reg = addr.value if isinstance(addr.value, int) else 0
            op.offset = addr.offset
            op.width = addr.width
        return op

    def _parse_param_ref(self) -> Operand:
        self.pop()  # #param
        self.expect("LPAREN")
        name_t = self.expect("IDENT")
        self.expect("RPAREN")
        return Operand(OperandKind.PARAM_REF, name_t.text)

    def _parse_const_bank(self) -> Operand:
        self.pop()  # c
        self.expect("LBRACKET")
        bank_t = self.expect("HEX", "NUMBER")
        bank = int(bank_t.text, 0)
        self.expect("RBRACKET")
        self.expect("LBRACKET")
        off_t = self.expect("HEX", "NUMBER")
        offset = int(off_t.text, 0)
        self.expect("RBRACKET")
        return Operand.const_bank(bank, offset)

    def _parse_mem_addr(self) -> Operand:
        self.pop()  # LBRACKET
        t = self.peek()
        if t is None:
            raise SyntaxError("unexpected EOF in memory address")
        base = self._parse_operand_inner()
        # base already consumed its .width suffix; don't call _parse_width_suffix again
        offset = 0
        if self.peek() and self.peek().type in ("PLUS", "MINUS"):
            sign = 1 if self.pop().type == "PLUS" else -1
            off_t = self.expect("HEX", "NUMBER")
            offset = sign * int(off_t.text, 0)
        self.expect("RBRACKET")
        op = Operand.mem_addr(base, offset=offset)
        op.width = base.width
        return op

    def parse_kernel(self) -> KernelDecl:
        """Parse a #fn name(p1<4>, p2<8>, ...) { ... } block."""
        while self.peek() and self.peek().type == "NEWLINE":
            self.pop()
        self.expect("FN_DIRECTIVE")
        name_t = self.expect("IDENT")
        decl = KernelDecl(name=name_t.text)

        # parameters: (p1<4>, p2<8>, ...)
        self.expect("LPAREN")
        while self.peek() and self.peek().type != "RPAREN":
            p = self.peek()
            if p.type == "COMMA":
                self.pop()
                continue
            pname = self.expect("IDENT").text
            # optional <size> suffix
            psize = 4
            if self.peek() and self.peek().type == "LT":
                self.pop()
                sz_t = self.expect("NUMBER", "HEX")
                psize = int(sz_t.text, 0)
                self.expect("GT")
            decl.params.append(ParamDecl(name=pname, size=psize))
        self.expect("RPAREN")

        # allocate cmem offsets for params
        decl.layout_params()

        # { ... } body
        self.expect("LBRACE")

        # Parse pragmas and instructions until }
        while self.peek() and self.peek().type != "RBRACE":
            t = self.peek()
            if t.type == "NEWLINE":
                self.pop()
                continue
            if t.type == "PRAGMA_DIRECTIVE":
                self._parse_pragma(decl)
                continue
            if t.type == "IDENT" and self._is_label():
                decl.instructions.append(self._parse_label_only())
            else:
                inst = self._parse_instruction()
                self._resolve_params(inst, decl)
                decl.instructions.append(inst)
            while self.peek() and self.peek().type == "NEWLINE":
                self.pop()

        self.expect("RBRACE")
        return decl

    def _parse_pragma(self, decl: KernelDecl) -> None:
        self.pop()  # #pragma
        name_t = self.expect("IDENT")
        attr_name = name_t.text
        if self.peek() and self.peek().type == "LPAREN":
            self.pop()
            val_t = self.expect("NUMBER", "HEX")
            decl.attributes[attr_name] = int(val_t.text, 0)
            self.expect("RPAREN")

    def _resolve_params(self, inst: ParsedInstruction, decl: KernelDecl) -> None:
        """Replace PARAM_REF operands with CONST_BANK using actual cmem offsets."""
        for op in inst.operands:
            if op.kind == OperandKind.PARAM_REF:
                pname = op.value
                found = None
                for p in decl.params:
                    if p.name == pname:
                        found = p
                        break
                if found is None:
                    raise SyntaxError(f"unknown parameter {pname!r}")
                abs_off = decl.param_base + found.ordinal
                op.kind = OperandKind.CONST_BANK
                op.value = 0
                op.offset = abs_off

    def _parse_bracket(self) -> str:
        self.pop()  # LBRACKET
        parts: list[str] = []
        depth = 1
        while self.peek() and depth > 0:
            t = self.pop()
            if t.type == "LBRACKET":
                depth += 1
            elif t.type == "RBRACKET":
                depth -= 1
                if depth == 0:
                    break
            parts.append(t.text)
        return "[" + "".join(parts) + "]"


def parse_sass(source: str) -> list[ParsedInstruction]:
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    if tokens and tokens[0].type == "FN_DIRECTIVE":
        return []  # use parse_kernel instead
    return parser.parse()


def parse_kernel(source: str) -> KernelDecl:
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    return parser.parse_kernel()
