#!/usr/bin/env python3
"""CPU-side fidelity test for the V1 multi-warp CTA TMEM allocator."""

from pathlib import Path
import hashlib
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from assembler import assemble_kernel  # noqa: E402
from sassdbg.cubin import (  # noqa: E402
    _sections, native_relocations, native_symbols,
)


SOURCE = Path(__file__).with_name(
    "tcgen05_alloc_multiwarp_v1_sm100.sass").read_text()
# Layout-sensitive EIATTRs must be derived from final SASS, not hand-maintained
# numeric offsets that become stale whenever an instruction is inserted.
assert "#pragma INT_WARP_WIDE_OFFSETS" not in SOURCE
assert "#pragma COOP_GROUP_INSTR_OFFSETS" not in SOURCE
assert SOURCE.count("#coop_group") == 4
result = assemble_kernel(SOURCE, arch="sm100a", check_deps=False)
cubin = result.code

# CUDA 12.8 ptxas alloc_multi contains exactly these 136 instruction words.
# This hash covers the complete user text, including scheduling controls and
# relative CALL/RET immediates; the driver-injected V1 prefix is not in cubin.
text = b"".join(struct.pack("<QQ", lo, hi) for lo, hi in result.encoded)
assert len(result.encoded) == 136
assert hashlib.sha256(text).hexdigest() == (
    "9f2fe6d6a0d5119415af239ab9f13dde050ba23c6ff939445f2e00681c0f1c4b")

# Multi-warp additions relative to alloc32: one named CTA barrier and four
# cooperative-group sites.  Mask-regid list cardinality must match offsets.
assert bytes((2, 0x4c, 1, 0)) in cubin
assert (struct.pack("<BBH4I", 4, 0x29, 16, *([0xffffffff] * 4))
        in cubin)
assert (struct.pack("<BBH4I", 4, 0x28, 16,
                    0x60, 0x310, 0x470, 0x6c0) in cubin)
assert (struct.pack("<BBH2I", 4, 0x31, 8, 0x5b0, 0x600) in cubin)
assert (struct.pack("<BBH3I", 4, 0x1c, 12,
                    0x410, 0x6d0, 0x740) in cubin)
assert struct.pack("<BBHI", 4, 0x1e, 4, 0) in cubin

# Complete V1 loader contract and exact shared-memory extents.
for name in (
    b"__nv_reservedSMEM_allocation_phase\0",
    b"__nv_reservedSMEM_devtool_atexit_pc\0",
    b"__nv_reservedSMEM_allocation_mask\0",
    b".nv.reservedSmem.cap\0",
):
    assert name in cubin
secs = _sections(cubin)
sizes = {s.name: s.size for s in secs}
assert sizes[".nv.shared.reserved.0"] == 0x54
assert sizes[".nv.shared._Z14alloc_multi_v1"] == 0x404

symbols = {s.name: s for s in native_symbols(cubin, secs)}
assert symbols["__nv_reservedSMEM_offset_0_alias"].value == 0x40
assert symbols["__nv_reservedSMEM_offset_0_alias"].other == 0xa0
assert symbols[".nv.reservedSmem.cap"].value == 0x400

# nvcc emits a zero-sized .rela.text.alloc_multi section.  The repository
# builder omits the empty container; semantically both have zero native text
# relocations.  In particular, no relocation can be shifted by entry-prefix
# insertion: all intra-user-text branches/calls are already PC-relative.
assert native_relocations(cubin, secs) == []

# An explicit mask id is paired with the exact next instruction.  The
# annotation itself is zero-width, so the marked NOP remains at offset zero.
marked = assemble_kernel("""#fn marked() {
    #coop_group(0x0500000f)
    NOP;[7:7:{}:1:0]
    EXIT;[7:7:{}:5:0]
}""", arch="sm100a", check_deps=False).code
assert struct.pack("<BBHI", 4, 0x29, 4, 0x0500000f) in marked
assert struct.pack("<BBHI", 4, 0x28, 4, 0) in marked

# Legacy numeric pragmas are accepted only when they agree with the final
# inferred layout; this catches stale metadata after editing the lowering.
stale = SOURCE.replace(
    "    #pragma TCGEN05_1CTA_USED(1)",
    "    #pragma TCGEN05_1CTA_USED(1)\n"
    "    #pragma INT_WARP_WIDE_OFFSETS(0x10,0x20)", 1)
try:
    assemble_kernel(stale, arch="sm100a", check_deps=False)
except ValueError as ex:
    assert "does not match final VOTEU/REDUX layout" in str(ex)
else:
    raise AssertionError("stale INT_WARP_WIDE_OFFSETS was accepted")

try:
    assemble_kernel("""#fn dangling() {
        EXIT;[7:7:{}:5:0]
        #coop_group
    }""", arch="sm100a", check_deps=False)
except ValueError as ex:
    assert "must be followed by a real instruction" in str(ex)
else:
    raise AssertionError("dangling #coop_group was accepted")

print("tcgen05 V1 multi-warp allocator ELF/SASS: PASS")
