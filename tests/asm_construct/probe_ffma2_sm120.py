#!/usr/bin/env python3
"""Probe whether RTX Blackwell (sm_120) executes the sm_100 FFMA2 opcode.

This deliberately does not ask ptxas or the sm_120 assembler to accept
FFMA2.  It builds a normal sm_120 cubin, then replaces one instruction with
the exact 128-bit RRR FFMA2 word encoded from sm100.json.  A scalar-FFMA
control kernel is run first to distinguish an ISA result from a broken test
harness.

Expected packed operation:
    {1.5, -2.0} * {2.0, 4.0} + {0.5, 1.0} = {3.5, -7.0}

Run from the repository root:
    python3 tests/asm_construct/probe_ffma2_sm120.py

Use --emit-cubin DIR to retain the control and patched cubins for cuobjdump.
Use --no-run for a CPU-only construction/encoding check.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from assembler import CudaModule, assemble_kernel  # noqa: E402
from assembler.sass_encoder import SassEncoder  # noqa: E402
from assembler.sass_matcher import SassMatcher  # noqa: E402
from assembler.sass_parser import parse_sass  # noqa: E402


KERNEL = "ffma2_sm120_probe"
EXPECTED = (0x40600000, 0xC0E00000)  # 3.5f, -7.0f
CANARY = (0xDEADBEEF, 0xA5A5A5A5)

# The marker is a legal sm_120 instruction and occurs exactly once in the
# generated cubin.  It is replaced after ELF construction, leaving the sm_120
# ELF flags/ABI and all launch metadata intact.
MARKER = "FFMA R20, R2, R4, R6;[7:7:{}:5:1]"


def _source(second: str) -> str:
    nops = "\n".join("    NOP;[7:7:{}:5:1]" for _ in range(32))
    return f"""#fn {KERNEL}(out<8>) {{
    #pragma MAXREG_COUNT(32)
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R8,R9}}, #param(out);[1:7:{{}}:1:0]
    MOV32I R2, 0x3fc00000;[7:7:{{}}:5:1]
    MOV32I R3, 0xc0000000;[7:7:{{}}:5:1]
    MOV32I R4, 0x40000000;[7:7:{{}}:5:1]
    MOV32I R5, 0x40800000;[7:7:{{}}:5:1]
    MOV32I R6, 0x3f000000;[7:7:{{}}:5:1]
    MOV32I R7, 0x3f800000;[7:7:{{}}:5:1]
    MOV32I R20, 0x{CANARY[0]:08x};[7:7:{{}}:5:1]
    MOV32I R21, 0x{CANARY[1]:08x};[7:7:{{}}:5:1]
    {MARKER}
    {second}
{nops}
    STG.E.64 desc[{{UR4,UR5}}][{{R8,R9}}+0x0], {{R20,R21}};[7:7:{{0,1}}:8:0]
    EXIT;[7:7:{{}}:5:0]
}}
"""


def _sm100_ffma2_word() -> tuple[int, int]:
    """Encode the packed RRR form using the sm_100 database itself."""
    db = json.loads((REPO / "sm100.json").read_text())
    sm120 = json.loads((REPO / "sm120.json").read_text())
    collisions = [v["class"] for v in sm120["variants"]
                  if v.get("opcode") == 0x249]
    if collisions:
        raise RuntimeError(
            f"sm_120 opcode 0x249 is no longer unassigned: {collisions}"
        )
    text = (
        "FFMA2.F32x2.F32x2.F32x2 "
        "{R20,R21}, {R2,R3}, {R4,R5}, {R6,R7};[7:7:{}:5:1]"
    )
    inst = parse_sass(text)[0]
    match = SassMatcher(db).match(inst)
    assert match.variant["class"] == "ffma2_rb_rc__RRR"
    assert match.variant["opcode"] == 0x249
    return SassEncoder(db).encode(match, inst.sched)


def _build() -> tuple[bytes, bytes, tuple[int, int]]:
    control = assemble_kernel(
        _source("FFMA R21, R3, R5, R7;[7:7:{}:5:1]"),
        check_deps=False,
        arch="sm120",
    )
    probe = assemble_kernel(
        _source("NOP;[7:7:{}:5:1]"),
        check_deps=False,
        arch="sm120",
    )

    # Find the marker by its assembler-produced word, rather than assuming an
    # ELF section offset.  Requiring one occurrence makes the patch fail safe.
    marker_word = assemble_marker()
    marker_index = next(
        i for i, word in enumerate(probe.encoded)
        if word == marker_word
    )
    marker_bytes = struct.pack("<QQ", *probe.encoded[marker_index])
    offsets = []
    start = 0
    while True:
        off = probe.code.find(marker_bytes, start)
        if off < 0:
            break
        offsets.append(off)
        start = off + 1
    if len(offsets) != 1:
        raise RuntimeError(
            f"marker word occurs {len(offsets)} times in cubin, expected once"
        )

    raw = _sm100_ffma2_word()
    patched = bytearray(probe.code)
    struct.pack_into("<QQ", patched, offsets[0], *raw)
    if struct.unpack_from("<QQ", patched, offsets[0]) != raw:
        raise AssertionError("cubin patch verification failed")
    return control.code, bytes(patched), raw


def assemble_marker() -> tuple[int, int]:
    """Encode one parsed marker through the normal sm_120 public path."""
    # A one-instruction kernel avoids depending on assembler private caches.
    src = f"#fn marker() {{\n    #pragma MAXREG_COUNT(32)\n    {MARKER}\n}}\n"
    return assemble_kernel(src, check_deps=False, arch="sm120").encoded[0]


def _run(cubin: bytes) -> tuple[int, int]:
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(8)
    try:
        mod.device_write(out, struct.pack("<II", *CANARY))
        mod.launch(KERNEL, grid=(1,), block=(1,), args=[out])
        mod.synchronize()
        return struct.unpack("<II", mod.device_read(out, 8))
    finally:
        # On an illegal-instruction fault the CUDA context is poisoned and
        # cuMemFree may itself fail.  Process exit will reclaim the allocation.
        try:
            mod.devmem_free(out)
        except Exception:
            pass


def _fmt(words: tuple[int, int]) -> str:
    vals = struct.unpack("<ff", struct.pack("<II", *words))
    return (f"[{words[0]:#010x}, {words[1]:#010x}] "
            f"= [{vals[0]!r}, {vals[1]!r}]")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-run", action="store_true",
                    help="only construct and verify the patched cubin")
    ap.add_argument("--emit-cubin", type=Path, metavar="DIR",
                    help="write control.cubin and ffma2_patched.cubin")
    args = ap.parse_args()

    control, probe, raw = _build()
    lo, hi = raw
    print(f"sm_100 FFMA2 RRR word: lo={lo:#018x} hi={hi:#018x}")
    print("sm_120 public opcode table: 0x249 is unassigned")

    if args.emit_cubin:
        args.emit_cubin.mkdir(parents=True, exist_ok=True)
        (args.emit_cubin / "control.cubin").write_bytes(control)
        (args.emit_cubin / "ffma2_patched.cubin").write_bytes(probe)
        print(f"wrote cubins to {args.emit_cubin}")

    if args.no_run:
        print("construction PASS (--no-run)")
        return 0

    try:
        got_control = _run(control)
    except Exception as exc:
        print(f"CONTROL FAILED: {exc}", file=sys.stderr)
        print("The FFMA2 result would be inconclusive until the control runs.",
              file=sys.stderr)
        return 2
    print(f"control result: {_fmt(got_control)}")
    if got_control != EXPECTED:
        print(f"CONTROL FAILED: expected {_fmt(EXPECTED)}", file=sys.stderr)
        return 2

    try:
        got = _run(probe)
    except Exception as exc:
        msg = str(exc)
        print(f"probe fault: {msg}")
        if " 715 " in msg or "ILLEGAL_INSTRUCTION" in msg:
            print("VERDICT: sm_120 hardware rejects the sm_100 FFMA2 encoding "
                  "as an illegal instruction.")
            return 0
        print("VERDICT: inconclusive CUDA fault (not identified as error 715).")
        return 3

    print(f"probe result:   {_fmt(got)}")
    if got == EXPECTED:
        print("VERDICT: FFMA2 executes correctly on this sm_120 GPU; ptxas/spec "
              "exposure is absent but the tested hardware path remains live.")
        return 0
    if got == CANARY:
        print("VERDICT: opcode executed without a fault but left the destination "
              "unchanged; this is not functional FFMA2 support.")
        return 1
    print("VERDICT: opcode executed without a fault but produced a different "
          "result; inspect the raw bits before calling it FFMA2 support.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
