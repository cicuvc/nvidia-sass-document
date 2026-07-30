from __future__ import annotations
import struct
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

MASK64 = (1 << 64) - 1

SHT_NULL = 0
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_NOTE = 7
SHT_NOBITS = 8
SHT_RELA = 4

SHT_CUDA_INFO = 0x70000000
SHT_CUDA_CONST0 = 0x70000001
SHT_CUDA_CALLGRAPH = 0x70000001
SHT_CUDA_COMPAT = 0x70000086

SHF_WRITE = 1
SHF_ALLOC = 2
SHF_EXEC = 4
SHF_INFO_LINK = 0x40
SHF_CUDA_LINK_ONCE = 0x02000000
SHF_CUDA_RETAIN = 0x01000000


class ElfError(Exception):
    pass


# ---------------------------------------------------------------------------
class StringTable:
    def __init__(self):
        self._buf = b"\x00"
        self._offsets: dict[str, int] = {"": 0}

    def add(self, s: str) -> int:
        if s in self._offsets:
            return self._offsets[s]
        off = len(self._buf)
        self._buf += s.encode() + b"\x00"
        self._offsets[s] = off
        return off

    @property
    def size(self) -> int:
        return len(self._buf)

    @property
    def data(self) -> bytes:
        return self._buf


# ---------------------------------------------------------------------------
STB_LOCAL = 0
STB_GLOBAL = 1
STT_NOTYPE = 0
STT_OBJECT = 1
STT_FUNC = 2
STT_SECTION = 3
VIS_HIDDEN = 2


@dataclass
class SymEntry:
    name_off: int = 0
    st_info: int = 0
    st_other: int = 0
    st_shndx: int = 0
    st_value: int = 0
    st_size: int = 0


class SymbolTable:
    def __init__(self):
        self.entries: list[SymEntry] = [SymEntry()]

    def add(self, name_off: int, bind: int, type_: int, shndx: int,
            value: int = 0, size: int = 0, other: int = 0) -> int:
        info = (bind << 4) | type_
        idx = len(self.entries)
        self.entries.append(SymEntry(
            name_off=name_off, st_info=info, st_other=other,
            st_shndx=shndx, st_value=value, st_size=size,
        ))
        return idx

    @property
    def size(self) -> int:
        return len(self.entries) * 24

    def serialize(self) -> bytes:
        buf = b""
        for e in self.entries:
            buf += struct.pack("<IBBHQQ", e.name_off, e.st_info,
                               e.st_other, e.st_shndx,
                               e.st_value, e.st_size)
        return buf

    @property
    def first_nonlocal(self) -> int:
        for i, e in enumerate(self.entries):
            if e.st_info >> 4:
                return i
        return len(self.entries)


# ---------------------------------------------------------------------------
@dataclass
class Section:
    name: str = ""
    sh_type: int = SHT_NULL
    sh_flags: int = 0
    content: bytes = b""
    link_idx: int = 0
    info_idx: int = 0
    addralign: int = 1
    entsize: int = 0
    addr: int = 0
    # filled later
    sh_name_off: int = 0
    sh_offset: int = 0
    sh_size: int = 0
    is_nobits: bool = False

    def __post_init__(self):
        self.sh_size = len(self.content) if not self.is_nobits else self.sh_size
        if self.sh_type == SHT_NOBITS:
            self.is_nobits = True

    def serialize_header(self) -> bytes:
        off = self.sh_offset
        sz = self.sh_size
        return struct.pack("<IIQQQQIIQQ",
                           self.sh_name_off, self.sh_type, self.sh_flags,
                           self.addr, off, sz,
                           self.link_idx, self.info_idx,
                           self.addralign, self.entsize)

    def data(self) -> bytes:
        if self.is_nobits:
            return b""
        return self.content


# ---------------------------------------------------------------------------
def eiattr_sval(etype: int, value: int) -> bytes:
    return struct.pack("<BBHI", 4, etype, 4, value)


def eiattr_hval(etype: int, value: int) -> bytes:
    return struct.pack("<BBH", 3, etype, value & 0xFFFF)


def eiattr_bval(etype: int, value: int) -> bytes:
    return struct.pack("<BBBB", 2, etype, value & 0xFF, 0)


