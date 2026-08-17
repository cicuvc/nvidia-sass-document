#!/usr/bin/env python3
"""Generate semu's compiled-in capability manifest from sm120.json.

Deterministic generator: identical repo state -> byte-identical outputs.  It
is the single source for the build inputs

    semu/generated/capability_data.hpp
    semu/generated/capability_data.cpp

which are committed so ordinary builds never need Python.  The C++ CLI
'capability' command prints the manifest from the compiled-in table.

Phase 1 baseline: every encoding variant is 'decode-only' (the decoder uniquely
decodes all 1414 variants).  Later phases raise states to
decode-only/functional/profiled and re-run this script.

Usage:
    python3 semu/tools/gen_capability.py [--db PATH] [--output-dir DIR]
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFEST_VERSION = 1
ARCH = "sm120"
STATE_NAMES = {"decode-only": "kDecodeOnly", "functional": "kFunctional",
               "profiled": "kProfiled", "unsupported": "kUnsupported"}

# Phase transitions baked into the default generator run (so the regeneration
# gate — which runs the generator with default args — reproduces the committed
# manifest byte-identically).  Phase 9: the dense F32-accumulator tensor-core
# shapes are functional (HMMA/QMMA/OMMA via semu::tensor).  Only the exact
# variant classes the interpreter's do_tensor implements are raised; the
# sparse / rowcol / scale alternatives stay decode-only (runtime faults).
DEFAULT_MNEMONIC_STATES = {"HMMA": "functional", "QMMA": "functional",
                           "OMMA": "functional"}
# Exact variant-class overrides (win over the mnemonic default).  Values are
# the C++ enum names (STATE_NAMES), not the CLI strings.
DEFAULT_CLASS_STATES = {"hmma_x8_": "kFunctional",
                        "qmma_": "kFunctional",
                        "omma_scale_": "kFunctional"}
# Tensor mnemonics whose non-dense alternative variants are decode-only: the
# mnemonic default marks every variant functional, so these classes are forced
# back to decode-only (the interpreter faults at runtime on them).
DEFAULT_DECODEONLY_CLASSES = {
    "hmma_sparse_", "hmma_sparse_indexedRF_", "hmma_x8_indexedRF_",
    "qmma_rowcol_", "qmma_scale_", "qmma_sp_", "qmma_sp_rowcol_",
    "qmma_sp_scale_", "omma_sp_scale_",
}

REFERENCE_PLATFORM = (
    "NVIDIA RTX 5090 (GB202, sm_120); CUDA 13.0 (launchprobe), "
    "CUDA 13.1 (repo sm90/sm100 toolchain); driver 580.65.06"
)


def baseline_corpus(repo: Path) -> str:
    """Count the existing verification corpus at baseline-freeze time."""
    cu = sorted(repo.glob("tests/*.cu"))
    asm = sorted(repo.glob("tests/asm_construct/test_*.py"))
    dec = sorted(repo.glob("tools/decode_*.py"))
    return (f"tests/*.cu: {len(cu)}; "
            f"tests/asm_construct/test_*.py: {len(asm)}; "
            f"tools/decode_*.py: {len(dec)}")


def row_state(variant: dict, mnemonic_states: dict) -> tuple[str, str]:
    """Return (C++ state name, note) for a variant.

    Phase 1: the decoder uniquely decodes every sm120 variant, so the baseline
    state is 'decode-only' for all 1414.  Later phases raise states to
    functional/profiled per mnemonic.  Override with mnemonic_states for a
    phase transition (e.g. {'IMAD': 'functional'} once a semantic handler
    lands).
    """
    st = mnemonic_states.get(variant["mnemonic"], "decode-only")
    return STATE_NAMES[st], ""


def build_rows(db: dict, mnemonic_states: dict):
    """Deterministic row list: sorted by (opcode, mnemonic, variant_class)."""
    rows = []
    for v in db["variants"]:
        st, note = row_state(v, mnemonic_states)
        st = DEFAULT_CLASS_STATES.get(v["class"], st)
        if v["class"] in DEFAULT_DECODEONLY_CLASSES:
            st = "kDecodeOnly"
        rows.append({
            "mnemonic": v["mnemonic"],
            "variant_class": v["class"],
            "opcode": int(v["opcode"]),
            "pipe": v["pipe_suffix"],
            "state": st,
            "note": note,
        })
    rows.sort(key=lambda r: (r["opcode"], r["mnemonic"], r["variant_class"]))
    return rows


def emit_hpp(out: Path, rows: list) -> None:
    lines = [
        "// Generated file -- do not edit.  Regenerate with:",
        "//   python3 semu/tools/gen_capability.py",
        "#pragma once",
        "#include <semu/capability.hpp>",
        "",
        "namespace semu::generated {",
        "struct CapabilityRow {",
        "    const char* mnemonic;",
        "    const char* variant_class;",
        "    std::uint16_t opcode;",
        "    const char* pipe;",
        "    semu::CapabilityState state;",
        "    const char* note;",
        "};",
        "",
        "struct CapabilityManifestData {",
        "    int manifest_version;",
        "    const char* generator;",
        "    const char* generated_from;",
        "    const char* arch;",
        "    int variants;",
        "    int mnemonics;",
        "    int enums;",
        "    int tables;",
        "    int funit_fields;",
        "    int pipes;",
        "    const char* reference_platform;",
        "    const char* baseline_corpus;",
        "    int num_rows;",
        "    const CapabilityRow* rows;",
        "};",
        "",
        "extern const CapabilityManifestData kCapabilityManifest;",
        "}  // namespace semu::generated",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")


def emit_cpp(out: Path, header: dict, rows: list, generated_from: str) -> None:
    def q(s: str) -> str:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    L = [
        "// Generated file -- do not edit.  Regenerate with:",
        "//   python3 semu/tools/gen_capability.py",
        "#include <semu/capability.hpp>",
        "#include \"capability_data.hpp\"",
        "",
        "namespace semu::generated {",
        "static constexpr CapabilityRow kRows[] = {",
    ]
    for r in rows:
        L.append(
            f'    {{{q(r["mnemonic"])}, {q(r["variant_class"])}, '
            f'{r["opcode"]}, {q(r["pipe"])}, '
            f'semu::CapabilityState::{r["state"]}, {q(r["note"])}}},'
        )
    L += [
        "};",
        "",
        f"const CapabilityManifestData kCapabilityManifest = {{",
        f"    {header['manifest_version']},",
        f"    {q(header['generator'])}, {q(generated_from)}, {q(ARCH)},",
        f"    {header['variants']}, {header['mnemonics']}, {header['enums']}, "
        f"{header['tables']}, {header['funit_fields']}, {header['pipes']},",
        f"    {q(header['reference_platform'])}, {q(header['baseline_corpus'])},"
        f" {len(rows)}, kRows,",
        "};",
        "}  // namespace semu::generated",
        "",
    ]
    out.write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(REPO / "sm120.json"))
    ap.add_argument("--output-dir", default=str(REPO / "semu" / "generated"))
    ap.add_argument("--mnemonic-state", action="append", default=[],
                    metavar="MNEM=state",
                    help="override state for a mnemonic (e.g. IMAD=decode-only)")
    args = ap.parse_args()

    db = json.load(open(args.db))
    counts = db["meta"]["counts"]

    mnemonic_states = dict(DEFAULT_MNEMONIC_STATES)
    for spec in args.mnemonic_state:
        m, _, st = spec.partition("=")
        if st not in STATE_NAMES:
            print(f"error: bad state {st!r} (want {sorted(STATE_NAMES)})",
                  file=sys.stderr)
            return 1
        mnemonic_states[m] = st

    rows = build_rows(db, mnemonic_states)

    header = {
        "manifest_version": MANIFEST_VERSION,
        "generator": "semu/tools/gen_capability.py",
        "variants": counts["variants"],
        "mnemonics": counts["mnemonics"],
        "enums": counts["enums"],
        "tables": counts["tables"],
        "funit_fields": counts["funit_fields"],
        "pipes": counts["pipes"],
        "reference_platform": REFERENCE_PLATFORM,
        "baseline_corpus": baseline_corpus(REPO),
    }

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    hpp = out_dir / "capability_data.hpp"
    cpp = out_dir / "capability_data.cpp"
    emit_hpp(hpp, rows)
    emit_cpp(cpp, header, rows, Path(args.db).name)

    print(f"wrote {hpp} ({len(rows)} rows)")
    print(f"wrote {cpp}")
    print(f"states: {rows[0]['state']}..{rows[-1]['state']} baseline "
          f"(opcodes {rows[0]['opcode']}..{rows[-1]['opcode']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
