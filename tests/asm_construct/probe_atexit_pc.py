#!/usr/bin/env python3
"""Probe CBU ATEXIT_PC and device-copy the pointed-to SASS.

The interesting case is after half a warp has executed EXIT: the surviving
lanes read ATEXIT_PC.LO/HI, while LEPC supplies a known code VA that validates
the copy path.  Host cuMemcpyDtoH is tried only after the device-side copy.

Artifacts are written under /tmp/atexit_pc_probe/.  If ATEXIT_PC is nonzero,
``atexit_target.cubin`` contains the copied 0x100 bytes as a synthetic text
section and can be decoded with::

    python3 tools/disasm.py /tmp/atexit_pc_probe/atexit_target.cubin dump
"""
from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from assembler import CudaModule, assemble, assemble_kernel  # noqa: E402


OUTDIR = Path("/tmp/atexit_pc_probe")
NBYTES = 0x100
B = "[7:7:{}:5:1]"
PAD = "\n".join("    IADD3 R30, R30, RZ, RZ;[7:7:{}:5:1]" for _ in range(8))


def capture_source(partial_exit: bool) -> str:
    exit_half = "" if not partial_exit else f"""
    S2R R2, SR_TID.X;[0:7:{{}}:5:1]
    ISETP.LT.U32.AND P0, PT, R2, 0x10, PT;[7:7:{{0}}:13:1]
    @P0 EXIT;[7:7:{{}}:5:0]
"""
    return f"""#fn capture(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6,R7}}, #param(out);[1:7:{{}}:1:0]
{exit_half}    LEPC {{R20,R21}};[7:7:{{}}:5:1]
    BMOV R22, ATEXIT_PC.LO;[2:7:{{}}:5:1]
{PAD}
    BMOV R23, ATEXIT_PC.HI;[3:7:{{}}:5:1]
{PAD}
    BMOV R24, MATEXIT;[4:7:{{}}:5:1]
{PAD}
    BMOV R25, MEXITED;[5:7:{{}}:5:1]
{PAD}
    STG.E.64.STRONG.GPU desc[{{UR4,UR5}}][{{R6,R7}}+0x00], {{R20,R21}};[7:7:{{0,1}}:8:0]
    STG.E.64.STRONG.GPU desc[{{UR4,UR5}}][{{R6,R7}}+0x08], {{R22,R23}};[7:7:{{2,3}}:8:0]
    STG.E.STRONG.GPU desc[{{UR4,UR5}}][{{R6,R7}}+0x10], R24;[7:7:{{4}}:8:0]
    STG.E.STRONG.GPU desc[{{UR4,UR5}}][{{R6,R7}}+0x14], R25;[7:7:{{5}}:8:0]
    EXIT;{B}
}}"""


def copy_source() -> str:
    body = []
    for off in range(0, NBYTES, 16):
        first_req = "{0}" if off == 0 else "{}"
        store_req = "{1,2}" if off == 0 else "{2}"
        body += [
            f"    LDG.E.128.STRONG.GPU {{R8,R9,R10,R11}}, [{{R4,R5}}+0x{off:x}];[2:7:{first_req}:8:0]",
            f"    STG.E.128.STRONG.GPU [{{R6,R7}}+0x{off:x}], {{R8,R9,R10,R11}};[7:7:{store_req}:8:0]",
        ]
    return "#fn copy(src<8>, dst<8>) {\n" + "\n".join([
        "    LDC.64 {R4,R5}, #param(src);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(dst);[1:7:{}:1:0]",
        *body,
        f"    EXIT;{B}",
        "}",
    ])


def trap_write_source() -> str:
    """Try the nominal owner context for ATEXIT_PC (isolated subprocess)."""
    return f"""#fn trap_owner(out<8>) {{
    #pragma SHADER_TYPE(7)
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6,R7}}, #param(out);[1:7:{{}}:1:0]
    LEPC {{R20,R21}}, #label(handler);[2:7:{{}}:5:1]
    BMOV.64 ATEXIT_PC, {{R20,R21}};[7:7:{{2}}:5:1]
{PAD}
    BMOV R22, ATEXIT_PC.LO;[3:7:{{}}:5:1]
{PAD}
    BMOV R23, ATEXIT_PC.HI;[4:7:{{}}:5:1]
{PAD}
    STG.E.64.STRONG.GPU desc[{{UR4,UR5}}][{{R6,R7}}], {{R22,R23}};[7:7:{{0,1,3,4}}:8:0]
    EXIT.NO_ATEXIT;{B}
    #def_label(handler)
    EXIT.NO_ATEXIT;{B}
}}"""


def trap_write_child() -> int:
    src = trap_write_source()
    try:
        mod = CudaModule(assemble(src))
        out = mod.devmem_alloc(16)
        mod.device_write(out, bytes(16))
        mod.launch("trap_owner", grid=(1,), block=(1,), args=[out])
        mod.synchronize()
        print("trap-tagged write/read: ATEXIT_PC=%#018x" %
              struct.unpack("<Q", mod.device_read(out, 8))[0])
        return 0
    except RuntimeError as ex:
        print(f"trap-tagged image rejected: {ex}")
        return 2


def capture(mod: CudaModule) -> tuple[int, int, int, int]:
    out = mod.devmem_alloc(0x800)
    mod.device_write(out, bytes(0x800))
    mod.launch("capture", grid=(1,), block=(32,), args=[out])
    mod.synchronize()
    raw = mod.device_read(out, 0x18)
    # All active lanes race identical warp-uniform values to the same words.
    vals = struct.unpack("<QQII", raw)
    mod.devmem_free(out)
    return vals


