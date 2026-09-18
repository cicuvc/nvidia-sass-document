#!/usr/bin/env python3
"""Static regression for the closed-set TMEM allocation builtin."""

from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from assembler import assemble, assemble_kernel  # noqa: E402
from assembler.sass_parser import parse_kernel  # noqa: E402
from assembler.sass_builtins import expand_builtins  # noqa: E402


SOURCE = Path(__file__).with_name(
    "tcgen05_builtin_alloc_sm100.sass").read_text()
decl = parse_kernel(SOURCE)
assert [i.mnemonic for i in decl.instructions].count(
    "_builtin_tmem_alloc_1cta_") == 1
expand_builtins(decl)
mnems = [i.mnemonic for i in decl.instructions]
assert not any(m.startswith("_builtin_") for m in mnems)
assert mnems.count("UTCATOMSWS") == 2
assert mnems.count("ATOMS") == 4
assert mnems.count("WARPSYNC") == 3
assert decl.attributes["TCGEN05_1CTA_USED"] == 1
assert decl.attributes["AT_ENTRY_FRAGMENT_TMEM_CTA1_V2"] == 1

result = assemble_kernel(SOURCE, arch="sm100a", check_deps=False)
cubin = result.code
# Leading comments must not make the convenience API misclassify a #fn kernel
# as flat SASS.
assert assemble(SOURCE, arch="sm100a", check_deps=False) == cubin
assert bytes((4, 0x4f, 4, 0, 6, 0, 0, 0)) in cubin
assert bytes((1, 0x51, 0, 0)) in cubin
# Six generated cooperative-group sites, deallocation-wide ops, and one EXIT.
assert struct.pack("<BBH6I", 4, 0x29, 24,
                   *([0xffffffff] * 6)) in cubin
assert struct.pack("<BBH6I", 4, 0x28, 24,
                   0x60, 0x1d0, 0x260, 0x440, 0x470, 0x4e0) in cubin
assert struct.pack("<BBH3I", 4, 0x31, 12,
                   0x370, 0x3c0, 0x3e0) in cubin
assert struct.pack("<BBHI", 4, 0x1c, 4, 0x4f0) in cubin

# Removing only the V2 entry-fragment selector must silently switch all three
# builtins to the V1 reserved-shared protocol and emit the V1 fragment enum.
V1_SOURCE = SOURCE.replace(
    "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1_V2(1)\n", "")
v1_decl = parse_kernel(V1_SOURCE)
expand_builtins(v1_decl)
v1_mnems = [i.mnemonic for i in v1_decl.instructions]
assert v1_decl.attributes["TCGEN05_1CTA_USED"] == 1
assert "AT_ENTRY_FRAGMENT_TMEM_CTA1_V2" not in v1_decl.attributes
assert v1_mnems.count("UTCATOMSWS") == 2
assert v1_mnems.count("ATOMS") == 2  # one combined V1 mask, set + clear
assert v1_mnems.count("WARPSYNC") == 3
v1 = assemble_kernel(V1_SOURCE, arch="sm100a", check_deps=False)
assert bytes((4, 0x4f, 4, 0, 4, 0, 0, 0)) in v1.code
assert bytes((1, 0x51, 0, 0)) in v1.code
assert struct.pack("<BBH6I", 4, 0x28, 24,
                   0x60, 0x200, 0x290, 0x470, 0x4a0, 0x510) in v1.code
assert struct.pack("<BBH2I", 4, 0x31, 8, 0x3d0, 0x420) in v1.code
assert struct.pack("<BBHI", 4, 0x1c, 4, 0x520) in v1.code

# The explicit V1 spelling is an optional assertion of the same default ABI.
explicit_v1 = V1_SOURCE.replace(
    "    #pragma SHARED(4)\n",
    "    #pragma SHARED(4)\n"
    "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)\n")
assert assemble_kernel(explicit_v1, arch="sm100a",
                       check_deps=False).encoded == v1.encoded
v1_fixture = Path(__file__).with_name(
    "tcgen05_builtin_alloc_v1_sm100.sass").read_text()
assert assemble_kernel(v1_fixture, arch="sm100a",
                       check_deps=False).encoded == v1.encoded

both_versions = explicit_v1.replace(
    "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)\n",
    "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)\n"
    "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1_V2(1)\n")
try:
    assemble_kernel(both_versions, arch="sm100a", check_deps=False)
except ValueError as ex:
    assert "both CTA1 V1 and V2" in str(ex)
else:
    raise AssertionError("conflicting V1/V2 entry fragments were accepted")

# The full architectural allocation sizes lower under both entry-fragment
# ABIs.  A 512-column allocation uses 16 occupied-unit bits but only one
# allocation-head bit.
wide = SOURCE.replace("(UR5, 32)", "(UR5, 512)")
for wide_source in (wide, wide.replace(
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1_V2(1)\n", "")):
    wide_result = assemble_kernel(
        wide_source, arch="sm100a", check_deps=False)
    assert wide_result.encoded

bad_columns = SOURCE.replace("(UR5, 32)", "(UR5, 96)")
try:
    assemble_kernel(bad_columns, arch="sm100a", check_deps=False)
except ValueError as ex:
    assert "must be one of" in str(ex)
else:
    raise AssertionError("unsupported 96-column builtin was accepted")

missing_free = SOURCE.replace(
    "    #!tmem_dealloc_1cta(UR5, 32)\n"
    "    #!tmem_relinquish_alloc_permit_1cta()\n", "")
try:
    assemble_kernel(missing_free, arch="sm100a", check_deps=False)
except ValueError as ex:
    assert "lifecycle must be exactly" in str(ex)
else:
    raise AssertionError("unpaired allocation builtin was accepted")

mismatched_free = SOURCE.replace(
    "#!tmem_dealloc_1cta(UR5, 32)",
    "#!tmem_dealloc_1cta(UR4, 32)")
try:
    assemble_kernel(mismatched_free, arch="sm100a", check_deps=False)
except ValueError as ex:
    assert "same shared-address UR" in str(ex)
else:
    raise AssertionError("mismatched deallocation builtin was accepted")

print("tcgen05 allocation builtin: PASS")
