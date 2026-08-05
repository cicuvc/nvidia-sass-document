#!/usr/bin/env python3
"""Read a CUDA cubin (ELF) and extract per-kernel code + EIATTR metadata.

Pure-stdlib ELF reader.  The layout follows what the assembler writes
(assembler/sass_elf.py) and what nvcc/ptxas emits:

- `.text.<mangled>`          — 128-bit SASS instructions, one per 16 bytes
- `.nv.info.<mangled>`       — EIATTR records for that kernel
- `.symtab`                  — kernel symbols (mangled names)
- `.nv.constant0.<mangled>`  — kernel parameter constant-bank image

EIATTR record header is 4 bytes: <B version><B type><H payload_len>, then the
payload.  Recognised types: 0x17 KPARAM_INFO, 0x2f REGCOUNT, 0x1b MAXREG_COUNT,
0x0d SHARED (cbinfo), 0x4a VRC, 0x0a PARAM_CBANK.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

# ELF constants
SHT_SYMTAB = 2
SHT_PROGBITS = 1
SHT_CUDA_INFO = 0x70000000  # SHT_CUDA_INFO
SHT_CUDA_DATA = 0x70000001

# EIATTR types (payload is 4-byte version + type + 2-byte len header)
EIATTR_KPARAM = 0x17
EIATTR_REGCOUNT = 0x2f
EIATTR_MAXREG = 0x1b
EIATTR_SHADER_TYPE = 0x49
EIATTR_EXIT = 0x1c


@dataclass
class KParam:
    index: int      # parameter ordinal (0,1,2,...)
    offset: int     # byte offset within the cbank param buffer (matches
                    # assembler layout_params: 0, 8, 16, ...)
    size: int       # byte width of the parameter


@dataclass
class Kernel:
    mangled: str
    name: str
    instructions: list[tuple[int, int]] = field(default_factory=list)  # (lo,hi)
    kparams: list[KParam] = field(default_factory=list)
    regcount: int = 0
    maxreg: int = 0
    shared: int = 0

    def param_by_offset(self, offset: int) -> KParam | None:
        for kp in self.kparams:
            if kp.offset == offset:
                return kp
        return None

    def param_by_index(self, index: int) -> KParam | None:
        for kp in self.kparams:
            if kp.index == index:
                return kp
        return None


class ELFReader:
    """Minimal ELF64 reader (little-endian) with section/symbol lookup."""

    def __init__(self, data: bytes):
        if data[:4] != b"\x7fELF":
            raise ValueError("not an ELF file")
        self.data = data
        self.e_shoff = struct.unpack_from("<Q", data, 0x28)[0]
        self.e_shentsize = struct.unpack_from("<H", data, 0x3a)[0]
        self.e_shnum = struct.unpack_from("<H", data, 0x3c)[0]
        self.e_shstrndx = struct.unpack_from("<H", data, 0x3e)[0]
        self.sections = self._read_sections()

    def _read_sections(self) -> dict[str, tuple[int, int, int, int]]:
        """name -> (type, offset, size, addr)."""
        shstr_off, shstr_size = self._section_bounds(self.e_shstrndx)
        shstr = self.data[shstr_off:shstr_off + shstr_size]

        def sname(off: int) -> str:
            end = shstr.index(b"\x00", off)
            return shstr[off:end].decode(errors="replace")

        out: dict[str, tuple[int, int, int, int]] = {}
        for i in range(self.e_shnum):
            ent = self.e_shoff + i * self.e_shentsize
            name_off = struct.unpack_from("<I", self.data, ent)[0]
            stype = struct.unpack_from("<I", self.data, ent + 4)[0]
            off = struct.unpack_from("<Q", self.data, ent + 0x18)[0]
            size = struct.unpack_from("<Q", self.data, ent + 0x20)[0]
            addr = struct.unpack_from("<Q", self.data, ent + 0x10)[0]
            out[sname(name_off)] = (stype, off, size, addr)
        return out

    def _section_bounds(self, idx: int) -> tuple[int, int]:
        ent = self.e_shoff + idx * self.e_shentsize
        off = struct.unpack_from("<Q", self.data, ent + 0x18)[0]
        size = struct.unpack_from("<Q", self.data, ent + 0x20)[0]
        return off, size

    def section(self, name: str) -> bytes | None:
        info = self.sections.get(name)
        if info is None:
            return None
        stype, off, size, _ = info
        if stype == SHT_CUDA_INFO or size == 0:
            return self.data[off:off + size]
        return self.data[off:off + size]

    def symtab(self) -> list[tuple[str, int, int, int]]:
        """(name, value, size, shndx) for defined symbols."""
        info = self.sections.get(".symtab")
        if info is None:
            return []
        _, off, size, _ = info
        # find .strtab
        strtab = None
        for name, (stype, soff, ssize, _) in self.sections.items():
            if name == ".strtab":
                strtab = (soff, ssize)
                break
        if strtab is None:
            return []
        out = []
        n = size // 24
        for i in range(n):
            e = off + i * 24
            st_name = struct.unpack_from("<I", self.data, e)[0]
            st_value = struct.unpack_from("<Q", self.data, e + 8)[0]
            st_size = struct.unpack_from("<Q", self.data, e + 16)[0]
            st_shndx = struct.unpack_from("<H", self.data, e + 22)[0]
            if st_name == 0:
                continue
            so, ss = strtab
            end = self.data.index(b"\x00", so + st_name, so + ss)
            name = self.data[so + st_name:end].decode(errors="replace")
            out.append((name, st_value, st_size, st_shndx))
        return out


def demangle(name: str) -> str:
    """Itanium-style CUDA mangling: _Z{len}{name}{argtypes}."""
    if name.startswith("_"):
        name = name[1:]
    if not name.startswith("Z"):
        return name
    rest = name[1:]
    i = 0
    while i < len(rest) and rest[i].isdigit():
        i += 1
    if i == 0:
        return name
    n = int(rest[:i])
    return rest[i:i + n]


def parse_eiattr(payload: bytes) -> list[tuple[int, bytes]]:
    """Parse an EIATTR blob into [(type, payload), ...]."""
    out = []
    i = 0
    while i + 4 <= len(payload):
        etype = payload[i + 1]
        plen = struct.unpack_from("<H", payload, i + 2)[0]
        if i + 4 + plen > len(payload):
            break
        out.append((etype, payload[i + 4:i + 4 + plen]))
        i += 4 + plen
    return out


def kparam_size_code(flags: int) -> int:
    """size = (flags >> 14) & 0xffff...  nvcc packs (size<<2)|1 in bits 16-31."""
    code = (flags >> 16) & 0xffff
    return (code - 1) >> 2 if code else 0


def parse_eiattr_kparam(pl: bytes) -> KParam:
    # <BBHII: 4,0x17,12, u32[0]=0, u32[1]=offset<<16|index, u32[2]=flags
    _, _, plen = struct.unpack_from("<BBH", pl[:4])
    body = pl[4:4 + plen]
    if len(body) < 12:
        body = pl
    w1 = struct.unpack_from("<I", body, 4)[0]
    w2 = struct.unpack_from("<I", body, 8)[0]
    offset = (w1 >> 16) & 0xffff
    index = w1 & 0xffff
    size = kparam_size_code(w2)
    return KParam(index, offset, size)


def read_cubin(path: str) -> dict[str, Kernel]:
    """Read a cubin and return {mangled: Kernel}."""
    data = open(path, "rb").read()
    el = ELFReader(data)
    kernels: dict[str, Kernel] = {}

    # map .text.<mangled> / .nv.info.<mangled>
    text_secs: dict[str, bytes] = {}
    info_secs: dict[str, bytes] = {}
    for name, (stype, off, size, _) in el.sections.items():
        if name.startswith(".text."):
            sec = el.section(name)
            if sec is not None:
                text_secs[name[6:]] = sec
        elif name.startswith(".nv.info."):
            sec = el.section(name)
            if sec is not None:
                info_secs[name[9:]] = sec

    for mangled, text in text_secs.items():
        k = Kernel(mangled=mangled, name=demangle(mangled))
        for off in range(0, len(text) - 15, 16):
            lo = struct.unpack_from("<Q", text, off)[0]
            hi = struct.unpack_from("<Q", text, off + 8)[0]
            k.instructions.append((lo, hi))
        info = info_secs.get(mangled)
        if info:
            for etype, pl in parse_eiattr(info):
                if etype == EIATTR_KPARAM:
                    k.kparams.append(parse_eiattr_kparam(pl))
                elif etype == EIATTR_REGCOUNT:
                    if len(pl) >= 4:
                        k.regcount = struct.unpack_from("<I", pl, 0)[0]
                elif etype == EIATTR_MAXREG:
                    k.maxreg = pl[0] | (pl[1] << 8) if pl else 0
        k.kparams.sort(key=lambda kp: kp.index)
        kernels[mangled] = k
    return kernels


if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        ks = read_cubin(path)
        print(f"{path}: {len(ks)} kernel(s)")
        for mangled, k in ks.items():
            print(f"  {k.name:30s} ({mangled})  insts={len(k.instructions)} "
                  f"regcount={k.regcount} kparams={[(p.index, p.offset, p.size) for p in k.kparams]}")
