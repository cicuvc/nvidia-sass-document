#!/usr/bin/env python3
"""parse_seg.py - parse pushbuffer segments dumped by libnvtrace.

Method header format (Volta+, verified by perfect tiling of 1848B segments):
  hdr[12:0]  = method offset / 4
  hdr[15:13] = subchannel
  hdr[28:16] = data word count
  hdr[31:29] = mode (1=INC, 3=NONINC)

usage: parse_seg.py SEGMENT.bin [--hdrs clc1c0.h clc96f.h] [--qmd out.bin]
"""
import argparse
import re
import struct
import sys


def load_methods(paths):
    """Extract method address defines; a name is a method if no other define
    extends it with _FIELD (envytools heuristic)."""
    defines = {}
    for p in paths:
        for m in re.finditer(r"^#define\s+(NV\w+?)\s+(0x[0-9a-fA-F]+)\s*$",
                             open(p).read(), re.M):
            defines[m.group(1)] = int(m.group(2), 16)
    names = set(defines)
    methods = {}
    for name, val in defines.items():
        if not any(n.startswith(name + "_") for n in names):
            methods.setdefault(val, name)
    return methods


def parse(data, methods):
    d = struct.unpack("<%dI" % (len(data) // 4), data)
    i = 0
    recs = []
    while i < len(d):
        hdr = d[i]
        if hdr == 0 and all(x == 0 for x in d[i:]):
            break
        mthd = (hdr & 0x1FFF) * 4
        subch = (hdr >> 13) & 7
        cnt = (hdr >> 16) & 0x1FFF
        mode = (hdr >> 29) & 7
        words = d[i + 1:i + 1 + cnt]
        recs.append({
            "off": i * 4, "mthd": mthd, "subch": subch, "cnt": cnt,
            "mode": mode, "data": words,
            "name": methods.get(mthd, "?"),
        })
        i += 1 + cnt
    return recs


def show(recs, verbose_data=8):
    qmd_addr = None
    qmd_words = []
    for r in recs:
        mode_s = {1: "INC", 3: "NONINC"}.get(r["mode"], str(r["mode"]))
        print(f"{r['off']:#06x}: [{r['subch']}] {r['name']} ({r['mthd']:#06x}) "
              f"{mode_s} x{r['cnt']}")
        if r["name"].startswith("NVC1C0_SET_INLINE_QMD_ADDRESS"):
            pass
        if r["mthd"] == 0x318 and r["cnt"] >= 2:
            # SET_INLINE_QMD_ADDRESS_A/B: value is QMD GPU VA >> 8.
            # A carries flags in bit30 (0x40000000 = launch trigger/valid);
            # addr = {A,B}<<8 with flag bits masked out (empirical).
            flags = r["data"][0] & ~0x3FFFFFFF
            qmd_addr = ((r["data"][0] & 0x3FFFFFFF) << 32 | r["data"][1]) << 8
            rest = r["data"][2:]
            qmd_words.extend(rest)
            print(f"       QMD address = {qmd_addr:#x} flags = {flags:#x}, "
                  f"then {len(rest)} inline dwords")
        elif qmd_addr is not None and r["mthd"] == 0x318:
            qmd_words.extend(r["data"])
        elif r["mthd"] == 0x318:
            qmd_words.extend(r["data"])
        for j, w in enumerate(r["data"][:verbose_data]):
            print(f"       +{j * 4:#04x} = {w:#010x}")
        if r["cnt"] > verbose_data:
            print(f"       ... ({r['cnt'] - verbose_data} more)")
    return qmd_addr, qmd_words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("segment")
    ap.add_argument("--hdrs", nargs="+",
                    default=["include/sdk/clc1c0.h", "include/sdk/clc96f.h"])
    ap.add_argument("--data", type=int, default=8, help="data words to print")
    args = ap.parse_args()
    methods = load_methods(args.hdrs)
    data = open(args.segment, "rb").read()
    recs = parse(data, methods)
    qmd_addr, qmd_words = show(recs, args.data)
    if qmd_words:
        out = args.segment + ".qmd.bin"
        open(out, "wb").write(struct.pack("<%dI" % len(qmd_words), *qmd_words))
        print(f"QMD ({len(qmd_words) * 4} bytes) -> {out}")


if __name__ == "__main__":
    main()
