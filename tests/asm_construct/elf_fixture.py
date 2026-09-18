"""tests/asm_construct/elf_fixture.py — minimal ELF64 cubin builder for the
M12a acceptance fixtures (CPU-only; the images never run on a GPU).

The sassdbg.cubin readers are general ELF64 parsers, so the fixtures only
need a structurally valid ELF with controlled .text/.symtab/.rela/.rel
sections.  This lets the tests exercise the module model's relocation
association, SHT_REL handling, multi-island resolution, per-opcode CALL/RET
decoding, container/overlap functions, token hazards, zero-sized symbols and
duplicate names without depending on a particular nvcc codegen.
"""
from __future__ import annotations

import struct

SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_RELA = 4
SHT_REL = 9
STT_FUNC = 2
STO_ENTRY = 0x10


def _pack_words(words):
    return b"".join(struct.pack("<QQ", lo, hi) for lo, hi in words)


def build_elf(*, texts, rela=(), rel=()):
    """Build a minimal, structurally valid ELF64 (ET_REL) byte image.

    texts: list of (name, sh_addr, words, funcs) where
           words = [(lo64, hi64), ...] and
           funcs = [(name, value, size, entry_flag), ...] with `value` the
                   byte offset of the function within its own text section.
    rela:  list of (reloc_section_name, target_text_index,
                    [(r_offset, r_type, sym_index, r_addend)])
    rel:   list of (reloc_section_name, target_text_index,
                    [(r_offset, r_type, sym_index)])

    Section indices: 0 NULL, 1 .shstrtab, 2 .strtab, 3 .symtab,
    4..3+n_texts the text sections, then the reloc sections in order.
    """
    n_texts = len(texts)
    reloc_names = [r[0] for r in rela] + [r[0] for r in rel]
    n_reloc = len(reloc_names)
    n_secs = 4 + n_texts + n_reloc

    # ---- string tables ----------------------------------------------------
    sec_names = ([".shstrtab", ".strtab", ".symtab"]
                 + [t[0] for t in texts] + reloc_names)
    shstr = b"\0" + b"\0".join(s.encode() for s in sec_names) + b"\0"

    all_funcs = []               # (text_index, name, value, size, entry)
    for ti, t in enumerate(texts):
        for f in t[3]:
            all_funcs.append((ti,) + f)
    strtab = b"\0"
    sym_name_offs = {}
    for _ti, fname, _v, _s, _e in all_funcs:
        sym_name_offs[fname] = len(strtab)
        strtab += fname.encode() + b"\0"

    # ---- layout: header, shstrtab, strtab, symtab, texts, relocs ----------
    ehsize = 64
    shentsize = 64
    off = ehsize
    shstr_off = off
    off += len(shstr)
    strtab_off = off
    off += len(strtab)
    symtab_off = off
    symtab_size = (len(all_funcs) + 1) * 24
    off += symtab_size

    text_offs = []
    for _name, _addr, words, _funcs in texts:
        text_offs.append(off)
        off += len(_pack_words(words))
    reloc_offs = []
    for _name, _ti, entries in rela:
        reloc_offs.append(off)
        off += _rela_bytes_len(entries)
    for _name, _ti, entries in rel:
        reloc_offs.append(off)
        off += _rel_bytes_len(entries)

    shoff = off
    shstr_size = len(shstr)
    strtab_size = len(strtab)

    # ---- symbol table -----------------------------------------------------
    symtab = bytearray(symtab_size)
    struct.pack_into("<IBBHQQ", symtab, 0, 0, 0, 0, 0, 0, 0)
    for i, (ti, fname, value, size, entry) in enumerate(all_funcs):
        st_info = (0 << 4) | STT_FUNC
        st_other = STO_ENTRY if entry else 0
        st_shndx = 4 + ti
        struct.pack_into("<IBBHQQ", symtab, (i + 1) * 24,
                         sym_name_offs[fname], st_info, st_other, st_shndx,
                         value, size)
    first_global = 1

    # ---- section header table ---------------------------------------------
    sh = []
    # 0 NULL
    sh.append(struct.pack("<IIQQQQIIQQ", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    # 1 .shstrtab
    sh.append(struct.pack("<IIQQQQIIQQ", _name_offset(shstr, sec_names,
                                                      ".shstrtab"),
                          SHT_STRTAB, 0, 0, shstr_off, shstr_size, 0, 0,
                          1, 0))
    # 2 .strtab
    sh.append(struct.pack("<IIQQQQIIQQ", _name_offset(shstr, sec_names,
                                                      ".strtab"),
                          SHT_STRTAB, 0, 0, strtab_off, strtab_size, 0, 0,
                          1, 0))
    # 3 .symtab
    sh.append(struct.pack("<IIQQQQIIQQ", _name_offset(shstr, sec_names,
                                                      ".symtab"),
                          SHT_SYMTAB, 0, 0, symtab_off, symtab_size, 2,
                          first_global, 8, 24))
    # text sections (4..)
    for i, (name, addr, words, _funcs) in enumerate(texts):
        nm = _name_offset(shstr, sec_names, name)
        size = len(_pack_words(words))
        sh.append(struct.pack("<IIQQQQIIQQ", nm, SHT_PROGBITS, 0x6, addr,
                              text_offs[i], size, 3, first_global, 16, 0))
    # reloc sections
    for k, (name, target_ti, entries) in enumerate(rela):
        nm = _name_offset(shstr, sec_names, name)
        size = _rela_bytes_len(entries)
        sh.append(struct.pack("<IIQQQQIIQQ", nm, SHT_RELA, 0, 0,
                              reloc_offs[k], size, 3, 4 + target_ti, 8, 24))
    base = len(rela)
    for k, (name, target_ti, entries) in enumerate(rel):
        nm = _name_offset(shstr, sec_names, name)
        size = _rel_bytes_len(entries)
        sh.append(struct.pack("<IIQQQQIIQQ", nm, SHT_REL, 0, 0,
                              reloc_offs[base + k], size, 3, 4 + target_ti,
                              8, 16))

    # ---- assemble the file ------------------------------------------------
    out = bytearray(shoff + n_secs * shentsize)
    # ELF header
    out[0:4] = b"\x7fELF"
    out[4] = 2                          # ELFCLASS64
    out[5] = 1                          # ELFDATA2LSB
    out[6] = 1                          # EV_CURRENT
    struct.pack_into("<HHI", out, 0x10, 1, 190, 1)   # ET_REL, EM_CUDA, ver
    struct.pack_into("<QQ", out, 0x28, shoff, 0)     # e_shoff, e_flags(0x30)
    struct.pack_into("<HHHHHH", out, 0x34, 64, 0, 0, 64, n_secs, 1)
    out[shstr_off:shstr_off + len(shstr)] = shstr
    out[strtab_off:strtab_off + len(strtab)] = strtab
    out[symtab_off:symtab_off + len(symtab)] = symtab
    for ti, (_n, _a, words, _f) in enumerate(texts):
        body = _pack_words(words)
        out[text_offs[ti]:text_offs[ti] + len(body)] = body
    for k, (_n, _ti, entries) in enumerate(rela):
        body = _rela_bytes(entries)
        out[reloc_offs[k]:reloc_offs[k] + len(body)] = body
    for k, (_n, _ti, entries) in enumerate(rel):
        body = _rel_bytes(entries)
        out[reloc_offs[base + k]:reloc_offs[base + k] + len(body)] = body
    for i, hdr in enumerate(sh):
        struct.pack_into(
            "<64s", out, shoff + i * shentsize, bytes(hdr))
    return bytes(out)


def _name_offset(shstr: bytes, names: list[str], name: str) -> int:
    """Byte offset of `name` inside the section-name string table (which
    starts with a leading NUL byte)."""
    pos = 1
    for n in names:
        if n == name:
            return pos
        pos += len(n) + 1
    raise ValueError(f"name {name!r} not in section-name table")


def _rela_bytes_len(entries) -> int:
    return len(entries) * 24


def _rel_bytes_len(entries) -> int:
    return len(entries) * 16


def _rela_bytes(entries) -> bytes:
    out = b""
    for off, typ, symidx, add in entries:
        out += struct.pack("<QQq", off, (symidx << 32) | typ, add)
    return out


def _rel_bytes(entries) -> bytes:
    out = b""
    for off, typ, symidx in entries:
        out += struct.pack("<QQ", off, (symidx << 32) | typ)
    return out