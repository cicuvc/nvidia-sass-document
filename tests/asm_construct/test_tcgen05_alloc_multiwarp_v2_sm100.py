#!/usr/bin/env python3
"""CPU-side fidelity test for CUDA 13.1's V2 multi-warp TMEM allocator."""

from pathlib import Path
import hashlib
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from assembler import assemble_kernel  # noqa: E402
from sassdbg.cubin import _sections, native_relocations, native_symbols  # noqa: E402


SOURCE = Path(__file__).with_name(
    "tcgen05_alloc_multiwarp_v2_sm100.sass").read_text()
assert SOURCE.count("#coop_group") == 4
assert "#pragma INT_WARP_WIDE_OFFSETS" not in SOURCE
assert "#pragma COOP_GROUP_INSTR_OFFSETS" not in SOURCE

result = assemble_kernel(SOURCE, arch="sm100a", check_deps=False)
cubin = result.code
text = b"".join(struct.pack("<QQ", lo, hi) for lo, hi in result.encoded)

# Exact CUDA 13.1 ptxas user text, including scheduling controls.  This is a
# separate lowering from V1, not the V1 text with a changed entry enum.
assert len(result.encoded) == 120
assert hashlib.sha256(text).hexdigest() == (
    "1452d1deab36497257b07ddce5605e5728cc00daa2648a14bdb902de4b6a964a")

# V2 ABI and layout-derived instruction metadata.
assert bytes((4, 0x4f, 4, 0, 6, 0, 0, 0)) in cubin
assert bytes((3, 0x5f, 1, 1)) in cubin
assert bytes((2, 0x4c, 1, 0)) in cubin
assert (struct.pack("<BBH2I", 4, 0x31, 8, 0x490, 0x4e0) in cubin)
assert (struct.pack("<BBH4I", 4, 0x29, 16, *([0xffffffff] * 4))
        in cubin)
assert (struct.pack("<BBH4I", 4, 0x28, 16,
                    0x60, 0x250, 0x3c0, 0x5c0) in cubin)
assert (struct.pack("<BBH3I", 4, 0x1c, 12,
                    0x340, 0x5f0, 0x630) in cubin)

# V2 exposes one opaque 32-byte partition rather than V1's three named state
# symbols.  Static shared still contains the 0x400 cap plus the published base.
secs = _sections(cubin)
sizes = {s.name: s.size for s in secs}
assert sizes[".nv.shared.reserved.0"] == 0x60
assert sizes[".nv.shared._Z14alloc_multi_v2"] == 0x404
symbols = {s.name: s for s in native_symbols(cubin, secs)}
partition = symbols["__nv_reservedSMEM_tcgen05_partition"]
assert partition.value == 0x40 and partition.size == 0x20
for v1_name in (
    "__nv_reservedSMEM_allocation_phase",
    "__nv_reservedSMEM_devtool_atexit_pc",
    "__nv_reservedSMEM_allocation_mask",
):
    assert v1_name not in symbols

assert native_relocations(cubin, secs) == []

print("tcgen05 V2 multi-warp allocator ELF/SASS: PASS")
