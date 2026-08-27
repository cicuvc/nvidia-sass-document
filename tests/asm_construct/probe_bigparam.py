"""Big kernel-param ABI probe (H20 / sm90) — where do bytes >=8 land?

Run on the target:
    ASSEMBLER_ARCH=sm90 ~/miniconda3/bin/python3 probe_bigparam.py

Kernel receives one <N>-byte parameter whose words are a known pattern
(1..32), echoes them back through LDC -> STG. The runner packs a raw
bytes arg at the parameter's KPARAM size (runner.py _kernel_param_array).  Vary N in
{16,32,64,128} and read-back window; if >8-byte reads return zeros at any
window start, the placement rule differs from the sm_120 0x380 layout.
"""

import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("ASSEMBLER_ARCH", "sm90")

from archutil import adapt_source  # noqa: E402
from assembler import assemble  # noqa: E402
from assembler.runner import CudaModule, reset_context  # noqa: E402


def make_kernel(nwords):
    """Echo nwords from a single big param (`p`) into out[]."""
    lines = ["    ULDC.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[7:7:{}:2:0]",
             "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]"]
    for i in range(nwords):
        lines.append(f"    LDC R8, #param(p)[{i * 4:X}];[1:7:{1}:3:0]")
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{i * 4:X}], "
                     f"R8;[0:1:{1}:1:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    body = "\n".join(lines)
    return f"#fn k(out<8>, p<{nwords * 4}>) {{\n{body}\n}}\n"


def run_case(nbytes):
    nwords = nbytes // 4
    src = adapt_source(make_kernel(nwords))
    reset_context()
    mod = CudaModule(assemble(src))
    d_out = mod.devmem_alloc(max(64, nbytes))
    payload = struct.pack(f"<{nwords}I", *range(1, nwords + 1))
    mod.device_write(d_out, b"\xEE" * max(64, nbytes))
    try:
        mod.launch("k", grid=(1,), block=(1,), args=[d_out, payload])
        mod.synchronize()
        got = struct.unpack(f"<{nwords}I", mod.device_read(d_out, nbytes))
    except RuntimeError as e:
        return f"LAUNCH-ERR {str(e)[:50]}"
    finally:
        try:
            mod.devmem_free(d_out)
        except Exception:
            pass
    exp = tuple(range(1, nwords + 1))
    nz = [i for i, w in enumerate(got) if w != 0]
    if got == exp:
        return "OK"
    return f"MISMATCH first-nonzero-idx={nz[:4]} got[:8]={got[:8]}"


if __name__ == "__main__":
    for nbytes in (8, 16, 32, 64, 128):
        print(f"param<{nbytes:>3}B>: {run_case(nbytes)}")
