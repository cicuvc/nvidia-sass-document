#!/usr/bin/env python3
"""SM120 SASS assembler CLI.

Usage:
  python3 -m assembler.sass_asm input.sass [-o output.cubin]
"""
import argparse
import json
import re
import struct
import sys
from pathlib import Path

from .sass_parser import Lexer, Parser, parse_sass, parse_kernel
from .sass_matcher import create_matcher, MatchError
from .sass_encoder import SassEncoder
from .sass_elf import CubinBuilder, ElfError
from .operand import OperandKind, KernelDecl


def fmt_operand(op) -> str:
    kind = op.kind
    if kind == OperandKind.REG:
        if op.regs:
            return "{" + ", ".join("RZ" if r == 255 else f"R{r}" for r in op.regs) + "}"
        s = f"R{op.value}" if op.value != 255 else "RZ"
        return s
    if kind == OperandKind.UREG:
        if op.regs:
            return "{" + ", ".join("URZ" if r in (63, 255) else f"UR{r}" for r in op.regs) + "}"
        s = "URZ" if op.value in (63, 255) else f"UR{op.value}"
        return s
    if kind == OperandKind.INDEXED_RF:
        s = "URZ" if op.value in (63, 255) else f"UR{op.value}"
        return f"R[{s}]"
    if kind == OperandKind.PRED:
        return f"P{op.value}" if op.value != 7 else "PT"
    if kind == OperandKind.UPRED:
        return f"UP{op.value}" if op.value != 7 else "UPT"
    if kind == OperandKind.IMM_U:
        if op.value < 10:
            return str(op.value)
        return f"0x{op.value:x}"
    if kind == OperandKind.IMM_S:
        return str(op.value)
    if kind == OperandKind.IMM_F32:
        return f"0f{op.value}"
    if kind == OperandKind.SPECIAL_REG:
        return str(op.value)
    if kind == OperandKind.CONST_BANK:
        return f"c[0x{op.offset:x}]"  # simplified
    if kind == OperandKind.MEM_DESC:
        if op.regs:
            return "desc[{" + ", ".join("URZ" if r == 255 else f"UR{r}" for r in op.regs) + "}]"
        return "desc[URZ]" if op.value in (63, 255) else f"desc[UR{op.value}]"
    if kind == OperandKind.MEM_ADDR:
        off = f"+0x{op.offset:x}" if op.offset >= 0 else f"-0x{-op.offset:x}"
        if op.regs:
            base = "{" + ", ".join(f"R{r}" for r in op.regs) + "}"
            return f"[{base}{off}]"
        return f"[R{op.value}.64{off}]"
    return f"<?{kind.name}>"


def fmt_operand_dbg(op) -> str:
    base = fmt_operand(op)
    extra = ""
    if op.negated:
        extra = " neg"
    if op.absolute:
        extra += " abs"
    return f"{base:<20} kind={op.kind.name:<12} val={op.value} w={op.width}{extra}"