def eiattr_regcount(func_sym: int, count: int) -> bytes:
    return struct.pack("<BBHII", 4, 0x2f, 8, func_sym, count)


def eiattr_kparam(ordinal: int, offset: int, size: int) -> bytes:
    sz_code = 0x21 if size >= 8 else 0x11
    flags = (sz_code << 16) | 0xf000
    return struct.pack("<BBHIHHI", 4, 0x17, 12, 0,
                       ordinal, offset, flags)


def eiattr_param_cbank(sym_idx: int, base: int, param_size: int) -> bytes:
    packed = (param_size << 16) | base
    return struct.pack("<BBHII", 4, 0x0a, 8, sym_idx, packed)


# ---------------------------------------------------------------------------
def note_nv_tkinfo() -> bytes:
    """NOTE section for toolkit info (0xa4 bytes, directly from reference cubin)."""
    with open(Path(__file__).resolve().parent / "minimal.cubin", "rb") as f:
        d = f.read()
    return d[0x4b8:0x4b8 + 0xa4]


def note_nv_cuver() -> bytes:
    with open(Path(__file__).resolve().parent / "minimal.cubin", "rb") as f:
        d = f.read()
    return d[0x55c:0x55c + 0x24]



# ---------------------------------------------------------------------------
class CubinBuilder:
    def __init__(self):
        self._instructions: list[tuple[int, int]] = []
        self._kernel_name = "my_kernel"
        self._regcount = 4
        self._exit_offset = 0
        self._params: list[tuple[int, int, int]] = []

    def set_code(self, instructions: list[tuple[int, int]],
                 kernel_name: str = "my_kernel") -> None:
        self._instructions = instructions
        self._kernel_name = kernel_name

    def set_params(self, params: list[tuple[int, int, int]]) -> None:
        self._params = params

    def set_regcount(self, count: int) -> None:
        self._regcount = count

    def set_exit_offset(self, offset: int) -> None:
        self._exit_offset = offset

    def set_sass(self, instructions: list[tuple[int, int]],
                 exit_offset: int = 0) -> None:
        self._instructions = instructions
        self._exit_offset = exit_offset

    @property
    def kernel_name(self) -> str:
        return self._kernel_name

    def strip_optional(self) -> int:
        return 0

    # ------------------------------------------------------------------
    def _mangle(self) -> str:
        return f"_Z{len(self._kernel_name)}{self._kernel_name}"

    # ------------------------------------------------------------------
    def build(self) -> bytes:
        mn = self._mangle()
        shstr = StringTable()
        strtab = StringTable()
        symtab = SymbolTable()
        secs: list[Section] = []

        def sec(name, type_, content=b"", flags=0, link=0, info=0,
                align=4, entsize=0, nobits=False):
            s = Section(name=name, sh_type=type_, sh_flags=flags,
                        content=content, link_idx=link, info_idx=info,
                        addralign=align, entsize=entsize)
            if nobits or type_ == SHT_NOBITS:
                s.is_nobits = True
                s.sh_size = len(content) if content else 0
                s.content = b""
            secs.append(s)
            return s

        # Section 0: NULL (mandatory)
        secs.append(Section())

        # Section 1: .shstrtab
        sec(".shstrtab", SHT_STRTAB, align=1)

        # 2: .strtab
        sec(".strtab", SHT_STRTAB, align=1)

        # 3: .symtab
        sec(".symtab", SHT_SYMTAB, align=8, entsize=24)

        # 4: .note.nv.tkinfo
        sec(".note.nv.tkinfo", SHT_NOTE, content=note_nv_tkinfo(),
            flags=SHF_CUDA_LINK_ONCE)

        # 6: .note.nv.cuver — link to .note.nv.tkinfo section
        # (link is filled after both sections exist)
        sec(".note.nv.cuver", SHT_NOTE, content=note_nv_cuver(),
            flags=SHF_INFO_LINK | SHF_CUDA_RETAIN)

        # 7: .nv.info (device-wide)
        nv_info = eiattr_regcount(6, self._regcount)
        # FRAME_SIZE, MIN/MAX_STACK_SIZE use 8-byte payloads (func_sym + value)
        nv_info += struct.pack("<BBHII", 4, 0x11, 8, 6, 0)  # FRAME_SIZE
        nv_info += struct.pack("<BBHII", 4, 0x12, 8, 6, 0)  # MIN_STACK_SIZE
        nv_info += struct.pack("<BBHII", 4, 0x23, 8, 6, 0)  # MAX_STACK_SIZE
        sec(".nv.info", SHT_CUDA_INFO, content=nv_info)

        # 8: .nv.info.<mangled> (per-kernel)
        buf = eiattr_sval(0x37, 0x80)  # CUDA_API_VERSION
        for ordinal, offset, size in self._params:
            buf += eiattr_kparam(ordinal, offset, size)
        buf += eiattr_hval(0x50, 0)    # SPARSE_MMA_MASK
        buf += eiattr_hval(0x1b, 0xff)  # MAXREG_COUNT
        buf += eiattr_bval(0x4a, 0)    # VRC_CTA_INIT_COUNT
        buf += eiattr_sval(0x1c, self._exit_offset)  # EXIT_INSTR_OFFSETS
        total_ps = sum(sz for _, _, sz in self._params)
        buf += eiattr_hval(0x19, total_ps)  # CBANK_PARAM_SIZE
        buf += eiattr_param_cbank(7, 0x380, total_ps)  # PARAM_CBANK
        buf += eiattr_sval(0x36, 0)  # SW_WAR
        sec(f".nv.info.{mn}", SHT_CUDA_INFO, content=buf,
            flags=SHF_INFO_LINK)

        # 9: .nv.compat
        compat = bytes([
            0x02, 0x02, 0x01, 0x00,  # ISA_CLASS=1
            0x02, 0x05, 0x05, 0x00,  # TCGEN05_MMA=5
            0x02, 0x03, 0x00, 0x00,  # TENSORMAP_V1=0
            0x02, 0x06, 0x01, 0x00,  # OPPORTUNISTIC_FINALIZATION=1
        ])
        sec(".nv.compat", SHT_CUDA_COMPAT, content=compat)

        # 10: .nv.callgraph
        cg = struct.pack("<8i", 0, -1, 0, -2, 0, -3, 0, -4)
        sec(".nv.callgraph", SHT_CUDA_CALLGRAPH, content=cg, entsize=8)

        # 11: .text.<mangled>
        raw = b"".join(struct.pack("<QQ", lo & MASK64, hi & MASK64)
                       for lo, hi in self._instructions)
        min_text = 256
        if len(raw) < min_text:
            nop = struct.pack("<QQ", 0x0000000000007918, 0x000fc00000000000)
            raw += nop * ((min_text - len(raw)) // 16 + 1)
            raw = raw[:min_text]
        sec(f".text.{mn}", SHT_PROGBITS, content=raw,
            flags=SHF_ALLOC | SHF_EXEC, align=128)

        # 13: .nv.shared.reserved.0 (NOBITS)
        sec(".nv.shared.reserved.0", SHT_NOBITS, content=b"\x00" * 0x40,
            flags=SHF_WRITE | SHF_ALLOC, align=1, nobits=True)

        # 14: .nv.constant0._Z<name>
        c0_size = 0x380 + total_ps
        sec(f".nv.constant0.{mn}", SHT_PROGBITS, content=b"\x00" * c0_size,
            flags=SHF_ALLOC | SHF_INFO_LINK)

        # ---------------------------------------------------------------
        # Build string tables
        for s in secs:
            s.sh_name_off = shstr.add(s.name)

        strtab.add(".nv.reservedSmem.offset0")
        strtab.add("__nv_reservedSMEM_offset_0_alias")
        for s in secs:
            strtab.add(s.name)
        strtab.add(mn)

        # Build symbols
        sym_text = symtab.add(strtab.add(f".text.{mn}"),
                              STB_LOCAL, STT_SECTION, 0)
        sym_rsm = symtab.add(strtab.add(".nv.reservedSmem.offset0"),
                             STB_LOCAL, STT_OBJECT, 0,
                             value=0x40, size=4, other=VIS_HIDDEN)
        sym_rsma = symtab.add(strtab.add("__nv_reservedSMEM_offset_0_alias"),
                              STB_GLOBAL, STT_NOTYPE, 0, value=0x40)
        sym_cg = symtab.add(strtab.add(".nv.callgraph"),
                            STB_LOCAL, STT_SECTION, 0)
        sym_func = symtab.add(strtab.add(mn), STB_GLOBAL, STT_FUNC, 0,
                              size=len(self._instructions) * 16)
        sym_c0 = symtab.add(strtab.add(f".nv.constant0.{mn}"),
                            STB_LOCAL, STT_SECTION, 0)

        # Fix shndx
        text_sec_name = f".text.{mn}"
        shmem_sec_name = ".nv.shared.reserved.0"
        cg_sec_name = ".nv.callgraph"
        c0_sec_name = f".nv.constant0.{mn}"

        for i, s in enumerate(secs):
            if s.name == text_sec_name:
                text_sec_idx = i
            if s.name == shmem_sec_name:
                shmem_sec_idx = i
            if s.name == cg_sec_name:
                cg_sec_idx = i
            if s.name == c0_sec_name:
                c0_sec_idx = i

        symtab.entries[sym_text].st_shndx = text_sec_idx
        symtab.entries[sym_rsm].st_shndx = shmem_sec_idx
        symtab.entries[sym_rsma].st_shndx = shmem_sec_idx
        symtab.entries[sym_cg].st_shndx = cg_sec_idx
        symtab.entries[sym_func].st_shndx = text_sec_idx
        symtab.entries[sym_c0].st_shndx = c0_sec_idx

        # Fix link/info
        symtab_idx = next(i for i, s in enumerate(secs) if s.name == ".symtab")
        strtab_idx = next(i for i, s in enumerate(secs) if s.name == ".strtab")
        secs[symtab_idx].link_idx = strtab_idx
        secs[symtab_idx].info_idx = sym_func

        nvinfo_krn_name = f".nv.info.{mn}"
        for i, s in enumerate(secs):
            if s.name == ".nv.info":
                s.link_idx = symtab_idx
            if s.name == nvinfo_krn_name:
                s.link_idx = symtab_idx
                s.info_idx = text_sec_idx
            if s.name == ".nv.callgraph":
                s.link_idx = symtab_idx
            if s.name == ".note.nv.cuver":
                for j, sj in enumerate(secs):
                    if sj.name == ".note.nv.tkinfo":
                        s.link_idx = j
                    if sj.name == ".nv.compat":
                        s.info_idx = j
            if s.name == text_sec_name:
                s.link_idx = symtab_idx
                s.info_idx = sym_func
            if s.name == c0_sec_name:
                s.info_idx = text_sec_idx

        shstrtab_idx = next(i for i, s in enumerate(secs)
                            if s.name == ".shstrtab")

        # Assign section data
        for s in secs:
            if s.name == ".shstrtab":
                s.content = shstr.data
                s.sh_size = shstr.size
            if s.name == ".strtab":
                s.content = strtab.data
                s.sh_size = strtab.size
            if s.name == ".symtab":
                s.content = symtab.serialize()
                s.sh_size = symtab.size

        # Layout: ELF header first, then section data, then section headers.
        # NOBITS sections share the current offset (occupy no file space).
        cur = 64
        for s in secs:
            if s.sh_type == SHT_NULL:
                s.sh_offset = 0
                continue
            if s.is_nobits:
                s.sh_offset = cur  # same as current — next PROGBITS
                continue
            al = max(s.addralign, 1)
            cur = (cur + al - 1) & ~(al - 1)
            s.sh_offset = cur
            s.sh_size = max(s.sh_size, len(s.content))
            cur += s.sh_size

        shdr_off = cur
        shdr_size = len(secs) * 64

        ehdr = struct.pack("<16sHHIQQQIHHHHHH",
                           b"\x7fELF\x02\x01\x01\x41\x08\x00\x00\x00\x00\x00\x00\x00\x00",
                           2, 190, 1, 0, 0, shdr_off,
                           0x06007802, 64, 0, 0, 64,
                           len(secs), shstrtab_idx,
                           )

        # Assemble: ELF header + section data + section headers
        buf = bytearray(ehdr)
        # Write section data
        for s in secs:
            d = s.data()
            if d:
                # Pad to alignment
                al = max(s.addralign, 1)
                pad = (al - (len(buf) % al)) % al
                if pad:
                    buf.extend(b"\x00" * pad)
                buf.extend(d)
        # Write section headers at the end
        for s in secs:
            buf += s.serialize_header()

        return bytes(buf)