def elf_text(data: bytearray, suffix: str) -> tuple[int, int]:
    shoff = struct.unpack_from("<Q", data, 40)[0]
    shentsz, shnum, shstrndx = struct.unpack_from("<HHH", data, 58)
    shstr = shoff + shstrndx * shentsz
    str_off = struct.unpack_from("<Q", data, shstr + 24)[0]
    for i in range(shnum):
        sh = shoff + i * shentsz
        name_off = struct.unpack_from("<I", data, sh)[0]
        end = data.find(b"\0", str_off + name_off)
        name = bytes(data[str_off + name_off:end]).decode(errors="replace")
        if name.startswith(".text.") and (name == f".text.{suffix}"
                                              or name.endswith(suffix)):
            return struct.unpack_from("<QQ", data, sh + 24)
    raise RuntimeError(f"text section for {suffix!r} not found")


def synthetic_cubin(raw: bytes, stem: str) -> Path:
    n = len(raw) // 16
    src = "#fn dump() {\n" + "\n".join(
        "    NOP;[7:7:{}:5:1]" for _ in range(n - 1)
    ) + f"\n    EXIT;{B}\n}}"
    data = bytearray(assemble(src, check_deps=False))
    off, size = elf_text(data, "dump")
    if len(raw) > size:
        raise RuntimeError(f"synthetic text only {size:#x}, need {len(raw):#x}")
    data[off:off + len(raw)] = raw
    path = OUTDIR / f"{stem}.cubin"
    path.write_bytes(data)
    return path


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cap_src = capture_source(partial_exit=False)
    post_src = capture_source(partial_exit=True)
    (OUTDIR / "capture_baseline.sass").write_text(cap_src)
    (OUTDIR / "capture_after_exit.sass").write_text(post_src)
    cp_src = copy_source()
    (OUTDIR / "copy.sass").write_text(cp_src)

    # Separate modules avoid function-name collision and keep all code VAs in
    # the same CUDA context used by CudaModule.
    baseline_mod = CudaModule(assemble(cap_src))
    post_mod = CudaModule(assemble(post_src))
    copy_mod = CudaModule(assemble(cp_src))

    base = capture(baseline_mod)
    post = capture(post_mod)
    print("baseline:   LEPC=%#018x ATEXIT_PC=%#018x MATEXIT=%#010x MEXITED=%#010x" % base)
    print("after EXIT: LEPC=%#018x ATEXIT_PC=%#018x MATEXIT=%#010x MEXITED=%#010x" % post)

    dst = copy_mod.devmem_alloc(NBYTES)
    copy_mod.device_write(dst, bytes(NBYTES))

    # Control: prove a kernel can read code memory even when host D2H cannot.
    copy_mod.launch("copy", grid=(1,), block=(1,), args=[base[0], dst])
    copy_mod.synchronize()
    lepc_raw = bytes(copy_mod.device_read(dst, NBYTES))
    (OUTDIR / "lepc_code.bin").write_bytes(lepc_raw)
    expected = assemble_kernel(cap_src).encoded
    lepc_idx = 2
    want = struct.pack("<QQ", *expected[lepc_idx])
    assert lepc_raw[:16] == want, (
        f"device-copy control mismatch: got={lepc_raw[:16].hex()} want={want.hex()}")
    print(f"device-copy control OK: LEPC points at capture instruction {lepc_idx}")
    lepc_cubin = synthetic_cubin(lepc_raw, "lepc_control")
    subprocess.run([sys.executable, str(REPO / "tools/disasm.py"),
                    str(lepc_cubin), "dump", "--out",
                    str(OUTDIR / "lepc_control.sass")], check=True)
    print("tools/disasm.py control output -> "
          f"{OUTDIR / 'lepc_control.sass'} (BMOV warnings expected)")

    target = post[1] or base[1]
    if target:
        copy_mod.device_write(dst, bytes(NBYTES))
        copy_mod.launch("copy", grid=(1,), block=(1,), args=[target, dst])
        copy_mod.synchronize()
        raw = bytes(copy_mod.device_read(dst, NBYTES))
        (OUTDIR / "atexit_target.bin").write_bytes(raw)
        cubin = synthetic_cubin(raw, "atexit_target")
        print(f"ATEXIT target device-copy OK: {len(raw):#x} bytes -> {cubin}")
        subprocess.run([sys.executable, str(REPO / "tools/disasm.py"),
                        str(cubin), "dump"], check=False)
    else:
        print("ATEXIT_PC is zero in both observations; target copy skipped")

    trap = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--trap-write-child"],
        text=True, capture_output=True, timeout=15)
    detail = (trap.stdout + trap.stderr).strip().replace("\n", " | ")
    print(f"trap-tagged owner probe: rc={trap.returncode}: {detail}")

    try:
        baseline_mod.device_read(base[0], 16)
        print("host D2H from LEPC unexpectedly succeeded")
    except RuntimeError as ex:
        print(f"host D2H from LEPC rejected as expected: {ex}")

    copy_mod.devmem_free(dst)
    return 0


if __name__ == "__main__":
    if "--trap-write-child" in sys.argv:
        raise SystemExit(trap_write_child())
    raise SystemExit(main())
