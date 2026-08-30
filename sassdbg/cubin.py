"""sassdbg.cubin — cubin ELF parsing for the real-cubin debugger path (M10).

Stdlib-only ELF64 reader for nvcc cubins: locates a kernel's .text.<func>
section (file offset + words), the FUNC symbol's entry offset within it,
and every text relocation targeting the entry trampoline window
([entry, entry+0x20)) — the M10 trampoline overwrites the first two
instructions, so a relocation applied there by the driver would corrupt
it (such kernels are rejected).

CUDA 13 "merc" cubins carry relocations in `.nv.merc.rela.text.<func>`
(LOPROC+0x82) instead of (empty) `.rela.text.<func>` — both are checked.
"""
import struct
import shutil
import subprocess
from dataclasses import dataclass

SHT_SYMTAB = 2
SHT_RELA = 4
SHT_REL = 9
STT_FUNC = 2                      # st_info & 0xF
STO_ENTRY = 0x10                  # CUDA kernel entry (st_other)


@dataclass
class Section:
    name: str
    typ: int
    off: int
    size: int
    link: int
    entsize: int
    index: int


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
        name, typ, _fl, _ad, off, size, link, _info, _al, es = \
            struct.unpack_from("<IIQQQQIIQQ", data, b)
        raw.append((name, typ, off, size, link, es))
    stroff = raw[shstrndx][2]

    def name_of(n: int) -> str:
        e = data.index(b"\0", stroff + n)
        return data[stroff + n:e].decode()

    return [Section(name_of(n), t, off, sz, lk, es, i)
            for i, (n, t, off, sz, lk, es) in enumerate(raw)]


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


def text_reloc_offsets(data: bytes, secs: list[Section],
                       func: str) -> list[int]:
    """All r_offsets from .rela.text.<func> / .rel.text.<func> and the
    CUDA-13 merc variant .nv.merc.rela.text.<func>."""
    out = []
    for s in secs:
        if s.name not in (f".rela.text.{func}", f".rel.text.{func}",
                          f".nv.merc.rela.text.{func}"):
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

    def word(self, i: int) -> tuple[int, int]:
        return self.words[i]


def load_kernel(cubin_path: str, func: str | None = None) -> KernelText:
    """Locate `func`'s .text section in a cubin; reject entry relocs.

    With func=None the cubin must contain exactly one FUNC symbol.
    The entry window [entry, entry+0x20) must be relocation-free (the
    M10 trampoline goes there).
    """
    data = open(cubin_path, "rb").read()
    secs = _sections(data)
    funcs = [s for s in _symbols(data, secs)
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
    body = data[sec.off + entry: sec.off + entry + sym.size] \
        if sym.size else data[sec.off + entry: sec.off + sec.size]
    assert len(body) % 16 == 0 and len(body) >= 0x20
    words = [struct.unpack_from("<QQ", body, i)
             for i in range(0, len(body), 16)]
    return KernelText(sec.name[len(".text."):], sec.off + entry,
                      len(words), words)


def cuobjdump_sass(cubin_path: str) -> str:
    exe = shutil.which("cuobjdump") or "/usr/local/cuda/bin/cuobjdump"
    return subprocess.run([exe, "-sass", cubin_path],
                          capture_output=True, text=True, check=True).stdout
