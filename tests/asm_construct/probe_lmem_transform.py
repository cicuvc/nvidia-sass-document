"""Probe the physical/global-VA layout behind per-thread local memory.

The important distinction is between:

* the 32-bit address consumed by STL/LDL (``frame`` below),
* the generic local-window address (``c[0][0x2f8] + frame``), and
* the backing-store VA returned by GETLMEMBASE.

Observed on sm_120 (RTX 5090) and sm_90 (H20): ``LWINLO + frame`` is the
generic-local address.  The corresponding single-warp backing VA is ``GETLMEMBASE +
(local_addr-SR_LMEMHIOFF)*32 + lane_id*4``.  Thus each successive 32-bit local
word advances 128 bytes in the backing aperture, while the 32 lanes occupy one
contiguous 128-byte segment.  The scanner below derives this rather than
assuming it.  Multi-warp and multi-CTA probes confirm that the formula remains
valid when each warp uses its own GETLMEMBASE value; GETLMEMBASE includes the
dynamic SM/resident-warp-slot selection and must not be derived from CTAID.
Set ``ASSEMBLER_ARCH=sm90`` for Hopper; the launch-ABI constant-bank slots are
selected automatically.
"""

import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble


WARP_SIZE = 32
RECORD_WORDS = 28
MAGIC_BASE = 0x51A70000
ACTIVE_ARCH = os.environ.get("ASSEMBLER_ARCH", "sm120")
STACK_FRAME_CBANK = 0x28 if ACTIVE_ARCH == "sm90" else 0x37C
LOCAL_WINDOW_CBANK = 0x20 if ACTIVE_ARCH == "sm90" else 0x2F8


def arch_source(source):
    """Substitute launch-ABI constant-bank slots that differ by architecture."""
    return source.replace("@STACK_FRAME@", f"0x{STACK_FRAME_CBANK:x}").replace(
        "@LOCAL_WINDOW@", f"0x{LOCAL_WINDOW_CBANK:x}"
    )


