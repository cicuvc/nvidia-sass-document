#!/usr/bin/env python3
"""Remove named ELF sections from a cubin while repairing section indices.

GNU objcopy does not recognize CUDA's processor-specific ELF section types.
This deliberately small utility preserves section payload offsets and rewrites
only the section-header table, sh_link/sh_info references, and native symbol
table st_shndx values.
"""

from __future__ import annotations

import argparse
import fnmatch
import struct
from pathlib import Path


EH_SHOFF = 0x28
EH_SHENTSIZE = 0x3A
EH_SHNUM = 0x3C
EH_SHSTRNDX = 0x3E
SHDR = struct.Struct("<IIQQQQIIQQ")
SYMENT = struct.Struct("<IBBHQQ")
SHT_SYMTAB = 2
SHT_RELA = 4
SHF_INFO_LINK = 0x40


def strip_sections(data: bytes, patterns: list[str],
                   *, zero_payload: bool = False) -> bytes:
    out = bytearray(data)
    shoff = struct.unpack_from("<Q", out, EH_SHOFF)[0]
    shentsize = struct.unpack_from("<H", out, EH_SHENTSIZE)[0]
    shnum = struct.unpack_from("<H", out, EH_SHNUM)[0]
    shstrndx = struct.unpack_from("<H", out, EH_SHSTRNDX)[0]
    if shentsize != SHDR.size:
        raise ValueError(f"unsupported section-header size {shentsize}")
    headers = [list(SHDR.unpack_from(out, shoff + i * shentsize))
               for i in range(shnum)]
    shstr = headers[shstrndx]
    names = bytes(out[shstr[4]:shstr[4] + shstr[5]])

    def section_name(header: list[int]) -> str:
        return names[header[0]:].split(b"\0", 1)[0].decode()

    remove = {i for i, h in enumerate(headers)
              if i and any(fnmatch.fnmatch(section_name(h), p)
                           for p in patterns)}
    if zero_payload:
        # A removed section normally becomes unreachable but its bytes remain
        # in the sparse ELF layout.  Zeroing is useful for experiments that
        # must exclude a loader finding retained capsule data through some
        # non-section-header side channel.  SHT_NOBITS has no file payload.
        for i in remove:
            h = headers[i]
            if h[1] != 8 and h[5]:  # SHT_NOBITS
                out[h[4]:h[4] + h[5]] = b"\0" * h[5]
    keep = [i for i in range(shnum) if i not in remove]
    remap = {old: new for new, old in enumerate(keep)}

    # Native symbol tables may contain section symbols for retained Mercury
    # sections.  Make removed definitions undefined and remap every kept one.
    for h in headers:
        if h[1] != SHT_SYMTAB:
            continue
        off, size, entsize = h[4], h[5], h[9]
        if entsize != SYMENT.size:
            continue
        for p in range(off, off + size, entsize):
            ent = list(SYMENT.unpack_from(out, p))
            old_shndx = ent[3]
            if old_shndx in remove:
                ent[3] = 0
            elif old_shndx in remap:
                ent[3] = remap[old_shndx]
            SYMENT.pack_into(out, p, *ent)

    rewritten = []
    for old in keep:
        h = headers[old]
        if h[6] in remap:  # sh_link is a section index
            h[6] = remap[h[6]]
        elif h[6] in remove:
            h[6] = 0
        # sh_info is a section index for relocations and SHF_INFO_LINK.
        if h[1] == SHT_RELA or (h[2] & SHF_INFO_LINK):
            if h[7] in remap:
                h[7] = remap[h[7]]
            elif h[7] in remove:
                h[7] = 0
        rewritten.append(h)

    for i, h in enumerate(rewritten):
        SHDR.pack_into(out, shoff + i * shentsize, *h)
    # Zero stale headers so accidental scanners do not rediscover them.
    end = shoff + len(rewritten) * shentsize
    out[end:shoff + shnum * shentsize] = b"\0" * ((shnum - len(rewritten)) * shentsize)
    struct.pack_into("<H", out, EH_SHNUM, len(rewritten))
    struct.pack_into("<H", out, EH_SHSTRNDX, remap[shstrndx])
    return bytes(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("patterns", nargs="+")
    ap.add_argument("--zero-payload", action="store_true")
    args = ap.parse_args()
    args.output.write_bytes(strip_sections(
        args.input.read_bytes(), args.patterns,
        zero_payload=args.zero_payload))


if __name__ == "__main__":
    main()
