#!/usr/bin/env python3
"""Split src/interpreter.cpp into semantic family files under
src/interpreter/baseline/sm120/.  Pure reorganization: member-function
definitions move to family .cpp files verbatim; anonymous-namespace helpers
either go to a shared header (cross-family) or stay with their family;
the Interpreter class, dispatch and orchestration code are untouched
(core.cpp keeps the run/step/group loop and entry points).

Run from the semu/ directory:  python3 tools/split_interpreter.py
"""
import re
from pathlib import Path

SRC = Path("src/interpreter.cpp")
OUT = Path("src/interpreter/baseline/sm120")

# (first,last) inclusive lines.  anon-1/2/3/4 are cross-family helpers ->
# sm120_shared.hpp.  anon-5 (mem_sz) stays with memory.cpp.  anon-6
# (DefaultInterpreter + registry) stays with core.cpp.
ANON = {
    1: (26, 211),
    2: (1415, 1449),
    3: (1600, 1630),
    4: (1970, 2109),
    5: (2537, 2895),   # mem_sz block (incl. namespace { })
    6: (7030, 7070),   # DefaultInterpreter + registry table (incl. namespace { })
    7: (7071, 7104),   # InterpreterRegistry method definitions (core tail)
}
ANON_EXCLUDE = set()
for lo, hi in ANON.values():
    ANON_EXCLUDE.update(range(lo, hi + 1))
ANON_EXCLUDE.add(7105)  # trailing "}  // namespace semu" is the writer's job

# mnemonic family -> Interpreter member name
FAMILY = {
    "core": [
        "Interpreter", "plan_fp32", "plan_fp64", "run_shared", "step_once",
        "step_group", "step_consistent", "run_result", "run_result_parallel",
        "run_owned", "scan_schedule", "next_group", "execute_group",
        "resolve_guard", "supports", "record_memory_event",
        "record_coupled_l1_to_shared", "record_l2_access", "flush_l2_events",
        "record_race_access", "record_debug_access", "detect_deadlock",
        "do_unsupported", "run", "terminal_state", "barrier_deadlock_fault",
        "reg", "read_reg",
    ],
    "control_flow": [
        "do_bra", "branch_target", "probe_branch_target", "do_bssy",
        "converge_completed_sync", "do_bsync", "do_exit", "do_bar",
        "do_depbar", "do_ldgdepbar", "do_elect", "validate_control_target",
    ],
    "memory": [
        "do_s2r", "do_s2ur", "special_register_value", "special_reg",
        "resolve_mem_addr",
        "mem_ldst_atom_core", "do_ldg", "do_stg", "do_lds", "do_sts",
        "do_ldl", "do_stl", "do_ldc", "do_atom", "do_atoms", "do_reds",
        "do_atomg", "do_redg", "do_membar", "do_fence", "do_errbar",
        "do_cgaerrbar", "do_cctl", "sm_of_cta", "resolve_shared_target",
        "mbarrier_at", "do_ldgsts", "do_syncs", "do_arrives",
        "warp_linear_id", "do_shfl",
    ],
    "int_vector": [
        "do_mov", "do_iadd3", "do_isetp", "do_imad", "do_p2r", "do_vote",
        "do_redux", "do_lop3", "do_lop", "do_shf", "do_iabs", "do_imnmx",
        "do_iscadd", "do_lea", "bitops_core", "do_popc", "do_flo",
        "do_bmsk", "do_prmt", "lut_core",
    ],
    "fp_vector": [
        "fp32_arith_core", "do_fadd", "do_fmul", "do_ffma",
        "fp64_arith_core", "do_dadd", "do_dmul", "do_dfma", "fset_core",
        "do_fsetp", "do_fset", "do_fmnmx", "do_fsel", "do_f2f",
        "cvtx_core", "do_i2f", "do_f2i", "do_frnd",
    ],
    "scalar": ["do_umov", "do_uiadd3", "do_ushf", "do_ldcu"],
    "tma": [
        "prepare_tma", "tma_store_core", "do_utmacmdflush", "do_utmacctl",
        "do_utmaldg", "do_utmastg", "do_utmaredg",
    ],
    "tensor": [
        "tensor_unsupported", "tensor_lane_core", "do_hmma", "do_qmma",
        "do_omma",
    ],
}
NAME_TO_FAMILY = {}
for fam, names in FAMILY.items():
    for n in names:
        NAME_TO_FAMILY[n] = fam

