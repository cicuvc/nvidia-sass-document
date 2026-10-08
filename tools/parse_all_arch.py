#!/usr/bin/env python3
"""Build the JSON ISA database for every architecture dump in the repo.

The repo holds nvdisasm dumps for eight architectures; each already has — or can reuse — a
parser backend:

| arch    | dump                       | latencies | backend          |
|---------|----------------------------|-----------|------------------|
| sm70    | `sm_70_instructions.txt`   | -         | `parse_sm90`     |
| sm75    | `sm_75_instructions.txt`   | -         | `parse_sm90`     |
| sm80    | `sm_80_instructions.txt`   | -         | `parse_sm90`     |
| sm89    | `sm_89_instructions.txt`   | yes       | `parse_sm90`     |
| sm90    | `sm_90_instructions.txt`   | yes       | `parse_sm90`     |
| sm100   | `sm100_instructions.txt`   | yes       | `parse_sm100`    |
| sm103   | `sm_103_instructions.txt`  | yes       | `parse_sm100`    |
| sm107   | `sm_107_instructions.txt`  | yes       | `parse_sm100`    |
| sm120   | `sm120_instructions.txt`   | yes       | `parse_sm120`    |

The backends are near-copies with the same dump grammar, so this driver just points each
one at the right files and reports the structural gate per architecture.  No architecture
is silently skipped: a missing dump or a failing gate is an error.

Usage
-----
    python3 tools/parse_all_arch.py                # build every DB
    python3 tools/parse_all_arch.py --only sm103   # one architecture
    python3 tools/parse_all_arch.py --list         # what would be built, and from where
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

#: arch -> (instructions dump, latencies dump or None, parser module, output db)
ARCHES: dict[str, tuple[str, str | None, str, str]] = {
    "sm70":  ("sm_70_instructions.txt",  None,                  "parse_sm90",  "sm70.json"),
    "sm75":  ("sm_75_instructions.txt",  None,                  "parse_sm90",  "sm75.json"),
    "sm80":  ("sm_80_instructions.txt",  None,                  "parse_sm90",  "sm80.json"),
    "sm89":  ("sm_89_instructions.txt",  "sm_89_latencies.txt", "parse_sm90",  "sm89.json"),
    "sm90":  ("sm_90_instructions.txt",  "sm_90_latencies.txt", "parse_sm90",  "sm90.json"),
    "sm100": ("sm100_instructions.txt",  "sm100_latencies.txt", "parse_sm100", "sm100.json"),
    "sm103": ("sm_103_instructions.txt", "sm_103_latencies.txt", "parse_sm100", "sm103.json"),
    "sm107": ("sm_107_instructions.txt", "sm_107_latencies.txt", "parse_sm100", "sm107.json"),
    "sm120": ("sm120_instructions.txt",  "sm120_latencies.txt", "parse_sm120", "sm120.json"),
}

#: No-latency architectures: the OPERATION SETS block is absent, so the pipe list is
#: derived from the OPCODES-name suffixes (parse_sm75_80.py's approach).
NO_LATENCY = {"sm70", "sm75", "sm80"}


def build(arch: str, indent: int = 1) -> int:
    instr, lat, backend_name, out_name = ARCHES[arch]
    instr_path = REPO / instr
    if not instr_path.exists():
        print(f"{arch}: MISSING {instr}", file=sys.stderr)
        return 1

    backend = __import__(backend_name)
    if arch in NO_LATENCY:
        import parse_sm75_80
        return parse_sm75_80.build(instr, out_name)

    backend.INSTR = instr_path
    if lat:
        lat_path = REPO / lat
        if not lat_path.exists():
            print(f"{arch}: MISSING {lat}", file=sys.stderr)
            return 1
        backend.LAT = lat_path

    argv = ["-o", str(REPO / out_name), "--indent", str(indent)]
    # parse_sm100/parse_sm90 accept --instructions/--latencies; parse_sm120 only takes
    # --out, so the file paths are always injected through the module globals above.
    if backend_name != "parse_sm120":
        argv = ["--instructions", str(instr_path)] + argv
        if lat:
            argv = ["--latencies", str(REPO / lat)] + argv
    saved = sys.argv
    sys.argv = [backend_name] + argv
    try:
        backend.main()
    finally:
        sys.argv = saved
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append", choices=sorted(ARCHES),
                    help="build only this architecture (repeatable)")
    ap.add_argument("--list", action="store_true", help="show the build matrix and exit")
    ap.add_argument("--indent", type=int, default=1)
    args = ap.parse_args(argv)

    if args.list:
        for arch, (instr, lat, backend, out) in sorted(ARCHES.items()):
            have = "yes" if (REPO / instr).exists() else "**MISSING**"
            lath = "n/a" if lat is None else ("yes" if (REPO / lat).exists() else "**MISSING**")
            print(f"{arch:6s} instr={have:10s} lat={lath:10s} backend={backend:12s} -> {out}")
        return 0

    targets = args.only or sorted(ARCHES)
    failures = []
    for arch in targets:
        print(f"=== {arch} ===")
        if build(arch, args.indent):
            failures.append(arch)
    if failures:
        print(f"\nFAILED: {', '.join(failures)}", file=sys.stderr)
        return 1
    print(f"\nbuilt {len(targets)} ISA database(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
