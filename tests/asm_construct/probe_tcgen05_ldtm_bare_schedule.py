#!/usr/bin/env python3
"""Build strictly scheduled raw-LDTM bandwidth kernels for sm100a."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_kernel  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "tests/asm_construct/tcgen05_alloc_sm100.sass"
ANCHOR = """    LDS R5, [UR5];[2:7:{}:1:0]
    ISETP.NE.AND P0, PT, R0, RZ, PT;[7:7:{0}:13:1]
    @!P0 LDC.64 {R2,R3}, c[0x0][0x380];[2:7:{}:2:0]
    @!P0 STG.E desc[{UR8,UR9}][{R2,R3}], R5;[7:0:{2}:1:0]
    NOP;[7:7:{}:1:0]"""


def group(base: int, width: int) -> str:
    if width == 1:
        return f"R{base}"
    return "{" + ",".join(f"R{base + i}" for i in range(width)) + "}"


def make_source(loads: int, batches: int, paired: bool = False,
                columns: tuple[int, ...] = (0,), width: int = 16,
                ) -> tuple[str, str]:
    if loads not in (4, 6, 8, 12):
        raise ValueError(loads)
    name = f"ldtm_raw_l{loads}_b{batches}"
    source = TEMPLATE.read_text()
    source = source.replace("#fn alloc32(out<8>) {",
                            f"#fn {name}(out<8>) {{", 1)
    source = source.replace("    #pragma REGCOUNT(12)",
                            "    #pragma REGCOUNT(224)", 1)
    n_sb = loads // 2 if paired else min(loads, 6)
    req_all = ",".join(str(i) for i in range(n_sb))
    if batches % 4:
        raise ValueError("batches must be divisible by four")
    if width not in (1, 2, 4, 8, 16):
        raise ValueError(width)
    if not columns or any(column < 0 or column > 32 - width
                          for column in columns):
        raise ValueError(
            f"x{width} start columns must be in [0, {32 - width}]")
    body = [
        "    LDS R5, [UR5];[2:7:{}:1:0]",
        "    ISETP.NE.AND P0, PT, R0, RZ, PT;[7:7:{0}:13:1]",
        "    @!P0 LDC.64 {R2,R3}, c[0x0][0x380];[2:7:{}:2:0]",
        "    R2UR UR10, R5;[7:7:{2}:13:1]",
        "    CS2R {R208,R209}, SR_CLOCKLO;[7:7:{}:1:0]",
        f"    UMOV UR11, 0x{batches // 4:x};[7:7:{{}}:5:1]",
        "    #def_label(ldtm_loop)",
        "    UIADD3 UR11, UPT, UPT, UR11, -0x1, URZ;[7:7:{}:5:1]",
        "    UISETP.NE.AND UP0, UPT, UR11, URZ, UPT;[7:7:{}:1:0]",
    ]
    for _unroll in range(4):
        for i in range(loads):
            if paired:
                sb = i % n_sb
                req = str(sb) if i < n_sb else ""
            else:
                sb = i if i < 6 else i - 6
                req = str(sb) if i < 6 else ""
            column = columns[i % len(columns)]
            addr = ("tmem[UR10]" if column == 0
                    else f"tmem[UR10+0x{column:x}]")
            suffix = "" if width == 1 else f".x{width}"
            body.append(
                f"    LDTM{suffix} {group(16 + width * i, width)}, {addr};"
                f"[{sb}:7:{{{req}}}:1:0]")
    body += [
        "    BRA.U UP0, #label(ldtm_loop);[7:7:{}:5:0]",
        f"    CS2R {{R210,R211}}, SR_CLOCKLO;[7:7:{{{req_all}}}:5:1]",
        "    @!P0 STG.E.128 desc[{UR8,UR9}][{R2,R3}], "
        "{R208,R209,R210,R211};"
        "[7:0:{2}:1:0]",
    ]
    if ANCHOR not in source:
        raise ValueError("allocator payload anchor not found")
    return name, source.replace(ANCHOR, "\n".join(body), 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("loads", type=int, choices=(4, 6, 8, 12))
    ap.add_argument("--batches", type=int, default=128)
    ap.add_argument("--pair", action="store_true",
                    help="put two LDTMs on each completion scoreboard")
    ap.add_argument("--columns", default="0",
                    help="comma-separated start columns, repeated")
    ap.add_argument("--width", type=int, choices=(1, 2, 4, 8, 16),
                    default=16, help="LDTM vector width")
    ap.add_argument("--output", type=Path)
    ns = ap.parse_args()
    if ns.batches <= 0 or ns.batches % 4:
        ap.error("batches must be positive and divisible by four")
    try:
        columns = tuple(int(x, 0) for x in ns.columns.split(","))
    except ValueError as exc:
        ap.error(f"bad --columns: {exc}")
    name, source = make_source(
        ns.loads, ns.batches, ns.pair, columns, ns.width)
    output = ns.output or Path(f"/tmp/{name}.cubin")
    result = assemble_kernel(source, arch="sm100a", check_deps=False)
    output.write_bytes(result.code)
    print(f"{name} -> {output} ({len(result.code)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