START_RE = re.compile(r"^[A-Za-z_].*?\bInterpreter::([A-Za-z0-9_]+)\(")
START_RE2 = re.compile(r"^[A-Za-z_].*?\b([A-Za-z0-9_]+) Interpreter::")


def member_name(line):
    if line.startswith("Interpreter::Interpreter("):
        return "Interpreter"
    m = START_RE.match(line)
    if m:
        return m.group(1)
    m = START_RE2.search(line)
    return m.group(1) if m else None


def main():
    lines = SRC.read_text().splitlines(keepends=True)
    n = len(lines)

    # ---- locate member-definition starts (excluding anon blocks) ----
    starts = []  # (line_no_1based, name)
    for i, line in enumerate(lines):
        ln = i + 1
        if ln in ANON_EXCLUDE:
            continue
        s = line.lstrip()
        if not s or s.startswith("//") or s.startswith("/*") or s.startswith("*"):
            continue
        if "Interpreter::" not in line:
            continue
        name = member_name(line)
        if name is None:
            continue
        # a definition start: return type + Interpreter::name(  at col 0
        if not line.startswith(("bool ", "void ", "int ", "std::", "Status ",
                                "InterpreterResult ", "Fault ", "uint",
                                "Interpreter::Interpreter", "const ")):
            # tolerate constructors / odd returns: any col-0 Identifier:: too
            if not (line[0].isalpha() and "::" in line.split("(")[0]):
                continue
        starts.append((ln, name))

    # sanity: every family name must appear
    found = {name for _, name in starts}
    for fam, names in FAMILY.items():
        missing = [x for x in names if not any(n == x for n in found)]
        if missing:
            print(f"WARN {fam}: missing {missing}")
    for name in found:
        if name not in NAME_TO_FAMILY:
            print(f"WARN unhandled member: {name}")

    # ---- slice ranges ----
    ranges = []  # (start_ln, end_ln_exclusive, name)
    for idx, (ln, name) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else n + 1
        ranges.append((ln, end, name))

    # ---- build per-family text (preserve source order) ----
    blocks = [(ln, end, NAME_TO_FAMILY[name], "member") for ln, end, name in ranges]
    for (lo, hi), fam in (((2537, 2895), "memory"),     # mem_sz block
                          ((7030, 7070), "core"),        # DefaultInterpreter + table
                          ((7071, 7104), "core")):       # registry methods
        blocks.append((lo, hi + 1, fam, "anon"))
    blocks.sort(key=lambda b: b[0])
    fam_lines = {f: [] for f in FAMILY}
    for ln, end, fam, kind in blocks:
        for i in range(ln, end):
            if kind == "member" and i in ANON_EXCLUDE:
                continue  # anon 1-4 live in sm120_shared.hpp; 5-7 in their blocks
            fam_lines[fam].append(lines[i - 1])
    # the final "}  // namespace semu" of the source file is the writer's
    # job -- drop any stray copy a tail member range picked up.
    fam_lines["core"] = [l for l in fam_lines["core"]
                          if not l.strip().startswith("}  // namespace semu")]

    # ---- write files ----
    COMMON_HEAD = (
        "// sm120 baseline interpreter -- {desc}.\n"
        "// Split from src/interpreter.cpp (Interpreter member definitions\n"
        "// moved verbatim; class, dispatch and orchestration untouched).\n"
        "\n#include <semu/interpreter/interpreter.hpp>\n"
        "\n#include <algorithm>\n"
        "#include <cfenv>\n"
        "#include <cmath>\n"
        "#include <cstdio>\n"
        "#include <cstdlib>\n"
        "#include <cstring>\n"
        "#include <thread>\n"
        "\n#include <semu/fp/fast_fp.hpp>\n"
        "#include <semu/fp/fp.hpp>\n"
        "#include <semu/memory/l1tex_model.hpp>\n"
        "\n#include \"isa_shapes_fill.hpp\"\n"
        "#include \"isa_data.hpp\"\n"
        '\n#include "sm120_shared.hpp"\n\n'
        "namespace semu {\n"
    )
    DESC = {
        "core": "run/step/orchestration, events, registry adapter",
        "control_flow": "control flow: BRA/BRX/JMP/JMX/BSSY/BSYNC/EXIT/BAR/"
                        "DEPBAR/LDGDEPBAR/ELECT",
        "memory": "memory & sync: S2R/S2UR, LD/ST/ATOM/RED families, "
                  "MEMBAR/FENCE/ERRBAR/CGAERRBAR/CCTL, LDGSTS, SYNC/ARRIVE, SHFL",
        "int_vector": "vector integer: MOV/IADD3/ISETP/IMAD, P2R/VOTE/REDUX/"
                      "SHFL-, LOP3/LOP/SHF, IMNMX/ISCADD/LEA, POPC/FLO/BMSK/PRMT",
        "fp_vector": "vector float: FFMA/FADD/FMUL, FP64, FSET/FSETP/FMNMX/"
                     "FSEL, F2F/I2F/F2I/FRND conversions",
        "scalar": "scalar/uniform: UMOV/UIADD3/USHF/LDCU",
        "tma": "TMA: UTMALDG/UTMASTG/UTMAREDG/UTMACMDFLUSH/UTMACCTL",
        "tensor": "tensor core: HMMA/QMMA/OMMA (decode-only boundary)",
    }
    for fam, body in fam_lines.items():
        text = COMMON_HEAD.replace("{desc}", DESC[fam]) + "".join(body) + "}  // namespace semu\n"
        (OUT / f"{fam}.cpp").write_text(text)

    # ---- shared header (cross-family anon helpers) ----
    shared = []
    for idx in (1, 2, 3, 4):
        lo, hi = ANON[idx]
        shared.extend(lines[lo - 1:hi])
    header = (
        "// Shared internal helpers for the sm120 baseline interpreter\n"
        "// (moved from src/interpreter.cpp anonymous namespace; internal\n"
        "// linkage per TU -- cross-family operand/memory/int helpers).\n"
        "// unused-function warnings are silenced: each TU includes the full\n"
        "// set but only uses the helpers of its own family.\n"
        "#pragma once\n"
        "\n"
        "#if defined(__clang__)\n"
        "#pragma clang diagnostic push\n"
        "#pragma clang diagnostic ignored \"-Wunused-function\"\n"
        "#elif defined(__GNUC__)\n"
        "#pragma GCC diagnostic push\n"
        "#pragma GCC diagnostic ignored \"-Wunused-function\"\n"
        "#endif\n"
        "\n#include <semu/interpreter/interpreter.hpp>\n\n"
        "namespace semu {\nnamespace {\n" + "".join(shared) +
        "}  // namespace\n}  // namespace semu\n" +
        ("#if defined(__clang__)\n#pragma clang diagnostic pop\n"
         "#elif defined(__GNUC__)\n#pragma GCC diagnostic pop\n#endif\n")
    )
    (OUT / "sm120_shared.hpp").write_text(header)

    total = sum(len(v) for v in fam_lines.values()) + sum(
        hi - lo + 1 for lo, hi in (ANON[1], ANON[2], ANON[3], ANON[4]))
    print(f"written: {[f.name for f in sorted(OUT.glob('*'))]}")
    print(f"total lines routed: {total} (source {n})")


if __name__ == "__main__":
    main()