def dump_instructions(insts, verbose=False) -> None:
    for i, inst in enumerate(insts):
        if inst.label:
            print(f"{inst.label}:")
            if inst.mnemonic == "_label_":
                continue
        parts = [inst.mnemonic]
        if inst.modifiers:
            parts.append("." + ".".join(inst.modifiers))
        if inst.operands:
            parts.append(" ")
            parts.append(", ".join(fmt_operand(o) for o in inst.operands))
        line = "".join(parts)
        s = inst.sched
        req = ",".join(str(r) for r in sorted(s.req_bits)) if s.req_bits else ""
        bracket = f"[{s.wr_sb}:{s.rd_sb}:{{{req}}}:{s.stall}:{s.yield_val}]"
        print(f"  [{i:3d}] {line};{bracket}")
        if verbose:
            for o in inst.operands:
                print(f"         {fmt_operand_dbg(o)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="SASS assembler (sm90/sm120)")
    ap.add_argument("input", type=str, help="Input .sass file")
    ap.add_argument("-o", "--output", type=str, default=None, help="Output .cubin path")
    ap.add_argument("-n", "--kernel-name", type=str, default="my_kernel", help="Kernel name")
    ap.add_argument("--arch", type=str, default=None,
                    help="Target arch: sm90 or sm120 (default: process arch)")
    ap.add_argument("--template", type=str, default=None, help="Minimal cubin template path (required for -o)")
    ap.add_argument("--dump-text", type=str, default=None, help="Dump raw instruction bytes to file (no ELF)")
    ap.add_argument("--dump", action="store_true", default=True, help="Dump parsed instructions")
    ap.add_argument("-v", "--verbose", action="store_true", help="Verbose operand detail")
    ap.add_argument("--debug-tokens", action="store_true", help="Dump raw tokens")
    ap.add_argument("--no-check-deps", action="store_true",
                    help="Disable the scoreboard dependency checker")
    ap.add_argument("--strict-deps", action="store_true",
                    help="Treat dependency warnings as errors (exit 1)")
    args = ap.parse_args()

    # The matcher is architecture-specific.  Select it before parsing and
    # matching (the old CLI switched only immediately before encoding).
    from . import arch
    if args.arch:
        arch.set_arch(args.arch)

    path = Path(args.input)
    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 1

    source = path.read_text()

    if args.debug_tokens:
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        print(f"Tokens ({len(tokens)}):")
        for t in tokens:
            print(f"  {t.type:15} {t.text!r}")

    # Detect kernel declaration vs standalone instructions
    kernel: KernelDecl | None = None
    try:
        if re.search(r"(?m)^\s*#fn\b", source):
            kernel = parse_kernel(source)
            from .sass_builtins import expand_builtins
            expand_builtins(kernel)
            insts = kernel.instructions
        else:
            insts = parse_sass(source)
    except SyntaxError as e:
        print(f"syntax error: {e}", file=sys.stderr)
        return 1

    # Resolve PC-relative labels before matching: LABEL is parser IR, not an
    # ISA operand kind.  Directives are zero-width in the final layout.
    labels: dict[str, int] = {}
    addrs: list[int] = []
    pc = 0
    for inst in insts:
        if inst.mnemonic == "_label_":
            labels.setdefault(inst.label, pc)
        addrs.append(pc)
        if not inst.mnemonic.startswith("_"):
            pc += 16
    for inst, ia in zip(insts, addrs):
        for op in inst.operands:
            if op.kind == OperandKind.LABEL:
                if op.value not in labels:
                    print(f"matching error: undefined label {op.value!r}",
                          file=sys.stderr)
                    return 1
                op.kind = OperandKind.IMM_S
                op.value = labels[op.value] - (ia + 16)

    # Match each instruction to a CLASS variant
    try:
        matcher = create_matcher()
        results = []
        for inst in insts:
            if inst.mnemonic.startswith("_"):
                results.append(None)
                continue
            results.append(matcher.match(inst))
    except MatchError as e:
        print(f"matching error: {e}", file=sys.stderr)
        return 1

    if args.dump:
        label = f"kernel {kernel.name}" if kernel else f"{len(insts)} instruction(s)"
        print(f"Parsed {label}:\n")
        for i, inst in enumerate(insts):
            if inst.label:
                print(f"{inst.label}:")
                if inst.mnemonic == "_label_":
                    continue
            parts = [inst.mnemonic]
            if inst.modifiers:
                parts.append("." + ".".join(inst.modifiers))
            if inst.operands:
                parts.append(" ")
                parts.append(", ".join(fmt_operand(o) for o in inst.operands))
            line = "".join(parts)
            s = inst.sched
            req = ",".join(str(r) for r in sorted(s.req_bits)) if s.req_bits else ""
            bracket = f"[{s.wr_sb}:{s.rd_sb}:{{{req}}}:{s.stall}:{s.yield_val}]"
            cls = results[i].variant["class"] if results[i] else "(directive)"
            print(f"  [{i:3d}] {line:55s};{bracket:25s} → {cls}")
            if args.verbose and results[i]:
                for k, v in list(results[i].slot_map.items())[:8]:
                    print(f"         {k:20s} = {v}")

    # Encode — the ISA db and const-bank layout follow the selected arch.
    with open(arch.db_path()) as f:
        db = json.load(f)
    encoder = SassEncoder(db)

    # Scoreboard dependency check (CFG).  Needs resolved label offsets.
    if not args.no_check_deps:
        from .sass_depcheck import run_depcheck
        addrs: list[int | None] = []
        labels: dict[str, int] = {}
        pc = 0
        for i, inst in enumerate(insts):
            if inst.mnemonic == "_label_":
                labels.setdefault(inst.label, pc)
            addrs.append(pc)
            if not inst.mnemonic.startswith("_"):
                pc += 16
        for inst, ia in zip(insts, addrs):
            if inst.mnemonic.startswith("_") or inst is None:
                continue
            for op in inst.operands:
                if op.kind == OperandKind.LABEL:
                    op.kind = OperandKind.IMM_S
                    op.value = labels[op.value] - (ia + 16)
        dep_rows = [(inst, result, addr)
                    for inst, result, addr in zip(insts, results, addrs)
                    if inst.mnemonic != "_coop_group_"]
        diags = run_depcheck(db,
                             [row[0] for row in dep_rows],
                             [row[1] for row in dep_rows],
                             [row[2] for row in dep_rows],
                             kernel_name=kernel.name if kernel else args.kernel_name,
                             strict=args.strict_deps)
        if args.strict_deps and diags:
            print(f"error: {len(diags)} dependency diagnostic(s) under "
                  f"--strict-deps", file=sys.stderr)
            return 1

    encoded: list[tuple[int, int]] = []
    for i, inst in enumerate(insts):
        if inst.mnemonic.startswith("_") or results[i] is None:
            encoded.append((0, 0))
            continue
        lo, hi = encoder.encode(results[i], inst.sched)
        encoded.append((lo, hi))

    if args.dump:
        for i, inst in enumerate(insts):
            if inst.mnemonic == "_label_":
                continue
            lo, hi = encoded[i]
            print(f"         lo=0x{lo:016x}  hi=0x{hi:016x}")

    if args.dump_text:
        raw = b"".join(struct.pack("<QQ", lo, hi)
                       for inst, (lo, hi) in zip(insts, encoded)
                       if not inst.mnemonic.startswith("_"))
        Path(args.dump_text).write_bytes(raw)
        print(f"\nWrote {len(raw) // 16} raw instructions "
              f"({len(raw)} bytes) to {args.dump_text}")

    if args.output:
        try:
            if kernel:
                # Keep the CLI on the canonical kernel path: it performs
                # builtin expansion, final-layout EIATTR inference and emits
                # the complete pragma/ABI metadata required by the driver.
                from . import assemble_kernel
                result = assemble_kernel(
                    source, check_deps=not args.no_check_deps,
                    strict_deps=args.strict_deps, arch=arch.current().name)
                Path(args.output).write_bytes(result.code)
                print(f"\nWrote {args.output}: {len(result.code)} bytes, "
                      f"kernel={result.kernel_name}")
                return 0
            cb = CubinBuilder()
            kn = kernel.name if kernel else args.kernel_name
            cb.set_code(encoded, kernel_name=kn)
            regcount = 8
            if kernel:
                regcount = int(kernel.attributes.get("MAXREG_COUNT", 8))
            cb.set_regcount(regcount)
            if kernel and "MAXREG_COUNT" in kernel.attributes:
                cb.set_pragma("MAXREG_COUNT",
                              str(kernel.attributes["MAXREG_COUNT"]))
            if kernel and kernel.params:
                kparams = [(i, p.ordinal, p.size) for i, p in enumerate(kernel.params)]
                cb.set_params(kparams)
            data = cb.build()
            Path(args.output).write_bytes(data)
            print(f"\nWrote {args.output}: {len(data)} bytes, kernel={kn}")
        except ElfError as e:
            print(f"ELF error: {e}", file=sys.stderr)
            return 1
    else:
        nfo = kernel.name if kernel else f"{len(insts)} instructions"
        print(f"\nParsed {nfo} — no output path given (use -o)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
