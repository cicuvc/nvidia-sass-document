#!/usr/bin/env python3
"""Build SM120 cubins from hand-written SASS instructions.

Provides CubinBuilder: load a compiled template cubin, patch in custom SASS,
strip optional sections, and produce a loadable cubin for cuModuleLoadData.

Usage:
  from build_sm120_cubin import CubinBuilder, INS
  cb = CubinBuilder('/tmp/minimal.cubin')
  cb.set_sass([
      INS(lo64=0x..., hi64=0x...),  # instruction 0
      # ... more instructions ...
  ])
  cb.strip_mercury()
  with open('out.cubin', 'wb') as f: f.write(cb.build())
"""
import struct
from pathlib import Path

# Module's own compiled-in template.
# Generated at first use by compiling a minimal kernel.
REPO = Path(__file__).resolve().parent.parent

class CubinBuilder:
    """Load an SM120 cubin template and allow patching the .text section."""

    def __init__(self, template_path):
        with open(template_path, 'rb') as f:
            self._data = bytearray(f.read())
        self._parse()

    def _parse(self):
        d = self._data
        self._e_shoff = struct.unpack_from('<Q', d, 40)[0]
        self._e_shentsize, self._e_shnum, self._e_shstrndx = \
            struct.unpack_from('<HHH', d, 58)
        self._text_idx = None

        # Locate shstrtab data
        shstr_root = self._e_shoff + self._e_shstrndx * self._e_shentsize
        self._shstr_data = struct.unpack_from('<Q', d, shstr_root + 24)[0]

        for i in range(self._e_shnum):
            name = self._sec_name(i)
            if '.text._Z' in name:
                off = self._e_shoff + i * self._e_shentsize
                self._text_offset = struct.unpack_from('<Q', d, off + 24)[0]
                self._text_size = struct.unpack_from('<Q', d, off + 32)[0]
                self._text_idx = i
                self._kernel_name = name[len('.text.'):]
                break

    def _sec_name(self, idx):
        off = self._e_shoff + idx * self._e_shentsize
        name_off = struct.unpack_from('<I', self._data, off)[0]
        return self._data[self._shstr_data + name_off:].split(b'\0')[0].decode(errors='replace')

    @property
    def kernel_name(self):
        return self._kernel_name

    def set_sass(self, instructions):
        """Write SASS instructions to .text. Each is (lo64, hi64)."""
        max_insns = self._text_size // 16
        for i, (lo, hi) in enumerate(instructions):
            if i >= max_insns:
                break
            off = self._text_offset + i * 16
            struct.pack_into('<QQ', self._data, off, lo, hi)
        # Zero remaining slots
        for i in range(len(instructions), max_insns):
            off = self._text_offset + i * 16
            struct.pack_into('<QQ', self._data, off, 0, 0)

    def strip_mercury(self):
        """Remove Mercury/capmerc sections (not needed for loading)."""
        merc = set()
        for i in range(self._e_shnum):
            name = self._sec_name(i)
            if any(x in name.lower() for x in ('merc', 'capmerc')):
                merc.add(i)
        for i in merc:
            off = self._e_shoff + i * self._e_shentsize
            struct.pack_into('<II', self._data, off, 0, 0)
        for i in range(self._e_shnum):
            if i in merc:
                continue
            off = self._e_shoff + i * self._e_shentsize
            sh_link = struct.unpack_from('<I', self._data, off + 40)[0]
            if sh_link in merc:
                struct.pack_into('<I', self._data, off + 40, 0)
        return len(merc)

    def strip_optional(self):
        """Remove all optional sections (Mercury, debug, compat, callgraph, shared)."""
        names = set()
        for i in range(self._e_shnum):
            names.add(self._sec_name(i).lower())
        to_strip = []
        for name in names:
            if any(x in name for x in ('merc', 'capmerc', 'debug_frame',
                                         'compat', 'callgraph',
                                         'shared.reserved')):
                to_strip.append(name)
        # Actually strip them
        merc = set()
        for i in range(self._e_shnum):
            name = self._sec_name(i).lower()
            if any(x in name for x in ('merc', 'capmerc', 'debug_frame',
                                         'compat', 'callgraph',
                                         'shared.reserved')):
                merc.add(i)
        for i in merc:
            off = self._e_shoff + i * self._e_shentsize
            struct.pack_into('<II', self._data, off, 0, 0)
        for i in range(self._e_shnum):
            if i in merc:
                continue
            off = self._e_shoff + i * self._e_shentsize
            sh_link = struct.unpack_from('<I', self._data, off + 40)[0]
            if sh_link in merc:
                struct.pack_into('<I', self._data, off + 40, 0)
        return len(merc)

    def build(self):
        return bytes(self._data)


