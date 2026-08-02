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
    ("DEF_LABEL_DIRECTIVE", r"#def_label\b"),
    ("LABEL_REF_DIRECTIVE", r"#label\b"),
    ("PARAM_DIRECTIVE", r"#param\b"),
    ("PRAGMA_DIRECTIVE", r"#pragma\b"),
    ("COMMENT", r"#[^\n]*|//[^\n]*"),
    ("SEMICOLON", r";"),
    ("COMMA", r","),
    ("COLON", r":"),
    ("DOT", r"\."),
    ("PLUS", r"\+"),
    ("MINUS", r"-"),
    ("TILDE", r"~"),
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
    ("BAR", r"(?<!\.)B(?:15|1[0-4]|[0-9])\b"),
    ("SB", r"SB[0-5]\b"),
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
            # Token.col carries the absolute char offset so the parser can
            # check text adjacency (".4A" -> NUMBER+IDENT merge).
            tokens.append(Token(m.lastgroup, m.group(), line=0, col=m.start()))
        return tokens


class Parser:
    """Recursive-descent parser for SASS assembly."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def peek2(self) -> Token | None:
        return self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None

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
            if t.type == "DEF_LABEL_DIRECTIVE":
                insts.append(self._parse_def_label())
            elif t.type == "IDENT" and self._is_label():
                insts.append(self._parse_label_only())
            else:
                insts.append(self._parse_instruction())
            # consume trailing newlines
            while self.peek() and self.peek().type == "NEWLINE":
                self.pop()
        return insts

    def _parse_def_label(self) -> ParsedInstruction:
        self.pop()  # #def_label
        self.expect("LPAREN")
        name_t = self.expect("IDENT")
        self.expect("RPAREN")
        return ParsedInstruction(mnemonic="_label_", label=name_t.text, operands=[])

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
        pred = None
        pred_not = False
        # optional predicate prefix: @[!]Px
        if self.peek() and self.peek().type == "EXCLAM":
            self.pop()
            pred_not = True
        if self.peek() and self.peek().type in ("PRED", "UPRED"):
            t = self.pop()
            val = 7 if t.text.upper() == "PT" else int(t.text[1:])
            # PT with no negation = unpredicated (store as None for encoding defaults).
            # @!PT is a legitimate encoding (Pg=7, Pg_not=1, "never execute").
            pred = val if (pred_not or val != 7) else None

        mn = self.expect("IDENT")
        mnemonic = mn.text

        # modifiers: .IDENT or .NUMBER+IDENT (e.g. .2D)
        modifiers: list[str] = []
        while self.peek() and self.peek().type == "DOT":
            self.pop()
            tok = self.peek()
            if tok and tok.type == "IDENT":
                modifiers.append(self.pop().text)
            elif tok and tok.type == "REG" and tok.text.upper() == "RZ":
                # ".RZ" rounding modifier — RZ is lexed as a REG token
                modifiers.append(self.pop().text)
            elif tok and tok.type == "NUMBER":
                num_tok = self.pop()
                num = num_tok.text
                nxt = self.peek()
                # merge ".2D"-style only when the IDENT is textually adjacent
                # (no whitespace, tracked via the absolute char offset in
                # Token.col); ".64 ATEXIT_PC" stays two tokens.
                if (nxt and nxt.type == "IDENT"
                        and nxt.col == num_tok.col + len(num_tok.text)):
                    merged = num + self.pop().text
                    # ".2A.LO"/".2A.HI" — a size+alpha modifier directly
                    # followed by .LO/.HI is one enum value (IDP.2A mode).
                    if (merged[-1].isalpha() and self.peek()
                            and self.peek().type == "DOT"
                            and self.peek2() and self.peek2().type == "IDENT"
                            and self.peek2().text in ("LO", "HI")
                            and self.peek2().col == self.peek().col + 1):
                        self.pop()
                        merged += "." + self.pop().text
                    modifiers.append(merged)
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

        return ParsedInstruction(mnemonic=mnemonic, modifiers=modifiers, operands=operands, sched=sched, pred=pred, pred_not=pred_not)

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
        if self.peek() and self.peek().type == "TILDE":
            self.pop()
            op = self._parse_operand_inner()
            op.invert = True
            return op
        if self.peek() and self.peek().type == "EXCLAM":
            self.pop()
            op = self._parse_operand_inner()
            op.lnot = True
            return op
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

        # explicit register group: {Ra,Rb} / {Ra,Rb,Rc,Rd} (64/128-bit)
        if t.type == "LBRACE":
            return self._parse_reg_group()

        # registers
        if t.type == "REG":
            self.pop()
            self._reject_width_suffix(t.text)
            iswz = self._parse_iswz_suffix()
            op = Operand.reg(t.text, width=32)
            op.iswz = iswz
            return op

        if t.type == "UREG":
            self.pop()
            self._reject_width_suffix(t.text)
            iswz = self._parse_iswz_suffix()
            op = Operand.ureg(t.text, width=32)
            op.iswz = iswz
            return op

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

        # PR (predicate register file access)
        if t.type == "IDENT" and t.text == "PR":
            self.pop()
            return Operand(OperandKind.PR, 0)

        # bar register: B0..B15 (BSSY/BSYNC sync-stack id, BAR.SYNC etc.)
        if t.type == "BAR":
            self.pop()
            return Operand(OperandKind.BAR, int(t.text[1:]))

        # scoreboard: SB0..SB5 (DEPBAR)
        if t.type == "SB":
            self.pop()
            return Operand.sb(t.text)

        # label reference: #label(name)
        if t.type == "LABEL_REF_DIRECTIVE":
            self.pop()
            self.expect("LPAREN")
            name_t = self.expect("IDENT")
            self.expect("RPAREN")
            return Operand(OperandKind.LABEL, name_t.text)

        # param reference: #param(name)
        if t.type == "PARAM_DIRECTIVE":
            return self._parse_param_ref()

        # memory address: [Rx.64+offset]
        if t.type == "LBRACKET":
            return self._parse_mem_addr()

        # special register: SR_NAME[.SUB]
        if t.type == "IDENT":
            ident = self.pop().text
            # FSWZADD swizzle pattern: 8-char P/N/Z string (e.g. NPPNNPPN)
            if re.fullmatch(r"[PNZ]{8}", ident):
                pairs = {"PP": 0, "PN": 1, "NP": 2, "ZP": 3}
                val = 0
                for i in range(0, 8, 2):
                    val = val * 4 + pairs[ident[i:i + 2]]
                return Operand.np(val)
            if self.peek() and self.peek().type == "DOT":
                self.pop()
                sub = self.expect("IDENT", "NUMBER").text
                ident += "." + sub
            return Operand(OperandKind.SPECIAL_REG, ident)

        raise SyntaxError(f"unexpected token {t.type}({t.text!r})")

    def _reject_width_suffix(self, regname: str) -> None:
        """A numeric register-width suffix (.64/.128) is obsolete — every
        register of a wide operand must be listed explicitly as {Ra,Rb}."""
        if self.peek() and self.peek().type == "DOT":
            nxt = self.peek2()
            if nxt and (nxt.type == "NUMBER"
                        or (nxt.type == "IDENT" and nxt.text.isdigit())):
                raise SyntaxError(
                    f"register width suffix .{nxt.text} on {regname} is "
                    f"obsolete — list every register explicitly, e.g. "
                    f"{{{regname},{regname[:-1]}{int(regname[-1:])+1 if regname[-1].isdigit() else ''}}}"
                    f" for a 64-bit operand")

    def _parse_reg_group(self) -> Operand:
        """Parse an explicit multi-register operand {Ra,Rb} / {Ra,Rb,Rc,Rd},
        or a DEPBAR scoreboard_list bitset {0,2,4} when the members are
        plain numbers."""
        self.expect("LBRACE")
        t0 = self.peek()
        if t0 and t0.type in ("NUMBER", "HEX"):
            idxs: list[int] = []
            while True:
                t = self.expect("NUMBER", "HEX")
                idxs.append(int(t.text, 0))
                if not self.skip("COMMA"):
                    break
            self.expect("RBRACE")
            for b in idxs:
                if b < 0 or b > 5:
                    raise SyntaxError(
                        f"scoreboard_list bit {b} out of range (SB0..SB5)")
            return Operand.bitset(idxs)
        regs: list[int] = []
        uniform: bool | None = None
        while True:
            t = self.expect("REG", "UREG")
            is_uni = t.type == "UREG"
            if uniform is None:
                uniform = is_uni
            elif uniform != is_uni:
                raise SyntaxError(
                    "register group cannot mix R and UR registers")
            if t.text.upper() in ("RZ", "URZ"):
                regs.append(255)
            else:
                regs.append(int(t.text[2:] if is_uni else t.text[1:]))
            if not self.skip("COMMA"):
                break
        self.expect("RBRACE")
        if len(regs) not in (2, 4):
            raise SyntaxError(
                f"register group must list 2 (64-bit) or 4 (128-bit) "
                f"registers, got {len(regs)}")
        all_rz = all(r == 255 for r in regs)
        if not all_rz:
            if 255 in regs:
                raise SyntaxError(
                    "register group cannot mix RZ with real registers")
            for a, b in zip(regs, regs[1:]):
                if b != a + 1:
                    raise SyntaxError(
                        f"register group must be consecutive, got {regs}")
            kind = OperandKind.UREG if uniform else OperandKind.REG
            hi = 63 if uniform else 254
            for r in regs:
                if r > hi:
                    raise SyntaxError(
                        f"register {r} out of range for "
                        f"{'uniform' if uniform else 'general'} register group")
        return Operand.reg_group(regs, uniform=bool(uniform))

    _ISWZ_MAP = {"H1_H0": 0, "F32": 1, "H0_H0": 2, "H1_H1": 3, "H0_NH1": 4}

    def _parse_iswz_suffix(self) -> int | None:
        """Optional .H0_H0 / .H1_H1 / .F32 / .H0_NH1 lane-swizzle suffix
        (HFMA2/HADD2 ISWZ* operand modifiers).  Returns the enum value or None."""
        if self.peek() and self.peek().type == "DOT":
            self.pop()
            t = self.expect("IDENT")
            val = self._ISWZ_MAP.get(t.text)
            if val is None:
                raise SyntaxError(f"unknown ISWZ suffix .{t.text}")
            return val
        return None

    def _parse_mem_desc(self) -> Operand:
        self.pop()  # desc
        self.expect("LBRACKET")
        t = self.peek()
        if t and t.type == "LBRACE":
            grp = self._parse_reg_group()
            if grp.kind != OperandKind.UREG or len(grp.regs or ()) != 2:
                raise SyntaxError(
                    "descriptor must be a 64-bit uniform pair: "
                    "desc[{URx,URx+1}]")
            base = grp.regs[0]
        elif t and t.type in ("REG", "UREG"):
            raise SyntaxError(
                "single-register descriptor is ambiguous (a descriptor is "
                "always the 64-bit pair URx:URx+1) — write "
                "desc[{URx,URx+1}]")
        else:
            raise SyntaxError(
                "expected descriptor register group after 'desc['")
        self.expect("RBRACKET")
        ureg_op = Operand.ureg("URZ" if base == 255 else f"UR{base}")
        ureg_op.regs = [base, base + 1] if base != 255 else [255, 255]
        ureg_op.width = 64
        op = Operand.mem_desc(ureg_op)
        op.regs = ureg_op.regs
        op.width = 64
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
        # optional uniform-register index: [RZ + URb + off] (LDS/STS uniform)
        addr_ureg = None
        if self.peek() and self.peek().type == "PLUS":
            nxt = self.peek2()
            if nxt and nxt.type == "UREG":
                self.pop()
                self.pop()
                addr_ureg = 255 if nxt.text.upper() == "URZ" else int(nxt.text[2:])
        offset = 0
        if self.peek() and self.peek().type in ("PLUS", "MINUS"):
            sign = 1 if self.pop().type == "PLUS" else -1
            off_t = self.expect("HEX", "NUMBER")
            offset = sign * int(off_t.text, 0)
        self.expect("RBRACKET")
        op = Operand.mem_addr(base, offset=offset)
        op.width = base.width
        op.regs = base.regs
        op.addr_ureg = addr_ureg
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
            if t.type == "DEF_LABEL_DIRECTIVE":
                decl.instructions.append(self._parse_def_label())
            elif t.type == "IDENT" and self._is_label():
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
