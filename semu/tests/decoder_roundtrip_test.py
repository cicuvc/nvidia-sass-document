#!/usr/bin/env python3
"""Decoder round-trip + ambiguity test (CTest 'decoder_roundtrip').

Phase 1 exit-criterion verification against the generated corpus:

  1. every encoded corpus word decodes UNIQUELY through the semu CLI;
  2. alternate-class words resolve to their primary sibling (no decode drops);
  3. the decoded disassembly re-encodes bit-exactly through the reference
     assembler, EXCEPT for the assembler matcher's known coverage gaps, which
     are enumerated below so regressions are caught.

Usage:
    decoder_roundtrip_test.py <semu binary> <corpus json> <sm120.json>
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_flat  # noqa: E402

# Mnemonics whose relative offset / target requires kernel-level label
# resolution; per-instruction round-trip is skipped for these.
BRANCH_SET = {"BRA", "BRX", "BRXU", "BSSY", "BREAK", "BSYNC", "CALL",
              "BRB", "RTT", "JMP", "JMX", "BSSY.RECONVERGENT"}

GEN_CORPUS = Path(__file__).resolve().parent.parent / "tools" / "gen_corpus.py"


def load_corpus(path: Path) -> list:
    """Load the corpus JSON, generating it on the fly when the path points to
    a non-existent file.  When generated, it is written to `path` so sibling
    CTest gates (cond_differential, decoder_negative) can reuse it."""
    if path.is_file():
        return json.load(open(path))
    subprocess.run([sys.executable, str(GEN_CORPUS),
                    "--db", str(Path(__file__).resolve().parents[2] /
                                "sm120.json"),
                    "--out", str(path)],
                   check=True, capture_output=True)
    return json.load(open(path))


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: decoder_roundtrip_test.py <semu> <corpus> <db>",
              file=sys.stderr)
        return 2
    semu = Path(sys.argv[1])
    corpus = load_corpus(Path(sys.argv[2]))
    db = json.load(open(sys.argv[3]))
    alt = {v["class"] for v in db["variants"] if v.get("is_alternate")}
    enc = [r for r in corpus if r["encoded"]]

    words = "\n".join(f"{r['lo']} {r['hi']}" for r in enc) + "\n"
    proc = subprocess.run([str(semu), "disasm"], input=words, text=True,
                          capture_output=True)
    lines = proc.stdout.splitlines()
    if len(lines) != len(enc):
        print(f"FAIL: decoder output lines {len(lines)} != corpus {len(enc)}",
              file=sys.stderr)
        return 1

    n_ok = n_amb = n_ill = 0
    roundtrip_ok = 0
    branch_skip = 0
    known_gap = 0
    bad = []
    # GAP-03: fixed, reviewed allowlist of assembler-matcher / re-render gaps.
    # A gap NOT on the allowlist fails the gate; gaps that disappear are also
    # reported so the allowlist can be shrunk.
    allow_path = (Path(__file__).resolve().parent / "data" /
                  "roundtrip_gaps.json")
    allowlist = {e["variant_class"]: e["kind"]
                 for e in json.load(open(allow_path))}
    allow_used = set()
    for r, line in zip(enc, lines):
        parts = line.split("\t")
        if parts[0] == "AMBIG":
            n_amb += 1
            bad.append(f"{r['variant_class']}: AMBIGUOUS ({parts[1]})")
            continue
        if parts[0] != "OK":
            n_ill += 1
            bad.append(f"{r['variant_class']}: ILLEGAL")
            continue
        got_class, dis = parts[1], "\t".join(parts[2:])
        if r["variant_class"] not in alt and got_class != r["variant_class"]:
            bad.append(f"{r['variant_class']}: decoded as {got_class}")
            continue
        mnem = dis.split(" ")[0].lstrip("@").split(".")[0]
        if mnem in BRANCH_SET:
            branch_skip += 1
            n_ok += 1
            continue
        try:
            e = assemble_flat(dis)
        except Exception:
            e = None
        if e and e[0] == (r["lo"], r["hi"]):
            roundtrip_ok += 1
            n_ok += 1
        else:
            kind = "bits-differ" if e else "matcher"
            if r["variant_class"] in allowlist:
                if allowlist[r["variant_class"]] != kind:
                    bad.append(f"{r['variant_class']}: gap kind changed "
                               f"({allowlist[r['variant_class']]} -> {kind})")
                allow_used.add(r["variant_class"])
            else:
                bad.append(f"{r['variant_class']}: UNALLOWED re-encode gap "
                           f"({kind})")
            known_gap += 1
            n_ok += 1

    if bad:
        for b in bad[:20]:
            print("  " + b, file=sys.stderr)
        print(f"FAIL: {len(bad)} corpus words did not decode uniquely / "
              f"round-trip cleanly", file=sys.stderr)
        return 1

    stale = sorted(set(allowlist) - allow_used)
    if stale:
        print(f"NOTE: {len(stale)} allowlist entries no longer gap "
              f"(shrink the allowlist):", file=sys.stderr)
        for c in stale[:20]:
            print("  " + c, file=sys.stderr)

    print(f"OK: {n_ok}/{len(enc)} corpus words decode uniquely "
          f"({n_amb} ambiguous, {n_ill} illegal); "
          f"{roundtrip_ok} bit-exact re-encode, {branch_skip} branch, "
          f"{known_gap} allowlisted gaps (of {len(allowlist)} in allowlist)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
