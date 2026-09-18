"""sassdbg.cubin — cubin ELF parsing for the real-cubin debugger path (M10)
and the M12 module/call-closure model.

Stdlib-only ELF64 reader for nvcc cubins: locates a kernel's .text.<func>
section (file offset + words), the FUNC symbol's entry offset within it,
and every native text relocation targeting the entry trampoline window
([entry, entry+0x20)) — the M10 trampoline overwrites the first two
instructions, so a relocation applied there by the driver would corrupt
it (such kernels are rejected).

CUDA 13 "capmerc" cubins carry a retained Mercury capsule: `.nv.merc.*`
sections (relocations, symbol table, debug info) that live in the capsule's
**separate Mercury address space**, not in the finalized native `.text`.
They must never be projected onto native instruction offsets (the offsets
can point outside the native section entirely).  This module therefore
distinguishes native symbols/relocations from capsule ones throughout.

Native symbols: the ordinary `.symtab` (SHT_SYMTAB).
Native relocations: `.rela.text.<func>` / `.rel.text.<func>`.
Capsule symbols: `.nv.merc.symtab`.
Capsule relocations: `.nv.merc.rela.*` / `.nv.merc.rel.*` (LOPROC+0x82).
"""
import struct
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

SHT_SYMTAB = 2
SHT_RELA = 4
SHT_REL = 9
STT_FUNC = 2                      # st_info & 0xF
STO_ENTRY = 0x10                  # CUDA kernel entry (st_other)

# Processor-specific section types (LOPROC + n).
SHT_NV_MERC_RELA = 0x70000082     # .nv.merc.rela.*
SHT_NV_MERC_SYMTAB = 0x70000085   # .nv.merc.symtab


def _is_merc_name(name: str) -> bool:
    """Mercury/capmerc sections live in the capsule's own address space."""
    return name.startswith(".nv.merc.") or name.startswith(".nv.capmerc.")


@dataclass
class Section:
    name: str
    typ: int
    off: int
    size: int
    link: int
    entsize: int
    index: int
    addr: int = 0              # sh_addr (link-time VA)
    flags: int = 0             # sh_flags
    info: int = 0              # sh_info (section-relative symbol index)
    reloc: bool = False        # sh_info selects the target section for RELA/REL


@dataclass
class Symbol:
    name: str
    value: int
    size: int
    info: int
    other: int
    shndx: int


def _sections(data: bytes) -> list[Section]:
    assert data[:4] == b"\x7fELF", "not an ELF"
    assert data[4] == 2, "not ELF64"
    shoff, = struct.unpack_from("<Q", data, 0x28)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 0x3A)
    raw = []
    for i in range(shnum):
        b = shoff + i * shentsize
        name, typ, fl, addr, off, size, link, info, _al, es = \
            struct.unpack_from("<IIQQQQIIQQ", data, b)
        raw.append((name, typ, fl, addr, off, size, link, info, es))
    stroff = raw[shstrndx][4]

    def name_of(n: int) -> str:
        e = data.index(b"\0", stroff + n)
        return data[stroff + n:e].decode()

    return [Section(name_of(n), t, off, sz, lk, es, i, ad, fl, inf,
                    t in (SHT_RELA, SHT_REL))
            for i, (n, t, fl, ad, off, sz, lk, inf, es) in enumerate(raw)]


