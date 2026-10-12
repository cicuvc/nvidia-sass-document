#!/usr/bin/env python3
"""Reassemble the lifted DISM sync reproducer with address-form-only variants."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from assembler import assemble_flat
from sassdbg.lift import normalize_source

HERE = Path(__file__).resolve().parent
base = normalize_source((HERE / "kernel.sass").read_text())

forms = {
    # (expect/tx registration, async completion, producer release)
    "all_offset": ("[UR7+0x8]", "[UR7+0x8]", "[UR7+0x8]"),
    "arrives_zero": ("[UR7+0x8]", "[UR10]", "[UR7+0x8]"),
    "pair_zero": ("[UR10]", "[UR10]", "[UR7+0x8]"),
    "all_zero": ("[UR10]", "[UR10]", "[UR10]"),
}

# EIATTR_MBARRIER_INSTR_OFFSETS separately records address offset (u32 #3)
# and address register (byte 2 of u32 #4).  Keep it consistent with each SASS
# patch; stale metadata is itself a useful negative control but not equivalent.
meta_arrives_off = bytes.fromhex("70070000ff0000000800000007010700")
meta_arrives_zero = bytes.fromhex("70070000ff0000000000000007010a00")
meta_release_off = bytes.fromhex("c0070000ff0000000800000001010700")
meta_release_zero = bytes.fromhex("c0070000ff0000000000000001010a00")

old_expect = "SYNCS.ARRIVE.TRANS64.RED.A0T1 RZ, [UR7+0x8], RZ"
old_async = "ARRIVES.LDGSTSBAR.64.TRANSCNT [UR7+0x8]"
old_release = "SYNCS.ARRIVE.TRANS64.ART0 RZ, [UR7+0x8], R2"

def word(src: str) -> bytes:
    lo, hi = assemble_flat(src, arch="sm120")[0]
    return lo.to_bytes(8, "little") + hi.to_bytes(8, "little")

orig = (HERE / "legacy_sync_s1.1.sm_120a.cubin").read_bytes()
orig_exe_path = Path("/home/cicuvc/cs/project/dism-exp/dism_v3/build/legacy_sync_s1")
orig_exe = orig_exe_path.read_bytes()
# Reuse the producer-side NOP immediately before expect/ARRIVES.  This is
# unique by its following instruction, so the patch is robust to other NOPs.
nop = word("NOP;[7:7:{}:1:0]")
expect_off = word(old_expect + ";[7:7:{}:1:0]")
anchor = nop + expect_off
assert orig.count(anchor) == 1
add = word("ULOP3.LUT UR10, UR7, 0x8, URZ, 0xfe, !UPT;[7:7:{}:5:1]")

for name, (expect_addr, async_addr, release_addr) in forms.items():
    blob = orig.replace(anchor, add + expect_off)
    exe_blob = orig_exe.replace(anchor, add + expect_off)
    assert orig_exe.count(anchor) == 1
    replacements = (
        (word(old_expect + ";[7:7:{}:1:0]"),
         word(old_expect.replace("[UR7+0x8]", expect_addr) + ";[7:7:{}:1:0]")),
        (word(old_async + ";[7:7:{}:1:0]"),
         word(old_async.replace("[UR7+0x8]", async_addr) + ";[7:7:{}:1:0]")),
        (word(old_release + ";[7:2:{}:1:0]"),
         word(old_release.replace("[UR7+0x8]", release_addr) + ";[7:2:{}:1:0]")),
    )
    for old, new in replacements:
        assert blob.count(old) == 1, (name, old.hex(), blob.count(old))
        blob = blob.replace(old, new)
        assert exe_blob.count(old) == 1, (name, "exe", old.hex(), exe_blob.count(old))
        exe_blob = exe_blob.replace(old, new)
    if async_addr == "[UR10]":
        assert blob.count(meta_arrives_off) == exe_blob.count(meta_arrives_off) == 1
        blob = blob.replace(meta_arrives_off, meta_arrives_zero)
        exe_blob = exe_blob.replace(meta_arrives_off, meta_arrives_zero)
    if release_addr == "[UR10]":
        assert blob.count(meta_release_off) == exe_blob.count(meta_release_off) == 1
        blob = blob.replace(meta_release_off, meta_release_zero)
        exe_blob = exe_blob.replace(meta_release_off, meta_release_zero)
    assert len(blob) == len(orig)
    (HERE / f"{name}.cubin").write_bytes(blob)
    exe = HERE / f"{name}.exe"
    exe.write_bytes(exe_blob)
    exe.chmod(0o755)

# Emit the exact instruction words proving that +8 occupies the byte-offset
# field and that no other data bit changes for each instruction family.
for inst in (
    "ARRIVES.LDGSTSBAR.64.TRANSCNT {addr};[7:7:{{}}:1:0]",
    "SYNCS.ARRIVE.TRANS64.RED.A0T1 RZ, {addr}, RZ;[7:7:{{}}:1:0]",
    "SYNCS.ARRIVE.TRANS64.ART0 RZ, {addr}, R2;[7:2:{{}}:1:0]",
):
    a = assemble_flat(inst.format(addr="[UR7+0x8]"), arch="sm120")[0]
    b = assemble_flat(inst.format(addr="[UR10]"), arch="sm120")[0]
    print(inst.split()[0], "offset", f"{a[1]:016x}{a[0]:016x}",
          "zero", f"{b[1]:016x}{b[0]:016x}")
