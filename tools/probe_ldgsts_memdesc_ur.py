#!/usr/bin/env python3
"""Compile and classify ptxas LDGSTS shared-UR + memdesc output."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools" / "probes" / "ldgsts_memdesc_ur.cu"


def tool(env_name: str, fallback: str) -> str:
    configured = os.environ.get(env_name)
    if configured:
        return configured
    found = shutil.which(fallback)
    if found:
        return found
    candidate = Path("/usr/local/cuda/bin") / fallback
    if candidate.exists():
        return str(candidate)
    raise SystemExit(f"cannot find {fallback}; set {env_name}")


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def sass_functions(text: str) -> dict[str, list[str]]:
    functions: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        match = re.search(r"Function\s*:\s*(\S+)", line)
        if match:
            current = match.group(1)
        if "LDGSTS" in line:
            functions.setdefault(current, []).append(line.strip())
    return functions


def patch_probe_run_to_rur(cubin: bytes, shared_ur: int = 4) -> bytes:
    """Change probe_run's broken memdesc form to the non-memdesc RUR form."""
    data = bytearray(cubin)
    probe_run_lo = 0x0081012002077DAE
    hits: list[tuple[int, int]] = []
    for offset in range(len(data) - 15):
        lo, hi = struct.unpack_from("<QQ", data, offset)
        if lo == probe_run_lo and ((hi >> 12) & 1):
            hits.append((offset, hi))
    if len(hits) != 1:
        raise RuntimeError(f"expected one patch site, found {len(hits)}")
    offset, old_hi = hits[0]
    encoded_ur = old_hi & 0x3F
    selected_ur = encoded_ur if encoded_ur else shared_ur
    new_hi = (old_hi & ~(1 << 12) & ~0x3F) | selected_ur
    struct.pack_into("<Q", data, offset + 8, new_hi)
    print(f"patch: file+{offset:#x} hi {old_hi:#018x} -> {new_hi:#018x}")
    return bytes(data)


def run_patched(cubin: bytes) -> bool:
    sys.path.insert(0, str(ROOT))
    from assembler import CudaModule

    module = CudaModule(cubin)
    src = module.devmem_alloc(4096)
    out = module.devmem_alloc(128)
    values = [0x12340000 + i for i in range(1024)]
    module.device_write(src, struct.pack("<1024I", *values))
    module.devmem_set(out, 0, 32)
    count = 16 * 16
    module.launch("probe_run", grid=(1,), block=(32,), args=[src, out, count], shared_mem=4096)
    module.synchronize()
    got = struct.unpack("<32I", module.device_read(out, 128))
    expected = tuple(values[0x120 // 4 + lane * 4] if lane * 16 < count else 0
                     for lane in range(32))
    return got == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arches", nargs="+", default=["sm_90", "sm_120"])
    parser.add_argument("--run", action="store_true",
                        help="run probe_run on the installed GPU (currently exposes a CUDA 13.1 fault)")
    parser.add_argument("--patch-run", action="store_true",
                        help="patch probe_run to ldgsts__RUR and verify it on sm120")
    args = parser.parse_args()

    nvcc = tool("NVCC", "nvcc")
    cuobjdump = tool("CUOBJDUMP", "cuobjdump")
    with tempfile.TemporaryDirectory(prefix="ldgsts_memdesc_ur_") as tmp:
        tmpdir = Path(tmp)
        cubins: dict[str, Path] = {}
        for arch in args.arches:
            cubin = tmpdir / f"probe_{arch}.cubin"
            run([nvcc, "-std=c++20", "-O3", f"-arch={arch}", "-cubin",
                 str(SOURCE), "-o", str(cubin)])
            cubins[arch] = cubin
            sass = run([cuobjdump, "-sass", str(cubin)]).stdout
            print(f"== {arch} ==")
            for function, instructions in sass_functions(sass).items():
                for instruction in instructions:
                    print(f"{function}: {instruction}")

        if args.run:
            executable = tmpdir / "probe_run"
            completed = run([nvcc, "-std=c++20", "-O3", "-arch=sm_120",
                             str(SOURCE), "-o", str(executable)])
            if completed.stderr:
                print(completed.stderr, end="")
            result = run([str(executable)], check=False)
            print("== runtime ==")
            print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="")
            return result.returncode
        if args.patch_run:
            cubin = cubins.get("sm_120")
            if cubin is None:
                cubin = tmpdir / "probe_sm_120.cubin"
                run([nvcc, "-std=c++20", "-O3", "-arch=sm_120", "-cubin",
                     str(SOURCE), "-o", str(cubin)])
            patched = patch_probe_run_to_rur(cubin.read_bytes())
            print("== patched runtime ==")
            passed = run_patched(patched)
            print("result=PASS" if passed else "result=FAIL")
            return 0 if passed else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