def _symbols(data: bytes, secs: list[Section]) -> list[Symbol]:
    out = []
    for s in secs:
        if s.typ != SHT_SYMTAB:
            continue
        strs = secs[s.link]
        for j in range(s.size // s.entsize):
            st_name, st_info, st_other, st_shndx, st_value, st_size = \
                struct.unpack_from("<IBBHQQ", data,
                                   s.off + j * s.entsize)
            base = secs[s.link].off
            e = data.index(b"\0", base + st_name)
            out.append(Symbol(data[base + st_name:e].decode(),
                              st_value, st_size, st_info, st_other,
                              st_shndx))
    return out


def _symbols_in(data: bytes, secs: list[Section],
                names: tuple[str, ...]) -> list[Symbol]:
    """Symbols from the named symtab sections only (`.symtab` and the
    Mercury `.nv.merc.symtab` use different section types, so match by
    name rather than SHT_SYMTAB alone)."""
    out = []
    for s in secs:
        if s.name not in names:
            continue
        strs = secs[s.link]
        for j in range(s.size // s.entsize):
            st_name, st_info, st_other, st_shndx, st_value, st_size = \
                struct.unpack_from("<IBBHQQ", data,
                                   s.off + j * s.entsize)
            base = secs[s.link].off
            e = data.index(b"\0", base + st_name)
            out.append(Symbol(data[base + st_name:e].decode(),
                              st_value, st_size, st_info, st_other,
                              st_shndx))
    return out


def native_symbols(data: bytes, secs: list[Section]) -> list[Symbol]:
    """Symbols from the ordinary `.symtab` (native SASS text objects)."""
    return _symbols_in(data, secs, (".symtab",))


def capsule_symbols(data: bytes, secs: list[Section]) -> list[Symbol]:
    """Symbols from `.nv.merc.symtab` (retained capmerc capsule space)."""
    return _symbols_in(data, secs, (".nv.merc.symtab",))


@dataclass
class Relocation:
    """One ELF64 relocation record.

    `symbol` names the symbol table entry the record references (native or
    capsule, per `mercury`).  `target_section` is the *sh_info* of the
    relocation section: the section index the `offset` is relative to.  This
    is how a relocation is attached to its text island without any name
    concatenation (`.rela.text.foo` -> target `.text.foo`).
    """
    section: str        # the relocation section's name (e.g. .rela.text.<func>)
    offset: int         # r_offset: target-section-relative address
    type: int
    symbol: str
    symbol_index: int
    addend: int
    mercury: bool
    target_section: int = 0       # sh_info of the relocation section
    addend_implicit: bool = False  # True for SHT_REL (addend read from word)

    def is_native(self) -> bool:
        return not self.mercury


@dataclass
class NativeRelocation(Relocation):
    mercury: bool = False


@dataclass
class CapsuleRelocation(Relocation):
    mercury: bool = True


def _reloc_symtab(data: bytes, secs: list[Section], s: Section,
                  default_name: str) -> list[Symbol]:
    """Symbol table the relocation section's sh_link selects."""
    if s.link < len(secs):
        symtab = _symbols_in(data, secs, (secs[s.link].name,))
        if symtab:
            return symtab
    return _symbols_in(data, secs, (default_name,))


def _rela_records(data: bytes, secs: list[Section], s: Section,
                  mercury: bool, default_symtab: str) -> list[Relocation]:
    symtab = _reloc_symtab(data, secs, s, default_symtab)
    recs = []
    for j in range(s.size // s.entsize):
        r_off, r_info, r_add = struct.unpack_from(
            "<QQq", data, s.off + j * s.entsize)
        sym_idx = r_info >> 32
        typ = r_info & 0xFFFFFFFF
        symbol = symtab[sym_idx].name if sym_idx < len(symtab) else ""
        recs.append((CapsuleRelocation if mercury else NativeRelocation)(
            s.name, r_off, typ, symbol, sym_idx, r_add, mercury, s.info))
    return recs


def _rel_records(data: bytes, secs: list[Section], s: Section,
                 mercury: bool, default_symtab: str) -> list[Relocation]:
    """SHT_REL entries carry no explicit addend: the addend is implicit in
    the target word.  Read the 64-bit word the relocation points at and use
    it as the addend (the usual semantics for merging a .rel into .rela)."""
    symtab = _reloc_symtab(data, secs, s, default_symtab)
    target = secs[s.info] if 0 <= s.info < len(secs) else None
    recs = []
    for j in range(s.size // s.entsize):
        r_off, r_info = struct.unpack_from("<QQ", data, s.off + j * s.entsize)
        sym_idx = r_info >> 32
        typ = r_info & 0xFFFFFFFF
        symbol = symtab[sym_idx].name if sym_idx < len(symtab) else ""
        addend = 0
        if target is not None and r_off + 8 <= target.size:
            addend = struct.unpack_from(
                "<Q", data, target.off + r_off)[0]
        recs.append((CapsuleRelocation if mercury else NativeRelocation)(
            s.name, r_off, typ, symbol, sym_idx, addend, mercury, s.info,
            True))
    return recs


def _relocations(data: bytes, secs: list[Section],
                 names: tuple[str, ...], mercury: bool) -> list[Relocation]:
    """Exactly one record per input entry; RELA and REL parse separately."""
    out: list[Relocation] = []
    for s in secs:
        if s.name not in names:
            continue
        if s.typ == SHT_RELA or (mercury and s.typ == SHT_NV_MERC_RELA):
            out.extend(_rela_records(
                data, secs, s, mercury, ".nv.merc.symtab" if mercury
                else ".symtab"))
        elif s.typ == SHT_REL:
            out.extend(_rel_records(
                data, secs, s, mercury, ".nv.merc.symtab" if mercury
                else ".symtab"))
    return out


def native_relocations(data: bytes, secs: list[Section]) -> list[Relocation]:
    """Native `.rela.*` / `.rel.*` records referencing `.symtab`."""
    names = tuple(s.name for s in secs
                  if (s.typ in (SHT_RELA, SHT_REL)
                      and not _is_merc_name(s.name)))
    return _relocations(data, secs, names, False)


def capsule_relocations(data: bytes, secs: list[Section]) -> list[Relocation]:
    """Retained `.nv.merc.rela.*` records referencing `.nv.merc.symtab`."""
    names = tuple(s.name for s in secs
                  if s.typ in (SHT_RELA, SHT_REL, SHT_NV_MERC_RELA)
                  and _is_merc_name(s.name))
    return _relocations(data, secs, names, True)


def relocations(data: bytes, secs: list[Section]) -> list[Relocation]:
    """Every relocation, native first, capsule last."""
    return (list(native_relocations(data, secs))
            + list(capsule_relocations(data, secs)))


def native_funcs(data: bytes, secs: list[Section]) -> list[Symbol]:
    """Every FUNC symbol from the native `.symtab`."""
    return [s for s in native_symbols(data, secs)
            if (s.info & 0xF) == STT_FUNC and s.shndx]


def text_sections(data: bytes, secs: list[Section]) -> list[Section]:
    """Native executable text sections (`.text.<func>` or plain `.text`)."""
    return [s for s in secs if s.name == ".text"
            or (s.name.startswith(".text.") and not _is_merc_name(s.name))]


def callgraph_records(data: bytes, secs: list[Section]) -> list[tuple[int, int]]:
    """Raw 8-byte records from the `.nv.callgraph` LOPROC+0x1 section.

    sh_link selects the native symtab and sh_info the text section the
    record indices refer to.  The exact adjacency encoding is a
    cross-check aid only (decoded CALL targets are authoritative), so this
    returns the raw (a, b) u32 pairs for caller-side interpretation.
    """
    for s in secs:
        if s.name != ".nv.callgraph" or s.entsize < 8:
            continue
        n = s.size // 8
        return [struct.unpack_from("<II", data, s.off + 8 * j)
                for j in range(n)]
    return []


def text_reloc_offsets(data: bytes, secs: list[Section], func: str,
                       *, include_mercury: bool = False) -> list[int]:
    """All *native* r_offsets from .rela.text.<func> / .rel.text.<func>.

    CUDA 13 cubins also carry `.nv.merc.rela.text.<func>` records, but those
    name positions in the retained capsule's separate Mercury address space
    (they can point outside the native section).  They are excluded unless
    `include_mercury=True` and must never feed native relocation checks.
    """
    out = []
    for s in secs:
        if s.name == f".rela.text.{func}" or s.name == f".rel.text.{func}":
            pass
        elif include_mercury and s.name == f".nv.merc.rela.text.{func}":
            pass
        else:
            continue
        for j in range(s.size // s.entsize):
            r_off, = struct.unpack_from("<Q", data, s.off + j * s.entsize)
            out.append(r_off)
    return out


@dataclass
class KernelText:
    """One kernel's text: file range, entry offset, 128-bit words."""
    func: str                     # mangled symbol/section name
    file_off: int                 # file offset of the entry instruction
    n_insts: int
    words: list[tuple[int, int]]  # (lo64, hi64) per instruction
    link_addr: int = 0            # sh_addr + entry: link-time VA base
    entry_off: int = 0            # entry offset within .text
    relocs: tuple[int, ...] = ()  # ALL text r_offsets (text-relative)

    def word(self, i: int) -> tuple[int, int]:
        return self.words[i]


def load_kernel(cubin_path: str, func: str | None = None) -> KernelText:
    """Locate `func`'s .text section in a cubin; reject entry relocs.

    With func=None the cubin must contain exactly one FUNC symbol.
    The entry window [entry, entry+0x20) must be relocation-free (the
    M10 trampoline goes there).
    """
    data = Path(cubin_path).read_bytes()
    secs = _sections(data)
    funcs = [s for s in native_symbols(data, secs)
             if (s.info & 0xF) == STT_FUNC and s.shndx]
    # Modern cubins mark host-launchable kernels with STO_ENTRY.  Keep
    # the fallback for older/tool-generated cubins that omit st_other.
    entries = [s for s in funcs if s.other & STO_ENTRY]
    syms = entries or funcs
    if func is None:
        if len(syms) != 1:
            raise ValueError(
                f"cubin has {len(syms)} kernels; pass func= "
                f"({[s.name for s in syms]})")
        sym = syms[0]
    else:
        cand = [s for s in syms if s.name == func]
        if not cand:      # allow a unique C++ base name -> mangled lookup
            prefix = f"_Z{len(func)}{func}"
            cand = [s for s in syms if s.name.startswith(prefix)]
        if len(cand) > 1:
            raise ValueError(f"kernel name {func!r} is ambiguous; "
                             f"matches {[s.name for s in cand]}")
        if not cand:
            raise ValueError(f"kernel {func!r} not found; "
                             f"have {[s.name for s in syms]}")
        sym = cand[0]
    sec = secs[sym.shndx]
    assert sec.name.startswith(".text."), \
        f"FUNC symbol in unexpected section {sec.name}"
    entry = sym.value               # offset of the entry within .text
    if entry > sec.size or (sym.size and entry + sym.size > sec.size):
        raise ValueError(f"kernel {sym.name!r} range is outside {sec.name}")
    for r in text_reloc_offsets(data, secs, sec.name[len(".text."):]):
        if entry <= r < entry + 0x20:
            raise ValueError(
                f"relocation at text+{r:#x} overlaps the M10 trampoline "
                f"window [{entry:#x}, {entry + 0x20:#x}) — kernel not "
                "supported")
    all_relocs = tuple(text_reloc_offsets(
        data, secs, sec.name[len(".text."):]))
    body = data[sec.off + entry: sec.off + entry + sym.size] \
        if sym.size else data[sec.off + entry: sec.off + sec.size]
    assert len(body) % 16 == 0 and len(body) >= 0x20
    words = [struct.unpack_from("<QQ", body, i)
             for i in range(0, len(body), 16)]
    return KernelText(sec.name[len(".text."):], sec.off + entry,
                      len(words), words, sec.addr + entry, entry,
                      all_relocs)


def cuobjdump_sass(cubin_path: str) -> str:
    exe = shutil.which("cuobjdump") or "/usr/local/cuda/bin/cuobjdump"
    return subprocess.run([exe, "-sass", cubin_path],
                          capture_output=True, text=True, check=True).stdout
