#!/usr/bin/env python3
"""DEPRECATED diagnostic: replace ptxas's LDS loop in a lifted cubin.

This script is retained only to document the failed lift/relocation approach.
It depends on ptxas's numeric control-flow and allocator ABI and MUST NOT be
used to produce measurement kernels.  New probes must be generated completely
from assembler source.  Running it requires an explicit diagnostic opt-in.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import arch, assemble  # noqa: E402
from sassdbg.lift import normalize_source  # noqa: E402


def info_offsets(cubin: Path, func: str, attr: str) -> list[int]:
    text = subprocess.run(
        ["/usr/local/cuda-13.1/bin/cuobjdump", "-elf", str(cubin)],
        check=True, text=True, stdout=subprocess.PIPE).stdout
    marker = f".nv.info.{func}\n"
    # cuobjdump prints the section name once in the ELF section table and once
    # again before decoding its attributes; use the latter occurrence.
    start = text.rindex(marker) + len(marker)
    end = text.find("\n.nv.info.", start)
    block = text[start:] if end < 0 else text[start:end]
    m = re.search(rf"Attribute:\s+{re.escape(attr)}.*?Value:\s+([^\n]+)",
                  block, re.S)
    if not m:
        raise RuntimeError(f"missing {attr} for {func}")
    return [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]+", m.group(1))]


def instruction_count(text: str) -> int:
    return sum(1 for line in text.splitlines()
               if ";[" in line and not line.lstrip().startswith("#"))


def relocate_numeric_control(source: str, *, begin_pc: int, old_end_pc: int,
                             new_end_pc: int, delta: int,
                             old_label_pcs: set[int], old_code_size: int) -> str:
    """Relocate ptxas numeric CALL/RET and saved-PC MOV operands.

    sassdbg faithfully lifts these operands as numbers rather than labels.
    Growing a middle block therefore requires the same relocation work that
    ptxas did when it laid out the original function.
    """
    out: list[str] = []
    new_pc = 0
    for line in source.splitlines():
        is_inst = ";[" in line and not line.lstrip().startswith("#")
        if is_inst and "CALL.REL" in line:
            m = re.search(r"(CALL\.REL(?:\.[A-Z]+)*\s+)(-?0x[0-9a-fA-F]+)",
                          line)
            if m:
                old_pc = (new_pc if new_pc < begin_pc else new_pc - delta)
                old_disp = int(m.group(2), 0)
                old_target = old_pc + 16 + old_disp
                new_target = old_target + (delta if old_target >= old_end_pc else 0)
                new_disp = new_target - (new_pc + 16)
                token = (f"-{abs(new_disp):#x}" if new_disp < 0
                         else f"{new_disp:#x}")
                line = line[:m.start(2)] + token + line[m.end(2):]
        if is_inst and "RET.REL" in line:
            # ptxas helper convention: target = next_pc + Ra + immediate;
            # hence every lifted helper uses immediate == -next_pc.
            line = re.sub(r"(RET\.REL(?:\.[A-Z]+)*\s+\{[^}]+\})-0x[0-9a-fA-F]+",
                          lambda m: f"{m.group(1)}-{new_pc + 16:#x}", line)
        if is_inst and re.search(r"\bMOV R\d+, 0x", line):
            m = re.search(r"(\bMOV R\d+, )(0x[0-9a-fA-F]+)", line)
            if m:
                value = int(m.group(2), 0)
                if (value >= old_end_pc and value < old_code_size and
                        (value in old_label_pcs or value % 16 == 0)):
                    line = (line[:m.start(2)] + f"{value + delta:#x}"
                            + line[m.end(2):])
        out.append(line)
        if is_inst:
            new_pc += 16
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--function", required=True)
    ap.add_argument("--count", type=int, default=512)
    ap.add_argument("--static", action="store_true",
                    help="emit count distinct LDS instructions (no hot loop)")
    ap.add_argument("--keep-original", action="store_true",
                    help="reassemble the normalized function unchanged")
    ap.add_argument(
        "--diagnostic-allow-nvcc-lift", action="store_true",
        help="acknowledge that the output is diagnostic-only and not a probe")
    ns = ap.parse_args()
    if not ns.diagnostic_allow_nvcc_lift:
        ap.error("deprecated nvcc-lift path; use a from-source assembler "
                 "kernel (or pass --diagnostic-allow-nvcc-lift only for "
                 "historical diagnosis)")

    src = subprocess.run(
        [sys.executable, "-m", "sassdbg.lift", str(ns.input),
         "--func", ns.function], check=True, text=True,
        stdout=subprocess.PIPE).stdout
    # cuobjdump omits UTCHMMA's default disable-output-lane URi=URZ operand;
    # the assembler dialect keeps it explicit.  Then run the normal lifter
    # repair loop (CS2R.64 groups, etc.) under the sm100 database.
    src = re.sub(r"(idesc\[[^\n]+?\]), ([!]?(?:UP[0-6]|UPT))([,;])",
                 r"\1, URZ, \2\3", src)
    # The 1CTA/2CTA classes share the opcode and cuobjdump omits the default
    # `.1CTA` suffix.  Keep it explicit so the matcher does not choose 2CTA.
    src = src.replace("UTCHMMA ", "UTCHMMA.1CTA ")
    src = src.replace("UTCBAR ", "UTCBAR.1CTA ")
    arch.set_arch("sm100a")
    src = normalize_source(src)
    begin_token = "CS2R {R20,R21}, SR_CLOCKLO;"
    end_token = "CS2R {R6,R7}, SR_CLOCKLO;"
    begin = src.index(begin_token)
    end = src.index(end_token, begin)
    begin_pc = instruction_count(src[:begin]) * 16
    old = src[begin:end]
    old_n = instruction_count(old)
    old_code_size = instruction_count(src) * 16
    old_label_pcs = {
        int(x, 16) for x in re.findall(r"#def_label\(L_([0-9a-fA-F]+)\)", src)
    }

    # Preserve the original instruction count and ptxas's reconvergence frame.
    # The lifted allocator helpers use numeric CALL.REL/RET.REL displacements,
    # so growing code in the middle silently retargets those calls.  A compact
    # raw loop fits exactly in the old 23 slots.  The hot loop deliberately
    # leaves LDS unscoreboarded (like probe_sm100_lsu_exchange.py), so queue
    # backpressure measures throughput rather than load-latency round trips.
    # Static mode rotates over 40 private vector destinations.  RZ encodes but
    # is not a safe repeated vector-load sink: hardware still tracks closure.
    n_loads = ns.count if ns.static else min(ns.count, 6)
    iterations = 1 if ns.static else (ns.count + n_loads - 1) // n_loads
    setup = [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:1:0]",
        "    UIADD3 UR4, UPT, UPT, UR16, 0x2080, URZ;[7:7:{}:1:0]",
        "    BSSY.RECONVERGENT B0, #label(L_ea0);[7:7:{}:1:0]",
        "    IMAD.MOV.U32 R23, RZ, RZ, RZ;[7:7:{}:2:0]",
        "    ULEA UR4, UR11, UR4, 0x18;[7:7:{}:1:0]",
        "    SHL R26, R0, 0x4;[7:7:{}:5:1]",
        "    #def_label(__sat_lds_loop)",
    ]
    for i in range(n_loads):
        if ns.static:
            r = 32 + 4 * (i % 32)
            dest = f"{{R{r},R{r+1},R{r+2},R{r+3}}}"
            wr = 0 if i == n_loads - 1 else 7
        else:
            r = 32 + 4 * i
            dest = f"{{R{r},R{r+1},R{r+2},R{r+3}}}"
            wr = i
        setup.append(f"    LDS.128 {dest}, [R26];[{wr}:7:{{}}:1:1]")
    if not ns.static:
        setup.extend([
            "    NOP;[7:7:{0,1,2,3,4,5}:1:0]",
            "    VIADD R23, R23, 0x1;[7:7:{}:3:1]",
            f"    ISETP.NE.AND P0, PT, R23, {iterations:#x}, PT;"
            "[7:7:{}:13:1]",
            "    @P0 BRA #label(__sat_lds_loop);[7:7:{}:5:0]",
        ])
        setup.extend("    NOP;[7:7:{}:1:0]" for _ in range(12 - n_loads))
    setup.extend([
        ("    BSYNC.RECONVERGENT B0;[7:7:{0}:5:0]" if ns.static
         else "    BSYNC.RECONVERGENT B0;[7:7:{}:5:0]"),
        "    #def_label(L_ea0)",
    ])
    replacement = old if ns.keep_original else "\n".join(setup) + "\n"
    new_n = instruction_count(replacement)
    delta_bytes = (new_n - old_n) * 16
    old_end_off = instruction_count(src[:end]) * 16
    src = src[:begin] + replacement + src[end:]
    if delta_bytes:
        src = relocate_numeric_control(
            src, begin_pc=begin_pc, old_end_pc=old_end_off,
            new_end_pc=old_end_off + delta_bytes, delta=delta_bytes,
            old_label_pcs=old_label_pcs, old_code_size=old_code_size)
    # Keep global output addresses disjoint from both the measured registers
    # and ptxas's R4/R5 allocator temporaries.  R24/R25 are otherwise unused.
    out_begin = src.index("#def_label(L_ea0)")
    out_end = src.index("#def_label(L_f60)", out_begin)
    out_block = src[out_begin:out_end]
    out_block = out_block.replace("LDC.64 {R4,R5},", "LDC.64 {R24,R25},")
    out_block = out_block.replace(
        "IMAD.WIDE.U32 {R2,R3}, R3, 0x8, {R4,R5}",
        "IMAD.WIDE.U32 {R2,R3}, R3, 0x8, {R24,R25}")
    out_block = out_block.replace(
        "IMAD.WIDE.U32 {R4,R5}, R9, 0x8, {R4,R5}",
        "IMAD.WIDE.U32 {R4,R5}, R9, 0x8, {R24,R25}")
    out_block = out_block.replace("[{R4,R5}]", "[{R24,R25}]")
    out_block = out_block.replace("[{R4,R5}+", "[{R24,R25}+")
    out_block = out_block.replace("[{R24,R25}+0x48]", "[{R24,R25}+0x80]")
    src = src[:out_begin] + out_block + src[out_end:]

    attrs = {}
    for attr in ("EIATTR_INT_WARP_WIDE_INSTR_OFFSETS",
                 "EIATTR_COOP_GROUP_INSTR_OFFSETS"):
        vals = info_offsets(ns.input, ns.function, attr)
        attrs[attr] = [v + delta_bytes if v >= old_end_off else v
                       for v in vals]

    pragma = [
        f"    #pragma REGCOUNT({168 if ns.static else 64})",
        "    #pragma SHARED(0x3480)",
        "    #pragma NUM_MBARRIERS(1)",
        "    #pragma TCGEN05_1CTA_USED(1)",
        "    #pragma INT_WARP_WIDE_OFFSETS(" +
        ",".join(hex(x) for x in
                 attrs["EIATTR_INT_WARP_WIDE_INSTR_OFFSETS"]) + ")",
        "    #pragma COOP_GROUP_INSTR_OFFSETS(" +
        ",".join(hex(x) for x in
                 attrs["EIATTR_COOP_GROUP_INSTR_OFFSETS"]) + ")",
    ]
    first_nl = src.index("\n") + 1
    src = src[:first_nl] + "\n".join(pragma) + "\n" + src[first_nl:]
    ns.output.with_suffix(".sass").write_text(src)
    ns.output.write_bytes(assemble(src, arch="sm100a", check_deps=False))
    print(f"{ns.function}: replaced {old_n} instructions with {new_n}, "
          f"metadata shift {delta_bytes:#x}, old end {old_end_off:#x}; "
          f"{n_loads} LDS x {iterations} iterations")


if __name__ == "__main__":
    main()
