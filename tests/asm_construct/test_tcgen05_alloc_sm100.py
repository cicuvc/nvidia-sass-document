#!/usr/bin/env python3
"""Assembler/ELF regression for the hand-written tcgen05 allocator kernel."""

from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from assembler import assemble_kernel  # noqa: E402


source = (Path(__file__).with_name("tcgen05_alloc_sm100.sass").read_text())
result = assemble_kernel(source, arch="sm100a", check_deps=False)
cubin = result.code

# sm_100a accelerator contract, not generic sm_100.
assert struct.unpack_from("<I", cubin, 0x30)[0] == 0x0600640A

# Both allocator primitives made it into the native code.
opcodes = [(((hi >> 27) & 1) << 12) | (lo & 0xFFF)
           for lo, hi in result.encoded]
assert opcodes.count(0x15E3) == 2       # FIND_AND_SET retry path
assert opcodes.count(0x19E3) == 1       # AND deallocation

# Native entry-fragment metadata and the reserved-shared ABI names are all
# required.  Removing the symbols while retaining identical SASS reproduces
# CUDA error 719 on B200.
for blob in (
    bytes((1, 0x41, 0, 0)),             # RESERVED_SMEM_USED
    bytes((1, 0x51, 0, 0)),             # TCGEN05_1CTA_USED
    b"__nv_reservedSMEM_allocation_phase\0",
    b"__nv_reservedSMEM_devtool_atexit_pc\0",
    b"__nv_reservedSMEM_allocation_mask\0",
    b".nv.reservedSmem.cap\0",
):
    assert blob in cubin

# Explicit REGCOUNT avoids the generic raw-bit scanner mistaking branch
# immediates for R128..R252 in this control-heavy lowering.
regcount_records = []
for off in range(len(cubin) - 12):
    if cubin[off:off + 4] == bytes((4, 0x2F, 8, 0)):
        regcount_records.append(struct.unpack_from("<I", cubin, off + 8)[0])
assert regcount_records == [12]

# V2 is a distinct, explicit source-level choice.  Its enum value is 6;
# cuobjdump names 4 as TMEM_CTA1 and 6 as TMEM_CTA1_V2.
v2_source = source.replace(
    "    #pragma TCGEN05_1CTA_USED(1)",
    "    #pragma TCGEN05_1CTA_USED(1)\n"
    "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1_V2(1)", 1)
v2 = assemble_kernel(v2_source, arch="sm100a", check_deps=False).code
assert bytes((4, 0x4f, 4, 0, 6, 0, 0, 0)) in v2
assert bytes((4, 0x4f, 4, 0, 4, 0, 0, 0)) not in v2
assert b"__nv_reservedSMEM_tcgen05_partition\0" in v2
for old_v1_symbol in (
    b"__nv_reservedSMEM_allocation_phase\0",
    b"__nv_reservedSMEM_devtool_atexit_pc\0",
    b"__nv_reservedSMEM_allocation_mask\0",
):
    assert old_v1_symbol not in v2
# CUDA 13.1 V2 .nv.compat and per-kernel ABI marker.
assert bytes.fromhex(
    "0209010002020200020505000307010102030000"
    "040b08000900000000000000") in v2
assert bytes((3, 0x5f, 1, 1)) in v2

bad_v2 = """#fn bad() {
    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1_V2(1)
    EXIT;[7:7:{}:5:0]
}"""
try:
    assemble_kernel(bad_v2, arch="sm100a")
except ValueError as ex:
    assert "requires TCGEN05_1CTA_USED" in str(ex)
else:
    raise AssertionError("V2 entry fragment without TCGEN05 marker accepted")

print("tcgen05 alloc/dealloc sm100a ELF: PASS")
