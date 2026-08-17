#!/usr/bin/env python3
"""Decoder ambiguity + reserved-bit test (CTest 'decoder_ambig').

Phase 1 exit-criterion verification for high-overlap opcodes:

  1. every F2FP/F2I/BAR/CCTL/PLOP3/PSETP (and other) corpus word decodes
     UNIQUELY (the discriminator/enum-membership logic must not regress);
  2. flipping a *reserved* bit -- one not covered by any encoding field of any
     candidate variant at that opcode -- must NOT silently match a different
     variant: the decode must be illegal or ambiguous, never a wrong unique
     decode.

Operand/discriminator/opcode bits ARE covered by fields, so flipping them may
legitimately produce a different valid instruction; those flips are not errors.

Usage:
    decoder_ambig_test.py <semu binary> <corpus json> <sm120.json>
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

GEN_CORPUS = Path(__file__).resolve().parent.parent / "tools" / "gen_corpus.py"


def field_ranges(v):
    """Flatten a variant's encoding field bit ranges into a set of bits."""
    bits = set()
    for f in v["encoding"]:
        for hi, lo in f["targets"]:
            for b in range(lo, hi + 1):
                bits.add(b)
    return bits


def load_corpus(path: Path) -> list:
    if path.is_file():
        return json.load(open(path))
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "corpus.json"
        subprocess.run([sys.executable, str(GEN_CORPUS),
                        "--db", str(Path(__file__).resolve().parents[2] /
                                    "sm120.json"),
                        "--out", str(out)],
                       check=True, capture_output=True)
        return json.load(open(out))


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: decoder_ambig_test.py <semu> <corpus> <db>",
              file=sys.stderr)
        return 2
    semu = Path(sys.argv[1])
    corpus = load_corpus(Path(sys.argv[2]))
    db = json.load(open(sys.argv[3]))

    # opcode -> union of bits covered by ANY candidate variant's fields
    covered_by_op = {}
    for v in db["variants"]:
        covered_by_op.setdefault(int(v["opcode"]), set()).update(
            field_ranges(v))

    focus = {"F2FP", "F2I", "BAR", "CCTL", "PLOP3", "PSETP", "HMMA", "QMMA",
             "IMAD", "IADD3", "LDG", "STG", "ATOM", "HFMA2", "ISETP"}
    focus_rows = [r for r in corpus
                  if r["encoded"] and r["mnemonic"] in focus]

    # 1. focus-set unique decode
    words = "\n".join(f"{r['lo']} {r['hi']}" for r in focus_rows) + "\n"
    proc = subprocess.run([str(semu), "disasm"], input=words, text=True,
                          capture_output=True)
    lines = proc.stdout.splitlines()
    bad = 0
    for r, line in zip(focus_rows, lines):
        if not line.startswith("OK"):
            print(f"  {r['variant_class']}: {line.split(chr(9))[0]}",
                  file=sys.stderr)
            bad += 1
    if bad:
        print(f"FAIL: {bad}/{len(focus_rows)} focus words not unique",
              file=sys.stderr)
        return 1

    # 2. reserved-bit flips: only bits NOT covered by any candidate field.
    # A truly reserved bit must not change the decode at all (it is read by no
    # field and no legality condition); if the flipped word decodes differently
    # the decoder is reading a bit it should not (or the spec data does).
    flips_ill = flips_same = flips_ambig = flips_other = 0
    flip_bad = []
    sample = focus_rows[::max(1, len(focus_rows) // 60)][:60]
    for r in sample:
        covered = covered_by_op.get(int(r["opcode"]), set())
        reserved = [b for b in range(128) if b not in covered]
        if not reserved:
            continue
        lo, hi = r["lo"], r["hi"]
        # reference decode of the unflipped word (corpus alternates resolve to
        # their primary sibling, so compare flip-decode against this, not the
        # corpus's alternate class name)
        p0 = subprocess.run([str(semu), "disasm", str(lo), str(hi)],
                            text=True, capture_output=True)
        out0 = p0.stdout.splitlines()[0] if p0.stdout.splitlines() else ""
        if not out0.startswith("OK"):
            continue
        ref_cls = out0.split("|")[0].replace("OK", "").strip()
        for bit in reserved:
            if bit >= 64:
                nlo, nhi = lo, hi ^ (1 << (bit - 64))
            else:
                nlo, nhi = lo ^ (1 << bit), hi
            p = subprocess.run([str(semu), "disasm", str(nlo), str(nhi)],
                               text=True, capture_output=True)
            out = p.stdout.splitlines()[0] if p.stdout.splitlines() else ""
            if out.startswith("ILLEGAL"):
                flips_ill += 1
            elif out.startswith("AMBIG"):
                flips_ambig += 1
            elif out.startswith("OK"):
                parts = out.split("|")
                got = parts[0].replace("OK", "").strip() if parts else ""
                dis = parts[2].strip() if len(parts) > 2 else ""
                if got == ref_cls:
                    flips_same += 1
                else:
                    flips_other += 1
                    if len(flip_bad) < 10:
                        flip_bad.append((r["variant_class"], bit, got, dis))
    if flip_bad:
        print("reserved-bit flip matched a DIFFERENT variant (must not):",
              file=sys.stderr)
        for cls, bit, got, dis in flip_bad:
            print(f"  {cls}: flip reserved bit {bit} -> {got}: {dis}",
                  file=sys.stderr)
        print(f"FAIL: {len(flip_bad)} reserved-bit flip(s) mis-decoded",
              file=sys.stderr)
        return 1

    print(f"OK: {len(focus_rows)} focus words unique; "
          f"{sum(1 for r in sample if covered_by_op.get(int(r['opcode']), set()))} "
          f"sample words, reserved-bit flips -> {flips_ill} illegal, "
          f"{flips_same} same, {flips_ambig} ambiguous, {flips_other} other")
    return 0


if __name__ == "__main__":
    sys.exit(main())
