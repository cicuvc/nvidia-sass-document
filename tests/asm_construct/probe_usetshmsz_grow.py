"""Try to falsify the claim that USETSHMSZ is shrink-only on sm_120."""

import struct
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = str(Path(__file__).resolve().parents[2])
WAIT = "".join("    NOP;[7:7:{}:8:1]\n" for _ in range(256))

sys.path.insert(0, ROOT)
from assembler import assemble_kernel  # noqa: E402


def run_case(body: str, *, static_shared: int = 0x1000,
             launch_shared: int = 0, block: int = 32) -> str:
    outfile = tempfile.mktemp(prefix="usetshmsz_grow_", suffix=".out")
    src = f"""#fn k(out<8>) {{
    #pragma SHARED(0x{static_shared:X})
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6,R7}}, #param(out);[1:7:{{}}:1:0]
{body}
    MOV32I R2, 0x12345678;[7:7:{{}}:5:1]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}], R2;[0:1:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""
    code = f"""
import struct, sys
sys.path.insert(0, {ROOT!r})
from assembler import assemble, CudaModule
try:
    mod = CudaModule(assemble({src!r}))
    out = mod.devmem_alloc(4)
    mod.device_write(out, bytes(4))
    mod.launch('k', grid=(1,), block=({block},), args=[out],
               shared_mem={launch_shared})
    mod.synchronize()
    value = struct.unpack('<I', mod.device_read(out, 4))[0]
    result = 'OK 0x%08x' % value
except Exception as exc:
    result = 'ERR ' + str(exc)
open({outfile!r}, 'w').write(result)
"""
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=20)
    try:
        result = Path(outfile).read_text().strip()
        Path(outfile).unlink()
        return result
    except FileNotFoundError:
        return "NOOUTPUT " + (proc.stderr or proc.stdout)[-200:]


CASES = [
    ("direct initial top", "    USETSHMSZ 0x1400;[7:7:{}:1:0]\n", {}),
    ("direct beyond allocation", "    USETSHMSZ 0x1480;[7:7:{}:1:0]\n", {}),
    ("adjacent shrink -> grow", """
    USETSHMSZ 0x800;[7:7:{}:1:0]
    USETSHMSZ 0x1000;[7:7:{}:1:0]
""", {}),
    ("shrink -> long wait -> grow", """
    USETSHMSZ 0x800;[7:7:{}:1:0]
""" + WAIT + "    USETSHMSZ 0x1000;[7:7:{}:1:0]\n", {}),
    ("shrink -> BAR -> grow", """
    USETSHMSZ 0x800;[7:7:{}:1:0]
    BAR.SYNC 0;[7:7:{}:5:1]
    USETSHMSZ 0x1000;[7:7:{}:1:0]
""", {}),
    ("shrink -> FLUSH -> wait -> grow", """
    USETSHMSZ 0x800;[7:7:{}:1:0]
    USETSHMSZ.FLUSH;[7:7:{}:1:0]
""" + WAIT + "    USETSHMSZ 0x1000;[7:7:{}:1:0]\n", {}),
    ("shrink -> FLUSH -> ACQSHMINIT -> grow", """
    USETSHMSZ 0x800;[7:7:{}:1:0]
    USETSHMSZ.FLUSH;[7:7:{}:1:0]
    ACQSHMINIT;[7:7:{}:1:0]
    USETSHMSZ 0x1000;[7:7:{}:1:0]
""", {}),
    ("ACQSHMINIT -> shrink -> FLUSH -> ACQ -> grow", """
    ACQSHMINIT;[7:7:{}:1:0]
    USETSHMSZ 0x800;[7:7:{}:1:0]
    USETSHMSZ.FLUSH;[7:7:{}:1:0]
    ACQSHMINIT;[7:7:{}:1:0]
    USETSHMSZ 0x1000;[7:7:{}:1:0]
""", {}),
    ("shrink -> FLUSH twice -> grow", """
    USETSHMSZ 0x800;[7:7:{}:1:0]
    USETSHMSZ.FLUSH;[7:7:{}:1:0]
    USETSHMSZ.FLUSH;[7:7:{}:1:0]
    USETSHMSZ 0x1000;[7:7:{}:1:0]
""", {}),
    ("all 2 warps shrink/BAR/grow", """
    USETSHMSZ 0x800;[7:7:{}:1:0]
    BAR.SYNC 0;[7:7:{}:5:1]
    USETSHMSZ 0x1000;[7:7:{}:1:0]