def INS(lo64, hi64):
    """Create an instruction tuple."""
    return (lo64, hi64)


# --- Known-good SASS templates from SM120 compiled kernels ---
# Control words (hi64) encode stall counts, write barriers, scoreboard refs.
# These are verified against cuobjdump output.

CTL_LDC    = 0x000fe20000000800   # ?trans1 — load from constant bank
CTL_S2R    = 0x000e220000002100   # ?trans1 — special register read
CTL_LDCU   = 0x000e2c0008000a00   # ?trans6 — uniform load from constant
CTL_LDC64  = 0x000e240000000a00   # ?trans2 — 64-bit load from constant
CTL_STG    = 0x001fe2000c101904   # &req={0} ?trans1 — store to global
CTL_LDG    = 0x002f22000c1e1900   # &req={1} &wr=0x4 ?trans1 — load from global
CTL_IMAD   = 0x002fca000f8e0200   # &req={1} ?WAIT5_END_GROUP — integer multiply-add
CTL_IMAD_W = 0x001fcc00078e0202   # &req={0} ?WAIT6_END_GROUP — IMAD.WIDE
CTL_EXIT   = 0x000fea0003800000   # ?trans5 — kernel exit
CTL_NOP    = 0x000fc00000000000   # control barrier NOP
CTL_BRA    = 0x000fc0000383ffff   # unconditional branch (trap)

# Instruction encodings (lo64) — these are the actual SASS payloads.
# Control word in hi64; opcode and operands in lo64.

I_LDC_R1_37c     = 0x0000df00ff017b82  # LDC R1, c[0x0][0x37c] — global mem descriptor
I_LDC64_R2_380   = 0x0000e000ff027b82  # LDC.64 {R2,R3}, c[0x0][0x380]
I_S2R_R5_TIDX    = 0x0000000000057919  # S2R R5, SR_TID.X
I_LDCU_UR4_358   = 0x00006b00ff0477ac  # LDCU.64 {UR4,UR5}, c[0x0][0x358]
I_STG_UR4_R2_R5  = 0x0000000502007986  # STG.E desc[{UR4,UR5}][{R2,R3}], R5
I_EXIT           = 0x000000000000794d  # EXIT
I_NOP            = 0x0000000000007918  # NOP
I_BRA_0x60       = 0xfffffffc00fc7947  # BRA 0x60 (trap loop)

# Standard kernel prologue (6 instructions) + EXIT + padding
STD_PROLOGUE = [
    (I_LDC_R1_37c,    CTL_LDC),       # 0x000: load global mem descriptor
    (I_S2R_R5_TIDX,   CTL_S2R),       # 0x010: R5 = threadId.x
    (I_LDCU_UR4_358,  CTL_LDCU),      # 0x020: UR4 = out[] ptr (param 0)
    (I_LDC64_R2_380,  CTL_LDC64),     # 0x030: R2 = 0 (param 1 offset)
    (I_STG_UR4_R2_R5, CTL_STG),       # 0x040: store R5 to [UR4 + R2]
    (I_EXIT,          CTL_EXIT),      # 0x050: exit
]

# Fill a .text section (0x100 bytes = 16 slots)
def fill_section(instructions):
    """Pad instructions to fill a 16-slot (0x100-byte) .text section."""
    result = list(instructions)
    while len(result) < 16:
        result.append((I_NOP, CTL_NOP))
    return result


if __name__ == '__main__':
    import sys
    template = sys.argv[1] if len(sys.argv) > 1 else '/tmp/sm120_test/minimal.cubin'
    out = sys.argv[2] if len(sys.argv) > 2 else '/tmp/sm120_test/hand_built2.cubin'

    cb = CubinBuilder(template)
    sass = fill_section(STD_PROLOGUE)
    cb.set_sass(sass)
    n = cb.strip_optional()
    data = cb.build()
    with open(out, 'wb') as f:
        f.write(data)
    print(f"Wrote {out}: {len(data)} bytes, {n} sections stripped, kernel={cb.kernel_name}")
    print(f"  SASS: {len(sass)} instructions ({len(sass)*16} bytes)")