def build():
    source = f"""
#fn lmem_probe(out<8>) {{
    LDC.64 {{R2,R3}}, #param(out);[1:7:{{}}:1:0]
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[2:7:{{}}:2:0]
    LDC R14, c[0x0][@STACK_FRAME@];[0:7:{{}}:1:0]
    LDCU.64 {{UR8,UR9}}, c[0x0][@LOCAL_WINDOW@];[3:7:{{}}:2:0]
    GETLMEMBASE {{R18,R19}};[4:7:{{}}:5:1]
    S2R R0, SR_TID.X;[5:7:{{}}:5:1]

    IMAD.WIDE.U32 {{R6,R7}}, R0, 0x{RECORD_WORDS * 4:x}, {{R2,R3}};[7:7:{{1,5}}:8:0]
    MOV32I R20, 0x{MAGIC_BASE:08x};[7:7:{{}}:5:1]
    IADD3 R20, R20, R0, RZ;[7:7:{{5}}:5:1]
    MOV R10, UR8;[7:7:{{3}}:5:1]
    MOV R11, UR9;[7:7:{{}}:5:1]
    STL [R14], R20;[7:7:{{0}}:2:0]
    IADD3 R12, R14, R10, RZ;[7:7:{{}}:5:1]
    LD R28, [R12];[1:7:{{}}:4:0]
    IADD3 R29, R28, RZ, RZ;[7:7:{{1}}:5:1]
    S2R R36, SR_LMEMHIOFF;[5:7:{{}}:5:1]
    CCTLL.WB [R14];[7:7:{{}}:5:1]
    MEMBAR.ALL.SYS;[7:7:{{}}:5:1]

    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x00], R0;[7:2:{{2}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x04], R14;[7:2:{{0}}:1:0]
    STG.E.64 desc[{{UR4,UR5}}][{{R6,R7}}+0x08], {{R18,R19}};[7:2:{{4}}:1:0]
    STG.E.64 desc[{{UR4,UR5}}][{{R6,R7}}+0x10], {{R10,R11}};[7:2:{{}}:1:0]

    IADD3 R22, R14, -R36, RZ;[7:7:{{5}}:5:1]
    IMAD.WIDE.U32 {{R24,R25}}, R22, 0x20, {{R18,R19}};[7:7:{{4}}:5:1]
    IMAD.WIDE.U32 {{R24,R25}}, R0, 0x4, {{R24,R25}};[7:7:{{5}}:5:1]
    STG.E.64 desc[{{UR4,UR5}}][{{R6,R7}}+0x18], {{R24,R25}};[7:2:{{}}:1:0]

    LDG.E R26, desc[{{UR4,UR5}}][{{R24,R25}}];[1:7:{{}}:4:0]
    IADD3 R27, R26, RZ, RZ;[7:7:{{1}}:5:1]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x20], R27;[7:2:{{}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x24], R20;[7:2:{{}}:1:0]

    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x28], R29;[7:2:{{}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x2c], R20;[7:2:{{}}:1:0]

    S2R R32, SR_LWINHI;[0:7:{{}}:5:1]
    S2R R33, SR_LWINLO;[1:7:{{}}:5:1]
    S2R R34, SR_LWINSZ;[2:7:{{}}:5:1]
    S2R R35, SR_LMEMLOSZ;[3:7:{{}}:5:1]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x30], R32;[7:5:{{0,1,2,3}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x34], R33;[7:5:{{}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x38], R34;[7:5:{{}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x3c], R35;[7:5:{{}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x40], R36;[7:5:{{}}:1:0]
    S2R R37, SR_VIRTID;[0:7:{{}}:5:1]
    S2R R38, SR_VIRTCFG;[1:7:{{}}:5:1]
    S2R R39, SR_VIRTUALSMID;[2:7:{{}}:5:1]
    S2R R40, SR_VIRTUALENGINEID;[3:7:{{}}:5:1]
    S2R R41, SR_REGALLOC;[4:7:{{}}:5:1]
    S2R R42, SR_BARRIERALLOC;[5:7:{{}}:5:1]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x44], R37;[7:5:{{0,1,2,3,4,5}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x48], R38;[7:5:{{}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x4c], R39;[7:5:{{}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x50], R40;[7:5:{{}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x54], R41;[7:5:{{}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x58], R42;[7:5:{{}}:1:0]
    EXIT;[7:7:{{0,1,2,3,4,5}}:5:0]
}}
"""
    return assemble(arch_source(source))