""", {"block": 64}),
    ("dynamic allocation direct 0x2400", """
    USETSHMSZ 0x2400;[7:7:{}:1:0]
""", {"launch_shared": 0x1000}),
    ("dynamic alloc shrink -> grow", """
    USETSHMSZ 0x800;[7:7:{}:1:0]
    USETSHMSZ 0x1800;[7:7:{}:1:0]
""", {"launch_shared": 0x1000}),
]


print("=== USETSHMSZ growth falsification matrix (SM120) ===")
for name, body, kwargs in CASES:
    print(f"{name:<48} -> {run_case(body, **kwargs)}")


def patched_case(*, bits: tuple[int, ...], grow: bool) -> str:
    """Set spec-reserved bits on the target USETSHMSZ instruction."""
    marker = "USETSHMSZ 0x1000;[7:7:{}:1:0]"
    prefix = "    USETSHMSZ 0x800;[7:7:{}:1:0]\n" if grow else ""
    src = f"""#fn k(out<8>) {{
    #pragma SHARED(0x1000)
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6,R7}}, #param(out);[1:7:{{}}:1:0]
{prefix}    {marker}
    MOV32I R2, 0x12345678;[7:7:{{}}:5:1]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}], R2;[0:1:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""
    result = assemble_kernel(src, check_deps=False, arch="sm120")
    marker_word = assemble_kernel(
        f"#fn marker() {{\n    {marker}\n}}", check_deps=False,
        arch="sm120").encoded[0]
    indices = [i for i, word in enumerate(result.encoded)
               if word == marker_word]
    if len(indices) != 1:
        return f"HARNESS marker count {len(indices)}"
    marker_bytes = struct.pack("<QQ", *marker_word)
    offsets = []
    start = 0
    while True:
        off = result.code.find(marker_bytes, start)
        if off < 0:
            break
        offsets.append(off)
        start = off + 1
    if len(offsets) != 1:
        return f"HARNESS cubin marker count {len(offsets)}"

    lo, hi = marker_word
    for bit in bits:
        if bit < 64:
            lo |= 1 << bit
        else:
            hi |= 1 << (bit - 64)
    patched = bytearray(result.code)
    struct.pack_into("<QQ", patched, offsets[0], lo, hi)

    cubin_file = tempfile.mktemp(prefix="usetshmsz_bit_", suffix=".cubin")
    out_file = tempfile.mktemp(prefix="usetshmsz_bit_", suffix=".out")
    Path(cubin_file).write_bytes(patched)
    code = f"""
import struct, sys
sys.path.insert(0, {ROOT!r})
from assembler import CudaModule
try:
    mod = CudaModule(open({cubin_file!r}, 'rb').read())
    out = mod.devmem_alloc(4)
    mod.device_write(out, bytes(4))
    mod.launch('k', grid=(1,), block=(32,), args=[out])
    mod.synchronize()
    value = struct.unpack('<I', mod.device_read(out, 4))[0]
    text = 'OK 0x%08x' % value
except Exception as exc:
    text = 'ERR ' + str(exc)
open({out_file!r}, 'w').write(text)
"""
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=20)
    try:
        return Path(out_file).read_text().strip()
    except FileNotFoundError:
        return "NOOUTPUT " + (proc.stderr or proc.stdout)[-200:]
    finally:
        Path(cubin_file).unlink(missing_ok=True)
        Path(out_file).unlink(missing_ok=True)


print("\n=== Reserved modifier-neighborhood bit fuzz ===")
print("bit   direct initial                 shrink -> patched grow")
for candidate_bit in range(73, 91):
    direct = patched_case(bits=(candidate_bit,), grow=False)
    growth = patched_case(bits=(candidate_bit,), grow=True)
    print(f"{candidate_bit:>3}   {direct:<30} {growth}")

# Copy the meaningful field patterns from adjacent USETMAXREG: bit 73 is
# TRY_ALLOC, bit 74 is CTAPOOL, and bits 81:83 encode its output UP predicate.
print("\n=== Structured USETMAXREG-like hidden-mode patterns ===")
for name, bits in [
        ("TRY_ALLOC + UPT", (73, 81, 82, 83)),
        ("TRY_ALLOC.CTAPOOL + UPT", (73, 74, 81, 82, 83)),
]:
    direct = patched_case(bits=bits, grow=False)
    growth = patched_case(bits=bits, grow=True)
    print(f"{name:<28} direct={direct}; grow={growth}")
