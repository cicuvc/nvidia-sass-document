#!/usr/bin/env python3
"""disasm.py <cubin> <kernel> [--out FILE] — cubin kernel → assembler-dialect SASS.

Disassembles a kernel's .text into the assembler source dialect (see
ASSEMBLER_MANUAL.md) and round-trip verifies it: the output is fed back
through ``assemble`` and every encoded instruction must match the original.

Per-instruction decoding lives in sass_disasm.py (a solver: decode every bit
field, then verify with assemble_flat).  Branch targets become #label() refs;
kernel parameters become #param(); the default cache descriptor becomes
#spec_const(SLOT_DEFAULT_CDESC).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cubin_reader import read_cubin  # noqa: E402
from sass_disasm import SASSDisasm, load_db, BRANCH_SET  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assembler import assemble_kernel, arch  # noqa: E402

PARAM_BASE = 0x380
CDESC_ADDR = 0x358
ARCH_NAME = "sm120"

BRANCH_RE = re.compile(
    r"^(.*?)\b(BRA|BRX|BRXU|BSSY|BREAK|BSYNC|CALL)\b(.*?)\s*(-?0x[0-9a-fA-F]+)(\s*;.*)$")


def find_kernel(kernels: dict, name: str):
    for mangled, k in kernels.items():
        if k.name == name or k.mangled == name:
            return k
    raise SystemExit(
        f"kernel {name!r} not found. Available: "
        + ", ".join(k.name for k in kernels.values()))


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        return 1
    cubin_path = args[0]
    kname = args[1]
    out_path = None
    if "--out" in args:
        out_path = args[args.index("--out") + 1]
    arch_name = ARCH_NAME
    if "--arch" in args:
        arch_name = args[args.index("--arch") + 1]

    arch.set_arch(arch_name)
    cfg = arch.current()
    param_base = cfg.param_base
    cdesc_bank, cdesc_off = cfg.default_cdesc
    kernels = read_cubin(cubin_path)
    k = find_kernel(kernels, kname)
    db = load_db(cfg.db)
    ds = SASSDisasm(db)

    entries: list[tuple[int, str, str | None]] = []
    for i, (lo, hi) in enumerate(k.instructions):
        text, cls = ds.disasm(lo, hi)
        if text is None:
            print(f"// WARN: inst {i} undecoded "
                  f"(opcode={ds.opcode_of(lo, hi):#x})", file=sys.stderr)
            text = f"// UNDECODED {hi:016X}{lo:016X}"
            cls = None
        entries.append((i, text, cls))

    # branch offset -> target instruction index (offset is byte-relative to
    # the *next* instruction, per the assembler's label resolution)
    branch_target: dict[int, int] = {}
    for i, text, _ in entries:
        m = BRANCH_RE.match(text)
        if m:
            off = int(m.group(4), 0)
            target_pc = (i + 1) * 16 + off
            ti = target_pc // 16
            if 0 <= ti < len(entries):
                branch_target[i] = ti

    label_names: dict[int, str] = {}
    for i, ti in branch_target.items():
        if ti not in label_names:
            label_names[ti] = f"L{len(label_names)}"

    # parameter name lookup by cbank offset
    def param_ref(cbank_off: int) -> str | None:
        for kp in k.kparams:
            if param_base + kp.offset == cbank_off:
                return f"#param(p{kp.index})"
        return None

    params = ", ".join(f"p{p.index}<{p.size}>" for p in k.kparams)
    out = [f"#fn {k.name}({params}) {{"]
    for i, text, _ in entries:
        if i in label_names:
            out.append(f"    #def_label({label_names[i]})")
        m = BRANCH_RE.match(text)
        if m and (i + 1) + (int(m.group(4), 0) // 16) in label_names:
            ti = (i + 1) + (int(m.group(4), 0) // 16)
            text = (f"{m.group(1)}{m.group(2)}{m.group(3)} "
                    f"#label({label_names[ti]}){m.group(5)}")
        else:
            # replace cbank references with #param / #spec_const
            text = re.sub(r"c\[0x0\]\[0x([0-9a-fA-F]+)\]",
                          lambda m: param_ref(int(m.group(1), 16))
                          or f"c[0x0][0x{m.group(1).upper()}]", text)
            text = text.replace(f"c[0x{cdesc_bank:x}][0x{cdesc_off:X}]",
                                "#spec_const(SLOT_DEFAULT_CDESC)")
        out.append(f"    {text}")
    out.append("}")
    src = "\n".join(out)

    # round-trip verification through the real assembler
    try:
        res = assemble_kernel(src, check_deps=False)
        got = res.encoded
    except Exception as ex:
        got = None
        print(f"// ASSEMBLE FAILED: {type(ex).__name__}: {ex}",
              file=sys.stderr)
    if got is not None:
        want = k.instructions
        if len(got) == len(want) and all(g == w for g, w in zip(got, want)):
            print(f"// round-trip OK ({len(want)} instructions)", file=sys.stderr)
        else:
            bad = sum(1 for g, w in zip(got, want) if g != w)
            print(f"// round-trip FAIL {bad}/{len(want)} mismatch",
                  file=sys.stderr)
            for g, w in zip(got, want):
                if g != w:
                    print(f"//   got  {g[1]:016X}{g[0]:016X}  want {w[1]:016X}{w[0]:016X}",
                          file=sys.stderr)

    if out_path:
        Path(out_path).write_text(src)
    else:
        print(src)
    return 0


if __name__ == "__main__":
    sys.exit(main())