def build_setlmembase_behavior_probe():
    source = """
#fn setlmembase_behavior(out<8>, new_base<8>) {
    #pragma MAXREG_COUNT(64)
    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]
    LDC.64 {R4,R5}, #param(new_base);[2:7:{}:1:0]
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[3:7:{}:2:0]
    LDC R14, c[0x0][@STACK_FRAME@];[4:7:{}:1:0]
    S2R R16, SR_LMEMHIOFF;[5:7:{}:5:1]
    GETLMEMBASE {R18,R19};[0:7:{}:5:1]
    S2R R8, SR_LANEID;[1:7:{}:5:1]

    MOV32I R21, 0xc82d0000;[7:7:{}:5:1]
    IADD3 R21, R21, R8, RZ;[7:7:{1}:5:1]
    STL [R14], R21;[7:7:{4}:2:0]
    CCTLL.WB [R14];[7:7:{}:5:1]
    MEMBAR.ALL.SYS;[7:7:{}:5:1]

    SETLMEMBASE {R4,R5};[7:7:{2}:5:1]
    GETLMEMBASE {R12,R13};[2:7:{}:5:1]
    IADD3 R10, R14, -R16, RZ;[7:7:{4,5}:5:1]
    IMAD.WIDE.U32 {R22,R23}, R10, 0x20, {R12,R13};[7:7:{2}:5:1]
    IMAD.WIDE.U32 {R22,R23}, R8, 0x4, {R22,R23};[7:7:{1}:5:1]
    IMAD.WIDE.U32 {R24,R25}, R10, 0x20, {R18,R19};[7:7:{0}:5:1]
    IMAD.WIDE.U32 {R24,R25}, R8, 0x4, {R24,R25};[7:7:{}:5:1]

    MOV32I R20, 0xb71c0000;[7:7:{}:5:1]
    IADD3 R20, R20, R8, RZ;[7:7:{}:5:1]
    STL [R14], R20;[7:7:{}:2:0]
    CCTLL.WB [R14];[7:7:{}:5:1]
    MEMBAR.ALL.SYS;[7:7:{}:5:1]

    LDG.E R26, desc[{UR4,UR5}][{R22,R23}];[4:7:{3}:4:0]
    LDG.E R27, desc[{UR4,UR5}][{R24,R25}];[5:7:{}:4:0]
    LDL R28, [R14];[0:7:{}:4:0]
    IADD3 R30, R26, RZ, RZ;[7:7:{4}:5:1]
    IADD3 R31, R27, RZ, RZ;[7:7:{5}:5:1]
    IADD3 R32, R28, RZ, RZ;[7:7:{0}:5:1]

    SETLMEMBASE {R18,R19};[7:7:{}:5:1]
    GETLMEMBASE {R38,R39};[2:7:{}:5:1]
    IADD3 R37, R38, RZ, RZ;[7:7:{2}:5:1]
    LDL R33, [R14];[0:7:{}:4:0]
    IADD3 R34, R33, RZ, RZ;[7:7:{0}:5:1]
    SETLMEMBASE {R12,R13};[7:7:{}:5:1]
    GETLMEMBASE {R38,R39};[2:7:{}:5:1]
    IADD3 R37, R38, RZ, RZ;[7:7:{2}:5:1]
    LDL R35, [R14];[0:7:{}:4:0]
    IADD3 R36, R35, RZ, RZ;[7:7:{0}:5:1]
    SETLMEMBASE {R18,R19};[7:7:{}:5:1]

    IMAD.WIDE.U32 {R6,R7}, R8, 0x38, {R2,R3};[7:7:{1}:5:1]
    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x00], {R18,R19};[7:7:{}:1:0]
    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x08], {R12,R13};[7:7:{}:1:0]
    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x10], {R22,R23};[7:7:{}:1:0]
    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x18], {R24,R25};[7:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x20], R30;[7:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x24], R31;[7:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x28], R32;[7:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x2c], R20;[7:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x30], R34;[7:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x34], R36;[7:7:{}:1:0]
    EXIT;[7:7:{0,1,2,3,4,5}:5:0]
}
"""
    return assemble(arch_source(source))


