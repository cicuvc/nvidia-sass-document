#!/usr/bin/env python3
"""Static and sm_120 runtime regression for mbarrier builtins."""

from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from assembler import CudaModule, assemble_kernel  # noqa: E402
from assembler.sass_builtins import expand_builtins  # noqa: E402
from assembler.sass_parser import parse_kernel  # noqa: E402


SOURCE = Path(__file__).with_name("mbarrier_builtins_sm120.sass").read_text()
decl = parse_kernel(SOURCE)
assert [i.mnemonic for i in decl.instructions].count(
    "_builtin_mbarrier_init_") == 1
assert [i.mnemonic for i in decl.instructions].count(
    "_builtin_mbarrier_arrive_") == 2
assert [i.mnemonic for i in decl.instructions].count(
    "_builtin_mbarrier_wait_") == 2
expand_builtins(decl)
mnems = [i.mnemonic for i in decl.instructions]
assert not any(m.startswith("_builtin_") for m in mnems)
assert mnems.count("SYNCS") == 7
assert mnems.count("NANOSLEEP") == 2
assert mnems.count("WARPSYNC") == 1
assert decl.attributes["NUM_MBARRIERS"] == 1

result = assemble_kernel(SOURCE, arch="sm120", check_deps=False)
assert len(result.encoded) == 30

bad_phase = SOURCE.replace("#!mbarrier_wait(UR6, 0)",
                           "#!mbarrier_wait(UR6, 2)")
try:
    assemble_kernel(bad_phase, arch="sm120", check_deps=False)
except ValueError as ex:
    assert "phase must be 0 or 1" in str(ex)
else:
    raise AssertionError("invalid mbarrier phase was accepted")

too_many = SOURCE.replace(
    "    #pragma SHARED(0x408)\n",
    "    #pragma SHARED(0x408)\n    #pragma NUM_MBARRIERS(1)\n").replace(
        "    #!mbarrier_init(UR6, 1)\n",
        "    #!mbarrier_init(UR6, 1)\n"
        "    #!mbarrier_init(UR7, 1)\n")
try:
    assemble_kernel(too_many, arch="sm120", check_deps=False)
except ValueError as ex:
    assert "syntactically distinct" in str(ex)
else:
    raise AssertionError("undersized NUM_MBARRIERS was accepted")

try:
    mod = CudaModule(result.code)
except RuntimeError:
    print("mbarrier builtins: static PASS, no CUDA device; runtime SKIPPED")
    raise SystemExit(0)

out = mod.devmem_alloc(4)
mod.device_write(out, struct.pack("<I", 0))
mod.launch("mbarrier_builtins", grid=(1,), block=(1,), args=[out])
mod.synchronize()
assert struct.unpack("<I", mod.device_read(out, 4))[0] == 1
mod.devmem_free(out)
print("mbarrier builtins: static + runtime PASS")
