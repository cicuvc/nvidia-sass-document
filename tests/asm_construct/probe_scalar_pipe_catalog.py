#!/usr/bin/env python3
"""Minimal sm_120 scalar-math leaf-pipe catalog probe.

Each kernel contains only six MOV32I initializers, N independent instances of
one target operation, and EXIT.  Kernel names encode the operation so an ncu
CSV can be classified without relying on launch order.  Run this script under
ncu with the leaf metrics listed by ``--print-ncu``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assembler import CudaModule, assemble  # noqa: E402
from probe_subcore_compute_conflict import OPS  # noqa: E402


GROUPS = {
    "int_pipe": (
        "bmsk f2fp f2ip fmnmx fsel fset fsetp i2fp i2i i2ip iabs "
        "iadd iadd3 iadd32i imnmx iscadd iscadd32i isetp lea lop lop3 "
        "lop32i mov mov32i mov64iur p2r plop3 prmt psetp r2p sel sgxt "
        "shf shl shr vimnmx"
    ).split(),
    "fmalighter_pipe": (
        "fadd fadd32i ffma ffma32i fhadd fhfma fmul fmul32i fswzadd "
        "idp2 idp4 imad imul imul32i viadd"
    ).split(),
    "fp16_pipe": (
        "hadd2 hadd2_32i hfma2 hfma2_32i hmnmx2 hmul2 hmul2_32i "
        "hset2 hsetp2"
    ).split(),
    "fma64lite_pipe": "clmad dadd dfma dmul dsetp".split(),
}

ALL_OPS = [name for names in GROUPS.values() for name in names]
assert len(ALL_OPS) == len(set(ALL_OPS)) == 65
assert not (set(ALL_OPS) - set(OPS))

# Coverage gate against the actual sm120 database, rather than a hand-count.
_ALIASES = {"idp2": "IDP", "idp4": "IDP4A", "hsetp2": "HSETP2"}
_SPECIAL_OR_TENSOR = {
    "CS2R", "IDE", "IMMA", "LEPC", "MOVM", "RPCMOV", "VOTE",
    "HMMA", "MXQMMA", "OMMA", "QMMA", "DMMA",
}
with (Path(__file__).resolve().parents[2] / "sm120.json").open() as _f:
    _db = json.load(_f)
_variant_mnemonics = {v.get("mnemonic") for v in _db["variants"]}
_families = {"int_pipe", "fmalighter_pipe", "fp16_pipe", "fma64lite_pipe"}
_expected = {
    m for m, pipes in _db["pipes"].items()
    if m in _variant_mnemonics and _families.intersection(pipes)
} - _SPECIAL_OR_TENSOR
_covered = {_ALIASES.get(name, name.upper()) for name in ALL_OPS}
assert _covered == _expected, (
    f"scalar catalog drift: missing={sorted(_expected - _covered)}, "
    f"extra={sorted(_covered - _expected)}")
del _db, _variant_mnemonics, _expected, _covered, _f

# Same-mnemonic modifier modes whose static latency family can differ from the
# base mnemonic.  They are not counted again in the 65-mnemonic coverage.
MODE_CONTROLS = ["hadd2_f32", "hfma2_mma"]

METRICS = (
    "smsp__inst_executed_pipe_aluheavy.sum,"
    "smsp__inst_executed_pipe_fmaheavy_subpipe_alulite.sum,"
    "smsp__inst_executed_pipe_fmaheavy_subpipe_fmaheavy.sum,"
    "smsp__inst_executed_pipe_fmalite.sum,"
    "smsp__inst_executed_pipe_fma_type_fp16.sum,"
    "smsp__inst_executed_pipe_fp64.sum"
)


def source(name: str, count: int) -> str:
    op = OPS[name]
    lines = [
        f"#fn pipe_{name}() {{",
        "    #pragma MAXREG_COUNT(96)",
        "    MOV32I R24, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R25, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R26, 0x40003c00;[7:7:{}:5:1]",
        "    MOV32I R27, 0x40003c00;[7:7:{}:5:1]",
        "    MOV32I R28, 0x3f003c00;[7:7:{}:5:1]",
        "    MOV32I R29, 0x3f003c00;[7:7:{}:5:1]",
    ]
    lines.extend(f"    {op.instruction(i)};{op.sched}" for i in range(count))
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ops", default=",".join(ALL_OPS))
    p.add_argument("--length", type=int, default=128)
    p.add_argument("--reps", type=int, default=2)
    p.add_argument("--emit-dir", type=Path)
    p.add_argument("--print-ncu", action="store_true")
    ns = p.parse_args()
    if ns.print_ncu:
        print(METRICS)
        return 0
    names = [x.strip().lower() for x in ns.ops.split(",") if x.strip()]
    bad = set(names) - set(ALL_OPS) - set(MODE_CONTROLS)
    if bad:
        p.error(f"unknown/non-scalar operations: {sorted(bad)}")
    if ns.length <= 0 or ns.reps <= 0:
        p.error("--length and --reps must be positive")

    if ns.emit_dir:
        ns.emit_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        cubin = assemble(source(name, ns.length), check_deps=True)
        if ns.emit_dir:
            (ns.emit_dir / f"pipe_{name}.cubin").write_bytes(cubin)
            print(name, flush=True)
            continue
        mod = CudaModule(cubin)
        for rep in range(ns.reps):
            mod.launch(f"pipe_{name}", grid=(1,), block=(32,), args=[])
            mod.synchronize()
            print(f"{name},{rep}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