def run_setlmembase_behavior_probe():
    threads = 32
    record_bytes = 0x38
    mod = CudaModule(build_setlmembase_behavior_probe())
    out = mod.devmem_alloc(threads * record_bytes)
    redirected = mod.devmem_alloc(1 << 20)
    mod.device_write(out, bytes(threads * record_bytes))
    mod.device_write(redirected, bytes(1 << 20))
    try:
        mod.launch(
            "setlmembase_behavior",
            grid=(1,),
            block=(threads,),
            args=[out, redirected],
        )
        mod.synchronize()
        words = struct.unpack(
            f"<{threads * record_bytes // 4}I",
            mod.device_read(out, threads * record_bytes),
        )
        redirected_words = struct.unpack(
            f"<{threads}I", mod.device_read(redirected + 0x8000, threads * 4)
        )
    finally:
        mod.devmem_free(out)
        mod.devmem_free(redirected)
    records = [
        words[i * record_bytes // 4:(i + 1) * record_bytes // 4]
        for i in range(threads)
    ]
    return redirected, records, redirected_words


def build_multiwarp_verify():
    source = """
#fn multiwarp_verify(out<8>) {
    #pragma MAXREG_COUNT(64)
    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[2:7:{}:2:0]
    LDC R14, c[0x0][@STACK_FRAME@];[3:7:{}:1:0]
    GETLMEMBASE {R18,R19};[4:7:{}:5:1]
    S2R R0, SR_TID.X;[5:7:{}:5:1]
    S2R R1, SR_LANEID;[0:7:{}:5:1]
    S2R R16, SR_LMEMHIOFF;[3:7:{}:5:1]
    MOV32I R20, 0x95eb0000;[7:7:{}:5:1]
    IADD3 R20, R20, R0, RZ;[7:7:{5}:5:1]
    STL [R14], R20;[7:7:{3}:2:0]
    CCTLL.WB [R14];[7:7:{}:5:1]
    MEMBAR.ALL.SYS;[7:7:{}:5:1]
    CCTL.IVALL;[7:7:{}:5:1]
    IADD3 R22, R14, -R16, RZ;[7:7:{3}:5:1]
    IMAD.WIDE.U32 {R24,R25}, R22, 0x20, {R18,R19};[7:7:{4}:5:1]
    IMAD.WIDE.U32 {R24,R25}, R1, 0x4, {R24,R25};[7:7:{0}:5:1]
    LDG.E R26, desc[{UR4,UR5}][{R24,R25}];[3:7:{2}:4:0]
    IMAD.WIDE.U32 {R6,R7}, R0, 0x18, {R2,R3};[7:7:{1,5}:5:1]
    IADD3 R27, R26, RZ, RZ;[7:7:{3}:5:1]
    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x0], {R18,R19};[7:7:{}:1:0]
    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x8], {R24,R25};[7:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R27;[7:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x14], R20;[7:7:{}:1:0]
    EXIT;[7:7:{0,1,2,3,4,5}:5:0]
}
"""
    return assemble(arch_source(source))


def run_multiwarp_verify():
    threads = 256
    words_per_thread = 6
    mod = CudaModule(build_multiwarp_verify())
    out = mod.devmem_alloc(threads * words_per_thread * 4)
    mod.device_write(out, bytes(threads * words_per_thread * 4))
    try:
        mod.launch("multiwarp_verify", grid=(1,), block=(threads,), args=[out])
        mod.synchronize()
        words = struct.unpack(
            f"<{threads * words_per_thread}I",
            mod.device_read(out, threads * words_per_thread * 4),
        )
    finally:
        mod.devmem_free(out)
    records = [words[i * words_per_thread:(i + 1) * words_per_thread] for i in range(threads)]
    return records


def build_multicta_verify():
    source = """
#fn multicta_verify(out<8>) {
    #pragma MAXREG_COUNT(64)
    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[2:7:{}:2:0]
    LDC R14, c[0x0][@STACK_FRAME@];[3:7:{}:1:0]
    GETLMEMBASE {R18,R19};[4:7:{}:5:1]
    S2R R0, SR_TID.X;[5:7:{}:5:1]
    S2R R1, SR_LANEID;[0:7:{}:5:1]
    S2R R8, SR_CTAID.X;[1:7:{}:5:1]
    S2R R16, SR_LMEMHIOFF;[3:7:{}:5:1]
    S2R R10, SR_VIRTUALSMID;[0:7:{}:5:1]

    IMAD R9, R8, 0x100, R0;[7:7:{1,5}:5:1]
    IMAD R20, R8, 0x1000, R0;[7:7:{1,5}:5:1]
    IADD3 R20, R20, 0xa6000000, RZ;[7:7:{}:5:1]
    STL [R14], R20;[7:7:{3}:2:0]
    CCTLL.WB [R14];[7:7:{}:5:1]
    MEMBAR.ALL.SYS;[7:7:{}:5:1]
    CCTL.IVALL;[7:7:{}:5:1]

    IADD3 R22, R14, -R16, RZ;[7:7:{3}:5:1]
    IMAD.WIDE.U32 {R24,R25}, R22, 0x20, {R18,R19};[7:7:{4}:5:1]
    IMAD.WIDE.U32 {R24,R25}, R1, 0x4, {R24,R25};[7:7:{0}:5:1]
    LDG.E R26, desc[{UR4,UR5}][{R24,R25}];[3:7:{2}:4:0]

    IMAD.WIDE.U32 {R6,R7}, R9, 0x28, {R2,R3};[7:7:{}:5:1]
    IADD3 R27, R26, RZ, RZ;[7:7:{3}:5:1]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R8;[7:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R0;[7:7:{}:1:0]
    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x8], {R18,R19};[7:7:{}:1:0]
    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x10], {R24,R25};[7:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x18], R27;[7:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x1c], R20;[7:7:{}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}+0x20], R10;[7:7:{0}:1:0]
    EXIT;[7:7:{0,1,2,3,4,5}:5:0]
}
"""
    return assemble(arch_source(source))


def run_multicta_verify(ctas=16, threads=256):
    words_per_thread = 10
    total_threads = ctas * threads
    mod = CudaModule(build_multicta_verify())
    out = mod.devmem_alloc(total_threads * words_per_thread * 4)
    mod.device_write(out, bytes(total_threads * words_per_thread * 4))
    try:
        mod.launch("multicta_verify", grid=(ctas,), block=(threads,), args=[out])
        mod.synchronize()
        words = struct.unpack(
            f"<{total_threads * words_per_thread}I",
            mod.device_read(out, total_threads * words_per_thread * 4),
        )
    finally:
        mod.devmem_free(out)
    return [
        words[i * words_per_thread:(i + 1) * words_per_thread]
        for i in range(total_threads)
    ]


def build_global_reader():
    source = """
#fn global_reader(out<8>, base<8>) {
    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]
    LDC.64 {R4,R5}, #param(base);[2:7:{}:1:0]
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[3:7:{}:2:0]
    S2R R0, SR_LANEID;[4:7:{}:5:1]
    IMAD.WIDE.U32 {R6,R7}, R0, 0x4, {R4,R5};[7:7:{2,4}:5:1]
    IMAD.WIDE.U32 {R8,R9}, R0, 0x4, {R2,R3};[7:7:{1,4}:5:1]
    LDG.E R10, desc[{UR4,UR5}][{R6,R7}];[0:7:{3}:4:0]
    IADD3 R11, R10, RZ, RZ;[7:7:{0}:5:1]
    STG.E desc[{UR4,UR5}][{R8,R9}], R11;[7:7:{}:1:0]
    EXIT;[7:7:{0,1,2,3,4,5}:5:0]
}
"""
    return assemble(source)


def read_after_kernel(getbase, offsets):
    mod = CudaModule(build_global_reader())
    out = mod.devmem_alloc(WARP_SIZE * 4)
    results = []
    try:
        for name, offset in offsets:
            mod.device_write(out, bytes(WARP_SIZE * 4))
            mod.launch("global_reader", grid=(1,), block=(WARP_SIZE,), args=[out, getbase + offset])
            mod.synchronize()
            vals = struct.unpack(f"<{WARP_SIZE}I", mod.device_read(out, WARP_SIZE * 4))
            results.append((name, offset, vals))
    finally:
        mod.devmem_free(out)
    return results


def build_eviction_probe():
    stores = "\n".join(
        f"    STL [R14+0x{off:x}], R20;[7:7:{{}}:2:0]"
        for off in range(4, 0x240, 4)
    )
    source = f"""
#fn eviction_probe(out<8>) {{
    #pragma MAXREG_COUNT(64)
    LDC.64 {{R2,R3}}, #param(out);[1:7:{{}}:1:0]
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[2:7:{{}}:2:0]
    LDC R14, c[0x0][@STACK_FRAME@];[3:7:{{}}:1:0]
    GETLMEMBASE {{R18,R19}};[4:7:{{}}:5:1]
    S2R R0, SR_TID.X;[5:7:{{}}:5:1]
    MOV32I R20, 0x84da0000;[7:7:{{}}:5:1]
    IADD3 R20, R20, R0, RZ;[7:7:{{5}}:5:1]
    STL [R14], R20;[7:7:{{3}}:2:0]
{stores}
    CCTLL.WBALL;[7:7:{{}}:5:1]
    MEMBAR.ALL.SYS;[7:7:{{}}:5:1]
    BAR.SYNC 0;[7:7:{{}}:5:1]
    IADD3 R22, -R14, 0x1000000, RZ;[7:7:{{3}}:5:1]
    IMAD.WIDE.U32 {{R6,R7}}, R0, 0x10, {{R2,R3}};[7:7:{{1,5}}:5:1]
    IMAD.WIDE.U32 {{R24,R25}}, R0, 0x4, {{R18,R19}};[7:7:{{4,5}}:5:1]
    MOV32I R30, 0x20000;[7:7:{{}}:5:1]
    MOV32I R31, 0x84da0000;[7:7:{{}}:5:1]
    #def_label(scan_loop)
    LDG.E R26, desc[{{UR4,UR5}}][{{R24,R25}}];[0:7:{{2}}:4:0]
    LOP3.LUT R28, R26, 0xffff0000, RZ, 0xc0, !PT;[7:7:{{0}}:5:1]
    ISETP.EQ.U32.AND P0, PT, R28, R31, PT;[7:7:{{}}:13:1]
    @P0 STG.E.64 desc[{{UR4,UR5}}][{{R6,R7}}], {{R24,R25}};[7:7:{{}}:1:0]
    @P0 STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x8], R26;[7:7:{{}}:1:0]
    @P0 BRA #label(scan_done);[7:7:{{}}:5:1]
    IADD3 R24, P1, R24, 0x80, RZ;[7:7:{{}}:5:1]
    IADD3.X R25, R25, RZ, RZ, P1, !PT;[7:7:{{}}:5:1]
    IADD3 R30, R30, -0x1, RZ;[7:7:{{}}:5:1]
    ISETP.NE.U32.AND P2, PT, R30, RZ, PT;[7:7:{{}}:13:1]
    @P2 BRA #label(scan_loop);[7:7:{{}}:5:1]
    #def_label(scan_done)
    EXIT;[7:7:{{0,1,2,3,4,5}}:5:0]
}}
"""
    return assemble(arch_source(source))


def run_eviction_probe():
    threads = 32
    mod = CudaModule(build_eviction_probe())
    out = mod.devmem_alloc(threads * 16)
    mod.device_write(out, bytes(threads * 16))
    try:
        mod.launch("eviction_probe", grid=(1,), block=(threads,), args=[out])
        mod.synchronize()
        vals = struct.unpack(f"<{threads * 4}I", mod.device_read(out, threads * 16))
    finally:
        mod.devmem_free(out)
    return [
        (vals[4 * tid] | (vals[4 * tid + 1] << 32), vals[4 * tid + 2])
        for tid in range(threads)
        if vals[4 * tid] or vals[4 * tid + 1] or vals[4 * tid + 2]
    ]


def u64(words, index):
    return words[index] | (words[index + 1] << 32)


def main():
    cubin = build()
    mod = CudaModule(cubin)
    size = WARP_SIZE * RECORD_WORDS * 4
    out = mod.devmem_alloc(size)
    mod.device_write(out, bytes(size))
    mod.launch("lmem_probe", grid=(1,), block=(WARP_SIZE,), args=[out])
    mod.synchronize()
    words = struct.unpack(f"<{WARP_SIZE * RECORD_WORDS}I", mod.device_read(out, size))

    print(
        "lane  frame      GETLMEMBASE       "
        f"c[0][{LOCAL_WINDOW_CBANK:x}]          candidate VA       "
        "LDG(candidate) want"
    )
    direct_ok = True
    generic_ok = True
    for lane in range(WARP_SIZE):
        r = words[lane * RECORD_WORDS:(lane + 1) * RECORD_WORDS]
        frame = r[1]
        lmem_base = u64(r, 4)
        getbase = u64(r, 2)
        candidate = u64(r, 6)
        got, want = r[8], r[9]
        good = got == want
        generic_good = r[10] == r[11]
        direct_ok &= good
        generic_ok &= generic_good
        print(
            f"{lane:4d}  {frame:08x}  {getbase:016x}  {lmem_base:016x}  "
            f"{candidate:016x}  {got:08x} {'==' if good else '!='} {want:08x}"
            f"  generic-LD {r[10]:08x} {'==' if generic_good else '!='} {r[11]:08x}"
        )

    print()
    print("candidate = GETLMEMBASE + (frame - SR_LMEMHIOFF) * 32 + lane*4")
    print(f"STL -> LDG alias result: {'MATCH' if direct_ok else 'mismatch'}")
    print(f"STL -> generic LD result: {'MATCH' if generic_ok else 'mismatch'}")
    r0 = words[:RECORD_WORDS]
    print(
        "special regs: "
        f"LWINHI={r0[12]:08x} LWINLO={r0[13]:08x} LWINSZ={r0[14]:08x} "
        f"LMEMLOSZ={r0[15]:08x} LMEMHIOFF={r0[16]:08x}"
    )
    print(
        "thread mapping lane0: "
        f"VIRTID={r0[17]:08x} VIRTCFG={r0[18]:08x} VIRTUALSMID={r0[19]:08x} "
        f"VIRTUALENGINEID={r0[20]:08x} REGALLOC={r0[21]:08x} BARRIERALLOC={r0[22]:08x}"
    )
    print("VIRTID by lane:", " ".join(f"{words[i * RECORD_WORDS + 17]:x}" for i in range(WARP_SIZE)))
    print()
    print("second-kernel LDG reads after writer completion:")
    if ACTIVE_ARCH == "sm90":
        print("  skipped: the prior warp-slot GET aperture is invalid after relaunch on H20")
    else:
        offsets = [
            ("derived", (r0[1] - r0[16]) * 32),
            ("depth*32", 0x4800),
            ("depth*1536", 0xD8000),
            ("frame", r0[1]),
            ("generic-local", r0[1] + u64(r0, 4)),
        ]
        try:
            for name, offset, vals in read_after_kernel(u64(r0, 2), offsets):
                matches = sum(v == MAGIC_BASE + lane for lane, v in enumerate(vals))
                print(
                    f"  {name:14s} +0x{offset:x}: {matches}/32 match; "
                    f"first={vals[0]:08x}"
                )
        except RuntimeError as exc:
            print(f"  reader faulted: {exc}")
    print()
    print("SETLMEMBASE A -> B -> A -> B behavior:")
    try:
        new_base, records, redirected_words = run_setlmembase_behavior_probe()
        checks = {
            "GET reports B": sum(u64(r, 2) == new_base for r in records),
            "STL visible through B": sum(r[8] == r[11] for r in records),
            "old A retains old value": sum(
                r[9] == 0xC82D0000 + lane for lane, r in enumerate(records)
            ),
            "LDL while B selected": sum(r[10] == r[11] for r in records),
            "host reads B allocation": sum(
                v == 0xB71C0000 + lane for lane, v in enumerate(redirected_words)
            ),
            "LDL after restoring A": sum(
                r[12] == 0xC82D0000 + lane for lane, r in enumerate(records)
            ),
            "LDL after reselecting B": sum(
                r[13] == 0xB71C0000 + lane for lane, r in enumerate(records)
            ),
        }
        print(f"  B=0x{new_base:016x}")
        for name, matches in checks.items():
            print(f"  {name:28s}: {matches}/32")
    except RuntimeError as exc:
        print(f"  probe faulted: {exc}")
    print()
    print("single-warp scan of first 16 MiB of GETLMEMBASE aperture:")
    try:
        hits = run_eviction_probe()
        if hits:
            for va, value in hits[:32]:
                print(f"  hit VA=0x{va:016x} value=0x{value:08x}")
            print(f"  total reporting threads: {len(hits)}")
        else:
            print("  no 0x84da.... magic found in [GETLMEMBASE, 0x400000000000)")
    except RuntimeError as exc:
        print(f"  probe faulted: {exc}")
    print()
    print("16-CTA x 256-thread direct-formula verification:")
    try:
        records = run_multicta_verify(16, 256)
        matches = sum(r[6] == r[7] for r in records)
        print(f"  {matches}/{len(records)} match")
        for cta in range(16):
            r = records[cta * 256]
            print(
                f"  CTA {cta:2d}: VSM={r[8]:3d} "
                f"warp0_GET=0x{u64(r, 2):016x}"
            )
    except RuntimeError as exc:
        print(f"  probe faulted: {exc}")
    print()
    print("8-warp direct-formula verification:")
    try:
        records = run_multiwarp_verify()
        matches = sum(r[4] == r[5] for r in records)
        print(f"  {matches}/256 match")
        for warp in range(8):
            r = records[warp * 32]
            print(
                f"  warp {warp}: GET=0x{u64(r, 0):016x} "
                f"lane0_VA=0x{u64(r, 2):016x}"
            )
    except RuntimeError as exc:
        print(f"  probe faulted: {exc}")
    mod.devmem_free(out)
    return 0 if generic_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
