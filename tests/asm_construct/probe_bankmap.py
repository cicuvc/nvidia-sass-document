"""Bank map sweep — where does the driver actually place each param?

Static expansion: for offsets 0x200..0x340 (step 4) emit one LDC + STG.
Two kernels: single-big-param and two-param (ptr + big). The printed
'word-id' at each offset reveals the exact placement rule on this GPU.
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

OFF_LO, OFF_HI = 0x200, 0x340


def sweep_kernel(nwords_decl):
    lines = ["    ULDC.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[7:7:{}:2:0]",
             "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]",
             f"    // declared params: p<{nwords_decl * 4}>" if nwords_decl else ""]
    off = OFF_LO
    while off < OFF_HI:
        lines.append(f"    LDC R8, c[0x0][0x{off:X}];[1:7:{1}:3:0]")
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off - OFF_LO:X}], "
                     f"R8;[0:1:{1}:1:0]")
        off += 4
    lines.append("    EXIT;[7:7:{}:5:0]")
    sig = "#fn k(out<8>, p<" + str(nwords_decl * 4 or 8) + ">) {" if nwords_decl \
          else "#fn k(out<8>) {"
    return sig + "\n" + "\n".join(l for l in lines if l.strip()) + "\n}\n"


def run(mode, nwords_decl, payload_bytes_len=None):
    """mode='single': only out + p (payload); mode='two-kernel-out-first'."""
    src = adapt_source(sweep_kernel(nwords_decl))
    reset_context()
    mod = CudaModule(assemble(src))
    d_out = mod.devmem_alloc((OFF_HI - OFF_LO) * 2)
    mod.device_write(d_out, b"\xAA" * ((OFF_HI - OFF_LO) * 2))
    NW = NW_payload = nwords_decl
    payload = struct.pack(f"<{NW}I", *[0xCAFE0000 | (i & 0xFFFF) ^ 0x5555
                                       for i in range(NW)])
    args = [d_out, payload]
    mod.launch("k", grid=(1,), block=(1,), args=args)
    mod.synchronize()
    got = struct.unpack(f"<{(OFF_HI - OFF_LO) // 4}I",
                        mod.device_read(d_out, OFF_HI - OFF_LO))
    return got


if __name__ == "__main__":
    NWORDS = 32          # 128-byte param; words = 0xCAFE0000^0x5555 | i
    print("== two-param layout (out<8> first) ==")
    got = run("two", NWORDS)
    hits = []
    for k, w in enumerate(got):
        if (w & 0xFFFF8000) in (0xCAFE8000,) or ((w ^ 0x5555) & 0xFFFF0000) == 0xCAFE0000:
            pass
        if (w ^ 0x5555) >> 16 == 0xCAFE:
            word_id = (w & 0xFFFF) ^ 0x5555
            hits.append((OFF_LO + k * 4, word_id))
    print("param word -> bank offset:",
          [(hex(o), wid) for o, wid in hits[:10]], "..." if len(hits) > 10 else "")
