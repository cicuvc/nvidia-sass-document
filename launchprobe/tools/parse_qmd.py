#!/usr/bin/env python3
"""parse_qmd.py - extract & diff inline QMDs from launch segments.

Reconstructs the 96-dword (384B) QMD from SET_INLINE_QMD_ADDRESS records and
diffs QMDs across launches to isolate per-launch fields.
"""
import glob
import struct
import sys

sys.path.insert(0, "tools")
from parse_seg import parse, load_methods


def extract_qmds(path, methods):
    data = open(path, "rb").read()
    qmds = []
    for r in parse(data, methods):
        if r["mthd"] == 0x318:
            addr_hi, addr_lo = r["data"][0], r["data"][1]
            qmd = r["data"][2:]
            qmds.append({
                "flags_hi": addr_hi,
                "addr": addr_lo << 8,
                "words": qmd,
            })
    return qmds


def main():
    methods = load_methods(["include/sdk/clc1c0.h"])
    files = sorted(glob.glob(sys.argv[1]))
    all_q = []
    for f in files:
        qs = extract_qmds(f, methods)
        if qs:
            all_q.append((f, qs))
    if not all_q:
        print("no QMDs found")
        return
    # show first segment's QMDs
    f0, qs0 = all_q[0]
    print(f"{f0}: {len(qs0)} QMD record(s)")
    for qi, q in enumerate(qs0):
        print(f"  QMD[{qi}] flags_hi={q['flags_hi']:#x} addr={q['addr']:#x} "
              f"len={len(q['words']) * 4}B")
        w = q["words"]
        for i in range(0, len(w), 4):
            print(f"    +{i * 4:#04x}: " + " ".join(f"{x:08x}" for x in w[i:i + 4]))
    # diff first QMD of each launch segment against the first
    base = qs0[0]["words"]
    print("\n=== diff of QMD[0] across launches (dword idx: values) ===")
    n = min(len(all_q), 10)
    diffs = {}
    for li in range(n):
        w = all_q[li][1][0]["words"]
        for i in range(min(len(base), len(w))):
            if w[i] != base[i]:
                diffs.setdefault(i, {})[li] = w[i]
    for i, vals in sorted(diffs.items()):
        print(f"  dw{i:2d} (+{i * 4:#04x}): " +
              " ".join(f"L{li}={v:#010x}" for li, v in sorted(vals.items())))


if __name__ == "__main__":
    main()
