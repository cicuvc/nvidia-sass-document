#!/usr/bin/env python3
"""Extract real sm120 words from cubin SASS dumps into a JSON vector fixture
(GAP-05).  Each entry records the source cubin, kernel, PC, the SASS text
(cuobjdump's rendering), and the 128-bit word (lo64/hi64 from the two comment
lines).  The fixture is committed and used by decoder_cuobjdump_test.py.

The expectation text is cuobjdump's *printing* dialect (e.g. `desc[UR4]`,
`[R2.64]`), which the semu decoder renders in the assembler dialect; the test
compares mnemonics + register numbers, not the exact text.

Usage:
    extract_cuobj_vectors.py <out.json> [cubin ...]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

CUOBJDUMP = "/usr/local/cuda/bin/cuobjdump"


def extract(cubin: Path, arch="sm_120") -> list:
    p = subprocess.run([CUOBJDUMP, "-arch", arch, "-sass", str(cubin)],
                       text=True, capture_output=True)
    if p.returncode != 0:
        return []
    lines = p.stdout.splitlines()
    out = []
    kernel = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.search(r"Function : (\S+)", line)
        if m:
            kernel = m.group(1)
            i += 1
            continue
        m = re.match(r"\s*/\*([0-9a-fA-F]+)\*/\s+(.*?)\s*/\* 0x([0-9a-fA-F]{8,16}) \*/",
                     line)
        if m:
            pc = int(m.group(1), 16)
            text = m.group(2).strip()
            lo = int(m.group(3), 16)
            # next line has the hi64
            hi = 0
            if i + 1 < len(lines):
                m2 = re.search(r"0x([0-9a-fA-F]{8,16})", lines[i + 1])
                if m2:
                    hi = int(m2.group(1), 16)
            out.append({
                "cubin": cubin.name, "kernel": kernel, "pc": pc,
                "text": text, "lo": lo, "hi": hi,
            })
        i += 1
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: extract_cuobj_vectors.py <out.json> [cubin ...]",
              file=sys.stderr)
        return 2
    out_path = Path(sys.argv[1])
    rows = []
    for c in sys.argv[2:]:
        cubin = Path(c)
        if not cubin.is_file():
            print(f"skip missing {cubin}", file=sys.stderr)
            continue
        rows.extend(extract(cubin))
        print(f"{cubin.name}: {sum(1 for r in rows if r['cubin']==cubin.name)}"
              f" words", file=sys.stderr)
    # dedupe by (lo,hi)
    seen = set()
    uniq = []
    for r in rows:
        if (r["lo"], r["hi"]) in seen:
            continue
        seen.add((r["lo"], r["hi"]))
        uniq.append(r)
    out_path.write_text(json.dumps(uniq, indent=1), encoding="utf-8")
    print(f"wrote {out_path}: {len(uniq)} unique words from {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
